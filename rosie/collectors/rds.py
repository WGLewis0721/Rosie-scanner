import boto3
from datetime import datetime, timezone

def collect(region: str, account_id: str) -> list[dict]:
    client = boto3.client("rds", region_name=region)
    resources = []
    paginator = client.get_paginator("describe_db_instances")
    for page in paginator.paginate():
        for db in page["DBInstances"]:
            tags = {t["Key"]: t["Value"] for t in db.get("TagList", [])}
            resources.append({
                "resource_id": db["DBInstanceIdentifier"],
                "resource_type": "rds:db",
                "name": db["DBInstanceIdentifier"],
                "region": region,
                "account_id": account_id,
                "details": {
                    "engine": db.get("Engine"),
                    "engine_version": db.get("EngineVersion"),
                    "instance_class": db.get("DBInstanceClass"),
                    "status": db.get("DBInstanceStatus"),
                    "endpoint": db.get("Endpoint", {}).get("Address"),
                    "port": db.get("Endpoint", {}).get("Port"),
                    "publicly_accessible": db.get("PubliclyAccessible", False),
                    "multi_az": db.get("MultiAZ", False),
                    "storage_encrypted": db.get("StorageEncrypted", False),
                    "vpc_id": db.get("DBSubnetGroup", {}).get("VpcId"),
                },
                "tags": tags,
                "collected_at": datetime.now(timezone.utc).isoformat(),
            })
    return resources
