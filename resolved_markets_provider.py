"""Optional on-demand read-only Resolved Markets provider (https://resolvedmarkets.com).

Do not equate closed with resolved or historical prices with pregame quotes.
Sports data requires a sports-enabled Resolved Markets subscription.
API credentials stay only in process environment; never committed or logged.
"""
import json
import os
import re
from pathlib import Path
from urllib.parse import quote

import httpx

BASE="https://api.resolvedmarkets.com"
MARKET_ID=re.compile(r"^0x[0-9a-fA-F]{64}$")


def _client(key=None):
    key=key or os.environ.get("RESOLVED_MARKETS_API_KEY", "")
    if not key:
        raise RuntimeError("RESOLVED_MARKETS_API_KEY is not set; optional provider skipped")
    return httpx.Client(timeout=20,follow_redirects=True,
                        headers={"X-API-Key":key,"Accept":"application/json"})


def _get(client,path,params=None):
    result=client.get(BASE+path,params=params)
    result.raise_for_status()
    return result.json()


def resolved_nba(limit=100, key=None):
    """Download real NBA-resolution metadata, not training features.

    Only accept records explicitly marked resolved with a winning outcome label.
    The same event may contain multiple related contracts; use neg_risk_id/event
    to deduplicate and do not treat each leg as independent evidence.
    """
    limit=max(1,min(1000,int(limit)))
    with _client(key) as client:
        response=_get(client,"/v1/markets/metadata",{
            "category":"sports","subcategory":"NBA","resolution_status":"resolved",
            "group_by_event":"true","limit":limit})
    events=response.get("events",[]) if isinstance(response,dict) else []
    seen=set()
    rows=[]
    for event in events:
        if not isinstance(event,dict):
            continue
        for leg in event.get("legs",[]):
            if not isinstance(leg,dict):
                continue
            market_id=leg.get("market_id")
            if (not isinstance(market_id,str) or not MARKET_ID.fullmatch(market_id)
                or market_id in seen or leg.get("resolution_status")!="resolved"
                or not leg.get("resolved_outcome")):
                continue
            seen.add(market_id)
            rows.append({"market_id":market_id,"event_id":event.get("neg_risk_id"),
                 "event_title":event.get("event_title"),
                 "category":event.get("category"),"subcategory":event.get("subcategory"),
                 "question":leg.get("question"),"outcomes":leg.get("outcomes"),
                 "resolved_outcome":leg.get("resolved_outcome"),
                 "resolved_at":leg.get("resolved_at"),
                 "end_date":event.get("end_date"),
                 "source_url":f"https://resolvedmarkets.com/",
                 "verification":"provider_explicit_resolved"})
    return {"provider":"Resolved Markets","category":"NBA","count":len(rows),
            "markets":rows,
            "warning":"Settled outcomes are not independent probability forecasts or historical executable asks."}


def historical_snapshots(market_id, from_utc=None, to_utc=None, limit=500, key=None):
    """Fetch a bounded recorded quote sample for time-aware backtesting.

    Caller must compare each UTC snapshot timestamp to the *pregame* decision time.
    Data from after the pick/game start must never leak into forecast features.
    """
    if not MARKET_ID.fullmatch(str(market_id)):
        raise ValueError("Expected a 0x-prefixed 64-hex-character condition ID")
    limit=max(1,min(500,int(limit)))
    params={"limit":limit,"offset":0,"include_book":"false","order":"asc"}
    if from_utc: params["from"]=from_utc
    if to_utc: params["to"]=to_utc
    if not from_utc or not to_utc:
        raise ValueError("Both UTC bounds are required to avoid accidental whole-life queries")
    with _client(key) as client:
        data=_get(client,f"/v1/markets/{quote(market_id,safe='')}/snapshots",params)
    return {"provider":"Resolved Markets","market_id":market_id,
            "time_bounds":{"from":from_utc,"to":to_utc},
            "data":data.get("data",[]) if isinstance(data,dict) else [],
            "total":data.get("total") if isinstance(data,dict) else None,
            "warning":"Check each event timestamp: never use post-tipoff quotes for pregame predictions."}


def write_json(path,object_):
    target=Path(path)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(object_,indent=2),encoding="utf-8")
    return str(target)
