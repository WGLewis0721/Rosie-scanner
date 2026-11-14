"""Keyless NBA moneyline comparison. External sportsbook odds are not a proprietary model."""
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import httpx
from market_scan import Market, devig_power, fee_estimate, now_utc, parse_date, request_json

ESPN_URL="https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
TEAMS = {
 "Atlanta Hawks":"hawks", "Boston Celtics":"celtics", "Brooklyn Nets":"nets",
 "Charlotte Hornets":"hornets", "Chicago Bulls":"bulls", "Cleveland Cavaliers":"cavaliers",
 "Dallas Mavericks":"mavericks", "Denver Nuggets":"nuggets", "Detroit Pistons":"pistons",
 "Golden State Warriors":"warriors", "Houston Rockets":"rockets", "Indiana Pacers":"pacers",
 "LA Clippers":"clippers", "Los Angeles Clippers":"clippers", "Los Angeles Lakers":"lakers",
 "Memphis Grizzlies":"grizzlies", "Miami Heat":"heat", "Milwaukee Bucks":"bucks",
 "Minnesota Timberwolves":"timberwolves", "New Orleans Pelicans":"pelicans",
 "New York Knicks":"knicks", "Oklahoma City Thunder":"thunder", "Orlando Magic":"magic",
 "Philadelphia 76ers":"76ers", "Phoenix Suns":"suns", "Portland Trail Blazers":"blazers",
 "Sacramento Kings":"kings", "San Antonio Spurs":"spurs", "Toronto Raptors":"raptors",
 "Utah Jazz":"jazz", "Washington Wizards":"wizards"
}
EXCLUDE=re.compile(r"\b(?:spread|cover|total|over|under|points|rebounds|assists|quarter|half|player|margin|handicap)\b",re.I)

@dataclass(frozen=True)
class Game:
    id:str
    start:str
    home:str
    away:str
    odds_home:int
    odds_away:int
    fair_home:float
    fair_away:float
    provider:str
    link:str

def day_central():
    return now_utc().astimezone(ZoneInfo("America/Chicago")).strftime("%Y%m%d")

def american(raw):
    if raw is None:return None
    text=str(raw).replace("−","-").strip()
    if not re.fullmatch(r"[+-]?\d{2,5}",text):return None
    value=int(text)
    return value if value else None

def parse_nba(data):
    games=[]
    for event in data.get("events",[]):
        if ((event.get("status") or {}).get("type") or {}).get("state") not in ("pre",None):
            continue
        comps=event.get("competitions") or []
        if not comps:continue
        comp=comps[0]
        names={x.get("homeAway"):x.get("team",{}).get("displayName") for x in comp.get("competitors",[])}
        home,away=names.get("home"),names.get("away")
        if home not in TEAMS or away not in TEAMS:continue
        start=parse_date(event.get("date"))
        if not start or start<=now_utc():continue
        options=sorted(comp.get("odds") or [],key=lambda o:o.get("provider",{}).get("id")!="100")
        for option in options:
            ml=option.get("moneyline") or {}
            h=american((((ml.get("home") or {}).get("close") or {}).get("odds")))
            a=american((((ml.get("away") or {}).get("close") or {}).get("odds")))
            if a is None or h is None:continue
            fair_away=devig_power(a,h)
            games.append(Game(str(event.get("id")),start.isoformat(),home,away,h,a,
                  1-fair_away,fair_away,str(option.get("provider",{}).get("name") or "Listed sportsbook"),
                  "https://www.espn.com/nba/game/_/gameId/"+str(event.get("id"))))
            break
    return sorted(games,key=lambda x:x.start)

def get_nba(day=None):
    day=day or day_central()
    if not re.fullmatch(r"\d{8}",day):raise ValueError("Invalid YYYYMMDD")
    with httpx.Client(follow_redirects=True) as client:
        return parse_nba(request_json(client,ESPN_URL,{"dates":day}))

