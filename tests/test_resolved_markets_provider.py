"""Fixture-only Resolved Markets provenance tests; no paid API calls."""
import pytest
import resolved_markets_provider as rm


def test_missing_key_fails_closed(monkeypatch):
    monkeypatch.delenv("RESOLVED_MARKETS_API_KEY",raising=False)
    with pytest.raises(RuntimeError,match="RESOLVED_MARKETS_API_KEY"):
        rm.resolved_nba()


def test_requires_explicit_settlement(monkeypatch):
    class Client:
        def __enter__(self): return self
        def __exit__(self,*args): return False
    monkeypatch.setattr(rm,"_client",lambda key=None:Client())
    market="0x"+"a"*64
    monkeypatch.setattr(rm,"_get",lambda client,path,params:{
        "events":[{"neg_risk_id":"event1","category":"sports","subcategory":"NBA",
          "legs":[
            {"market_id":market,"resolution_status":"resolved","resolved_outcome":"Yes"},
            {"market_id":market,"resolution_status":"resolved","resolved_outcome":"Yes"},
            {"market_id":"0x"+"b"*64,"resolution_status":"unresolved","resolved_outcome":None}
          ]}]
    })
    out=rm.resolved_nba()
    assert out["count"]==1
    assert out["markets"][0]["event_id"]=="event1"


def test_snapshot_rejects_unbounded_and_bad_ids():
    with pytest.raises(ValueError):
        rm.historical_snapshots("garbage","2026-11-01","2026-11-02")
    with pytest.raises(ValueError):
        rm.historical_snapshots("0x"+"a"*64,from_utc="2026-11-01")
