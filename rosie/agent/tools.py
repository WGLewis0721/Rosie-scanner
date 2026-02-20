import json
import logging
from langchain_core.tools import tool
from ..storage.cache import load as load_cache

logger = logging.getLogger(__name__)

def _get_resources() -> list[dict]:
    return load_cache()

@tool
def list_resources_by_type(resource_type: str) -> str:
    """List all resources of a given type (e.g. ec2:instance, rds:db, lambda:function, s3:bucket, iam:role, ssm:managed_instance, ecs:cluster)."""
    resources = _get_resources()
    matched = [r for r in resources if r.get("resource_type") == resource_type]
    if not matched:
        return f"No resources of type '{resource_type}' found."
    return json.dumps(matched[:50], indent=2, default=str)

@tool
def get_resource_by_id(resource_id: str) -> str:
    """Get details of a specific resource by its resource_id."""
    resources = _get_resources()
    for r in resources:
        if r.get("resource_id") == resource_id:
            return json.dumps(r, indent=2, default=str)
    return f"Resource '{resource_id}' not found."

@tool
def search_resources(query: str) -> str:
    """Search resources by keyword across name, type, tags, and details."""
    resources = _get_resources()
    query_lower = query.lower()
    matched = []
    for r in resources:
        text = json.dumps(r, default=str).lower()
        if query_lower in text:
            matched.append(r)
    if not matched:
        return f"No resources matched query: '{query}'"
    return json.dumps(matched[:50], indent=2, default=str)

@tool
def filter_by_region(region: str) -> str:
    """List all resources in a specific AWS region."""
    resources = _get_resources()
    matched = [r for r in resources if r.get("region") == region]
    if not matched:
        return f"No resources found in region '{region}'."
    return json.dumps(matched[:50], indent=2, default=str)

@tool
def get_inventory_summary() -> str:
    """Return a count summary of all resources by type."""
    resources = _get_resources()
    summary: dict[str, int] = {}
    for r in resources:
        rt = r.get("resource_type", "unknown")
        summary[rt] = summary.get(rt, 0) + 1
    if not summary:
        return "No inventory data available. Run collector first."
    lines = [f"  {k}: {v}" for k, v in sorted(summary.items())]
    return "Inventory summary:\n" + "\n".join(lines)

@tool
def list_unpatched_instances(days: int = 90) -> str:
    """List SSM managed instances that have not had a successful patch run in the given number of days."""
    from datetime import datetime, timezone, timedelta
    resources = _get_resources()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    unpatched = []
    for r in resources:
        if r.get("resource_type") != "ssm:managed_instance":
            continue
        last_ping = r.get("details", {}).get("last_ping_date_time")
        if last_ping:
            try:
                dt = datetime.fromisoformat(last_ping)
                if dt < cutoff:
                    unpatched.append(r)
            except Exception:
                unpatched.append(r)
        else:
            unpatched.append(r)
    if not unpatched:
        return f"All managed instances have been active within {days} days."
    return json.dumps(unpatched, indent=2, default=str)

TOOLS = [
    list_resources_by_type,
    get_resource_by_id,
    search_resources,
    filter_by_region,
    get_inventory_summary,
    list_unpatched_instances,
]
