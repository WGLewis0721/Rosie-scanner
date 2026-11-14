# Rosie — keyless public data sources

Rosie runs without an API key for **public market discovery** and read-only analysis.

## Live sources

1. **Kalshi**: `https://external-api.kalshi.com/trade-api/v2/markets`. Public no-key GET endpoints for open markets, price, bid/ask, size, volume. Auth is required to place trades; Rosie cannot place them.
2. **Polymarket**: `https://gamma-api.polymarket.com/markets` (list/metadata) and `https://clob.polymarket.com/book?token_id=...` (public order books). Prices from Gamma are indicative and are never counted as executable asks.
3. **ESPN (unofficial)**: `https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/scoreboard`. Includes scores and *sometimes* sportsbook odds; the `sports.core.api.espn.com` event endpoints may provide moneyline and predictor probabilities. This is undocumented, may be unavailable or change, and is not integrated into automatic contract matching because game identity, cutoff, outcome, and settlement conditions need exact verification.

## Historical research — not live fair-value oracles

- **[pdata.world historical snapshot](https://huggingface.co/datasets/lowskillcoding/pdata-prediction-markets)**. 2026-10-07, ~450k resolved events across eight venues including Kalshi and Polymarket. CC BY 4.0, attribution to pdata.world. The *resolved* partition's final `probability` is frequently post-settlement; it must NOT be backtested as if known prior to close. There are documented date coverage gaps. Direct public REST docs: https://api.pdata.world/docs (no key). The snapshot is stale for live selection.
- **[marketlens Polymarket resolved markets](https://huggingface.co/datasets/marketlens/polymarket-resolved-markets)**. ~634k settled Polymarket markets through August 2026; outcome labels useful for historical validation. Primarily crypto 5-minute contracts; avoid projecting its win rates onto unrelated categories.
- **[tennant Polymarket historical paths](https://huggingface.co/datasets/tennant/agentic-polymarket)**. 38,915 resolved binary markets with hourly price trajectories and outcomes; 153MB primary JSONL plus 50MB questions. Better suited for leakage-aware time-indexed calibration, but requires storage and an ex-ante time cutoff.
- **[ImpliedData public sample](https://huggingface.co/datasets/ImpliedData/prediction-markets)**. Cross-platform market metadata and a narrow hour-candle sample, free for noncommercial research; commercial license required.
- **[Jon Becker historical mirror](https://huggingface.co/datasets/rhinot/prediction-market-analysis)**. Large ~36GiB compressed cross-platform historical data, unsuitable for direct deployment without batch preprocessing.

## What you can do NOW, without an odds key

```bash
pip install -r requirements.txt
python market_scan.py scan --limit 3000
streamlit run app.py
python scripts/keyless_smoke.py
```

The scanner can fetch markets and the dashboard can display them. It intentionally returns **zero supported picks until there is an independent, time-stamped fair probability** plus verified executable quotes and enough depth. Historical outcome archives are not automatically promoted into current fair-value estimates.

Use a user-supplied free independent forecast CSV or two-way sportsbook moneylines CSV for scoring. If ESPN odds become an automated source, require exact matchup/date/outcome reconciliation, valid pre-game timestamp, and source provenance; if uncertain, quarantine the match rather than claim an edge.

**Privacy and safety**: no wallets, trading keys, orders, or account credentials. Market availability and odds fluctuate. Fee calculations are illustrative screens; verify platform-specific rules and fees.
