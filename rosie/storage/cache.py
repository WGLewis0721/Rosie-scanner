import json
import os
from datetime import datetime, timezone
from pathlib import Path

CACHE_DIR = Path(os.getenv("ROSIE_CACHE_DIR", "/tmp/rosie_cache"))

def save(resources: list[dict]) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = CACHE_DIR / f"inventory_{ts}.json"
    path.write_text(json.dumps(resources, indent=2, default=str))
    latest = CACHE_DIR / "inventory_latest.json"
    latest.write_text(json.dumps(resources, indent=2, default=str))
    return path

def load() -> list[dict]:
    latest = CACHE_DIR / "inventory_latest.json"
    if not latest.exists():
        return []
    return json.loads(latest.read_text())
