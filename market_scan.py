"""Rosie: public, read-only Kalshi + Polymarket market research.

Never places orders, signs transactions, authenticates, or accesses wallets.
Market prices are NOT independent probability estimates.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import re
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

import httpx

KALSHI = "https://external-api.kalshi.com/trade-api/v2"
GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
USER_AGENT = "RosieMarketResearch/1.0 (public read-only market analysis)"
HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json"}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_date(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def number(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def fraction(value: Any) -> float | None:
    n = number(value)
    return n if n is not None and 0 < n < 1 else None


def array(value: Any) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            result = json.loads(value)
            return result if isinstance(result, list) else []
        except (ValueError, TypeError):
            return []
    return []


def request_json(client: httpx.Client, url: str, params: dict | None = None) -> Any:
    """GET only. Retry temporary errors and honor Retry-After (up to 8s)."""
    for attempt in range(3):
        try:
            response = client.get(url, params=params, headers=HEADERS, timeout=20)
            if response.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                delay = min(8.0, number(response.headers.get("Retry-After")) or 0.5 * (2 ** attempt))
                time.sleep(delay)
                continue
            response.raise_for_status()
            return response.json()
        except (httpx.TimeoutException, httpx.NetworkError):
            if attempt == 2:
                raise
            time.sleep(0.5 * (2 ** attempt))
    raise RuntimeError("Market API retry exhausted")


@dataclass
class Market:
    platform: str
    market_id: str
    title: str
    outcome_a: str
    outcome_b: str
    close_at: str
    url: str
    rules: str = ""
    category: str = ""
    volume: float = 0.0
    liquidity: float = 0.0
    ask_a: float | None = None
    ask_b: float | None = None
    bid_a: float | None = None
    bid_b: float | None = None
    ask_size_a: float | None = None
    ask_size_b: float | None = None
    indicative_a: float | None = None
    indicative_b: float | None = None
    token_a: str = ""
    token_b: str = ""
    quote_status: str = "unverified"

    @property
    def key(self) -> tuple[str, str]:
        return self.platform.lower(), self.market_id

    @property
    def days_left(self) -> float | None:
        closing = parse_date(self.close_at)
        return (closing - now_utc()).total_seconds() / 86400 if closing else None


def normalize_kalshi(row: dict) -> Market | None:
    if row.get("status") not in ("open", "active") or not row.get("ticker"):
        return None
    closing = parse_date(row.get("close_time") or row.get("expected_expiration_time"))
    if closing is None or closing <= now_utc():
        return None

    def price(side: str) -> float | None:
        v = fraction(row.get(side + "_dollars"))
        if v is not None:
            return v
        raw = number(row.get(side))
        return fraction(raw / 100) if raw is not None else None

    ticker = str(row["ticker"])
    ask_a, ask_b = price("yes_ask"), price("no_ask")
    bid_a, bid_b = price("yes_bid"), price("no_bid")
    return Market(
        platform="Kalshi", market_id=ticker,
        title=str(row.get("title") or ticker),
        outcome_a=str(row.get("yes_sub_title") or "Yes"),
        outcome_b=str(row.get("no_sub_title") or "No"),
        close_at=closing.isoformat(), url="https://kalshi.com/markets",
        rules=str(row.get("rules_primary") or ""),
        category=str(row.get("market_type") or ""),
        volume=number(row.get("volume_fp") or row.get("volume")) or 0,
        liquidity=number(row.get("liquidity_dollars")) or 0,
        ask_a=ask_a, ask_b=ask_b, bid_a=bid_a, bid_b=bid_b,
        ask_size_a=number(row.get("yes_ask_size_fp")),
        ask_size_b=number(row.get("no_ask_size_fp")),
        indicative_a=bid_a, indicative_b=bid_b,
        quote_status="feed" if ask_a or ask_b else "unverified",
    )


def normalize_poly(row: dict) -> Market | None:
    if row.get("active") is False or row.get("closed") is True:
        return None
    labels, prices, tokens = array(row.get("outcomes")), array(row.get("outcomePrices")), array(row.get("clobTokenIds"))
    if len(labels) != 2 or len(tokens) != 2:
        return None
    closing = parse_date(row.get("endDate"))
    if closing is None or closing <= now_utc():
        return None
    slug = str(row.get("slug") or "")
    if not slug or not row.get("id"):
        return None
    events = row.get("events")
    event_slug = (events[0].get("slug") if isinstance(events, list) and events
                  and isinstance(events[0], dict) else None)
    return Market(
        platform="Polymarket", market_id=str(row["id"]),
        title=str(row.get("question") or slug),
        outcome_a=str(labels[0]), outcome_b=str(labels[1]),
        close_at=closing.isoformat(),
        url="https://polymarket.com/event/" + quote(str(event_slug or slug), safe="-"),
        rules=str(row.get("description") or ""),
        category=str(row.get("category") or ""),
        volume=number(row.get("volumeNum") or row.get("volume")) or 0,
        liquidity=number(row.get("liquidityNum") or row.get("liquidity")) or 0,
        indicative_a=fraction(prices[0]) if len(prices) > 0 else None,
        indicative_b=fraction(prices[1]) if len(prices) > 1 else None,
        token_a=str(tokens[0]), token_b=str(tokens[1]),
        quote_status="indicative",
    )


def collect_kalshi(client: httpx.Client, limit: int = 3000) -> list[Market]:
    out, cursor, seen = [], None, set()
    while len(out) < limit:
        params: dict[str, Any] = {"status": "open", "limit": min(200, limit - len(out))}
        if cursor:
            params["cursor"] = cursor
        data = request_json(client, KALSHI + "/markets", params)
        rows = data.get("markets", [])
        if not rows:
            break
        for row in rows:
            m = normalize_kalshi(row)
            if m is not None:
                out.append(m)
                if len(out) >= limit:
                    break
        next_cursor = data.get("cursor")
        if not next_cursor or next_cursor in seen:
            break
        seen.add(next_cursor)
        cursor = next_cursor
    return out


def collect_polymarket(client: httpx.Client, limit: int = 3000) -> list[Market]:
    out, offset = [], 0
    while len(out) < limit:
        size = min(100, limit - len(out))
        rows = request_json(client, GAMMA + "/markets", {
            "active": "true", "closed": "false", "limit": size, "offset": offset,
            "order": "volumeNum", "ascending": "false",
        })
        if not isinstance(rows, list) or not rows:
            break
        for row in rows:
            m = normalize_poly(row)
            if m is not None:
                out.append(m)
                if len(out) >= limit:
                    break
        offset += len(rows)
        if len(rows) < size:
            break
    return out


def collect_all(max_per_platform: int = 3000) -> tuple[list[Market], dict[str, str]]:
    markets: list[Market] = []
    errors: dict[str, str] = {}
    with httpx.Client(follow_redirects=True) as client:
        for name, function in (("Kalshi", collect_kalshi), ("Polymarket", collect_polymarket)):
            try:
                markets.extend(function(client, max_per_platform))
            except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
                errors[name] = f"{type(exc).__name__}: {exc}"
    return markets, errors


def quote_poly_books(client: httpx.Client, markets: list[Market], max_markets: int = 75) -> tuple[list[Market], list[str]]:
    """Validate BOTH token books for at most max_markets evidence-supported markets.
    No order endpoints. Unavailable books remain ineligible for recommendations.
    """
    refreshed, warnings = [], []
    for m in markets[:max_markets]:
        if m.platform != "Polymarket" or not (m.token_a and m.token_b):
            refreshed.append(m)
            continue
        quotes = []
        try:
            for token in (m.token_a, m.token_b):
                book = request_json(client, CLOB + "/book", {"token_id": token})
                asks = [(fraction(x.get("price")), number(x.get("size"))) for x in book.get("asks", [])]
                bids = [fraction(x.get("price")) for x in book.get("bids", [])]
                asks = [(p, s) for p, s in asks if p is not None and s is not None and s > 0]
                bids = [p for p in bids if p is not None]
                quotes.append((min(asks, key=lambda x: x[0]) if asks else (None, None),
                               max(bids) if bids else None))
            refreshed.append(replace(m, ask_a=quotes[0][0][0], ask_size_a=quotes[0][0][1],
                                     bid_a=quotes[0][1], ask_b=quotes[1][0][0],
                                     ask_size_b=quotes[1][0][1], bid_b=quotes[1][1],
                                     quote_status="orderbook"))
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            warnings.append(f"{m.market_id}: quote unavailable ({type(exc).__name__})")
            refreshed.append(m)
    refreshed.extend(markets[max_markets:])
    return refreshed, warnings


def american_to_probability(odds: float) -> float:
    if odds == 0:
        raise ValueError("American odds cannot be zero")
    return -odds / (-odds + 100) if odds < 0 else 100 / (odds + 100)


def devig_power(odds_a: float, odds_b: float) -> float:
    """First-outcome fair probability after power-method de-vig."""
    x, y = american_to_probability(odds_a), american_to_probability(odds_b)
    lo, hi = 0.01, 10.0
    for _ in range(90):
        mid = (lo + hi) / 2
        if x ** mid + y ** mid > 1:
            lo = mid
        else:
            hi = mid
    return x ** ((lo + hi) / 2)


def _records(source: Any) -> Iterable[dict]:
    if source is None:
        return []
    if hasattr(source, "read"):
        source.seek(0)
        return csv.DictReader(source)
    if isinstance(source, (str, Path)) and Path(source).is_file():
        with open(source, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    return []


def load_evidence(forecasts: Any = None, sportsbooks: Any = None) -> dict[tuple[str, str], dict]:
    """Evidence requires exact external market IDs, source URL and ISO timestamp.
    No automatic inference of fair value from another prediction market.
    """
    result: dict[tuple[str, str], dict] = {}
    for row in _records(sportsbooks):
        try:
            key = (row["platform"].strip().lower(), row["market_id"].strip())
            probability = devig_power(float(row["odds_a"]), float(row["odds_b"]))
            payload = {"probability_a": probability, "source_url": row["source_url"].strip(),
                       "as_of": row["as_of"].strip(), "method": "Sportsbook power de-vig",
                       "notes": row.get("notes", "")}
            if valid_evidence(payload):
                result[key] = payload
        except (KeyError, ValueError, TypeError, AttributeError):
            continue
    for row in _records(forecasts):
        try:
            key = (row["platform"].strip().lower(), row["market_id"].strip())
            payload = {"probability_a": float(row["probability_a"]),
                       "source_url": row["source_url"].strip(), "as_of": row["as_of"].strip(),
                       "method": row.get("method") or "External estimate",
                       "notes": row.get("notes", "")}
            if valid_evidence(payload):
                result[key] = payload
        except (KeyError, ValueError, TypeError, AttributeError):
            continue
    return result


def valid_evidence(e: dict, max_age_hours: int = 48) -> bool:
    p = number(e.get("probability_a"))
    timestamp = parse_date(e.get("as_of"))
    age = (now_utc() - timestamp).total_seconds() / 3600 if timestamp else -1
    return (p is not None and 0 < p < 1 and bool(re.match(r"^https?://", str(e.get("source_url") or "")))
            and 0 <= age <= max_age_hours)


def fee_estimate(platform: str, price: float) -> float:
    """Conservative illustrative taker fee per contract, NOT a live fee quote.
    Product-specific exceptions and rounding can differ; final trade fees must be checked.
    """
    raw = 0.07 * price * (1 - price)
    return math.ceil(raw * 100 - 1e-12) / 100 if platform == "Kalshi" else raw


def score(markets: list[Market], evidence: dict, minimum_probability: float = 0.55,
          minimum_edge: float = 0.05, maximum_days: int = 30,
          slippage: float = 0.01) -> list[dict]:
    picks: list[dict] = []
    for m in markets:
        e = evidence.get(m.key)
        if not e or not valid_evidence(e):
            continue
        days = m.days_left
        if days is None or days < 0 or days > maximum_days:
            continue
        if m.platform == "Polymarket" and (m.quote_status != "orderbook" or m.liquidity < 1000):
            continue
        if m.platform == "Kalshi" and (m.quote_status != "feed" or m.volume < 100):
            continue
        p_a = e["probability_a"]
        for outcome, label, price, bid, depth, p in (
            ("A", m.outcome_a, m.ask_a, m.bid_a, m.ask_size_a, p_a),
            ("B", m.outcome_b, m.ask_b, m.bid_b, m.ask_size_b, 1 - p_a),
        ):
            if price is None or not (0 < price < 1) or p < minimum_probability:
                continue
            # Missing order depth on Kalshi is not treated as verified liquidity.
            if depth is None or depth < 10 or bid is None or price - bid > 0.08 or price < bid:
                continue
            fee = fee_estimate(m.platform, price)
            edge = p - price - fee - slippage
            if edge < minimum_edge:
                continue
            picks.append({
                "platform": m.platform, "market_id": m.market_id, "market": m.title,
                "outcome": label, "outcome_index": outcome, "estimated_probability": p,
                "buy_ask": price, "estimated_fee": fee, "slippage_buffer": slippage,
                "net_edge": edge, "expected_roi": edge / (price + fee + slippage),
                "days_to_market_close": round(days, 2), "ask_depth_shares": depth,
                "volume": m.volume, "liquidity": m.liquidity,
                "estimate_source": e["source_url"], "estimate_method": e["method"],
                "evidence_as_of": e["as_of"], "url": m.url,
                "warning": "Indicative EV only; verify market rules, quote freshness, execution and fees",
            })
    return sorted(picks, key=lambda r: (r["net_edge"], r["estimated_probability"]), reverse=True)


def matching_candidates(markets: list[Market]) -> list[dict]:
    """Strict title+close-date pairs for HUMAN review, never certified arbitrage."""
    def normalized(title: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", title.lower())).strip()
    groups: dict[tuple, dict[str, list[Market]]] = defaultdict(lambda: defaultdict(list))
    for m in markets:
        date = parse_date(m.close_at)
        if date:
            groups[(normalized(m.title), date.date().isoformat())][m.platform].append(m)
    matches: list[dict] = []
    for (title, date), sites in groups.items():
        if "Kalshi" in sites and "Polymarket" in sites:
            for a in sites["Kalshi"][:3]:
                for b in sites["Polymarket"][:3]:
                    matches.append({"title": title, "close_date": date, "kalshi": a.market_id,
                                    "polymarket": b.market_id, "review_required": True})
    return matches


def backtest(rows: Iterable[dict]) -> dict:
    """Backtest external fair probabilities against resolved outcomes, without look-ahead."""
    results, bins = [], defaultdict(list)
    for row in rows:
        try:
            p, cost, fee, slip = (float(row[k]) for k in ("probability_a", "paid_price", "fee", "slippage"))
            y = int(row["settled_a"])
            if not (0 < p < 1 and 0 < cost < 1 and y in (0, 1) and fee >= 0 and slip >= 0):
                continue
        except (KeyError, ValueError, TypeError):
            continue
        results.append({"brier": (p-y)**2, "expected": p-cost-fee-slip, "realized": y-cost-fee-slip})
        bins[min(9, int(p*10))].append((p, y))
    n = len(results)
    return {"samples": n,
            "brier": sum(x["brier"] for x in results)/n if n else None,
            "expected_profit_per_contract": sum(x["expected"] for x in results)/n if n else None,
            "realized_profit_per_contract": sum(x["realized"] for x in results)/n if n else None,
            "calibration": [{"forecast": sum(p for p,_ in v)/len(v),
                             "observed": sum(y for _,y in v)/len(v), "count": len(v)}
                            for _,v in sorted(bins.items())]}


def cli() -> None:
    parser = argparse.ArgumentParser(description="Rosie read-only market intelligence")
    parser.add_argument("command", choices=["scan", "backtest"])
    parser.add_argument("--limit", type=int, default=3000, help="Maximum normalized markets per platform")
    parser.add_argument("--forecasts", default="data/forecasts.csv")
    parser.add_argument("--sportsbooks", default="data/sportsbooks.csv")
    parser.add_argument("--file", default="data/backtest.csv")
    args = parser.parse_args()
    if args.command == "backtest":
        print(json.dumps(backtest(_records(args.file)), indent=2))
        return
    markets, errors = collect_all(max(1, min(args.limit, 10000)))
    evidence = load_evidence(args.forecasts, args.sportsbooks)
    validated = [m for m in markets if m.platform == "Polymarket" and m.key in evidence]
    with httpx.Client(follow_redirects=True) as client:
        quotes, warnings = quote_poly_books(client, validated)
    updates = {m.key: m for m in quotes}
    markets = [updates.get(m.key, m) for m in markets]
    picks = score(markets, evidence)
    payload = {"scanned_at": now_utc().isoformat(), "market_count": len(markets),
               "platform_errors": errors, "quote_warnings": warnings,
               "evidence_count": len(evidence), "opportunities": picks,
               "match_review_candidates": matching_candidates(markets)}
    Path("rosie_scan.json").write_text(json.dumps(payload, indent=2))
    print(json.dumps({"market_count": len(markets), "errors": errors,
                      "opportunity_count": len(picks), "output": "rosie_scan.json"}, indent=2))


if __name__ == "__main__":
    cli()
