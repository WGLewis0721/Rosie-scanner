import csv
import io
from datetime import timedelta

from market_scan import (
    Market, american_to_probability, backtest, devig_power, fee_estimate,
    load_evidence, matching_candidates, normalize_kalshi, normalize_poly,
    now_utc, quote_poly_books, score, collect_kalshi, collect_polymarket,
)


def future():
    return (now_utc() + timedelta(days=3)).isoformat()


def evidence(market, prob=0.75):
    return {market.key: {"probability_a": prob, "source_url": "https://example.org/research",
            "as_of": now_utc().isoformat(), "method": "Independent", "notes": ""}}


def sample(platform="Kalshi"):
    return Market(platform, "ABC", "Will team A win?", "Team A", "Team B",
        future(), "https://example.org", volume=500, liquidity=5000,
        ask_a=0.60, ask_b=0.43, bid_a=0.59, bid_b=0.41,
        ask_size_a=50, ask_size_b=50, quote_status="feed" if platform == "Kalshi" else "orderbook")


def test_normalize_kalshi_dollar_and_cent_prices():
    m = normalize_kalshi({"ticker": "ABC", "title": "Event", "status": "open",
        "close_time": future(), "yes_ask_dollars": "0.6000",
        "no_ask": 41, "volume_fp": "250"})
    assert m.ask_a == 0.6
    assert m.ask_b == 0.41
    assert m.volume == 250



def test_kalshi_active_status_from_live_public_api():
    m = normalize_kalshi({"ticker": "KXACTIVE", "title": "Active event",
        "status": "active", "close_time": future(),
        "yes_ask_dollars": "0.6300", "no_ask_dollars": "0.3900",
        "yes_ask_size_fp": "30", "no_ask_size_fp": "30"})
    assert m is not None
    assert m.ask_a == .63
    assert m.ask_size_a == 30


def test_poly_indicative_not_verified():
    m = normalize_poly({"id": "99", "slug": "test-event", "question": "Will X?",
        "active": True, "closed": False, "endDate": future(),
        "outcomes": '["Yes", "No"]', "outcomePrices": '["0.7", "0.3"]',
        "clobTokenIds": '["t1", "t2"]'})
    assert m.indicative_a == 0.7 and m.ask_a is None
    assert score([m], evidence(m, 0.85)) == []


def test_poly_missing_or_empty_events_safe():
    for events in ([], None):
        m = normalize_poly({"id": "99", "slug": "event-title", "events": events,
            "question": "Will X?", "active": True, "closed": False,
            "endDate": future(), "outcomes": '["Yes","No"]',
            "clobTokenIds": '["t1","t2"]'})
        assert m is not None
        assert m.url.endswith("/event/event-title")


def test_score_uses_independent_evidence_and_actual_ask():
    m = sample()
    assert score([m], {}) == []
    picks = score([m], evidence(m))
    assert len(picks) == 1 and picks[0]["outcome"] == "Team A"
    assert abs(picks[0]["net_edge"] - (0.75 - 0.60 - 0.02 - 0.01)) < 0.00001


def test_high_odds_at_bad_price_not_a_pick():
    m = sample()
    m.ask_a = 0.92
    m.bid_a = 0.91
    assert score([m], evidence(m, 0.80)) == []


def test_quote_requires_size_and_spread():
    m = sample()
    m.ask_size_a = 2
    assert score([m], evidence(m)) == []
    m.ask_size_a = 50
    m.bid_a = .40
    assert score([m], evidence(m)) == []


def test_poly_needs_verified_orderbook_and_liquidity():
    m = sample("Polymarket")
    assert score([m], evidence(m))
    m.quote_status = "indicative"
    assert score([m], evidence(m)) == []
    m.quote_status = "orderbook"
    m.liquidity = 25
    assert score([m], evidence(m)) == []


