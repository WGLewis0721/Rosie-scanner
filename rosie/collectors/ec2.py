import boto3
from datetime import datetime, timezone

def collect(region: str, account_id: str) -> list[dict]:
    client = boto3.client("ec2", region_name=region)
    resources = []
    paginator = client.get_paginator("describe_instances")
    for page in paginator.paginate():
        for reservation in page["Reservations"]:
            for inst in reservation["Instances"]:
                tags = {t["Key"]: t["Value"] for t in inst.get("Tags", [])}
                resources.append({
                    "resource_id": inst["InstanceId"],
                    "resource_type": "ec2:instance",
                    "name": tags.get("Name", inst["InstanceId"]),
                    "region": region,
                    "account_id": account_id,
                    "details": {
                        "instance_type": inst.get("InstanceType"),
                        "state": inst.get("State", {}).get("Name"),
                        "platform": inst.get("Platform", "linux"),
                        "private_ip": inst.get("PrivateIpAddress"),
                        "public_ip": inst.get("PublicIpAddress"),
                        "security_groups": [sg["GroupId"] for sg in inst.get("SecurityGroups", [])],
                        "subnet_id": inst.get("SubnetId"),
                        "vpc_id": inst.get("VpcId"),
                        "image_id": inst.get("ImageId"),
                        "launch_time": inst.get("LaunchTime", "").isoformat() if inst.get("LaunchTime") else None,
                    },
                    "tags": tags,
                    "collected_at": datetime.now(timezone.utc).isoformat(),
                })
    return resources
