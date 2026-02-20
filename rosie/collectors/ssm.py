import boto3
from datetime import datetime, timezone

def collect(region: str, account_id: str) -> list[dict]:
    client = boto3.client("ssm", region_name=region)
    resources = []
    paginator = client.get_paginator("describe_instance_information")
    for page in paginator.paginate():
        for info in page["InstanceInformationList"]:
            resources.append({
                "resource_id": info["InstanceId"],
                "resource_type": "ssm:managed_instance",
                "name": info.get("ComputerName", info["InstanceId"]),
                "region": region,
                "account_id": account_id,
                "details": {
                    "ping_status": info.get("PingStatus"),
                    "last_ping_date_time": info.get("LastPingDateTime", "").isoformat() if info.get("LastPingDateTime") else None,
                    "agent_version": info.get("AgentVersion"),
                    "platform_type": info.get("PlatformType"),
                    "platform_name": info.get("PlatformName"),
                    "platform_version": info.get("PlatformVersion"),
                    "association_status": info.get("AssociationStatus"),
                    "patch_group": info.get("AssociationOverview", {}).get("InstanceAssociationStatusAggregatedCount", {}),
                },
                "tags": {},
                "collected_at": datetime.now(timezone.utc).isoformat(),
            })
    return resources
