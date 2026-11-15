"""Rosie — read-only prediction market intelligence dashboard."""
import io
from dataclasses import asdict, replace

import httpx
import streamlit as st

from market_scan import (
    collect_all, load_evidence, matching_candidates, now_utc, quote_poly_books, score,
)
from nba_odds import get_nba, day_central, match_team_sides, board as nba_board


st.set_page_config(page_title="Rosie | Market Intelligence", page_icon="🌹", layout="wide")
st.title("🌹 Rosie")
st.caption("Kalshi + Polymarket research | Read-only | No account, wallet, or trading access")
st.warning("Market odds are prices, NOT validated win probabilities. Rosie only labels a candidate as an opportunity when independent evidence and an order-book quote are available. This is not investment advice.", icon="⚠️")


@st.cache_data(ttl=600, show_spinner="Fetching public markets (cached for 10 minutes)...")
def get_markets(per_platform: int):
    return (*collect_all(per_platform), now_utc().strftime('%Y-%m-%d %H:%M UTC'))


def to_stream(upload):
    if upload is None:
        return None
    return io.StringIO(upload.getvalue().decode("utf-8-sig"))


with st.sidebar:
    st.header("Scan settings")
    maximum = st.select_slider("Markets per platform", [500, 1000, 2000, 3000, 5000], value=3000)
    probability = st.slider("Minimum independently estimated win probability", 50, 95, 55, 5) / 100
    edge = st.slider("Minimum estimated after-cost edge", 0, 20, 5, 1) / 100
    days = st.slider("Maximum days to market close", 1, 180, 30)
    st.subheader("Independent evidence")
    forecasts = st.file_uploader("External estimates CSV", type="csv", help="Use data/forecasts.example.csv columns. Market price is not evidence.")
    sportsbooks = st.file_uploader("Sportsbook two-way odds CSV", type="csv", help="Use data/sportsbooks.example.csv columns. Odds are de-vigged with the power method.")
    st.caption("Include exact market IDs, source URLs, and UTC timestamps. Evidence older than 48 hours is excluded.")
    if st.button("Refresh public feeds"):
        get_markets.clear()
        st.rerun()

markets, errors, scanned_at = get_markets(maximum)
evidence = load_evidence(to_stream(forecasts), to_stream(sportsbooks))
validated_markets = [m for m in markets if m.platform == "Polymarket" and m.key in evidence]
quote_warnings = []
if validated_markets:
    with st.spinner("Checking live CLOB order books for evidence-supported contracts..."):
        with httpx.Client(follow_redirects=True) as client:
            quotes, quote_warnings = quote_poly_books(client, validated_markets, max_markets=75)
        by_key = {m.key: m for m in quotes}
        markets = [by_key.get(m.key, m) for m in markets]

picks = score(markets, evidence, probability, edge, days)
matches = matching_candidates(markets)
counts = {name: sum(m.platform == name for m in markets) for name in ("Kalshi", "Polymarket")}
a, b, c, d = st.columns(4)
a.metric("Contracts scanned", f"{len(markets):,}")
b.metric("Kalshi", f"{counts['Kalshi']:,}")
c.metric("Polymarket", f"{counts['Polymarket']:,}")
d.metric("Evidence-backed opportunities", len(picks))
st.caption(f"Scanned at {scanned_at} · Public quotes can change · Only the first 75 evidence-backed Polymarket markets receive CLOB verification per refresh")

for name, error in errors.items():
    st.error(f"{name} feed failed: {error}. Totals may be incomplete.")
if quote_warnings:
    st.info(f"{len(quote_warnings)} order-book quotes could not be verified. Those contracts are excluded.")

st.subheader("🏀 Tonight's NBA — no-key moneyline comparison")
st.caption("Free ESPN-listed sportsbook moneylines vs available Kalshi/Polymarket buy asks. Comparison only: not a proprietary win model.")
@st.cache_data(ttl=120, show_spinner="Reading ESPN's public NBA scoreboard...")
def nba_tonight(day):
    return get_nba(day)

nba_error = ""
nba_rows = []
nba_data = []
try:
    nba_data = nba_tonight(day_central())
except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
    nba_error = f"{type(exc).__name__}: {exc}"
if nba_error:
    st.error(f"NBA odds feed unavailable: {nba_error}. No substitute odds have been fabricated.")
