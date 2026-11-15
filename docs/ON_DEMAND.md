# Rosie — vertical NBA intelligence (on demand)

**No redesign.** Existing Streamlit interface, collectors, discovery views and CSV workflows remain. This is an additive, narrow NBA-moneyline research path. No scheduled tasks, credentials, wallets or orders.

## Run now, once

~~~
pip install -r requirements.txt
python rosie_advisor.py nba --date 20261114 --bankroll 500
~~~

Returns JSON with each pregame game's two sides, a source-by-source sportsbook breakdown, verified exchange ask if any, estimated after-fee edge, a **PASS** or **REVIEW** status, and a conditional stake cap. REVIEW is **not** an order instruction. If data is missing or the model fails its holdout, Rosie says PASS. No trades are placed.

## Explicitly load historic resolved NBA games and pregame bookmaker closes

~~~
python rosie_advisor.py history --start 2026-09-01 --end 2026-11-13 --out data/nba_history.csv
python rosie_advisor.py resolved --limit 100
python rosie_advisor.py nba --bankroll 500 --history data/nba_history.csv
~~~

Historical ingestion reads ESPN's **final game scores**, plus separate **core historical recorded sportsbook closing odds**. It does not use postgame scores to estimate pregame probabilities. Historical odds availability varies by game. Missing odds are skipped. Historic settled Kalshi contracts and closed Polymarket *candidates* are counted for provenance review, **not** mixed into the calibration training sample; closed Polymarket is not necessarily finally resolved, and two Kalshi binary contracts often represent a single game. That prevents a very common false-data/duplicate-label error.

Do not claim the application has a trained model until enough valid games have been ingested and held-out results pass. Minimum 120 training games and 30 holdout games. The last 20% (at least 30) are strictly chronological and untouched during fitting. L2-regularized logistic/Platt calibration is fit with a prior centered on unadjusted de-vig sportsbook probabilities; Brier score and log-loss must both beat the raw bookmaker baseline (with a 0.002 Brier improvement margin) to enable calibration. This is a rigorous starting baseline, not a proof of predictive superiority. Use truly independent future-season evaluation before trusting any claimed edge.

## More bookmakers (optional)

ESPN supplies an unauthenticated bookmaker (often DraftKings); it does **not** supply a guaranteed multi-book consensus. Provide your own **sourced, recently observed** additional pregame sportsbook quotes in a local CSV:

~~~
date,home,away,provider,home_ml,away_ml,source_url,as_of
2026-11-14,Cleveland Cavaliers,Dallas Mavericks,ExampleBook,+120,-140,https://your-real-bookmaker-source.example/game,2026-11-14T18:30:00Z
~~~

Example row is schema illustration ONLY — not an actual quote. Do not save it as historical or feed it into live picks. Only matching dates/team names, valid source URLs, and quotes observed in the last 2 hours are accepted. Every included sportsbook is de-vigged by the power method; the median is taken to reduce dependence on outliers. Without 2 distinct providers, Rosie won't produce REVIEW.

## AI access, with no automation

CLI JSON can be run, read and quoted by any agent that has access to your execution environment.

For local MCP-capable tools (for example, Claude Desktop):
~~~
pip install 'mcp>=1.28,<2'
python rosie_mcp.py
~~~
Configure an MCP stdio server with command \`python\` and the absolute path to \`rosie_mcp.py\` as an argument, using the repository as its working directory. Tools: \`nba_opportunities\`, \`nba_calibration_status\`, \`nba_resolved_catalog\`. Tools run ONLY when the client calls them. No polling.

For ChatGPT, the same JSON is usable through a supported execution environment; direct in-chat invocation requires connecting a supported tool or a separately hosted MCP endpoint. **No hosted endpoint or ChatGPT connection is created by this PR.** Never paste credentials into chat.

## Mathematics / betting safeguards

1. Two-way sportsbook implied probabilities → power-method de-vig.
2. Multiple independently sourced bookmakers → median and dispersion check (8pp maximum).
3. Chronological, L2-regularized logit calibration → held-out Brier and log-loss gate; otherwise baseline only and PASS.
4. An **actual verified buy ask**, bid/ask spread <=8pp, >=10 contracts ask size, venue liquidity/volume floors.
5. Cost = ask + conservative estimated taker fee + 1 cent slippage. Net edge = estimated win probability − total cost; minimum 5pp.
6. Even when REVIEW qualifies: conservative 1/4 Kelly **capped at 1% of bankroll**, conditional on manual lineup/settlement/rule review. No stake if unresolved.
7. No live injury or player-prop feature is claimed. Model risk, stale quotes, missing books, provider disagreements, correlated book prices, and execution slippage can invalidate an apparent edge.

The resolved-market catalog is a **starting ingestion/audit capability**, not a resolved-outcome predictive model and not a historical P/L backtest. True historical order-book replay, injury-adjusted model, and forward paper-trading evaluation belong in later vertical expansions.
