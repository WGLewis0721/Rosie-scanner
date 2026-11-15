"""Rosie NBA research: explicit on-demand calls, never trades or schedules.

Bookmaker estimates are priors, NOT a proprietary oracle. Historical game outcomes
train only a guarded calibration. Settled prediction markets are audited separately
to prevent duplicated contracts / look-ahead contamination.
"""
import argparse
import csv
import json
import math
import statistics
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from market_scan import (KALSHI, GAMMA, Market, collect_polymarket,
                         normalize_kalshi, quote_poly_books, request_json,
                         devig_power, fee_estimate, now_utc)
from nba_odds import Game, get_nba, match_team_sides, parse_nba

NBA_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
ESPN_CORE = "https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba"
ABBR = {
 "Atlanta Hawks":"ATL","Boston Celtics":"BOS","Brooklyn Nets":"BKN",
 "Charlotte Hornets":"CHA","Chicago Bulls":"CHI","Cleveland Cavaliers":"CLE",
 "Dallas Mavericks":"DAL","Denver Nuggets":"DEN","Detroit Pistons":"DET",
 "Golden State Warriors":"GSW","Houston Rockets":"HOU","Indiana Pacers":"IND",
 "LA Clippers":"LAC","Los Angeles Clippers":"LAC","Los Angeles Lakers":"LAL",
 "Memphis Grizzlies":"MEM","Miami Heat":"MIA","Milwaukee Bucks":"MIL",
 "Minnesota Timberwolves":"MIN","New Orleans Pelicans":"NOP","New York Knicks":"NYK",
 "Oklahoma City Thunder":"OKC","Orlando Magic":"ORL","Philadelphia 76ers":"PHI",
 "Phoenix Suns":"PHX","Portland Trail Blazers":"POR","Sacramento Kings":"SAC",
 "San Antonio Spurs":"SAS","Toronto Raptors":"TOR","Utah Jazz":"UTA",
 "Washington Wizards":"WAS"
}
HISTORY_FIELDS = ("game_id","date","home","away","home_ml","away_ml","winner","provider","source_url")
MIN_TRAIN, MIN_HOLDOUT = 120, 30


def _logit(p):
    return math.log(max(.001, min(.999, p)) / (1-max(.001, min(.999, p))))


def _sigmoid(x):
    return 1/(1+math.exp(-max(-35, min(35, x))))


def _loss(p, y):
    p = max(.000001, min(.999999, p))
    return -(y*math.log(p)+(1-y)*math.log(1-p))


def _metrics(rows, predictor):
    if not rows:
        return {"n":0,"brier":None,"log_loss":None}
    pred=[max(.001,min(.999,predictor(r))) for r in rows]
    labels=[r["y"] for r in rows]
    return {"n":len(rows),
            "brier":round(sum((p-y)**2 for p,y in zip(pred,labels))/len(rows),5),
            "log_loss":round(sum(_loss(p,y) for p,y in zip(pred,labels))/len(rows),5)}


def fit_calibrator(rows):
    """L2-regularized logistic calibration with an identity-centered prior.

    It learns ONLY from pregame sportsbook lines paired with later final outcomes.
    The last 20% of chronologically ordered games remain untouched for holdout.
    If the fit doesn't outperform the bookmaker baseline, do not use it.
    """
    rows=sorted(rows,key=lambda r:(r["date"],r["game_id"]))
    test_n=max(MIN_HOLDOUT,math.ceil(len(rows)*.2))
    train,hold=rows[:-test_n],rows[-test_n:]
    base={"history_games":len(rows),"train_games":len(train),"holdout_games":len(hold),
          "mode":"bookmaker_only","validated":False,
          "holdout_book":_metrics(hold,lambda r:r["p"]),
          "holdout_model":None,"a":0.0,"b":1.0}
    if len(train)<MIN_TRAIN or len(hold)<MIN_HOLDOUT:
        base["reason"]="Insufficient historical pregame odds with verified final scores"
        return base
    # MAP / penalized likelihood: intercept N(0, 1/8), slope N(1, 1/32).
    # Newton-Raphson, constrained to avoid extreme low-sample movement.
    a,b=0.0,1.0
    for _ in range(30):
        g0,g1=8*a,32*(b-1)
        h00,h01,h11=8.,0.,32.
        for r in train:
            x=_logit(r["p"])
            pred=_sigmoid(a+b*x)
            delta=pred-r["y"]
            w=pred*(1-pred)
            g0+=delta;g1+=delta*x
            h00+=w;h01+=w*x;h11+=w*x*x
        det=h00*h11-h01*h01
        if det<=0:
            break
        da=(g0*h11-g1*h01)/det
        db=(g1*h00-g0*h01)/det
        a=max(-.6,min(.6,a-da))
        b=max(.55,min(1.45,b-db))
        if abs(da)+abs(db)<1e-8:
            break
    proposed=lambda r:_sigmoid(a+b*_logit(r["p"]))
    hold_new=_metrics(hold,proposed)
    base["holdout_model"]=hold_new
    base["a"],base["b"]=round(a,6),round(b,6)
    # Predeclared conservative gate; don't select model based on full-sample fit.
    if (hold_new["brier"]+.002 < base["holdout_book"]["brier"]
            and hold_new["log_loss"]<=base["holdout_book"]["log_loss"]):
        base["validated"]=True
        base["mode"]="regularized_logistic"
        base["reason"]="Out-of-sample Brier and log loss beat the sportsbook baseline"
    else:
        base["reason"]="Calibration did not clear out-of-sample improvement gate"
    return base


