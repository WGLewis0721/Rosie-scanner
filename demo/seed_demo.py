#!/usr/bin/env python3
"""
Demo seeder for Rosie Scanner.

Creates a realistic set of dummy AWS resources inside a moto mock environment,
runs all Rosie collectors against them, and writes the resulting inventory to
the Rosie cache directory so the API and UI can answer questions immediately —
no real AWS account required.

Usage
-----
    python demo/seed_demo.py

Then start the stack and open the UI:
    docker compose up -d
    # Open http://localhost:8501
"""

import io
import os
import sys
import zipfile
import logging

# Ensure the repo root is on the path so `rosie` can be imported directly.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import boto3
from moto import mock_aws

from rosie.collectors.runner import run_all
from rosie.storage.cache import save as save_cache

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

REGION = "us-east-1"
ACCOUNT_ID = "123456789012"


def _make_lambda_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("index.py", "def handler(event, context): return {}")
    return buf.getvalue()


def _create_iam_role(iam, name: str, service: str = "lambda.amazonaws.com") -> str:
    role = iam.create_role(
        RoleName=name,
        AssumeRolePolicyDocument=(
            '{"Version":"2012-10-17","Statement":[{"Effect":"Allow",'
            f'"Principal":{{"Service":"{service}"}},'
            '"Action":"sts:AssumeRole"}]}'
        ),
        Description=f"Demo role for {name}",
    )
    return role["Role"]["Arn"]


