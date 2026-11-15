# Rosie 🌹 — Prediction Market Intelligence

**Read-only Kalshi + Polymarket market scanner.** This repository has been repurposed from its original AWS inventory assistant. The old AWS/LLM/OpenSearch app is intentionally removed.

Rosie scans **up to 3,000 active contracts per platform by default** (configurable to 5,000 via the UI), displays the market discovery feed, and ranks *only* opportunities supported by independent evidence and verified purchase-side quotes. A 90% market-implied probability is **not** itself an edge.

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
# open http://localhost:8501
```

Or `docker compose up --build`. No API keys, wallets, AWS, LLM, authentication, or trading setup required. Internet access to the public Kalshi, Gamma, and CLOB APIs is needed. Public feed errors are displayed, not masked.

CLI:

```bash
python market_scan.py scan --limit 3000
# writes rosie_scan.json
python market_scan.py backtest --file data/backtest.csv
python -m pytest -q
```

## What is actually implemented?

| Capability | Status |
|---|---|
| Public Kalshi open-market pagination | Implemented |
| Public Polymarket active-market pagination | Implemented |
| Thousands of markets / search / platform filters | Implemented (subject to API limits) |
| Order-book verification for independent-evidence Polymarket candidates | Implemented (first 75 by feed order per scan) |
| Require exact market ID, dated and sourced external probabilities | Implemented |
| Sportsbook odds power de-vig (two-way) | Implemented via CSV input |
| Estimated fees, spread/depth screens, liquidity checks, net EV and ROI | Implemented; estimates, NOT live fee quotes |
| Strict title+UTC-close-date cross-platform candidate matches | Implemented; ALWAYS requires manual rule review |
| Historical Brier, reliability buckets and realized P/L | Implemented via resolved-trade CSV |
| Forecast training, historical data ingestion at scale, independent odds feed subscription | Not implemented |
| Trading, position sizing, wallet connection, credentials, orders | **Not included** |

## Adding evidence

Download the example CSV headers from `data/forecasts.example.csv` and `data/sportsbooks.example.csv`. Upload either CSV using Rosie's sidebar. The application **does not fabricate** an independent fair probability from Kalshi, Polymarket, or a match across them.

External forecast CSV:

```csv
platform,market_id,probability_a,source_url,as_of,method,notes
```

For example, `probability_a=0.67` means your independent estimate of outcome A, *not* the current contract price. `as_of` is an ISO-8601 UTC timestamp (like `2026-11-14T18:30:00Z`). Required source URLs must begin with http(s), and estimates older than **48 hours** are excluded. For Polymarket `market_id` is the Gamma numeric market ID; for Kalshi it's the market ticker. `outcome_a` is the *first listed outcome* on Polymarket (which might be a team), and YES on Kalshi. Always confirm the outcome labels before uploading.

Sportsbook odds CSV:

```csv
platform,market_id,odds_a,odds_b,source_url,as_of,notes
```

Supply actual two-way American odds for the **same clearly identified event**. Rosie removes the sportsbook's vig via the power method. If both files contain the same contract, the external estimate takes precedence; correlated sources are not stacked to manufacture confidence. A sportsbook feed subscription is **not** included; the CSV is a transparent input.

### Ranking and eligibility

For each side `A` and `B`:

```
estimated fee (per share) = approx taker rate × ask × (1 − ask)
estimated net edge         = independent p(outcome) − actual buy ask − fee − $0.01 slippage
estimated ROI              = net edge / (ask + fee + slippage)
```

Kalshi's fee is conservatively **rounded up to the next cent per contract** using a 7% illustrative taker coefficient; Polymarket uses the same 7% conservative general buffer. **Real fee rates vary with product, venue and the current schedule**; these formulas are screens, not execution quotes. Fee exceptions, order size, spread, quote movement, and settlement risk can invalidate results. Always confirm the specific exchange's final fee.

A candidate is returned only if all are met (defaults):
- independently estimated outcome probability at least **55%**;
- estimated *after-cost* edge at least **5 percentage points**;
- market close within **30 days** (close date is NOT guaranteed settlement date);
- fresh independent evidence, with source URL and exact market ID;
- actual displayed buy ask, bid/ask spread no more than 8 points, top-of-book ask size at least 10 contracts;
- minimum Kalshi volume 100 contracts, or Polymarket liquidity $1,000;
- Polymarket must have a fresh public CLOB book for each outcome token; Gamma `outcomePrices` never count as executable quotes.

**Important:** Cross-platform market matching is intentionally conservative: exact normalized title plus UTC market close date only, and still requires human verification of settlement rules. Matches are never called riskless arbitrage. Screens do not prove positive expected value.

## Backtesting

Provide a CSV matching `data/backtest.example.csv` with one row per historical *ex-ante* forecast and resolved outcome:

```csv
probability_a,paid_price,fee,slippage,settled_a
```

`settled_a` must be 1 or 0. Reports average Brier score, expected P/L, realized P/L, and decile reliability. This is a reporting utility, not a trained model or a proof of an edge. Avoid look-ahead bias; keep training and evaluation markets disjoint. This simple backtest does not model fill probability, path-dependent execution, capital utilization, dependence, or settlement disputes.

## Architecture

- `market_scan.py` — HTTP GET-only collectors, normalization, independent evidence, de-vig, top-of-book verification, risk gates, EV, matching and backtesting.
- `app.py` — Streamlit dashboard, refresh/cache, research inputs, watchlists and exports.
- `tests/` — fixture-driven tests without exchange credentials/network access.

Read-only uses **only public GETs** to Kalshi's `/markets`, Polymarket Gamma's `/markets`, and Polymarket CLOB's `/book`. There are no order endpoints, API credential fields, transaction signing, or wallet integrations.

## Research sources (ideas, not copied code)

- [prediction-market-calibration](https://github.com/SLaffey24/prediction-market-calibration) — Brier/reliability and favorite–longshot analysis.
- [pred-arbitrage](https://github.com/pjmerica/pred-arbitrage) — strict pairing, exclusion rules and fee awareness.
- [polymarket-vegas-edge](https://github.com/crollila/polymarket-vegas-edge) — sportsbook power de-vig and ask-price execution discipline.
- [prediction-market-analysis](https://github.com/Jon-Becker/prediction-market-analysis) — public API pagination and comparative historical research.

API and fee references: [Kalshi market API](https://docs.kalshi.com/api-reference/market/get-markets), [Kalshi fee schedule](https://kalshi.com/fee-schedule), [Polymarket public data](https://docs.polymarket.com/), [Polymarket fees](https://help.polymarket.com/en/articles/13364478-trading-fees). Reference repos are research inspirations; Rosie contains an independent implementation.

**Risk:** Prices are volatile, markets can become illiquid or be voided, and an independently estimated probability may be wrong. This is research software, not a profitable strategy guarantee or financial advice.


## On-demand NBA + AI vertical

The existing dashboard stays intact. The separate optional \`rosie_advisor.py\` NBA research command adds historical closing-odds ingestion, guarded out-of-sample probability calibration, strict Kalshi NBA matching, sourced multi-book comparisons, conditional position sizing, a JSON output, and a local Claude/MCP-compatible server \`rosie_mcp.py\`. No automation or trading.

Full setup and math: **[docs/ON_DEMAND.md](docs/ON_DEMAND.md)**. Optional Resolved Markets historical NBA archive adapter is supported with a separately supplied provider key; the core engine does not require it.


### Just ask Rosie about tonight

From the existing Streamlit dashboard, open **Rosie Advisor**, type
\`Cavs vs Mavs tonight — what should I pick on Kalshi or Polymarket?\`,
and click **Ask Rosie now**. Or:

~~~bash
python rosie_advisor.py ask "Cavs vs Mavs tonight" --bankroll 500
~~~

The same \`ask_rosie(question, bankroll)\` tool is available through the optional
local MCP server for Claude-compatible clients. Output shows Kalshi and Polymarket
separately; unavailable prices are labeled unverified. PASS means do not bet;
REVIEW is conditional research, not a buy order. No scheduling or trading.
