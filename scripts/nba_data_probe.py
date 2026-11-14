"""Inspect public ESPN NBA scoreboard odds; no secrets, no trading."""
import json
import httpx
from market_scan import request_json
from datetime import datetime
with httpx.Client(timeout=20) as c:
    data=request_json(c,"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard",{"dates":"20261114"})
for item in data.get("events",[]):
    comp=(item.get("competitions") or [{}])[0]
    teams=[{"team": x.get("team",{}).get("displayName"),"abbreviation": x.get("team",{}).get("abbreviation"),"homeAway":x.get("homeAway")} for x in comp.get("competitors",[])]
    odds=comp.get("odds",[])
    print(json.dumps({"id":item.get("id"),"date":item.get("date"),"teams":teams,
        "odds":odds[:2],"odds_count":len(odds)}, default=str)[:3500],flush=True)