else:
    if not nba_data:
        st.info("No remaining pregame NBA games with supported two-way sportsbook moneylines tonight.")
    else:
        nba_poly = [m for m in markets if m.platform == "Polymarket"
                    and any(match_team_sides(m, g) for g in nba_data)]
        verified_update = {}
        if nba_poly:
            with st.spinner("Verifying matching Polymarket purchase-side asks..."):
                with httpx.Client(follow_redirects=True) as client:
                    quotes, issues = quote_poly_books(client, nba_poly, max_markets=75)
                verified_update = {m.key: m for m in quotes}
                if issues:
                    st.caption(f"{len(issues)} Polymarket book queries were unavailable and are excluded from supported edges.")
        nba_markets = [verified_update.get(m.key, m) for m in markets]
        nba_rows = nba_board(nba_data, nba_markets)
        f1, f2, f3 = st.columns(3)
        f1.metric("Pregame NBA matchups", len(nba_data))
        f2.metric("Verified buy-side comparisons", sum(x["verified"] for x in nba_rows))
        f3.metric("≥5-point estimated net edge", sum(x["supported"] for x in nba_rows))
        favorites_only = st.checkbox("Show only estimated 50%+ favorites", value=True)
        visible_nba = [r for r in nba_rows if r["fair"] >= .50 or not favorites_only]
        st.dataframe([{
            "Game": r["game"], "Outcome": r["team"],
            "Book": r["provider"], "Book moneyline": f"{r['american']:+d}",
            "No-vig book probability": f"{r['fair']:.1%}",
            "Max Kalshi ask for 5pt edge": f"{r['target_kalshi']:.0%}",
            "Max Poly ask for 5pt edge": f"{r['target_poly']:.0%}",
            "Best verified platform": r["platform"] or "Not matched/verified",
            "Actual verified ask": f"{r['ask']:.1%}" if r["ask"] is not None else "—",
            "Estimated net edge": f"{r['net_edge']:+.1%}" if r["net_edge"] is not None else "—",
            "Screen passes": "YES — recheck" if r["supported"] else "No confirmed edge",
            "Market": r["market_url"] or "",
        } for r in visible_nba], hide_index=True, use_container_width=True)
        if not any(r["supported"] for r in nba_rows):
            st.info("No NBA contracts currently pass the supported 5-point net-edge screen. The maximum-ask columns are thresholds, NOT live offers.")
        st.markdown("[Live NBA platform comparisons (Spot Angle)](https://spotangle.ai/odds/nba) · [ESPN NBA odds](https://www.espn.com/nba/scoreboard)")
        st.caption("Source: public ESPN scoreboard, refreshed at most every 2 min, plus Rosie's cached public market collection (manual Refresh available). ESPN may change the odds schema or omit games. 'Close' is ESPN's field name, not a timestamp verification. De-vigged sportsbook consensus is NOT a guarantee. No buy/no recommendation without a verified purchase ask and book depth; estimated fees/slippage may differ from execution.")


# Optional vertical expansion: run only when the user clicks; original views stay.
with st.expander("🌹 Rosie Advisor — ask about tonight's NBA game", expanded=False):
    st.caption("Ask about one matchup. Rosie compares Kalshi and Polymarket executable prices with sourced bookmaker odds; no trades or automatic alerts.")
    question = st.text_input("Ask Rosie", placeholder="Cavs vs Mavericks tonight — what should I pick?", key="rosie_question")
    budget = st.number_input("Reference bankroll (USD)", min_value=0.0, max_value=100000.0, value=0.0, step=10.0, key="advisor_bankroll")
    if st.button("Ask Rosie now", key="advisor_run"):
        from rosie_query import ask_game
        with st.spinner("Checking the game, bookmaker lines and eligible exchange asks..."):
            try:
                report = ask_game(question, bankroll=budget)
                st.write(report["summary"])
                if report.get("feed_errors"):
                    st.warning("Data provider issues: " + "; ".join(report["feed_errors"][:5]))
                model = report.get("model", {})
                st.caption(f"Probability basis: {model.get('mode','not available')}. Historical calibration validated: {model.get('validated', False)}.")
                comparisons = report.get("platform_comparisons", [])
                if comparisons:
                    st.dataframe([{
                        "Matchup": q["game"], "Team": q["team"], "Market": q["platform"],
                        "Verified buy ask": f"{q['ask']:.0%}" if q["ask"] is not None else "Not verified",
                        "Estimated fair probability": f"{q['estimated_probability']:.1%}",
                        "Max illustrative ask for 5pt edge": (
                            f"{q['max_buy_price_for_5pt_edge']:.1%}"
                            if q["max_buy_price_for_5pt_edge"] is not None else "—"),
                        "After-cost edge": (f"{q['estimated_after_cost_edge']:+.1%}"
                                            if q["estimated_after_cost_edge"] is not None else "—"),
                        "Status": q["recommendation_status"],
                        "Contract": q["market_url"] or "",
                    } for q in comparisons], hide_index=True, use_container_width=True)
                elif report.get("available_games"):
                    st.caption("Available pregame NBA games: " + "; ".join(report["available_games"]))
                st.download_button("Export Rosie answer (JSON)",
                                   data=__import__("json").dumps(report, indent=2),
                                   file_name="rosie_answer.json", mime="application/json")
            except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
                st.error(f"Rosie cannot produce a supported answer ({type(exc).__name__}): {exc}")

