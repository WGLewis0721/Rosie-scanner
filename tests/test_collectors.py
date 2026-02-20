import pytest
import boto3
from moto import mock_aws
from rosie.collectors import ec2, rds, lambda_, s3, iam, ssm, network


@mock_aws
def test_ec2_collect():
    region = "us-east-1"
    client = boto3.client("ec2", region_name=region)
    client.run_instances(ImageId="ami-12345678", MinCount=1, MaxCount=1, InstanceType="t2.micro")
    resources = ec2.collect(region, "123456789012")
    assert len(resources) >= 1
    r = resources[0]
    assert r["resource_type"] == "ec2:instance"
    assert r["region"] == region
    assert r["account_id"] == "123456789012"
    assert "instance_type" in r["details"]


@mock_aws
def test_rds_collect():
    region = "us-east-1"
    client = boto3.client("rds", region_name=region)
    client.create_db_instance(
        DBInstanceIdentifier="test-db",
        DBInstanceClass="db.t3.micro",
        Engine="postgres",
        MasterUsername="admin",
        MasterUserPassword="password123",
        AllocatedStorage=20,
    )
    resources = rds.collect(region, "123456789012")
    assert len(resources) >= 1
    r = resources[0]
    assert r["resource_type"] == "rds:db"
    assert r["details"]["engine"] == "postgres"


@mock_aws
def test_lambda_collect():
    region = "us-east-1"
    import zipfile, io
    zb = io.BytesIO()
    with zipfile.ZipFile(zb, "w") as zf:
        zf.writestr("index.py", "def handler(e, c): return {}")
    zb.seek(0)
    iam_client = boto3.client("iam", region_name=region)
    iam_client.create_role(
        RoleName="lambda-role",
        AssumeRolePolicyDocument='{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}',
    )
    role_arn = iam_client.get_role(RoleName="lambda-role")["Role"]["Arn"]
    lc = boto3.client("lambda", region_name=region)
    lc.create_function(
        FunctionName="test-fn",
        Runtime="python3.9",
        Role=role_arn,
        Handler="index.handler",
        Code={"ZipFile": zb.read()},
    )
    resources = lambda_.collect(region, "123456789012")
    assert len(resources) >= 1
    r = resources[0]
    assert r["resource_type"] == "lambda:function"
    assert r["details"]["runtime"] == "python3.9"


@mock_aws
def test_s3_collect():
    region = "us-east-1"
    client = boto3.client("s3", region_name=region)
    client.create_bucket(Bucket="my-test-bucket")
    resources = s3.collect(region, "123456789012")
    assert len(resources) >= 1
    bucket_ids = [r["resource_id"] for r in resources]
    assert "my-test-bucket" in bucket_ids


@mock_aws
def test_iam_collect():
    client = boto3.client("iam")
    client.create_role(
        RoleName="test-role",
        AssumeRolePolicyDocument='{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}',
        Description="Test role",
    )
    resources = iam.collect("us-east-1", "123456789012")
    role_names = [r["name"] for r in resources]
    assert "test-role" in role_names
    r = next(r for r in resources if r["name"] == "test-role")
    assert r["resource_type"] == "iam:role"


def test_ssm_collect():
    # moto does not implement describe_instance_information; mock the paginator
    from unittest.mock import patch, MagicMock
    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value = [{"InstanceInformationList": []}]
    with patch("boto3.client") as mock_client:
        mock_client.return_value.get_paginator.return_value = mock_paginator
        resources = ssm.collect("us-east-1", "123456789012")
    assert isinstance(resources, list)
    assert resources == []


@mock_aws
def test_network_collect_vpc():
    region = "us-east-1"
    client = boto3.client("ec2", region_name=region)
    vpc = client.create_vpc(CidrBlock="10.0.0.0/16")["Vpc"]
    resources = network.collect(region, "123456789012")
    vpc_resources = [r for r in resources if r["resource_type"] == "ec2:vpc"]
    assert any(r["resource_id"] == vpc["VpcId"] for r in vpc_resources)
    r = next(r for r in vpc_resources if r["resource_id"] == vpc["VpcId"])
    assert r["details"]["cidr_block"] == "10.0.0.0/16"


@mock_aws
def test_network_collect_subnet():
    region = "us-east-1"
    client = boto3.client("ec2", region_name=region)
    vpc = client.create_vpc(CidrBlock="10.0.0.0/16")["Vpc"]
    subnet = client.create_subnet(VpcId=vpc["VpcId"], CidrBlock="10.0.1.0/24")["Subnet"]
    resources = network.collect(region, "123456789012")
    subnet_resources = [r for r in resources if r["resource_type"] == "ec2:subnet"]
    assert any(r["resource_id"] == subnet["SubnetId"] for r in subnet_resources)
    r = next(r for r in subnet_resources if r["resource_id"] == subnet["SubnetId"])
    assert r["details"]["vpc_id"] == vpc["VpcId"]
    assert r["details"]["cidr_block"] == "10.0.1.0/24"


