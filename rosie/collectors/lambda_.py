import boto3
from datetime import datetime, timezone

def collect(region: str, account_id: str) -> list[dict]:
    client = boto3.client("lambda", region_name=region)
    resources = []
    paginator = client.get_paginator("list_functions")
    for page in paginator.paginate():
        for fn in page["Functions"]:
            tags = {}
            try:
                tags = client.list_tags(Resource=fn["FunctionArn"]).get("Tags", {})
            except Exception:
                pass
            resources.append({
                "resource_id": fn["FunctionArn"],
                "resource_type": "lambda:function",
                "name": fn["FunctionName"],
                "region": region,
                "account_id": account_id,
                "details": {
                    "runtime": fn.get("Runtime"),
                    "handler": fn.get("Handler"),
                    "memory_size": fn.get("MemorySize"),
                    "timeout": fn.get("Timeout"),
                    "last_modified": fn.get("LastModified"),
                    "code_size": fn.get("CodeSize"),
                    "description": fn.get("Description", ""),
                    "role": fn.get("Role"),
                },
                "tags": tags,
                "collected_at": datetime.now(timezone.utc).isoformat(),
            })
    return resources