def team_present(text, team):
    text=text.lower()
    parts=[team.lower(),TEAMS[team]]
    return any(re.search(r"(?<!\w)"+re.escape(x)+r"(?!\w)",text) for x in parts)

def match_team_sides(m:Market,g:Game):
    """Reject ambiguous contracts instead of treating props as game winners."""
    if EXCLUDE.search(m.title):return {}
    combined=" ".join((m.title,m.outcome_a,m.outcome_b))
    if not all(team_present(combined,t) for t in (g.home,g.away)):return {}
    end,start=parse_date(m.close_at),parse_date(g.start)
    if not end or not start or abs((end-start).total_seconds())>72*3600:return {}
    a=[t for t in (g.home,g.away) if team_present(m.outcome_a,t)]
    b=[t for t in (g.home,g.away) if team_present(m.outcome_b,t)]
    if len(a)==len(b)==1 and a[0]!=b[0]:return {a[0]:"A",b[0]:"B"}
    if m.outcome_a.lower().strip() in ("yes","") and m.outcome_b.lower().strip() in ("no",""):
        for team in (g.home,g.away):
            if re.search(r"\b(?:will|does)\s+(?:the\s+)?(?:"
                   +re.escape(team.lower())+"|"+re.escape(TEAMS[team])
                   +r")\s+(?:win|beat)\b",m.title.lower()):
                other=g.away if team==g.home else g.home
                return {team:"A",other:"B"}
    return {}

def target_ask(fair, platform, desired_edge=.05, slippage=.01):
    lo,hi=.001,.999
    for _ in range(35):
        mid=(lo+hi)/2
        if fair-mid-fee_estimate(platform,mid)-slippage >= desired_edge:lo=mid
        else:hi=mid
    return round(lo,3) if fair-lo-fee_estimate(platform,lo)-slippage>=desired_edge else 0.

def board(games,markets,desired_edge=.05,slippage=.01):
    """All sides, including 'no confirmed edge'. Price and source are kept separate."""
    rows=[]
    for game in games:
        matched={game.home:[],game.away:[]}
        for m in markets:
            for team,side in match_team_sides(m,game).items():
                ask,bid,size=(m.ask_a,m.bid_a,m.ask_size_a) if side=="A" else (m.ask_b,m.bid_b,m.ask_size_b)
                eligible=(m.quote_status in ("feed","orderbook") and ask is not None and bid is not None
                   and size is not None and size>=10 and 0<ask<1 and 0<=bid<=ask
                   and ask-bid<=.08 and ((m.platform=="Kalshi" and m.volume>=100)
                   or (m.platform=="Polymarket" and m.liquidity>=1000)))
                matched[team].append({"platform":m.platform,"ask":ask,"eligible":eligible,
                                     "id":m.market_id,"url":m.url})
        for team,fair,american in ((game.home,game.fair_home,game.odds_home),(game.away,game.fair_away,game.odds_away)):
            good=sorted([q for q in matched[team] if q["eligible"]],key=lambda x:x["ask"])
            best=good[0] if good else None
            net=(fair-best["ask"]-fee_estimate(best["platform"],best["ask"])-slippage) if best else None
            rows.append({"game":f"{game.away} at {game.home}","team":team,"start":game.start,
              "provider":game.provider,"american":american,"fair":fair,
              "platform":best["platform"] if best else None,"ask":best["ask"] if best else None,
              "net_edge":net,"supported":net is not None and net>=desired_edge,
              "target_kalshi":target_ask(fair,"Kalshi",desired_edge,slippage),
              "target_poly":target_ask(fair,"Polymarket",desired_edge,slippage),
              "matched":len(matched[team]),"verified":len(good),
              "market_url":best["url"] if best else None,"source_url":game.link})
    return sorted(rows,key=lambda r:(r["supported"],r["net_edge"] if r["net_edge"] is not None else -1),reverse=True)
