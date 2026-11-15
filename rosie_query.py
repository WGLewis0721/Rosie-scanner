"""Natural-language, on-demand NBA research for Streamlit, CLI and MCP.

Deterministic team/date parsing: no LLM or scheduler required. Never places orders.
"""
import re
from datetime import date, timedelta
from zoneinfo import ZoneInfo
from market_scan import now_utc
from rosie_advisor import ABBR, run_nba

CUSTOM_ALIASES = {
    "Cleveland Cavaliers": ("cavs",),
    "Dallas Mavericks": ("mavs",),
    "Golden State Warriors": ("dubs",),
    "Minnesota Timberwolves": ("wolves",),
    "New Orleans Pelicans": ("pels",),
    "Oklahoma City Thunder": ("okc",),
    "Philadelphia 76ers": ("sixers",),
    "Portland Trail Blazers": ("trailblazers", "blazers"),
    "LA Clippers": ("clippers",),
}


def _today():
    return now_utc().astimezone(ZoneInfo("America/Chicago")).date()


def parse_question(question, today=None):
    """Extract a date and NBA team aliases from casual questions."""
    if not isinstance(question, str) or not question.strip():
        raise ValueError("Ask a question such as 'Cavs vs Mavs tonight'")
    today = today or _today()
    text = question.casefold()
    iso = re.search(r"(?<!\d)(\d{4}-\d{2}-\d{2})(?!\d)", text)
    compact = re.search(r"(?<!\d)(20\d{6})(?!\d)", text)
    if iso:
        target = date.fromisoformat(iso.group(1))
    elif compact:
        x = compact.group(1)
        target = date.fromisoformat(f"{x[:4]}-{x[4:6]}-{x[6:]}")
    elif re.search(r"\btomorrow\b", text):
        target = today + timedelta(days=1)
    else:
        target = today
    teams = []
    for name, code in ABBR.items():
        if name == "Los Angeles Clippers":
            continue
        aliases = {name.casefold(), name.split()[-1].casefold(), code.casefold()}
        aliases.update(CUSTOM_ALIASES.get(name, ()))
        if name == "LA Clippers":
            aliases.add("los angeles clippers")
        for alias in aliases:
            if re.search(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])", text):
                teams.append(name)
                break
    if not teams and not re.search(r"\b(nba|basketball|game|games|tonight|tomorrow|pick|picks)\b", text):
        raise ValueError("No NBA game or team found in the question")
    return target.strftime("%Y%m%d"), teams


def _game_matches(game, team_names):
    return not team_names or all(t in game.split(" @ ") for t in team_names)


def ask_game(question, bankroll=0., history_file="data/nba_history.csv",
             books_file=None, report_provider=None):
    """Ask Rosie about an NBA matchup; output both venues and a reasoned PASS/REVIEW.

    Missing live quotes never become assumed prices. REVIEW is not buy execution.
    """
    day, teams = parse_question(question)
    try:
        budget = float(bankroll)
    except (TypeError, ValueError):
        raise ValueError("Bankroll must be a nonnegative number")
    if not 0 <= budget <= 1000000:
        raise ValueError("Bankroll must be between 0 and 1,000,000 USD")
    provider = report_provider or run_nba
    report = provider(day, history_file, books_file, budget)
    all_rows = report.get("recommendations") or []
    rows = [r for r in all_rows if _game_matches(r.get("game", ""), teams)]
    games = sorted({r["game"] for r in rows})
    if not games:
        available = sorted({r["game"] for r in all_rows})
        requested = " vs ".join(teams) if teams else "NBA slate"
        summary = (f"PASS. No pregame matchup with a sourced bookmaker line for "
                   f"{requested} on {day}. Suggested stake: USD 0.")
        return {"question":question,"date":day,"status":"PASS",
                "summary":summary,"requested_teams":teams,"games":[],
                "available_games":available,"recommendations":[],"platform_comparisons":[],
                "model":report.get("model",{}),"feed_errors":report.get("feed_errors",[]),
                "stake_usd":0.0,
                "note":"No active contract or matchup was inferred from historical results."}
    comparisons = []
    for r in rows:
        quotes = r.get("platform_quotes") or {}
        for platform in ("Kalshi", "Polymarket"):
            details = quotes.get(platform,{})
            best = details.get("best")
            comparisons.append({
                "game":r["game"],"team":r["team"],"platform":platform,
                "verified":bool(best),
                "ask":best["ask"] if best else None,
                "estimated_after_cost_edge":best["edge"] if best else None,
                "market_id":best["market_id"] if best else None,
                "market_url":best["url"] if best else None,
                "contract_side":best["side"] if best else None,
                "max_buy_price_for_5pt_edge":details.get("max_buy_price_for_5pt_edge"),
                "estimated_probability":r["estimated_probability"],
                "evidence_status":"calibrated" if report.get("model",{}).get("validated")
                                  else "bookmaker_baseline",
                "recommendation_status":r["status"]
            })
    approved = [r for r in rows if r["status"] == "REVIEW" and r.get("best_verified_contract")]
    approved.sort(key=lambda r:r["best_verified_contract"]["edge"],reverse=True)
    if approved:
        top = approved[0]
        best = top["best_verified_contract"]
        summary = (f"REVIEW ONLY: {top['team']} on {best['platform']} at "
                   f"{round(best['ask']*100)} cents has estimated after-cost edge "
                   f"{best['edge']:.1%}; conditional stake cap USD "
                   f"{top['conditional_stake_cap']:.2f}. Confirm lineups, settlement "
                   "rules, live quote and fees before purchasing.")
        status="REVIEW"
        stake=top["conditional_stake_cap"]
    else:
        with_quotes=[r for r in rows if r.get("best_verified_contract")]
        with_quotes.sort(key=lambda r:r["best_verified_contract"]["edge"],reverse=True)
        if with_quotes:
            candidate=with_quotes[0]
            best=candidate["best_verified_contract"]
            summary = (f"PASS. Best verified watchlist quote: {candidate['team']} "
                       f"on {best['platform']} at {round(best['ask']*100)} cents; "
                       f"estimated after-cost edge {best['edge']:+.1%}. "
                       "Model validation, bookmaker consensus, or eligibility gates "
                       "are not satisfied. Suggested stake: USD 0.")
        else:
            summary=("PASS. No eligible executable Kalshi or Polymarket quote verified "
                     "for this matchup. Maximum-price thresholds are illustrative, "
                     "not live offers. Suggested stake: USD 0.")
        status="PASS"
        stake=0.
    return {"question":question,"date":day,"status":status,"summary":summary,
            "requested_teams":teams,"games":games,"recommendations":rows,
            "platform_comparisons":comparisons,
            "model":report.get("model",{}),"feed_errors":report.get("feed_errors",[]),
            "stake_usd":stake,"generated_at":report.get("generated_at"),
            "note":"On-demand only. No order placement; check injuries, rules and quote freshness."}
