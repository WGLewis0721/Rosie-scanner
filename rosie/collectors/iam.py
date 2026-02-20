import boto3
from datetime import datetime, timezone

def collect(region: str, account_id: str) -> list[dict]:
    client = boto3.client("iam")
    resources = []
    paginator = client.get_paginator("list_roles")
    for page in paginator.paginate():
        for role in page["Roles"]:
            tags = {}
            try:
                tag_resp = client.list_role_tags(RoleName=role["RoleName"])
                tags = {t["Key"]: t["Value"] for t in tag_resp.get("Tags", [])}
            except Exception:
                pass
            resources.append({
                "resource_id": role["RoleId"],
                "resource_type": "iam:role",
                "name": role["RoleName"],
                "region": "global",
                "account_id": account_id,
                "details": {
                    "arn": role.get("Arn"),
                    "path": role.get("Path"),
                    "create_date": role.get("CreateDate", "").isoformat() if role.get("CreateDate") else None,
                    "description": role.get("Description", ""),
                    "max_session_duration": role.get("MaxSessionDuration"),
                },
                "tags": tags,
                "collected_at": datetime.now(timezone.utc).isoformat(),
            })
    return resources