def _odds(raw):
    from nba_odds import american
    if not isinstance(raw,dict):
        return None
    ml=raw.get("moneyline") or {}
    h=(ml.get("home") or {}) if isinstance(ml,dict) else {}
    a=(ml.get("away") or {}) if isinstance(ml,dict) else {}
    def pick(side):
        for key in ("close",):
            v=side.get(key) or {}
            if isinstance(v,dict):
                result=american(v.get("odds"))
                if result:
                    return result
        return american(side.get("odds"))
    home,away=pick(h),pick(a)
    if home is None or away is None:
        return None
    return home,away


def fetch_history(start, end, max_games=500):
    """Explicit historical ingestion. Never use today's in-play or final odds.

    ESPN core retains recorded closing odds for some historical games; missing
    odds are skipped, not replaced with postgame implied prices.
    """
    first,last=date.fromisoformat(start),date.fromisoformat(end)
    if first>last or (last-first).days>180 or last>=now_utc().date():
        raise ValueError("History dates must be past, ordered, and no more than 181 days")
    data,errors=[],[]
    with httpx.Client(follow_redirects=True) as client:
        day=first
        while day<=last and len(data)<max_games:
            try:
                result=request_json(client,NBA_SCOREBOARD,{"dates":day.strftime("%Y%m%d")})
                for ev in result.get("events",[]):
                    comp=(ev.get("competitions") or [{}])[0]
                    if ((ev.get("status") or {}).get("type") or {}).get("state")!="post":
                        continue
                    teams={x.get("homeAway"):x for x in comp.get("competitors",[])}
                    h,a=teams.get("home") or {},teams.get("away") or {}
                    home=(h.get("team") or {}).get("displayName")
                    away=(a.get("team") or {}).get("displayName")
                    if home not in ABBR or away not in ABBR:
                        continue
                    try:
                        hs,as_=int(float(h.get("score"))),int(float(a.get("score")))
                    except (ValueError,TypeError):
                        continue
                    if hs==as_:
                        continue
                    event_id=str(ev.get("id"))
                    comp_id=str(comp.get("id") or event_id)
                    try:
                        raw=request_json(client, f"{ESPN_CORE}/events/{event_id}/competitions/{comp_id}/odds",{"limit":100})
                        options=raw.get("items",[]) if isinstance(raw,dict) else []
                        found=None
                        for o in options:
                            pair=_odds(o)
                            provider=o.get("provider") or {}
                            name=provider.get("name") if isinstance(provider,dict) else ""
                            if pair and "live" not in str(name).lower():
                                found=(pair,str(name or "ESPN-listed"))
                                break
                        if not found:
                            continue
                        (home_ml,away_ml),provider=found
                        data.append({"game_id":event_id,"date":day.isoformat(),"home":home,
                                     "away":away,"home_ml":home_ml,"away_ml":away_ml,
                                     "winner":home if hs>as_ else away,"provider":provider,
                                     "source_url":f"https://www.espn.com/nba/game/_/gameId/{event_id}"})
                    except (httpx.HTTPError,ValueError,TypeError,KeyError) as exc:
                        errors.append(f"{event_id}: {type(exc).__name__}")
                    if len(data)>=max_games:
                        break
            except (httpx.HTTPError,ValueError,TypeError,KeyError) as exc:
                errors.append(f"{day.isoformat()}: {type(exc).__name__}")
            day+=timedelta(days=1)
    return data,errors