@mock_aws
def test_network_collect_security_group():
    region = "us-east-1"
    client = boto3.client("ec2", region_name=region)
    vpc = client.create_vpc(CidrBlock="10.0.0.0/16")["Vpc"]
    sg = client.create_security_group(
        GroupName="test-sg", Description="Test SG", VpcId=vpc["VpcId"]
    )
    client.authorize_security_group_ingress(
        GroupId=sg["GroupId"],
        IpPermissions=[{"IpProtocol": "tcp", "FromPort": 443, "ToPort": 443,
                        "IpRanges": [{"CidrIp": "0.0.0.0/0"}]}],
    )
    resources = network.collect(region, "123456789012")
    sg_resources = [r for r in resources if r["resource_type"] == "ec2:security_group"]
    assert any(r["resource_id"] == sg["GroupId"] for r in sg_resources)
    r = next(r for r in sg_resources if r["resource_id"] == sg["GroupId"])
    assert len(r["details"]["ingress_rules"]) >= 1
    rule = r["details"]["ingress_rules"][0]
    assert rule["from_port"] == 443
    assert "0.0.0.0/0" in rule["cidr_ranges"]


@mock_aws
def test_network_collect_nacl():
    region = "us-east-1"
    client = boto3.client("ec2", region_name=region)
    vpc = client.create_vpc(CidrBlock="10.0.0.0/16")["Vpc"]
    nacl = client.create_network_acl(VpcId=vpc["VpcId"])["NetworkAcl"]
    resources = network.collect(region, "123456789012")
    nacl_resources = [r for r in resources if r["resource_type"] == "ec2:nacl"]
    assert any(r["resource_id"] == nacl["NetworkAclId"] for r in nacl_resources)


@mock_aws
def test_network_collect_route_table():
    region = "us-east-1"
    client = boto3.client("ec2", region_name=region)
    vpc = client.create_vpc(CidrBlock="10.0.0.0/16")["Vpc"]
    rt = client.create_route_table(VpcId=vpc["VpcId"])["RouteTable"]
    resources = network.collect(region, "123456789012")
    rt_resources = [r for r in resources if r["resource_type"] == "ec2:route_table"]
    assert any(r["resource_id"] == rt["RouteTableId"] for r in rt_resources)
    r = next(r for r in rt_resources if r["resource_id"] == rt["RouteTableId"])
    assert r["details"]["vpc_id"] == vpc["VpcId"]


@mock_aws
def test_network_collect_internet_gateway():
    region = "us-east-1"
    client = boto3.client("ec2", region_name=region)
    vpc = client.create_vpc(CidrBlock="10.0.0.0/16")["Vpc"]
    igw = client.create_internet_gateway()["InternetGateway"]
    client.attach_internet_gateway(InternetGatewayId=igw["InternetGatewayId"], VpcId=vpc["VpcId"])
    resources = network.collect(region, "123456789012")
    igw_resources = [r for r in resources if r["resource_type"] == "ec2:internet_gateway"]
    assert any(r["resource_id"] == igw["InternetGatewayId"] for r in igw_resources)
    r = next(r for r in igw_resources if r["resource_id"] == igw["InternetGatewayId"])
    assert any(a["vpc_id"] == vpc["VpcId"] for a in r["details"]["attached_vpcs"])


@mock_aws
def test_network_collect_vpc_peering():
    region = "us-east-1"
    client = boto3.client("ec2", region_name=region)
    vpc1 = client.create_vpc(CidrBlock="10.0.0.0/16")["Vpc"]
    vpc2 = client.create_vpc(CidrBlock="10.1.0.0/16")["Vpc"]
    peering = client.create_vpc_peering_connection(
        VpcId=vpc1["VpcId"], PeerVpcId=vpc2["VpcId"]
    )["VpcPeeringConnection"]
    resources = network.collect(region, "123456789012")
    peer_resources = [r for r in resources if r["resource_type"] == "ec2:vpc_peering"]
    assert any(r["resource_id"] == peering["VpcPeeringConnectionId"] for r in peer_resources)
    r = next(r for r in peer_resources if r["resource_id"] == peering["VpcPeeringConnectionId"])
    assert r["details"]["requester_vpc_id"] == vpc1["VpcId"]
    assert r["details"]["accepter_vpc_id"] == vpc2["VpcId"]


@mock_aws
def test_network_resource_schema():
    region = "us-east-1"
    resources = network.collect(region, "123456789012")
    for r in resources:
        assert "resource_id" in r
        assert "resource_type" in r
        assert "name" in r
        assert "region" in r
        assert "account_id" in r
        assert "details" in r
        assert "tags" in r
        assert "collected_at" in r
