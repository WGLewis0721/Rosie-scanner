import pytest
import boto3
from moto import mock_aws
from rosie.collectors import ec2, rds, lambda_, s3, iam, ssm


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
