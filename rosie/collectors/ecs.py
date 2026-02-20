import boto3
from datetime import datetime, timezone

def collect(region: str, account_id: str) -> list[dict]:
    client = boto3.client("ecs", region_name=region)
    resources = []
    cluster_arns = []
    paginator = client.get_paginator("list_clusters")
    for page in paginator.paginate():
        cluster_arns.extend(page["clusterArns"])
    if not cluster_arns:
        return resources
    clusters = client.describe_clusters(clusters=cluster_arns, include=["TAGS"]).get("clusters", [])
    for cluster in clusters:
        tags = {t["key"]: t["value"] for t in cluster.get("tags", [])}
        resources.append({
            "resource_id": cluster["clusterArn"],
            "resource_type": "ecs:cluster",
            "name": cluster["clusterName"],
            "region": region,
            "account_id": account_id,
            "details": {
                "status": cluster.get("status"),
                "running_tasks_count": cluster.get("runningTasksCount", 0),
                "pending_tasks_count": cluster.get("pendingTasksCount", 0),
                "active_services_count": cluster.get("activeServicesCount", 0),
                "registered_container_instances_count": cluster.get("registeredContainerInstancesCount", 0),
            },
            "tags": tags,
            "collected_at": datetime.now(timezone.utc).isoformat(),
        })
    return resources