st.subheader("Evidence-backed opportunities")
if picks:
    st.dataframe([{
        "Platform": p["platform"], "Question": p["market"], "Pick": p["outcome"],
        "Fair estimate": f"{p['estimated_probability']:.1%}",
        "Verified ask": f"{p['buy_ask']:.1%}",
        "After-cost edge": f"{p['net_edge']:.1%}",
        "Est. ROI": f"{p['expected_roi']:.1%}",
        "Days to close": p["days_to_market_close"], "Method": p["estimate_method"],
        "Source": p["estimate_source"], "Market link": p["url"],
    } for p in picks], hide_index=True, use_container_width=True)
    st.download_button("Export supported picks (JSON)", data=__import__("json").dumps(picks, indent=2),
                       file_name="rosie_opportunities.json", mime="application/json")
else:
    st.info("No supported opportunities meet the current filters. Upload independently sourced estimates or sportsbook odds with exact market IDs. Rosie will not invent probabilities or opportunities.")

st.subheader("Market discovery (not picks)")
st.caption("This is a watchlist, NOT a ranked EV list. Polymarket Gamma prices are indicative; live books are required before scoring.")
search = st.text_input("Search market questions")
site = st.selectbox("Platform", ["Both", "Kalshi", "Polymarket"])
filtered = [m for m in markets if (site == "Both" or m.platform == site) and search.lower() in m.title.lower()]
filtered.sort(key=lambda m: m.volume, reverse=True)
st.dataframe([{
    "Platform": m.platform, "Question": m.title, "Outcome A": m.outcome_a,
    "Price A (indicative)": m.indicative_a if m.platform == "Polymarket" else m.ask_a,
    "Price B (indicative)": m.indicative_b if m.platform == "Polymarket" else m.ask_b,
    "Market volume": m.volume, "Liquidity": m.liquidity,
    "Closes": m.close_at[:10], "Quote status": m.quote_status,
    "ID": m.market_id, "Link": m.url,
} for m in filtered[:500]], hide_index=True, use_container_width=True)
st.caption(f"Showing {min(500, len(filtered)):,} of {len(filtered):,} matching markets. Kalshi volume is contracts; Polymarket volume is quoted in USD. These units are not directly comparable.")

with st.expander(f"Cross-platform matching candidates: {len(matches)}"):
    st.caption("Strict normalized question + UTC close date only. Different settlement rules may still apply. Never treated as guaranteed arbitrage.")
    if matches:
        st.dataframe(matches[:200], hide_index=True, use_container_width=True)

with st.expander("How Rosie calculates a supported pick"):
    st.markdown("""
1. Fetch and normalize thousands of active public markets through paginated APIs.
2. Require a recent **external** probability estimate, or exact-market-ID sportsbook odds de-vigged by the power method.
3. Verify the **buy-side ask**, spread, and top-of-book size. Polymarket uses its public CLOB order books.
4. Estimate contract fees and a 1¢/share slippage buffer. Calculate net edge: **independent fair probability − buy ask − estimated fee − slippage**.
5. Filter by probability, net edge, close date, volume/liquidity and book depth. Rank by estimated net edge.

All fees are conservative approximations, not exchange fee quotes. Sportsbook estimates may be correlated, stale, or incorrect. Market close does not necessarily mean settlement. Check exact rules and execution costs before acting. No automatic market-to-market fair-value inference, execution, wallet support, or keys.
""")
