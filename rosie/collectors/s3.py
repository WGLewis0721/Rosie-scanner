import boto3
from datetime import datetime, timezone

def collect(region: str, account_id: str) -> list[dict]:
    client = boto3.client("s3", region_name=region)
    resources = []
    buckets = client.list_buckets().get("Buckets", [])
    for bucket in buckets:
        name = bucket["Name"]
        tags = {}
        bucket_region = region
        public_access = {}
        try:
            loc = client.get_bucket_location(Bucket=name)
            bucket_region = loc.get("LocationConstraint") or "us-east-1"
        except Exception:
            pass
        try:
            tag_resp = client.get_bucket_tagging(Bucket=name)
            tags = {t["Key"]: t["Value"] for t in tag_resp.get("TagSet", [])}
        except Exception:
            pass
        try:
            pa = client.get_public_access_block(Bucket=name)
            public_access = pa.get("PublicAccessBlockConfiguration", {})
        except Exception:
            pass
        resources.append({
            "resource_id": name,
            "resource_type": "s3:bucket",
            "name": name,
            "region": bucket_region,
            "account_id": account_id,
            "details": {
                "creation_date": bucket.get("CreationDate", "").isoformat() if bucket.get("CreationDate") else None,
                "public_access_block": public_access,
            },
            "tags": tags,
            "collected_at": datetime.now(timezone.utc).isoformat(),
        })
    return resources