def prepare_history(records):
    """One dated game per row; exclude duplicate and future games."""
    games={}
    for r in records:
        try:
            day=date.fromisoformat(r["date"])
            game_id=str(r["game_id"]).strip()
            home,away=r["home"],r["away"]
            if not game_id or home not in ABBR or away not in ABBR or home==away:
                continue
            if day>=now_utc().date() or r["winner"] not in (home,away):
                continue
            if not str(r.get("source_url","")).startswith("https://"):
                continue
            hm,am=int(r["home_ml"]),int(r["away_ml"])
            p=devig_power(hm,am)
            if not .02<p<.98:
                continue
            if game_id in games:
                continue
            games[game_id]={"game_id":game_id,"date":day.isoformat(),"p":p,
                            "y":1 if r["winner"]==home else 0}
        except (ValueError,TypeError,KeyError,OverflowError):
            continue
    return sorted(games.values(),key=lambda r:(r["date"],r["game_id"]))


def read_history(path):
    if not path or not Path(path).is_file():
        return []
    with open(path,newline="",encoding="utf-8") as f:
        return prepare_history(csv.DictReader(f))


def write_history(path,records):
    target=Path(path)
    target.parent.mkdir(parents=True,exist_ok=True)
    with open(target,"w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=HISTORY_FIELDS)
        w.writeheader()
        w.writerows(records)


def resolved_market_audit(limit=100):
    """Fetch finalized Kalshi NBA contracts and closed Polymarket candidates.

    These records are NOT training features: two contracts may describe one game,
    Polymarket 'closed' needn't mean resolved, and final prices aren't pregame odds.
    """
    limit=max(1,min(500,int(limit)))
    result={"kalshi_resolved":0,"polymarket_closed_candidates":0,"errors":[],
            "warning":"Resolution counts are provenance checks, not prediction calibration"}
    with httpx.Client(follow_redirects=True) as client:
        for path,params in (
            ("/markets",{"series_ticker":"KXNBAGAME","status":"settled","limit":limit}),
            ("/historical/markets",{"series_ticker":"KXNBAGAME","limit":limit})
        ):
            try:
                raw=request_json(client,KALSHI+path,params)
                result["kalshi_resolved"]+=sum(1 for x in raw.get("markets",[])
                           if str(x.get("result","")).lower() in ("yes","no"))
            except (httpx.HTTPError,ValueError,TypeError,KeyError) as exc:
                result["errors"].append(f"Kalshi {path}: {type(exc).__name__}")
        try:
            raw=request_json(client,GAMMA+"/markets",
                     {"closed":"true","limit":min(limit,100),"order":"endDate","ascending":"false"})
            if isinstance(raw,list):
                result["polymarket_closed_candidates"]=sum(
                    1 for x in raw if any(n in str(x.get("question","")).lower()
                                            for n in ("nba","mavericks","cavaliers","lakers","nuggets")))
        except (httpx.HTTPError,ValueError,TypeError,KeyError) as exc:
            result["errors"].append(f"Polymarket closed catalog: {type(exc).__name__}")
    return result


def read_books(path,day):
    """Optional second+ bookmakers. Require dated, sourced, recent same-game quotes."""
    output={}
    if not path or not Path(path).is_file():
        return output
    with open(path,newline="",encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                if row["date"]!=day or row["home"] not in ABBR or row["away"] not in ABBR:
                    continue
                at=datetime.fromisoformat(row["as_of"].replace("Z","+00:00"))
                if at.tzinfo is None or not 0<=(now_utc()-at).total_seconds()<=7200:
                    continue
                if not row["source_url"].startswith("https://"):
                    continue
                provider=row["provider"].strip()
                if not provider:
                    continue
                p=devig_power(float(row["home_ml"]),float(row["away_ml"]))
                output.setdefault((row["home"],row["away"]),{})[provider.lower()]={
                    "provider":provider,"p":p,"url":row["source_url"],"as_of":row["as_of"]}
            except (KeyError,ValueError,TypeError,OverflowError):
                continue
    return output


def kalshi_match(m,game):
    """Match single-team Kalshi YES with game, date and BOTH NBA abbreviation codes."""
    if m.platform!="Kalshi":
        return {}
    local=datetime.fromisoformat(game.start).astimezone(ZoneInfo("America/New_York"))
    stamp=local.strftime("%y%b%d").upper()
    event=f"KXNBAGAME-{stamp}{ABBR[game.away]}{ABBR[game.home]}-"
    ticker=m.market_id.upper()
    if not ticker.startswith(event):
        return {}
    team_code=ticker[len(event):]
    for team in (game.home,game.away):
        if team_code==ABBR[team]:
            other=game.away if team==game.home else game.home
            return {team:"A",other:"B"}
    return {}


def collect_nba_markets(games):
    markets,errors=[],[]
    with httpx.Client(follow_redirects=True) as client:
        try:
            cursor=None
            for _ in range(5):
                params={"series_ticker":"KXNBAGAME","status":"open","limit":200}
                if cursor:
                    params["cursor"]=cursor
                data=request_json(client,KALSHI+"/markets",params)
                for row in data.get("markets",[]):
                    m=normalize_kalshi(row)
                    if m and any(kalshi_match(m,g) for g in games):
                        markets.append(m)
                cursor=data.get("cursor")
                if not cursor:
                    break
        except (httpx.HTTPError,TypeError,ValueError,KeyError) as exc:
            errors.append(f"Kalshi NBA series: {type(exc).__name__}")
        try:
            pool=collect_polymarket(client,1000)
            matches=[m for m in pool if any(match_team_sides(m,g) for g in games)]
            if matches:
                quoted,warnings=quote_poly_books(client,matches,max_markets=75)
                markets.extend(quoted)
                errors.extend(warnings)
        except (httpx.HTTPError,TypeError,ValueError,KeyError) as exc:
            errors.append(f"Polymarket NBA candidates: {type(exc).__name__}")
    return markets,errors


def evaluate(games,markets,history=(),extra_books=None,bankroll=0.,minimum_edge=.05):
    """Evidence-gated recommendations. Fail closed when critical inputs are missing."""
    model=fit_calibrator(history)
    extra_books=extra_books or {}
    result=[]
    for game in games:
        sources=[{"provider":game.provider,"p":game.fair_home,"url":game.link,"as_of":"ESPN pregame feed"}]
        for key,book in extra_books.get((game.home,game.away),{}).items():
            if key!=game.provider.lower():
                sources.append(book)
        ps=[x["p"] for x in sources]
        median=statistics.median(ps)
        disagreement=max(ps)-min(ps)
        calibrated=_sigmoid(model["a"]+model["b"]*_logit(median)) if model["validated"] else median
        for team,p in ((game.home,calibrated),(game.away,1-calibrated)):
            possible=[]
            for m in markets:
                mapping=kalshi_match(m,game) if m.platform=="Kalshi" else match_team_sides(m,game)
                side=mapping.get(team)
                if not side:
                    continue
                ask,bid,depth=(m.ask_a,m.bid_a,m.ask_size_a) if side=="A" else (m.ask_b,m.bid_b,m.ask_size_b)
                verified=(m.quote_status in ("feed","orderbook") and ask is not None and bid is not None
                          and depth is not None and depth>=10 and 0<ask<1 and 0<=bid<=ask
                          and ask-bid<=.08
                          and ((m.platform=="Kalshi" and m.volume>=100)
                               or (m.platform=="Polymarket" and m.liquidity>=1000)))
                if verified:
                    fee=fee_estimate(m.platform,ask)
                    cost=ask+fee+.01
                    ev=p-cost
                    possible.append({"platform":m.platform,"market_id":m.market_id,
                       "side":side,"ask":round(ask,4),"fee_estimate":fee,
                       "cost_estimate":round(cost,4),"edge":round(ev,4),
                       "spread":round(ask-bid,4),"ask_depth":depth,"url":m.url})
            best=max(possible,key=lambda x:x["edge"]) if possible else None
            reasons=[]
            if not model["validated"]:
                reasons.append("No out-of-sample-validated historical calibration")
            if len(sources)<2:
                reasons.append("Only one sourced bookmaker; no independent consensus")
            if disagreement>.08:
                reasons.append("Bookmakers disagree by more than 8 percentage points")
            if not best:
                reasons.append("No verified, liquid Kalshi/Polymarket purchase ask")
            elif best["edge"]<minimum_edge:
                reasons.append("Estimated after-cost edge below minimum")
            if p<.55:
                reasons.append("Estimated win probability below 55%")
            # No injury data wired: cannot claim lineup confirmation.
            reasons.append("Starting lineups/injuries and settlement rules require human review")
            qualified=(model["validated"] and len(sources)>=2 and disagreement<=.08
                       and best is not None and best["edge"]>=minimum_edge and p>=.55)
            # WAIT_REVIEW is not a recommendation to buy.
            status="REVIEW" if qualified else "PASS"
            stake=0.0
            if qualified and bankroll>0:
                cost=best["cost_estimate"]
                kelly=max(0,(p-cost)/(1-cost)) if cost<1 else 0
                stake=round(min(bankroll*.01,bankroll*.25*kelly),2)
            result.append({"game":f"{game.away} @ {game.home}",
                "game_id":game.id,"start":game.start,"team":team,
                "status":status,"estimated_probability":round(p,4),
                "bookmaker_count":len(sources),"bookmaker_sources":sources,
                "bookmaker_range":round(disagreement,4),
                "best_verified_contract":best,"conditional_stake_cap":stake,
                "reasons":reasons})
    result.sort(key=lambda x:(x["status"]=="REVIEW",
                        x["best_verified_contract"]["edge"] if x["best_verified_contract"] else -1),reverse=True)
    return {"generated_at":now_utc().isoformat(),"mode":"on_demand_read_only",
            "model":model,"recommendations":result,
            "disclaimer":"REVIEW requires manual lineup/rules/price confirmation. No auto execution, no certainty, no background work."}


def run_nba(day=None,history_file="data/nba_history.csv",books_file=None,bankroll=0.):
    from nba_odds import day_central
    day=day or day_central()
    games=get_nba(day)
    if not games:
        return {"generated_at":now_utc().isoformat(),"recommendations":[],
                "message":"No pregame NBA games with a sourced two-way bookmaker line for this date"}
    markets,errors=collect_nba_markets(games)
    report=evaluate(games,markets,read_history(history_file),read_books(books_file,
                      datetime.strptime(day,"%Y%m%d").strftime("%Y-%m-%d")),bankroll)
    report["feed_errors"]=errors
    report["market_count"]=len(markets)
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description="Rosie on-demand NBA intelligence; no trading")
    cmd=parser.add_subparsers(dest="command",required=True)
    nba=cmd.add_parser("nba",help="Return source-backed JSON and PASS/REVIEW statuses")
    nba.add_argument("--date",help="YYYYMMDD, defaults to today US Central")
    nba.add_argument("--history",default="data/nba_history.csv")
    nba.add_argument("--books",help="Optional manually sourced additional bookmaker CSV")
    nba.add_argument("--bankroll",type=float,default=0)
    history=cmd.add_parser("history",help="Explicitly fetch past games and pregame bookmaker lines")
    history.add_argument("--start",required=True)
    history.add_argument("--end",required=True)
    history.add_argument("--out",default="data/nba_history.csv")
    provider=cmd.add_parser("resolvedmarkets",help="Fetch Resolved Markets NBA settlements (optional API key)")
    provider.add_argument("--limit",type=int,default=100)
    provider.add_argument("--out",default="data/resolvedmarkets_nba.json")
    snapshots=cmd.add_parser("snapshots",help="Fetch one Resolved Markets historical pregame window")
    snapshots.add_argument("--market-id",required=True)
    snapshots.add_argument("--from-utc",required=True)
    snapshots.add_argument("--to-utc",required=True)
    snapshots.add_argument("--out",default="data/resolvedmarkets_snapshots.json")
    hist=cmd.add_parser("resolved",help="Inspect public resolved market catalogs (not train on them)")
    hist.add_argument("--limit",type=int,default=100)
    args=parser.parse_args(argv)
    if args.command=="nba":
        out=run_nba(args.date,args.history,args.books,max(0,args.bankroll))
    elif args.command=="history":
        rows,errors=fetch_history(args.start,args.end)
        write_history(args.out,rows)
        out={"saved_to":args.out,"games_with_bookmaker_closes":len(rows),
             "errors":errors,"note":"Historical closing lines may be incomplete. No model if sample/holdout insufficient."}
    elif args.command=="resolvedmarkets":
        from resolved_markets_provider import resolved_nba,write_json
        out=resolved_nba(args.limit)
        out["saved_to"]=write_json(args.out,out)
    elif args.command=="snapshots":
        from resolved_markets_provider import historical_snapshots,write_json
        out=historical_snapshots(args.market_id,args.from_utc,args.to_utc)
        out["saved_to"]=write_json(args.out,out)
    else:
        out=resolved_market_audit(args.limit)
    print(json.dumps(out,indent=2,allow_nan=False))
    return 0


if __name__=="__main__":
    sys.exit(main())
