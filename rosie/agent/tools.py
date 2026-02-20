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
    """List SSM managed instances that have not had active agent communication (last ping) within the given number of days."""
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

@tool
def summarize_network_topology() -> str:
    """Return a high-level summary of the network topology including VPCs, subnets, security groups, NACLs, route tables, gateways, TGW attachments, peering connections, and VPC endpoints."""
    resources = _get_resources()
    network_types = [
        "ec2:vpc", "ec2:subnet", "ec2:security_group", "ec2:nacl",
        "ec2:route_table", "ec2:internet_gateway", "ec2:nat_gateway",
        "ec2:transit_gateway", "ec2:tgw_attachment", "ec2:vpc_peering",
        "ec2:vpc_endpoint",
    ]
    counts: dict[str, int] = {}
    for r in resources:
        rt = r.get("resource_type", "")
        if rt in network_types:
            counts[rt] = counts.get(rt, 0) + 1
    if not counts:
        return "No network resources found. Run collector first."
    lines = [f"  {k}: {v}" for k, v in sorted(counts.items())]
    return "Network topology summary:\n" + "\n".join(lines)

@tool
def describe_vpc_layout(vpc_id: str) -> str:
    """Describe the layout of a specific VPC including its subnets, route tables, internet gateways, NAT gateways, NACLs, and security groups."""
    resources = _get_resources()

    def get_by_type_and_vpc(resource_type: str) -> list[dict]:
        return [
            r for r in resources
            if r.get("resource_type") == resource_type
            and r.get("details", {}).get("vpc_id") == vpc_id
        ]

    vpc_resources = [r for r in resources if r.get("resource_id") == vpc_id]
    if not vpc_resources:
        return f"VPC '{vpc_id}' not found in inventory."

    result = {
        "vpc": vpc_resources[0],
        "subnets": get_by_type_and_vpc("ec2:subnet"),
        "route_tables": get_by_type_and_vpc("ec2:route_table"),
        "nacls": get_by_type_and_vpc("ec2:nacl"),
        "security_groups": get_by_type_and_vpc("ec2:security_group"),
        "nat_gateways": get_by_type_and_vpc("ec2:nat_gateway"),
        "internet_gateways": [
            r for r in resources
            if r.get("resource_type") == "ec2:internet_gateway"
            and any(a.get("vpc_id") == vpc_id for a in r.get("details", {}).get("attached_vpcs", []))
        ],
        "vpc_endpoints": get_by_type_and_vpc("ec2:vpc_endpoint"),
    }
    return json.dumps(result, indent=2, default=str)

@tool
def list_security_group_rules(security_group_id: str) -> str:
    """List all ingress and egress rules for a specific security group by its ID."""
    resources = _get_resources()
    for r in resources:
        if r.get("resource_type") == "ec2:security_group" and r.get("resource_id") == security_group_id:
            details = r.get("details", {})
            return json.dumps({
                "security_group_id": security_group_id,
                "name": r.get("name"),
                "vpc_id": details.get("vpc_id"),
                "description": details.get("description"),
                "ingress_rules": details.get("ingress_rules", []),
                "egress_rules": details.get("egress_rules", []),
            }, indent=2, default=str)
    return f"Security group '{security_group_id}' not found."

@tool
def list_tgw_attachments(transit_gateway_id: str = "") -> str:
    """List Transit Gateway attachments, optionally filtered by a specific transit gateway ID."""
    resources = _get_resources()
    attachments = [r for r in resources if r.get("resource_type") == "ec2:tgw_attachment"]
    if transit_gateway_id:
        attachments = [
            a for a in attachments
            if a.get("details", {}).get("transit_gateway_id") == transit_gateway_id
        ]
    if not attachments:
        msg = f"No TGW attachments found for transit gateway '{transit_gateway_id}'." if transit_gateway_id else "No TGW attachments found."
        return msg
    return json.dumps(attachments, indent=2, default=str)

TOOLS = [
    list_resources_by_type,
    get_resource_by_id,
    search_resources,
    filter_by_region,
    get_inventory_summary,
    list_unpatched_instances,
    summarize_network_topology,
    describe_vpc_layout,
    list_security_group_rules,
    list_tgw_attachments,
]
