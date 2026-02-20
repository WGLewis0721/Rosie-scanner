import logging
import boto3
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def collect(region: str, account_id: str) -> list[dict]:
    client = boto3.client("ec2", region_name=region)
    resources = []

    # VPCs
    for page in client.get_paginator("describe_vpcs").paginate():
        for vpc in page["Vpcs"]:
            tags = {t["Key"]: t["Value"] for t in vpc.get("Tags", [])}
            resources.append({
                "resource_id": vpc["VpcId"],
                "resource_type": "ec2:vpc",
                "name": tags.get("Name", vpc["VpcId"]),
                "region": region,
                "account_id": account_id,
                "details": {
                    "cidr_block": vpc.get("CidrBlock"),
                    "state": vpc.get("State"),
                    "is_default": vpc.get("IsDefault", False),
                    "dhcp_options_id": vpc.get("DhcpOptionsId"),
                    "instance_tenancy": vpc.get("InstanceTenancy"),
                },
                "tags": tags,
                "collected_at": datetime.now(timezone.utc).isoformat(),
            })

    # Subnets
    for page in client.get_paginator("describe_subnets").paginate():
        for subnet in page["Subnets"]:
            tags = {t["Key"]: t["Value"] for t in subnet.get("Tags", [])}
            resources.append({
                "resource_id": subnet["SubnetId"],
                "resource_type": "ec2:subnet",
                "name": tags.get("Name", subnet["SubnetId"]),
                "region": region,
                "account_id": account_id,
                "details": {
                    "vpc_id": subnet.get("VpcId"),
                    "cidr_block": subnet.get("CidrBlock"),
                    "availability_zone": subnet.get("AvailabilityZone"),
                    "available_ip_address_count": subnet.get("AvailableIpAddressCount"),
                    "map_public_ip_on_launch": subnet.get("MapPublicIpOnLaunch", False),
                    "state": subnet.get("State"),
                },
                "tags": tags,
                "collected_at": datetime.now(timezone.utc).isoformat(),
            })

    # Security Groups
    for page in client.get_paginator("describe_security_groups").paginate():
        for sg in page["SecurityGroups"]:
            tags = {t["Key"]: t["Value"] for t in sg.get("Tags", [])}
            resources.append({
                "resource_id": sg["GroupId"],
                "resource_type": "ec2:security_group",
                "name": sg.get("GroupName", sg["GroupId"]),
                "region": region,
                "account_id": account_id,
                "details": {
                    "vpc_id": sg.get("VpcId"),
                    "description": sg.get("Description", ""),
                    "ingress_rules": [
                        {
                            "protocol": rule.get("IpProtocol"),
                            "from_port": rule.get("FromPort"),
                            "to_port": rule.get("ToPort"),
                            "cidr_ranges": [r["CidrIp"] for r in rule.get("IpRanges", [])],
                            "ipv6_ranges": [r["CidrIpv6"] for r in rule.get("Ipv6Ranges", [])],
                            "source_groups": [g["GroupId"] for g in rule.get("UserIdGroupPairs", [])],
                        }
                        for rule in sg.get("IpPermissions", [])
                    ],
                    "egress_rules": [
                        {
                            "protocol": rule.get("IpProtocol"),
                            "from_port": rule.get("FromPort"),
                            "to_port": rule.get("ToPort"),
                            "cidr_ranges": [r["CidrIp"] for r in rule.get("IpRanges", [])],
                            "ipv6_ranges": [r["CidrIpv6"] for r in rule.get("Ipv6Ranges", [])],
                            "dest_groups": [g["GroupId"] for g in rule.get("UserIdGroupPairs", [])],
                        }
                        for rule in sg.get("IpPermissionsEgress", [])
                    ],
                },
                "tags": tags,
                "collected_at": datetime.now(timezone.utc).isoformat(),
            })

    # Network ACLs
    for page in client.get_paginator("describe_network_acls").paginate():
        for nacl in page["NetworkAcls"]:
            tags = {t["Key"]: t["Value"] for t in nacl.get("Tags", [])}
            resources.append({
                "resource_id": nacl["NetworkAclId"],
                "resource_type": "ec2:nacl",
                "name": tags.get("Name", nacl["NetworkAclId"]),
                "region": region,
                "account_id": account_id,
                "details": {
                    "vpc_id": nacl.get("VpcId"),
                    "is_default": nacl.get("IsDefault", False),
                    "associated_subnets": [a["SubnetId"] for a in nacl.get("Associations", [])],
                    "entries": [
                        {
                            "rule_number": entry.get("RuleNumber"),
                            "protocol": entry.get("Protocol"),
                            "rule_action": entry.get("RuleAction"),
                            "egress": entry.get("Egress", False),
                            "cidr_block": entry.get("CidrBlock"),
                            "ipv6_cidr_block": entry.get("Ipv6CidrBlock"),
                            "port_range": entry.get("PortRange"),
                        }
                        for entry in nacl.get("Entries", [])
                    ],
                },
                "tags": tags,
                "collected_at": datetime.now(timezone.utc).isoformat(),
            })

    # Route Tables
    for page in client.get_paginator("describe_route_tables").paginate():
        for rt in page["RouteTables"]:
            tags = {t["Key"]: t["Value"] for t in rt.get("Tags", [])}
            resources.append({
                "resource_id": rt["RouteTableId"],
                "resource_type": "ec2:route_table",
                "name": tags.get("Name", rt["RouteTableId"]),
                "region": region,
                "account_id": account_id,
                "details": {
                    "vpc_id": rt.get("VpcId"),
                    "associated_subnets": [
                        a["SubnetId"] for a in rt.get("Associations", []) if a.get("SubnetId")
                    ],
                    "main": any(a.get("Main", False) for a in rt.get("Associations", [])),
                    "routes": [
                        {
                            "destination_cidr": route.get("DestinationCidrBlock"),
                            "destination_ipv6_cidr": route.get("DestinationIpv6CidrBlock"),
                            "destination_prefix_list": route.get("DestinationPrefixListId"),
                            "gateway_id": route.get("GatewayId"),
                            "nat_gateway_id": route.get("NatGatewayId"),
                            "transit_gateway_id": route.get("TransitGatewayId"),
                            "vpc_peering_connection_id": route.get("VpcPeeringConnectionId"),
                            "state": route.get("State"),
                        }
                        for route in rt.get("Routes", [])
                    ],
                },
                "tags": tags,
                "collected_at": datetime.now(timezone.utc).isoformat(),
            })

    # Internet Gateways
    for page in client.get_paginator("describe_internet_gateways").paginate():
        for igw in page["InternetGateways"]:
            tags = {t["Key"]: t["Value"] for t in igw.get("Tags", [])}
            resources.append({
                "resource_id": igw["InternetGatewayId"],
                "resource_type": "ec2:internet_gateway",
                "name": tags.get("Name", igw["InternetGatewayId"]),
                "region": region,
                "account_id": account_id,
                "details": {
                    "attached_vpcs": [
                        {"vpc_id": a["VpcId"], "state": a.get("State")}
                        for a in igw.get("Attachments", [])
                    ],
                },
                "tags": tags,
                "collected_at": datetime.now(timezone.utc).isoformat(),
            })

    # NAT Gateways
    for page in client.get_paginator("describe_nat_gateways").paginate():
        for nat in page["NatGateways"]:
            tags = {t["Key"]: t["Value"] for t in nat.get("Tags", [])}
            resources.append({
                "resource_id": nat["NatGatewayId"],
                "resource_type": "ec2:nat_gateway",
                "name": tags.get("Name", nat["NatGatewayId"]),
                "region": region,
                "account_id": account_id,
                "details": {
                    "vpc_id": nat.get("VpcId"),
                    "subnet_id": nat.get("SubnetId"),
                    "state": nat.get("State"),
                    "connectivity_type": nat.get("ConnectivityType", "public"),
                    "public_ip": next(
                        (a.get("PublicIp") for a in nat.get("NatGatewayAddresses", [])), None
                    ),
                    "private_ip": next(
                        (a.get("PrivateIp") for a in nat.get("NatGatewayAddresses", [])), None
                    ),
                },
                "tags": tags,
                "collected_at": datetime.now(timezone.utc).isoformat(),
            })

    # Transit Gateways
    try:
        for page in client.get_paginator("describe_transit_gateways").paginate():
            for tgw in page["TransitGateways"]:
                tags = {t["Key"]: t["Value"] for t in tgw.get("Tags", [])}
                resources.append({
                    "resource_id": tgw["TransitGatewayId"],
                    "resource_type": "ec2:transit_gateway",
                    "name": tags.get("Name", tgw["TransitGatewayId"]),
                    "region": region,
                    "account_id": account_id,
                    "details": {
                        "state": tgw.get("State"),
                        "owner_id": tgw.get("OwnerId"),
                        "amazon_side_asn": tgw.get("Options", {}).get("AmazonSideAsn"),
                        "dns_support": tgw.get("Options", {}).get("DnsSupport"),
                        "vpn_ecmp_support": tgw.get("Options", {}).get("VpnEcmpSupport"),
                        "default_route_table_association": tgw.get("Options", {}).get(
                            "DefaultRouteTableAssociation"
                        ),
                        "default_route_table_propagation": tgw.get("Options", {}).get(
                            "DefaultRouteTablePropagation"
                        ),
                    },
                    "tags": tags,
                    "collected_at": datetime.now(timezone.utc).isoformat(),
                })
    except Exception:
        logger.warning("Failed to collect transit gateways in region %s", region, exc_info=True)

    # Transit Gateway Attachments
    try:
        for page in client.get_paginator("describe_transit_gateway_attachments").paginate():
            for att in page["TransitGatewayAttachments"]:
                tags = {t["Key"]: t["Value"] for t in att.get("Tags", [])}
                resources.append({
                    "resource_id": att["TransitGatewayAttachmentId"],
                    "resource_type": "ec2:tgw_attachment",
                    "name": tags.get("Name", att["TransitGatewayAttachmentId"]),
                    "region": region,
                    "account_id": account_id,
                    "details": {
                        "transit_gateway_id": att.get("TransitGatewayId"),
                        "resource_type": att.get("ResourceType"),
                        "resource_id": att.get("ResourceId"),
                        "resource_owner_id": att.get("ResourceOwnerId"),
                        "state": att.get("State"),
                        "association_state": att.get("Association", {}).get("State"),
                        "association_route_table_id": att.get("Association", {}).get(
                            "TransitGatewayRouteTableId"
                        ),
                    },
                    "tags": tags,
                    "collected_at": datetime.now(timezone.utc).isoformat(),
                })
    except Exception:
        logger.warning("Failed to collect TGW attachments in region %s", region, exc_info=True)

    # VPC Peering Connections
    for page in client.get_paginator("describe_vpc_peering_connections").paginate():
        for peering in page["VpcPeeringConnections"]:
            tags = {t["Key"]: t["Value"] for t in peering.get("Tags", [])}
            resources.append({
                "resource_id": peering["VpcPeeringConnectionId"],
                "resource_type": "ec2:vpc_peering",
                "name": tags.get("Name", peering["VpcPeeringConnectionId"]),
                "region": region,
                "account_id": account_id,
                "details": {
                    "status": peering.get("Status", {}).get("Code"),
                    "status_message": peering.get("Status", {}).get("Message"),
                    "requester_vpc_id": peering.get("RequesterVpcInfo", {}).get("VpcId"),
                    "requester_cidr": peering.get("RequesterVpcInfo", {}).get("CidrBlock"),
                    "requester_owner_id": peering.get("RequesterVpcInfo", {}).get("OwnerId"),
                    "accepter_vpc_id": peering.get("AccepterVpcInfo", {}).get("VpcId"),
                    "accepter_cidr": peering.get("AccepterVpcInfo", {}).get("CidrBlock"),
                    "accepter_owner_id": peering.get("AccepterVpcInfo", {}).get("OwnerId"),
                },
                "tags": tags,
                "collected_at": datetime.now(timezone.utc).isoformat(),
            })

    # VPC Endpoints
    for page in client.get_paginator("describe_vpc_endpoints").paginate():
        for ep in page["VpcEndpoints"]:
            tags = {t["Key"]: t["Value"] for t in ep.get("Tags", [])}
            resources.append({
                "resource_id": ep["VpcEndpointId"],
                "resource_type": "ec2:vpc_endpoint",
                "name": tags.get("Name", ep["VpcEndpointId"]),
                "region": region,
                "account_id": account_id,
                "details": {
                    "vpc_id": ep.get("VpcId"),
                    "service_name": ep.get("ServiceName"),
                    "state": ep.get("State"),
                    "endpoint_type": ep.get("VpcEndpointType"),
                    "subnet_ids": ep.get("SubnetIds", []),
                    "route_table_ids": ep.get("RouteTableIds", []),
                    "network_interface_ids": ep.get("NetworkInterfaceIds", []),
                },
                "tags": tags,
                "collected_at": datetime.now(timezone.utc).isoformat(),
            })

    return resources
