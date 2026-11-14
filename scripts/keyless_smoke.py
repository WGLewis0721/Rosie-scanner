"""A real network smoke test for Rosie's public data sources; no API keys.

Live market tests: run from GitHub Actions or an internet-connected machine.
No trading endpoints, no wallets, no signed requests.
"""
import json
from pathlib import Path

import httpx
from market_scan import (
    KALSHI, GAMMA, normalize_kalshi, normalize_poly, now_utc, request_json,
)


def main():
    output = {"timestamp_utc": now_utc().isoformat(), "requires_api_key": False, "providers": {}}
    with httpx.Client(follow_redirects=True, timeout=20) as client:
        for name, url, params, normalizer, field in (
            ("kalshi", KALSHI + "/markets", {"limit": 10, "status": "open"}, normalize_kalshi, "markets"),
            ("polymarket", GAMMA + "/markets", {"limit": 10, "active": "true", "closed": "false"}, normalize_poly, None),
        ):
            print(f"Checking {name} public GET...", flush=True)
            try:
                data = request_json(client, url, params)
                raw = data.get(field, []) if field else data
                rows = [m for row in raw if (m := normalizer(row)) is not None]
                output["providers"][name] = {
                    "status": "ok", "markets": len(rows),
                    "example": [{"id": row.market_id, "title": row.title[:110],
                                 "ask_a": row.ask_a, "indicative_a": row.indicative_a}
                                for row in rows[:3]]
                }
            except Exception as exc:
                output["providers"][name] = {
                    "status": "error", "error": type(exc).__name__,
                    "detail": str(exc)[:200],
                }

        # Public, unofficial feed: useful for independent sports research.
        try:
            data = request_json(client,
                "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
                {"dates": "20261115"})
            events = data.get("events", [])
            with_odds = sum(bool(e.get("competitions") and e["competitions"][0].get("odds"))
                            for e in events)
            output["providers"]["espn_nfl"] = {
                "status": "ok", "events": len(events), "events_with_odds": with_odds,
                "note": "Unlicensed/undocumented public endpoint; not a guaranteed data source",
            }
        except Exception as exc:
            output["providers"]["espn_nfl"] = {
                "status": "error", "error": type(exc).__name__, "detail": str(exc)[:200],
            }

        # Dataset is research history only; do not use post-settlement prices as forecasts.
        try:
            response = client.get(
                "https://huggingface.co/datasets/lowskillcoding/pdata-prediction-markets",
                timeout=20, follow_redirects=True)
            response.raise_for_status()
            output["providers"]["huggingface_pdata"] = {
                "status": "accessible", "historical_only": True,
                "dataset": "lowskillcoding/pdata-prediction-markets"}
        except Exception as exc:
            output["providers"]["huggingface_pdata"] = {
                "status": "error", "error": type(exc).__name__, "detail": str(exc)[:200]}

    Path("keyless_smoke.json").write_text(json.dumps(output, indent=2))
    print(json.dumps(output, indent=2))
    if (output["providers"]["kalshi"].get("markets", 0) +
            output["providers"]["polymarket"].get("markets", 0)) == 0:
        raise SystemExit("Both live market feeds failed: Rosie cannot scan live contracts.")


if __name__ == "__main__":
    main()