def test_stale_or_unattributed_forecast_rejected():
    m = sample()
    stale = (now_utc() - timedelta(days=6)).isoformat()
    blob = f"platform,market_id,probability_a,source_url,as_of,method\nKalshi,ABC,.8,https://example.org,{stale},test\n"
    assert load_evidence(io.StringIO(blob)) == {}
    blob = f"platform,market_id,probability_a,source_url,as_of,method\nKalshi,ABC,.8,https://example.org,{now_utc().isoformat()},test\n"
    assert load_evidence(io.StringIO(blob))[m.key]["probability_a"] == .8


def test_power_devig_and_fee():
    assert american_to_probability(-110) > .52
    assert abs(devig_power(-110, -110) - .5) < .00001
    assert fee_estimate("Kalshi", .6) == .02
    assert 0 < fee_estimate("Polymarket", .6) < .02


def test_backtest_calibration_and_realized_profit():
    rows = [{"probability_a": ".8", "paid_price": ".7", "fee": ".01",
             "slippage": ".01", "settled_a": "1"}]
    result = backtest(rows)
    assert result["samples"] == 1
    assert abs(result["realized_profit_per_contract"] - .28) < 1e-9
    assert result["calibration"][0]["observed"] == 1


def test_matches_are_manual_review_only():
    a = sample()
    b = sample("Polymarket")
    pair = matching_candidates([a, b])
    assert len(pair) == 1 and pair[0]["review_required"] is True


def test_read_only_collection_pages():
    class Client:
        def __init__(self):
            self.calls = []
        def get(self, url, params=None, headers=None, timeout=None):
            self.calls.append((url, params))
            class Response:
                status_code = 200
                headers = {}
                def raise_for_status(self):
                    pass
                def json(self):
                    return {"markets": [{"ticker": "ABC", "status": "open",
                            "close_time": future()}], "cursor": ""}
            return Response()
    client = Client()
    assert len(collect_kalshi(client, 10)) == 1
    assert len(client.calls) == 1
    assert client.calls[0][1]["status"] == "open"


def test_clob_reads_both_token_books():
    m = sample("Polymarket")
    m.token_a, m.token_b = "first", "second"
    m.quote_status = "indicative"
    class Client:
        def get(self, url, params=None, headers=None, timeout=None):
            assert url.endswith("/book")
            class Response:
                status_code = 200
                headers = {}
                def raise_for_status(self):
                    pass
                def json(self):
                    return {"asks": [{"price": ".60", "size": "45"}],
                            "bids": [{"price": ".59", "size": "100"}]}
            return Response()
    updated, errors = quote_poly_books(Client(), [m])
    assert not errors and updated[0].quote_status == "orderbook"
    assert updated[0].ask_size_a == 45


def test_polymarket_collection_uses_keyset_beyond_gamma_offset_cap():
    # Gamma /markets rejects offset > 2000 with HTTP 422; deep scans need /markets/keyset.
    from datetime import timedelta
    closes = (now_utc() + timedelta(days=3)).isoformat()
    calls = []

    def row(i):
        return {"id": str(i), "slug": f"m{i}", "question": f"Q{i}",
                "outcomes": '["Yes","No"]', "outcomePrices": '["0.5","0.5"]',
                "clobTokenIds": '["a%d","b%d"]' % (i, i), "endDate": closes,
                "active": True, "closed": False}

    class Client:
        def get(self, url, params=None, headers=None, timeout=None):
            calls.append((url, dict(params or {})))
            assert "offset" not in (params or {}), "offset pagination hits the 2000 cap"
            page = len(calls)
            class Response:
                status_code = 200
                headers = {}
                def raise_for_status(self):
                    pass
                def json(self_inner):
                    return {"markets": [row(page * 1000 + k) for k in range(100)],
                            "next_cursor": f"c{page}"}
            return Response()

    out = collect_polymarket(Client(), 250)
    assert len(out) == 250
    assert all(url.endswith("/markets/keyset") for url, _ in calls)
    assert calls[1][1]["after_cursor"] == "c1"