@mock_aws
def seed() -> None:
    """Create dummy resources and persist them to the Rosie cache."""

    ec2 = boto3.client("ec2", region_name=REGION)
    rds = boto3.client("rds", region_name=REGION)
    lam = boto3.client("lambda", region_name=REGION)
    ecs = boto3.client("ecs", region_name=REGION)
    s3 = boto3.client("s3", region_name=REGION)
    iam = boto3.client("iam", region_name=REGION)

    # ------------------------------------------------------------------ #
    # EC2 Instances
    # ------------------------------------------------------------------ #
    log.info("Creating EC2 instances …")
    ec2_instances = [
        {"Name": "web-server-01",   "Type": "t3.medium",  "Env": "prod"},
        {"Name": "web-server-02",   "Type": "t3.medium",  "Env": "prod"},
        {"Name": "app-server-01",   "Type": "m5.large",   "Env": "prod"},
        {"Name": "app-server-02",   "Type": "m5.large",   "Env": "prod"},
        {"Name": "worker-01",       "Type": "c5.xlarge",  "Env": "prod"},
        {"Name": "bastion",         "Type": "t3.micro",   "Env": "prod"},
        {"Name": "staging-web-01",  "Type": "t3.small",   "Env": "staging"},
        {"Name": "staging-app-01",  "Type": "t3.small",   "Env": "staging"},
        {"Name": "dev-workstation", "Type": "t3.medium",  "Env": "dev"},
    ]
    for inst in ec2_instances:
        ec2.run_instances(
            ImageId="ami-0abcdef1234567890",
            MinCount=1,
            MaxCount=1,
            InstanceType=inst["Type"],
            TagSpecifications=[{
                "ResourceType": "instance",
                "Tags": [
                    {"Key": "Name",        "Value": inst["Name"]},
                    {"Key": "Environment", "Value": inst["Env"]},
                    {"Key": "Project",     "Value": "rosie-demo"},
                ],
            }],
        )

    # ------------------------------------------------------------------ #
    # RDS Databases
    # ------------------------------------------------------------------ #
    log.info("Creating RDS databases …")
    rds_instances = [
        {
            "id": "prod-postgres-01",
            "engine": "postgres",
            "version": "15.3",
            "cls": "db.r6g.large",
            "env": "prod",
            "public": False,
            "multi_az": True,
            "encrypted": True,
        },
        {
            "id": "prod-mysql-reports",
            "engine": "mysql",
            "version": "8.0.35",
            "cls": "db.t3.medium",
            "env": "prod",
            "public": False,
            "multi_az": False,
            "encrypted": True,
        },
        {
            "id": "staging-postgres-01",
            "engine": "postgres",
            "version": "14.9",
            "cls": "db.t3.micro",
            "env": "staging",
            "public": True,   # intentionally public for demo alert
            "multi_az": False,
            "encrypted": False,
        },
        {
            "id": "dev-mysql-01",
            "engine": "mysql",
            "version": "5.7.43",  # older version for demo
            "cls": "db.t3.micro",
            "env": "dev",
            "public": True,
            "multi_az": False,
            "encrypted": False,
        },
    ]
    for db in rds_instances:
        rds.create_db_instance(
            DBInstanceIdentifier=db["id"],
            DBInstanceClass=db["cls"],
            Engine=db["engine"],
            EngineVersion=db["version"],
            MasterUsername="admin",
            MasterUserPassword="DemoPassword1!",
            AllocatedStorage=20,
            PubliclyAccessible=db["public"],
            MultiAZ=db["multi_az"],
            StorageEncrypted=db["encrypted"],
            Tags=[
                {"Key": "Environment", "Value": db["env"]},
                {"Key": "Project",     "Value": "rosie-demo"},
            ],
        )

    # ------------------------------------------------------------------ #
    # IAM Roles (needed by Lambda functions below)
    # ------------------------------------------------------------------ #
    log.info("Creating IAM roles …")
    lambda_role_arn = _create_iam_role(iam, "demo-lambda-exec-role")
    _create_iam_role(iam, "demo-ecs-task-role",      "ecs-tasks.amazonaws.com")
    _create_iam_role(iam, "demo-ec2-instance-role",  "ec2.amazonaws.com")
    _create_iam_role(iam, "demo-rds-monitoring-role", "monitoring.rds.amazonaws.com")
    _create_iam_role(iam, "demo-data-pipeline-role",  "datapipeline.amazonaws.com")

    # ------------------------------------------------------------------ #
    # Lambda Functions
    # ------------------------------------------------------------------ #
    log.info("Creating Lambda functions …")
    zip_bytes = _make_lambda_zip()
    lambda_functions = [
        {"name": "api-authorizer",       "runtime": "python3.12", "desc": "API Gateway authorizer",          "env": "prod"},
        {"name": "user-notification",    "runtime": "python3.11", "desc": "Sends user notifications",        "env": "prod"},
        {"name": "data-sync",            "runtime": "nodejs18.x", "desc": "Syncs data between services",     "env": "prod"},
        {"name": "report-generator",     "runtime": "python3.9",  "desc": "Generates scheduled reports",     "env": "prod"},
        {"name": "legacy-processor",     "runtime": "python3.8",  "desc": "Legacy data processor",           "env": "prod"},  # deprecated runtime
        {"name": "old-etl-job",          "runtime": "nodejs16.x", "desc": "Old ETL pipeline",                "env": "prod"},  # deprecated runtime
        {"name": "staging-api-handler",  "runtime": "python3.11", "desc": "Staging API handler",             "env": "staging"},
        {"name": "dev-test-function",    "runtime": "python3.12", "desc": "Dev test function",               "env": "dev"},
    ]
    for fn in lambda_functions:
        lam.create_function(
            FunctionName=fn["name"],
            Runtime=fn["runtime"],
            Role=lambda_role_arn,
            Handler="index.handler",
            Code={"ZipFile": zip_bytes},
            Description=fn["desc"],
            Timeout=30,
            MemorySize=256,
            Tags={"Environment": fn["env"], "Project": "rosie-demo"},
        )

    # ------------------------------------------------------------------ #
    # ECS Clusters
    # ------------------------------------------------------------------ #
    log.info("Creating ECS clusters …")
    for cluster_name in ["prod-services", "staging-services", "dev-services"]:
        ecs.create_cluster(
            clusterName=cluster_name,
            tags=[
                {"key": "Environment", "value": cluster_name.split("-")[0]},
                {"key": "Project",     "value": "rosie-demo"},
            ],
        )

    # ------------------------------------------------------------------ #
    # S3 Buckets
    # ------------------------------------------------------------------ #
    log.info("Creating S3 buckets …")
    s3_buckets = [
        {"name": "rosie-demo-app-assets",      "env": "prod",    "public_block": True},
        {"name": "rosie-demo-user-uploads",    "env": "prod",    "public_block": True},
        {"name": "rosie-demo-data-exports",    "env": "prod",    "public_block": True},
        {"name": "rosie-demo-access-logs",     "env": "prod",    "public_block": True},
        {"name": "rosie-demo-staging-assets",  "env": "staging", "public_block": True},
        {"name": "rosie-demo-dev-scratch",     "env": "dev",     "public_block": False},  # no public access block (demo alert)
        {"name": "rosie-demo-public-website",  "env": "prod",    "public_block": False},  # intentionally public for demo
    ]
    for bkt in s3_buckets:
        s3.create_bucket(Bucket=bkt["name"])
        s3.put_bucket_tagging(
            Bucket=bkt["name"],
            Tagging={"TagSet": [
                {"Key": "Environment", "Value": bkt["env"]},
                {"Key": "Project",     "Value": "rosie-demo"},
            ]},
        )
        if bkt["public_block"]:
            s3.put_public_access_block(
                Bucket=bkt["name"],
                PublicAccessBlockConfiguration={
                    "BlockPublicAcls":       True,
                    "IgnorePublicAcls":      True,
                    "BlockPublicPolicy":     True,
                    "RestrictPublicBuckets": True,
                },
            )

    # ------------------------------------------------------------------ #
    # Network Topology
    # ------------------------------------------------------------------ #
    log.info("Creating network topology …")

    # Production VPC
    prod_vpc = ec2.create_vpc(
        CidrBlock="10.0.0.0/16",
        TagSpecifications=[{
            "ResourceType": "vpc",
            "Tags": [
                {"Key": "Name",        "Value": "prod-vpc"},
                {"Key": "Environment", "Value": "prod"},
                {"Key": "Project",     "Value": "rosie-demo"},
            ],
        }],
    )["Vpc"]
    prod_vpc_id = prod_vpc["VpcId"]

    # Staging VPC
    staging_vpc = ec2.create_vpc(
        CidrBlock="10.1.0.0/16",
        TagSpecifications=[{
            "ResourceType": "vpc",
            "Tags": [
                {"Key": "Name",        "Value": "staging-vpc"},
                {"Key": "Environment", "Value": "staging"},
                {"Key": "Project",     "Value": "rosie-demo"},
            ],
        }],
    )["Vpc"]
    staging_vpc_id = staging_vpc["VpcId"]

    # Subnets in prod VPC
    pub_subnet_a = ec2.create_subnet(
        VpcId=prod_vpc_id,
        CidrBlock="10.0.1.0/24",
        AvailabilityZone=f"{REGION}a",
        TagSpecifications=[{
            "ResourceType": "subnet",
            "Tags": [
                {"Key": "Name",        "Value": "prod-public-subnet-a"},
                {"Key": "Environment", "Value": "prod"},
            ],
        }],
    )["Subnet"]
    pub_subnet_b = ec2.create_subnet(
        VpcId=prod_vpc_id,
        CidrBlock="10.0.2.0/24",
        AvailabilityZone=f"{REGION}b",
        TagSpecifications=[{
            "ResourceType": "subnet",
            "Tags": [
                {"Key": "Name",        "Value": "prod-public-subnet-b"},
                {"Key": "Environment", "Value": "prod"},
            ],
        }],
    )["Subnet"]
    priv_subnet_a = ec2.create_subnet(
        VpcId=prod_vpc_id,
        CidrBlock="10.0.11.0/24",
        AvailabilityZone=f"{REGION}a",
        TagSpecifications=[{
            "ResourceType": "subnet",
            "Tags": [
                {"Key": "Name",        "Value": "prod-private-subnet-a"},
                {"Key": "Environment", "Value": "prod"},
            ],
        }],
    )["Subnet"]
    priv_subnet_b = ec2.create_subnet(
        VpcId=prod_vpc_id,
        CidrBlock="10.0.12.0/24",
        AvailabilityZone=f"{REGION}b",
        TagSpecifications=[{
            "ResourceType": "subnet",
            "Tags": [
                {"Key": "Name",        "Value": "prod-private-subnet-b"},
                {"Key": "Environment", "Value": "prod"},
            ],
        }],
    )["Subnet"]

    # Internet Gateway for prod VPC
    igw = ec2.create_internet_gateway(
        TagSpecifications=[{
            "ResourceType": "internet-gateway",
            "Tags": [
                {"Key": "Name",        "Value": "prod-igw"},
                {"Key": "Environment", "Value": "prod"},
            ],
        }],
    )["InternetGateway"]
    ec2.attach_internet_gateway(
        InternetGatewayId=igw["InternetGatewayId"],
        VpcId=prod_vpc_id,
    )

    # NAT Gateway in public subnet
    eip = ec2.allocate_address(Domain="vpc")
    nat_gw = ec2.create_nat_gateway(
        SubnetId=pub_subnet_a["SubnetId"],
        AllocationId=eip["AllocationId"],
        TagSpecifications=[{
            "ResourceType": "natgateway",
            "Tags": [
                {"Key": "Name",        "Value": "prod-nat-gw"},
                {"Key": "Environment", "Value": "prod"},
            ],
        }],
    )["NatGateway"]

    # Public route table
    pub_rt = ec2.create_route_table(
        VpcId=prod_vpc_id,
        TagSpecifications=[{
            "ResourceType": "route-table",
            "Tags": [
                {"Key": "Name",        "Value": "prod-public-rt"},
                {"Key": "Environment", "Value": "prod"},
            ],
        }],
    )["RouteTable"]
    ec2.create_route(
        RouteTableId=pub_rt["RouteTableId"],
        DestinationCidrBlock="0.0.0.0/0",
        GatewayId=igw["InternetGatewayId"],
    )
    ec2.associate_route_table(
        RouteTableId=pub_rt["RouteTableId"],
        SubnetId=pub_subnet_a["SubnetId"],
    )
    ec2.associate_route_table(
        RouteTableId=pub_rt["RouteTableId"],
        SubnetId=pub_subnet_b["SubnetId"],
    )

    # Private route table
    priv_rt = ec2.create_route_table(
        VpcId=prod_vpc_id,
        TagSpecifications=[{
            "ResourceType": "route-table",
            "Tags": [
                {"Key": "Name",        "Value": "prod-private-rt"},
                {"Key": "Environment", "Value": "prod"},
            ],
        }],
    )["RouteTable"]
    ec2.create_route(
        RouteTableId=priv_rt["RouteTableId"],
        DestinationCidrBlock="0.0.0.0/0",
        NatGatewayId=nat_gw["NatGatewayId"],
    )
    ec2.associate_route_table(
        RouteTableId=priv_rt["RouteTableId"],
        SubnetId=priv_subnet_a["SubnetId"],
    )
    ec2.associate_route_table(
        RouteTableId=priv_rt["RouteTableId"],
        SubnetId=priv_subnet_b["SubnetId"],
    )

    # Security Groups
    web_sg = ec2.create_security_group(
        GroupName="web-sg",
        Description="Web tier - allow HTTP/HTTPS from internet",
        VpcId=prod_vpc_id,
        TagSpecifications=[{
            "ResourceType": "security-group",
            "Tags": [
                {"Key": "Name",        "Value": "web-sg"},
                {"Key": "Environment", "Value": "prod"},
            ],
        }],
    )
    ec2.authorize_security_group_ingress(
        GroupId=web_sg["GroupId"],
        IpPermissions=[
            {"IpProtocol": "tcp", "FromPort": 80,  "ToPort": 80,  "IpRanges": [{"CidrIp": "0.0.0.0/0"}]},
            {"IpProtocol": "tcp", "FromPort": 443, "ToPort": 443, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]},
        ],
    )

    app_sg = ec2.create_security_group(
        GroupName="app-sg",
        Description="App tier - allow traffic from web tier only",
        VpcId=prod_vpc_id,
        TagSpecifications=[{
            "ResourceType": "security-group",
            "Tags": [
                {"Key": "Name",        "Value": "app-sg"},
                {"Key": "Environment", "Value": "prod"},
            ],
        }],
    )
    ec2.authorize_security_group_ingress(
        GroupId=app_sg["GroupId"],
        IpPermissions=[
            {"IpProtocol": "tcp", "FromPort": 8080, "ToPort": 8080,
             "UserIdGroupPairs": [{"GroupId": web_sg["GroupId"]}]},
        ],
    )

    db_sg = ec2.create_security_group(
        GroupName="db-sg",
        Description="DB tier - allow traffic from app tier only",
        VpcId=prod_vpc_id,
        TagSpecifications=[{
            "ResourceType": "security-group",
            "Tags": [
                {"Key": "Name",        "Value": "db-sg"},
                {"Key": "Environment", "Value": "prod"},
            ],
        }],
    )
    ec2.authorize_security_group_ingress(
        GroupId=db_sg["GroupId"],
        IpPermissions=[
            {"IpProtocol": "tcp", "FromPort": 5432, "ToPort": 5432,
             "UserIdGroupPairs": [{"GroupId": app_sg["GroupId"]}]},
        ],
    )

    # Overly-permissive security group (demo alert: SSH open to internet)
    bastion_sg = ec2.create_security_group(
        GroupName="bastion-sg",
        Description="Bastion host - SSH access (demo: open to internet)",
        VpcId=prod_vpc_id,
        TagSpecifications=[{
            "ResourceType": "security-group",
            "Tags": [
                {"Key": "Name",        "Value": "bastion-sg"},
                {"Key": "Environment", "Value": "prod"},
            ],
        }],
    )
    ec2.authorize_security_group_ingress(
        GroupId=bastion_sg["GroupId"],
        IpPermissions=[
            {"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22,
             "IpRanges": [{"CidrIp": "0.0.0.0/0"}]},  # intentionally open for demo alert
        ],
    )

    # VPC Endpoint for S3 (Gateway type)
    ec2.create_vpc_endpoint(
        VpcId=prod_vpc_id,
        ServiceName=f"com.amazonaws.{REGION}.s3",
        VpcEndpointType="Gateway",
        RouteTableIds=[priv_rt["RouteTableId"]],
        TagSpecifications=[{
            "ResourceType": "vpc-endpoint",
            "Tags": [
                {"Key": "Name",        "Value": "prod-s3-endpoint"},
                {"Key": "Environment", "Value": "prod"},
            ],
        }],
    )

    # VPC Peering between prod and staging
    ec2.create_vpc_peering_connection(
        VpcId=prod_vpc_id,
        PeerVpcId=staging_vpc_id,
        TagSpecifications=[{
            "ResourceType": "vpc-peering-connection",
            "Tags": [
                {"Key": "Name",        "Value": "prod-to-staging-peering"},
                {"Key": "Environment", "Value": "prod"},
            ],
        }],
    )

    # ------------------------------------------------------------------ #
    # ------------------------------------------------------------------ #
    log.info("Running Rosie collectors …")
    resources = run_all(region=REGION, account_id=ACCOUNT_ID)
    path = save_cache(resources)
    log.info("Saved %d resources to %s", len(resources), path)
    log.info("")
    log.info("Demo environment ready!  Start the stack and open the UI:")
    log.info("  docker compose up -d")
    log.info("  open http://localhost:8501")
    log.info("")
    log.info("Example questions to try:")
    log.info('  "How many EC2 instances do we have in production?"')
    log.info('  "Which Lambda functions are running deprecated runtimes?"')
    log.info('  "Do we have any publicly accessible RDS databases?"')
    log.info('  "Which S3 buckets are missing public access blocks?"')
    log.info('  "What VPCs do we have and what are their CIDR ranges?"')
    log.info('  "Which security groups allow inbound SSH from 0.0.0.0/0?"')
    log.info('  "Do we have a NAT gateway in production?"')
    log.info('  "Give me a summary of all resources."')


if __name__ == "__main__":
    seed()
