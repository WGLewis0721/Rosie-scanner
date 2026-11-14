"""Rosie — read-only prediction market intelligence dashboard."""
import io
from dataclasses import asdict, replace

import httpx
import streamlit as st

from market_scan import (
    collect_all, load_evidence, matching_candidates, now_utc, quote_poly_books, score,
)

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
