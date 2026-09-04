import os
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Tuple, Any, Optional, Set
import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError, PartialCredentialsError

import models
from models import ComponentType, Environment, Criticality, Status, DependencyType
from graph_builder import AWSDependencyGraphBuilder

logger = logging.getLogger("infratwin.aws")
logging.basicConfig(level=logging.INFO)

# Estimated monthly pricing table for common AWS resource types (hourly rate * 730 hours)
INSTANCE_COST_TABLE: Dict[str, float] = {
    # General Purpose EC2
    "t2.nano": 4.23, "t2.micro": 8.47, "t2.small": 16.94, "t2.medium": 33.87, "t2.large": 67.74,
    "t3.nano": 3.80, "t3.micro": 7.59, "t3.small": 15.18, "t3.medium": 30.37, "t3.large": 60.74, "t3.xlarge": 121.47,
    "t4g.nano": 3.07, "t4g.micro": 6.13, "t4g.small": 12.26, "t4g.medium": 24.53, "t4g.large": 49.06, "t4g.xlarge": 98.11,
    "m5.large": 70.08, "m5.xlarge": 140.16, "m5.2xlarge": 280.32, "m5.4xlarge": 560.64,
    "c5.large": 62.05, "c5.xlarge": 124.10, "c5.2xlarge": 248.20,
    "r5.large": 91.98, "r5.xlarge": 183.96, "r5.2xlarge": 367.92,
    # RDS DB Instances
    "db.t3.micro": 12.41, "db.t3.small": 24.82, "db.t3.medium": 49.64,
    "db.t4g.micro": 10.95, "db.t4g.small": 21.90, "db.t4g.medium": 43.80,
    "db.m5.large": 129.94, "db.m5.xlarge": 259.88, "db.m5.2xlarge": 519.76,
    "db.r5.large": 175.20, "db.r5.xlarge": 350.40,
    # Base rates
    "alb_base": 22.50,
    "nat_gateway": 32.85,
    "s3_baseline": 5.00,
}

_ACTIVE_AWS_SESSION: Optional[boto3.Session] = None

def set_active_aws_credentials(
    access_key_id: str,
    secret_access_key: str,
    session_token: Optional[str] = None,
    region: Optional[str] = "us-east-1"
) -> Dict[str, Any]:
    """
    Validates provided AWS credentials against STS GetCallerIdentity and sets the active session.
    """
    global _ACTIVE_AWS_SESSION
    reg = region or "us-east-1"
    session_kwargs = {
        "aws_access_key_id": access_key_id,
        "aws_secret_access_key": secret_access_key,
        "region_name": reg
    }
    if session_token:
        session_kwargs["aws_session_token"] = session_token
    
    test_session = boto3.Session(**session_kwargs)
    status = check_aws_credentials(test_session)
    if status["authenticated"]:
        _ACTIVE_AWS_SESSION = test_session
        logger.info("Activated live AWS session for account %s (%s)", status.get("account_id"), reg)
        return status
    else:
        return status

def clear_active_aws_session():
    global _ACTIVE_AWS_SESSION
    _ACTIVE_AWS_SESSION = None

def get_boto3_session(region_name: Optional[str] = None) -> boto3.Session:
    """
    Creates or returns active Boto3 Session using standard AWS credential mechanisms or dynamic credentials.
    Credentials resolve from:
    1. Active configured session via POST /api/aws/connect
    2. Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN)
    3. Shared credentials file (~/.aws/credentials)
    4. IAM Instance profile / Container credentials / SSO
    """
    global _ACTIVE_AWS_SESSION
    if _ACTIVE_AWS_SESSION is not None:
        if region_name and _ACTIVE_AWS_SESSION.region_name != region_name:
            creds = _ACTIVE_AWS_SESSION.get_credentials()
            return boto3.Session(
                aws_access_key_id=creds.access_key,
                aws_secret_access_key=creds.secret_key,
                aws_session_token=creds.token,
                region_name=region_name
            )
        return _ACTIVE_AWS_SESSION

    region = (
        region_name
        or os.environ.get("AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
        or "us-east-1"
    )
    return boto3.Session(region_name=region)

def check_aws_credentials(session: Optional[boto3.Session] = None) -> Dict[str, Any]:
    """
    Checks if active AWS credentials are valid by calling STS GetCallerIdentity.
    """
    if session is None:
        session = get_boto3_session()

    region = session.region_name or "us-east-1"
    try:
        sts = session.client("sts")
        identity = sts.get_caller_identity()
        logger.info("AWS Credentials validated for Account: %s, ARN: %s", identity.get("Account"), identity.get("Arn"))
        return {
            "authenticated": True,
            "account_id": identity.get("Account"),
            "arn": identity.get("Arn"),
            "region": region,
            "error": None
        }
    except (NoCredentialsError, PartialCredentialsError) as e:
        logger.warning("AWS Credentials not found: %s", str(e))
        return {
            "authenticated": False,
            "account_id": None,
            "arn": None,
            "region": region,
            "error": "No AWS credentials found. Configure AWS_ACCESS_KEY_ID or ~/.aws/credentials"
        }
    except (ClientError, BotoCoreError) as e:
        logger.warning("AWS Authentication failed: %s", str(e))
        return {
            "authenticated": False,
            "account_id": None,
            "arn": None,
            "region": region,
            "error": str(e)
        }
    except Exception as e:
        logger.error("Unexpected error checking AWS credentials: %s", str(e))
        return {
            "authenticated": False,
            "account_id": None,
            "arn": None,
            "region": region,
            "error": str(e)
        }

def _parse_tags(tags_list: Optional[List[Dict[str, str]]]) -> Dict[str, str]:
    """Helper to convert AWS tag list [{'Key': 'k', 'Value': 'v'}] into a dict."""
    if not tags_list:
        return {}
    return {t.get("Key", ""): t.get("Value", "") for t in tags_list if t.get("Key")}

def _derive_criticality(tags: Dict[str, str], resource_type: str, default: Criticality = Criticality.medium) -> Criticality:
    """Derives criticality from tags (e.g. Criticality, Environment) or resource type."""
    crit_tag = tags.get("Criticality", "").lower()
    if crit_tag in ["critical", "crit"]:
        return Criticality.critical
    elif crit_tag in ["high"]:
        return Criticality.high
    elif crit_tag in ["medium", "med"]:
        return Criticality.medium
    elif crit_tag in ["low"]:
        return Criticality.low

    env_tag = tags.get("Environment", "").lower()
    if env_tag in ["prod", "production"]:
        if resource_type in ["database", "rds"]:
            return Criticality.critical
        return Criticality.high
    elif env_tag in ["stage", "staging", "uat"]:
        return Criticality.medium
    elif env_tag in ["dev", "test"]:
        return Criticality.low

    if resource_type in ["database", "rds"]:
        return Criticality.critical
    if resource_type in ["vpc", "load_balancer"]:
        return Criticality.high

    return default

def _get_estimated_cost(resource_type: str, key: str, default: float = 0.0) -> float:
    """Estimates monthly cost from standard pricing table."""
    return INSTANCE_COST_TABLE.get(key, default)

class AWSInfrastructureCollector:
    """
    Discovers actual AWS infrastructure via Boto3 and extracts deterministic topology.
    """
    def __init__(self, session: Optional[boto3.Session] = None, region_name: Optional[str] = None):
        self.session = session or get_boto3_session(region_name)
        self.region = self.session.region_name or "us-east-1"

    def collect_vpcs(self) -> List[Dict[str, Any]]:
        """Discovers VPCs."""
        components = []
        ec2 = self.session.client("ec2")

        try:
            response = ec2.describe_vpcs()
            for vpc in response.get("Vpcs", []):
                vpc_id = vpc["VpcId"]
                tags = _parse_tags(vpc.get("Tags"))
                name = tags.get("Name", vpc_id)
                cidr = vpc.get("CidrBlock", "")
                is_default = vpc.get("IsDefault", False)
                state = vpc.get("State", "available")
                crit = _derive_criticality(tags, "vpc", Criticality.high)

                components.append({
                    "id": vpc_id,
                    "name": f"VPC: {name}",
                    "type": ComponentType.vpc,
                    "environment": Environment.cloud,
                    "location": self.region,
                    "criticality": crit,
                    "owner": tags.get("Owner", "Cloud Network"),
                    "status": Status.active if state == "available" else Status.degraded,
                    "cost_per_month": 0.0,
                    "arn": f"arn:aws:ec2:{self.region}:{vpc.get('OwnerId', '')}:vpc/{vpc_id}",
                    "aws_region": self.region,
                    "metadata_col": {
                        "cidr_block": cidr,
                        "is_default": is_default,
                        "state": state,
                        "discovery_source": "aws_api",
                        "tags": tags
                    }
                })
        except Exception as e:
            logger.error("Error describing VPCs: %s", str(e))
        return components

    def collect_subnets(self) -> List[Dict[str, Any]]:
        """Discovers Subnets."""
        components = []
        ec2 = self.session.client("ec2")

        try:
            response = ec2.describe_subnets()
            for subnet in response.get("Subnets", []):
                subnet_id = subnet["SubnetId"]
                vpc_id = subnet.get("VpcId")
                az = subnet.get("AvailabilityZone", self.region)
                tags = _parse_tags(subnet.get("Tags"))
                name = tags.get("Name", subnet_id)
                cidr = subnet.get("CidrBlock", "")
                state = subnet.get("State", "available")
                crit = _derive_criticality(tags, "subnet", Criticality.medium)

                components.append({
                    "id": subnet_id,
                    "name": f"Subnet: {name}",
                    "type": ComponentType.subnet,
                    "environment": Environment.cloud,
                    "location": az,
                    "criticality": crit,
                    "owner": tags.get("Owner", "Cloud Network"),
                    "status": Status.active if state == "available" else Status.degraded,
                    "cost_per_month": 0.0,
                    "arn": subnet.get("SubnetArn"),
                    "aws_region": self.region,
                    "metadata_col": {
                        "cidr_block": cidr,
                        "vpc_id": vpc_id,
                        "az": az,
                        "available_ip_count": subnet.get("AvailableIpAddressCount", 0),
                        "discovery_source": "aws_api",
                        "tags": tags
                    }
                })
        except Exception as e:
            logger.error("Error describing Subnets: %s", str(e))
        return components

    def collect_security_groups(self) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Discovers Security Groups and extracts inbound rules for graph building."""
        components = []
        rules = {}
        ec2 = self.session.client("ec2")

        try:
            response = ec2.describe_security_groups()
            for sg in response.get("SecurityGroups", []):
                sg_id = sg["GroupId"]
                vpc_id = sg.get("VpcId")
                name = sg.get("GroupName", sg_id)
                desc = sg.get("Description", "")
                tags = _parse_tags(sg.get("Tags"))

                inbound_parsed = []
                for perm in sg.get("IpPermissions", []):
                    from_p = perm.get("FromPort")
                    to_p = perm.get("ToPort")
                    proto = perm.get("IpProtocol")
                    allowed_sgs = [pair.get("GroupId") for pair in perm.get("UserIdGroupPairs", []) if pair.get("GroupId")]
                    inbound_parsed.append({
                        "from_port": from_p,
                        "to_port": to_p,
                        "protocol": proto,
                        "allowed_security_groups": allowed_sgs
                    })
                rules[sg_id] = {
                    "inbound": inbound_parsed,
                    "vpc_id": vpc_id
                }

                components.append({
                    "id": sg_id,
                    "name": f"SG: {name}",
                    "type": ComponentType.security_group,
                    "environment": Environment.cloud,
                    "location": self.region,
                    "criticality": Criticality.medium,
                    "owner": tags.get("Owner", "SecOps"),
                    "status": Status.active,
                    "cost_per_month": 0.0,
                    "arn": f"arn:aws:ec2:{self.region}::security-group/{sg_id}",
                    "aws_region": self.region,
                    "metadata_col": {
                        "description": desc,
                        "vpc_id": vpc_id,
                        "inbound_rules_count": len(sg.get("IpPermissions", [])),
                        "outbound_rules_count": len(sg.get("IpPermissionsEgress", [])),
                        "discovery_source": "aws_api",
                        "tags": tags
                    }
                })
        except Exception as e:
            logger.error("Error describing Security Groups: %s", str(e))
        return components, rules

    def collect_ec2_instances(self) -> Tuple[List[Dict[str, Any]], Set[str]]:
        """Discovers EC2 instances and attached IAM profiles."""
        components = []
        profile_names = set()
        ec2 = self.session.client("ec2")

        try:
            response = ec2.describe_instances()
            for res in response.get("Reservations", []):
                for inst in res.get("Instances", []):
                    inst_id = inst["InstanceId"]
                    inst_type = inst.get("InstanceType", "t3.medium")
                    state_name = inst.get("State", {}).get("Name", "running")
                    az = inst.get("Placement", {}).get("AvailabilityZone", self.region)
                    subnet_id = inst.get("SubnetId")
                    vpc_id = inst.get("VpcId")
                    tags = _parse_tags(inst.get("Tags"))
                    name = tags.get("Name", inst_id)

                    inst_profile = inst.get("IamInstanceProfile", {})
                    profile_arn = inst_profile.get("Arn")
                    profile_name = profile_arn.split("/")[-1] if profile_arn else None
                    if profile_name:
                        profile_names.add(profile_name)

                    status = Status.active if state_name == "running" else (Status.offline if state_name == "stopped" else Status.degraded)
                    crit = _derive_criticality(tags, "ec2", Criticality.high)
                    monthly_cost = _get_estimated_cost("ec2", inst_type, default=45.0)

                    components.append({
                        "id": inst_id,
                        "name": f"EC2: {name}",
                        "type": ComponentType.server,
                        "environment": Environment.cloud,
                        "location": az,
                        "criticality": crit,
                        "owner": tags.get("Owner", "Cloud Ops"),
                        "status": status,
                        "cpu": float(inst.get("CpuOptions", {}).get("CoreCount", 2)),
                        "cost_per_month": monthly_cost,
                        "arn": f"arn:aws:ec2:{self.region}::instance/{inst_id}",
                        "aws_region": self.region,
                        "metadata_col": {
                            "instance_type": inst_type,
                            "state": state_name,
                            "private_ip": inst.get("PrivateIpAddress"),
                            "public_ip": inst.get("PublicIpAddress"),
                            "subnet_id": subnet_id,
                            "vpc_id": vpc_id,
                            "security_groups": [sg.get("GroupId") for sg in inst.get("SecurityGroups", []) if sg.get("GroupId")],
                            "iam_instance_profile": profile_name,
                            "launch_time": str(inst.get("LaunchTime")),
                            "discovery_source": "aws_api",
                            "tags": tags
                        }
                    })
        except Exception as e:
            logger.error("Error describing EC2 instances: %s", str(e))
        return components, profile_names

    def collect_rds_instances(self) -> List[Dict[str, Any]]:
        """Discovers RDS Database instances with port, VPC, subnet, and SG metadata."""
        components = []
        rds = self.session.client("rds")

        try:
            response = rds.describe_db_instances()
            for db_inst in response.get("DBInstances", []):
                db_id = db_inst["DBInstanceIdentifier"]
                engine = db_inst.get("Engine", "postgres")
                db_class = db_inst.get("DBInstanceClass", "db.t3.medium")
                status_raw = db_inst.get("DBInstanceStatus", "available")
                az = db_inst.get("AvailabilityZone", self.region)
                multi_az = db_inst.get("MultiAZ", False)
                endpoint = db_inst.get("Endpoint", {}).get("Address", "")
                db_port = db_inst.get("Endpoint", {}).get("Port", 5432)
                tags = _parse_tags(db_inst.get("TagList"))

                subnet_group = db_inst.get("DBSubnetGroup", {})
                vpc_id = subnet_group.get("VpcId")
                subnet_ids = [sub.get("SubnetIdentifier") for sub in subnet_group.get("Subnets", []) if sub.get("SubnetIdentifier")]
                security_groups = [sg.get("VpcSecurityGroupId") for sg in db_inst.get("VpcSecurityGroups", []) if sg.get("VpcSecurityGroupId")]

                status = Status.active if status_raw == "available" else Status.degraded
                crit = _derive_criticality(tags, "database", Criticality.critical)
                monthly_cost = _get_estimated_cost("rds", db_class, default=95.0)

                components.append({
                    "id": f"rds-{db_id}",
                    "name": f"RDS: {db_id} ({engine})",
                    "type": ComponentType.database,
                    "environment": Environment.cloud,
                    "location": az,
                    "criticality": crit,
                    "owner": tags.get("Owner", "Data Team"),
                    "status": status,
                    "cost_per_month": monthly_cost,
                    "arn": db_inst.get("DBInstanceArn"),
                    "aws_region": self.region,
                    "metadata_col": {
                        "engine": engine,
                        "engine_version": db_inst.get("EngineVersion"),
                        "db_class": db_class,
                        "multi_az": multi_az,
                        "endpoint": endpoint,
                        "port": db_port,
                        "vpc_id": vpc_id,
                        "subnet_ids": subnet_ids,
                        "security_groups": security_groups,
                        "allocated_storage_gb": db_inst.get("AllocatedStorage", 20),
                        "discovery_source": "aws_api",
                        "tags": tags
                    }
                })
        except Exception as e:
            logger.error("Error describing RDS instances: %s", str(e))
        return components

    def collect_load_balancers(self) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Discovers Load Balancers and target health descriptions."""
        components = []
        target_health_records = []
        elbv2 = self.session.client("elbv2")

        try:
            response = elbv2.describe_load_balancers()
            for alb in response.get("LoadBalancers", []):
                alb_arn = alb["LoadBalancerArn"]
                alb_name = alb.get("LoadBalancerName", "alb")
                alb_type = alb.get("Type", "application")
                dns_name = alb.get("DNSName", "")
                vpc_id = alb.get("VpcId")
                state = alb.get("State", {}).get("Code", "active")
                alb_id = f"alb-{alb_name}"
                subnet_ids = [az.get("SubnetId") for az in alb.get("AvailabilityZones", []) if az.get("SubnetId")]
                security_groups = alb.get("SecurityGroups", [])

                components.append({
                    "id": alb_id,
                    "name": f"ALB: {alb_name}",
                    "type": ComponentType.load_balancer,
                    "environment": Environment.cloud,
                    "location": self.region,
                    "criticality": Criticality.high,
                    "owner": "Network Ops",
                    "status": Status.active if state == "active" else Status.degraded,
                    "cost_per_month": INSTANCE_COST_TABLE.get("alb_base", 22.50),
                    "arn": alb_arn,
                    "aws_region": self.region,
                    "metadata_col": {
                        "dns_name": dns_name,
                        "type": alb_type,
                        "scheme": alb.get("Scheme"),
                        "vpc_id": vpc_id,
                        "subnet_ids": subnet_ids,
                        "security_groups": security_groups,
                        "discovery_source": "aws_api"
                    }
                })

                # Discover target groups to determine deterministic route: ALB -> EC2 Target
                try:
                    tg_res = elbv2.describe_target_groups(LoadBalancerArn=alb_arn)
                    for tg in tg_res.get("TargetGroups", []):
                        tg_arn = tg.get("TargetGroupArn")
                        tg_proto = tg.get("Protocol", "HTTP")
                        tg_port = tg.get("Port", 80)
                        health_res = elbv2.describe_target_health(TargetGroupArn=tg_arn)
                        for target in health_res.get("TargetHealthDescriptions", []):
                            target_id = target.get("Target", {}).get("Id")
                            t_port = target.get("Target", {}).get("Port") or tg_port
                            target_state = target.get("TargetHealth", {}).get("State", "healthy")
                            if target_id:
                                target_health_records.append({
                                    "load_balancer_id": alb_id,
                                    "target_id": target_id,
                                    "target_group_arn": tg_arn,
                                    "port": t_port,
                                    "protocol": tg_proto,
                                    "state": target_state
                                })
                except Exception as tg_err:
                    logger.debug("Could not inspect target groups for %s: %s", alb_name, str(tg_err))

        except Exception as e:
            logger.error("Error describing Load Balancers: %s", str(e))
        return components, target_health_records

    def collect_s3_buckets(self) -> List[Dict[str, Any]]:
        """Discovers S3 storage buckets and determines actual bucket region via GetBucketLocation."""
        components = []
        s3 = self.session.client("s3")

        try:
            response = s3.list_buckets()
            for b in response.get("Buckets", []):
                b_name = b["Name"]
                bucket_region = self.region
                loc_status = "resolved"

                try:
                    loc_res = s3.get_bucket_location(Bucket=b_name)
                    loc_constraint = loc_res.get("LocationConstraint")
                    # AWS returns None or "" for us-east-1, and "EU" for eu-west-1
                    if loc_constraint is None or loc_constraint == "":
                        bucket_region = "us-east-1"
                    elif loc_constraint == "EU":
                        bucket_region = "eu-west-1"
                    else:
                        bucket_region = str(loc_constraint)
                except Exception as loc_err:
                    logger.debug("Could not determine bucket location for %s: %s", b_name, str(loc_err))
                    loc_status = "fallback_or_access_denied"

                components.append({
                    "id": f"s3-{b_name}",
                    "name": f"S3: {b_name}",
                    "type": ComponentType.storage,
                    "environment": Environment.cloud,
                    "location": bucket_region,
                    "criticality": Criticality.medium,
                    "owner": "Cloud Ops",
                    "status": Status.active,
                    "cost_per_month": INSTANCE_COST_TABLE.get("s3_baseline", 5.00),
                    "arn": f"arn:aws:s3:::{b_name}",
                    "aws_region": bucket_region,
                    "metadata_col": {
                        "creation_date": str(b.get("CreationDate")),
                        "discovery_source": "aws_api",
                        "bucket_region": bucket_region,
                        "location_status": loc_status
                    }
                })
        except Exception as e:
            logger.error("Error listing S3 buckets: %s", str(e))
        return components

    def collect_iam_instance_profiles(self, profile_names: Set[str]) -> Dict[str, Any]:
        """Inspects IAM instance profiles and attached policies for S3 bucket access."""
        iam = self.session.client("iam")
        profiles_data = {}
        for pname in profile_names:
            try:
                prof = iam.get_instance_profile(InstanceProfileName=pname)
                roles = prof.get("InstanceProfile", {}).get("Roles", [])
                allowed_buckets = []
                role_names = []
                for role in roles:
                    rname = role.get("RoleName")
                    role_names.append(rname)
                    # Check inline policies
                    try:
                        inline_res = iam.list_role_policies(RoleName=rname)
                        for pol_name in inline_res.get("PolicyNames", []):
                            pol_doc = iam.get_role_policy(RoleName=rname, PolicyName=pol_name)
                            doc = pol_doc.get("PolicyDocument", {})
                            allowed_buckets.extend(self._extract_s3_buckets_from_doc(doc))
                    except Exception:
                        pass
                    # Check attached managed policies
                    try:
                        attached_res = iam.list_attached_role_policies(RoleName=rname)
                        for att in attached_res.get("AttachedPolicies", []):
                            pol_arn = att.get("PolicyArn")
                            pol_info = iam.get_policy(PolicyArn=pol_arn)
                            v_id = pol_info.get("Policy", {}).get("DefaultVersionId")
                            v_doc = iam.get_policy_version(PolicyArn=pol_arn, VersionId=v_id)
                            doc = v_doc.get("PolicyVersion", {}).get("Document", {})
                            allowed_buckets.extend(self._extract_s3_buckets_from_doc(doc))
                    except Exception:
                        pass
                profiles_data[pname] = {
                    "role_name": role_names[0] if role_names else pname,
                    "allowed_s3_buckets": list(set(allowed_buckets)),
                    "actions": ["s3:GetObject", "s3:PutObject"]
                }
            except Exception as e:
                logger.debug("IAM profile %s inspection skipped/restricted: %s", pname, str(e))
        return profiles_data

    def _extract_s3_buckets_from_doc(self, doc: Dict[str, Any]) -> List[str]:
        """Extracts referenced S3 bucket names from IAM Policy document."""
        buckets = []
        statements = doc.get("Statement", [])
        if isinstance(statements, dict):
            statements = [statements]
        for stmt in statements:
            if stmt.get("Effect") != "Allow":
                continue
            resources = stmt.get("Resource", [])
            if isinstance(resources, str):
                resources = [resources]
            for res in resources:
                if "arn:aws:s3:::" in res:
                    bname = res.split("arn:aws:s3:::")[-1].split("/")[0].replace("*", "")
                    if bname:
                        buckets.append(bname)
        return buckets

def collect_health_events(session: Optional[boto3.Session] = None) -> Dict[str, Any]:
    """
    Discovers active/upcoming AWS Health events and affected infrastructure entities.
    Requires us-east-1 global endpoint. Gracefully handles accounts without Business/Enterprise support.
    Never fabricates fake health events.
    """
    if session is None:
        session = get_boto3_session()

    auth_status = check_aws_credentials(session)
    if not auth_status["authenticated"]:
        return {
            "authenticated": False,
            "health_available": False,
            "open_events_count": 0,
            "events": [],
            "source": "AWS Health API",
            "support_plan_required": False,
            "error": auth_status.get("error")
        }

    try:
        # AWS Health API endpoint is ONLY in us-east-1
        health = session.client("health", region_name="us-east-1")
        response = health.describe_events(
            filter={
                "eventStatusCodes": ["open", "upcoming"]
            },
            maxResults=25
        )

        events_raw = response.get("events", [])
        parsed_events = []

        if events_raw:
            event_arns = [e["arn"] for e in events_raw if "arn" in e]
            
            # Fetch detailed descriptions
            details_map = {}
            try:
                details_res = health.describe_event_details(eventArns=event_arns[:10])
                for detail in details_res.get("successfulSet", []):
                    arn = detail.get("event", {}).get("arn")
                    desc = detail.get("eventDescription", {}).get("latestDescription")
                    if arn and desc:
                        details_map[arn] = desc
            except Exception as d_err:
                logger.debug("Could not fetch health event details: %s", str(d_err))

            # Fetch affected entities
            entities_map = {}
            try:
                entities_res = health.describe_affected_entities(
                    filter={"eventArns": event_arns[:10]}
                )
                for ent in entities_res.get("entities", []):
                    arn = ent.get("eventArn")
                    val = ent.get("entityValue")
                    if arn and val:
                        entities_map.setdefault(arn, []).append(val)
            except Exception as e_err:
                logger.debug("Could not fetch affected health entities: %s", str(e_err))

            for e in events_raw:
                arn = e.get("arn", "")
                parsed_events.append({
                    "arn": arn,
                    "service": e.get("service", "AWS"),
                    "event_type_code": e.get("eventTypeCode", "ISSUE"),
                    "event_type_category": e.get("eventTypeCategory", "issue"),
                    "region": e.get("region", "global"),
                    "start_time": str(e.get("startTime")),
                    "end_time": str(e.get("endTime")) if e.get("endTime") else None,
                    "status_code": e.get("statusCode", "open"),
                    "description": details_map.get(arn, "AWS infrastructure notification"),
                    "affected_entities": entities_map.get(arn, [])
                })

        return {
            "authenticated": True,
            "health_available": True,
            "open_events_count": len(parsed_events),
            "events": parsed_events,
            "source": "AWS Health API (Global us-east-1)",
            "support_plan_required": False,
            "error": None
        }

    except ClientError as e:
        err_code = e.response.get("Error", {}).get("Code", "")
        err_msg = e.response.get("Error", {}).get("Message", str(e))
        is_sub_req = err_code == "SubscriptionRequiredException" or "subscription" in err_msg.lower()
        
        logger.info("AWS Health API check: %s (%s)", err_code, err_msg)
        return {
            "authenticated": True,
            "health_available": False,
            "open_events_count": 0,
            "events": [],
            "source": "AWS Health API",
            "support_plan_required": is_sub_req,
            "error": "AWS Health API requires an active AWS Business or Enterprise Support plan." if is_sub_req else err_msg
        }
    except Exception as e:
        logger.warning("AWS Health API error: %s", str(e))
        return {
            "authenticated": True,
            "health_available": False,
            "open_events_count": 0,
            "events": [],
            "source": "AWS Health API",
            "support_plan_required": False,
            "error": str(e)
        }

    def collect_all(self) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
        """
        Executes full resource collection and derives the deterministic dependency graph.
        """
        all_components: List[Dict[str, Any]] = []

        logger.info("Starting AWS resource collection in region: %s", self.region)
        vpcs = self.collect_vpcs()
        all_components.extend(vpcs)

        subnets = self.collect_subnets()
        all_components.extend(subnets)

        sgs, sg_rules = self.collect_security_groups()
        all_components.extend(sgs)

        instances, profile_names = self.collect_ec2_instances()
        all_components.extend(instances)

        dbs = self.collect_rds_instances()
        all_components.extend(dbs)

        albs, target_health = self.collect_load_balancers()
        all_components.extend(albs)

        s3s = self.collect_s3_buckets()
        all_components.extend(s3s)

        iam_profiles = self.collect_iam_instance_profiles(profile_names)

        # Build actual infrastructure dependency graph
        builder = AWSDependencyGraphBuilder(all_components)
        all_dependencies = builder.build_all(
            target_health_records=target_health,
            security_group_rules=sg_rules,
            iam_instance_profiles=iam_profiles
        )

        summary = {
            "vpcs": len(vpcs),
            "subnets": len(subnets),
            "security_groups": len(sgs),
            "ec2_instances": len(instances),
            "rds_databases": len(dbs),
            "load_balancers": len(albs),
            "s3_buckets": len(s3s),
            "total_components": len(all_components),
            "total_dependencies": len(all_dependencies)
        }
        logger.info("Collection complete. Discovered %d components, %d dependencies.", len(all_components), len(all_dependencies))
        return all_components, all_dependencies, summary


def generate_synthetic_aws_data(region: str = "us-east-1") -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    """
    Generates a realistic, high-fidelity synthetic AWS environment for development/testing
    when real AWS credentials are not configured or when testing offline.
    Uses the exact same AWSDependencyGraphBuilder to construct relationships deterministically.
    """
    vpc_id = "vpc-0a81729b14c3"
    subnet_pub_1a = "subnet-0192a83f1a"
    subnet_priv_1a = "subnet-0283b94c2a"
    subnet_priv_1b = "subnet-0394c05d3b"
    sg_web = "sg-01a2b3c4d5"
    sg_db = "sg-06e7f8a9b0"
    ec2_app_1 = "i-09f182c81a2b"
    ec2_app_2 = "i-03a89e1b2c3d"
    rds_id = "rds-prod-analytics-db"
    alb_id = "alb-prod-ingress"
    s3_id = "s3-enterprise-datalake"

    components = [
        # VPC
        {
            "id": vpc_id,
            "name": "VPC: Production-VPC",
            "type": ComponentType.vpc,
            "environment": Environment.cloud,
            "location": region,
            "criticality": Criticality.critical,
            "owner": "Cloud Network Ops",
            "status": Status.active,
            "cost_per_month": 0.0,
            "arn": f"arn:aws:ec2:{region}:123456789012:vpc/{vpc_id}",
            "aws_region": region,
            "metadata_col": {"cidr_block": "10.0.0.0/16", "is_default": False, "discovery_source": "aws_synthetic"}
        },
        # Subnets
        {
            "id": subnet_pub_1a,
            "name": "Subnet: Public-Ingress-1a",
            "type": ComponentType.subnet,
            "environment": Environment.cloud,
            "location": f"{region}a",
            "criticality": Criticality.high,
            "owner": "Cloud Network Ops",
            "status": Status.active,
            "cost_per_month": 0.0,
            "arn": f"arn:aws:ec2:{region}:123456789012:subnet/{subnet_pub_1a}",
            "aws_region": region,
            "metadata_col": {"cidr_block": "10.0.1.0/24", "az": f"{region}a", "vpc_id": vpc_id, "discovery_source": "aws_synthetic"}
        },
        {
            "id": subnet_priv_1a,
            "name": "Subnet: App-Private-1a",
            "type": ComponentType.subnet,
            "environment": Environment.cloud,
            "location": f"{region}a",
            "criticality": Criticality.high,
            "owner": "Cloud Network Ops",
            "status": Status.active,
            "cost_per_month": 0.0,
            "arn": f"arn:aws:ec2:{region}:123456789012:subnet/{subnet_priv_1a}",
            "aws_region": region,
            "metadata_col": {"cidr_block": "10.0.10.0/24", "az": f"{region}a", "vpc_id": vpc_id, "discovery_source": "aws_synthetic"}
        },
        {
            "id": subnet_priv_1b,
            "name": "Subnet: DB-Private-1b",
            "type": ComponentType.subnet,
            "environment": Environment.cloud,
            "location": f"{region}b",
            "criticality": Criticality.critical,
            "owner": "Cloud Network Ops",
            "status": Status.active,
            "cost_per_month": 0.0,
            "arn": f"arn:aws:ec2:{region}:123456789012:subnet/{subnet_priv_1b}",
            "aws_region": region,
            "metadata_col": {"cidr_block": "10.0.20.0/24", "az": f"{region}b", "vpc_id": vpc_id, "discovery_source": "aws_synthetic"}
        },
        # Security Groups
        {
            "id": sg_web,
            "name": "SG: Web-Ingress-SG",
            "type": ComponentType.security_group,
            "environment": Environment.cloud,
            "location": region,
            "criticality": Criticality.medium,
            "owner": "SecOps",
            "status": Status.active,
            "cost_per_month": 0.0,
            "arn": f"arn:aws:ec2:{region}:123456789012:security-group/{sg_web}",
            "aws_region": region,
            "metadata_col": {"description": "Inbound 443 from Internet", "vpc_id": vpc_id, "discovery_source": "aws_synthetic"}
        },
        {
            "id": sg_db,
            "name": "SG: DB-Access-SG",
            "type": ComponentType.security_group,
            "environment": Environment.cloud,
            "location": region,
            "criticality": Criticality.high,
            "owner": "SecOps",
            "status": Status.active,
            "cost_per_month": 0.0,
            "arn": f"arn:aws:ec2:{region}:123456789012:security-group/{sg_db}",
            "aws_region": region,
            "metadata_col": {"description": "Inbound 5432 from App subnet", "vpc_id": vpc_id, "discovery_source": "aws_synthetic"}
        },
        # Load Balancer
        {
            "id": alb_id,
            "name": "ALB: prod-ingress-alb",
            "type": ComponentType.load_balancer,
            "environment": Environment.cloud,
            "location": region,
            "criticality": Criticality.high,
            "owner": "Network Ops",
            "status": Status.active,
            "cost_per_month": 22.50,
            "arn": f"arn:aws:elasticloadbalancing:{region}:123456789012:loadbalancer/app/{alb_id}",
            "aws_region": region,
            "metadata_col": {
                "dns_name": "prod-ingress-alb.elb.amazonaws.com",
                "scheme": "internet-facing",
                "vpc_id": vpc_id,
                "subnet_ids": [subnet_pub_1a],
                "security_groups": [sg_web],
                "discovery_source": "aws_synthetic"
            }
        },
        # EC2 Instances
        {
            "id": ec2_app_1,
            "name": "EC2: Prod-API-Cluster-01",
            "type": ComponentType.server,
            "environment": Environment.cloud,
            "location": f"{region}a",
            "criticality": Criticality.high,
            "owner": "Cloud Ops",
            "status": Status.active,
            "cpu": 4.0,
            "cost_per_month": 140.16,
            "arn": f"arn:aws:ec2:{region}:123456789012:instance/{ec2_app_1}",
            "aws_region": region,
            "metadata_col": {
                "instance_type": "m5.xlarge",
                "private_ip": "10.0.10.45",
                "subnet_id": subnet_priv_1a,
                "vpc_id": vpc_id,
                "security_groups": [sg_web],
                "iam_instance_profile": "ProdAppInstanceRole",
                "discovery_source": "aws_synthetic"
            }
        },
        {
            "id": ec2_app_2,
            "name": "EC2: Prod-API-Cluster-02",
            "type": ComponentType.server,
            "environment": Environment.cloud,
            "location": f"{region}a",
            "criticality": Criticality.high,
            "owner": "Cloud Ops",
            "status": Status.active,
            "cpu": 4.0,
            "cost_per_month": 140.16,
            "arn": f"arn:aws:ec2:{region}:123456789012:instance/{ec2_app_2}",
            "aws_region": region,
            "metadata_col": {
                "instance_type": "m5.xlarge",
                "private_ip": "10.0.10.46",
                "subnet_id": subnet_priv_1a,
                "vpc_id": vpc_id,
                "security_groups": [sg_web],
                "iam_instance_profile": "ProdAppInstanceRole",
                "discovery_source": "aws_synthetic"
            }
        },
        # RDS Database
        {
            "id": rds_id,
            "name": "RDS: prod-analytics-postgres",
            "type": ComponentType.database,
            "environment": Environment.cloud,
            "location": f"{region}b",
            "criticality": Criticality.critical,
            "owner": "Data Team",
            "status": Status.active,
            "cost_per_month": 259.88,
            "arn": f"arn:aws:rds:{region}:123456789012:db:{rds_id}",
            "aws_region": region,
            "metadata_col": {
                "engine": "postgres",
                "engine_version": "15.4",
                "multi_az": True,
                "port": 5432,
                "endpoint": "prod-analytics-postgres.internal.aws.corp",
                "vpc_id": vpc_id,
                "subnet_ids": [subnet_priv_1b],
                "security_groups": [sg_db],
                "discovery_source": "aws_synthetic"
            }
        },
        # S3 Bucket
        {
            "id": s3_id,
            "name": "S3: enterprise-datalake-prod",
            "type": ComponentType.storage,
            "environment": Environment.cloud,
            "location": region,
            "criticality": Criticality.high,
            "owner": "Data Team",
            "status": Status.active,
            "cost_per_month": 35.0,
            "arn": f"arn:aws:s3:::{s3_id}",
            "aws_region": region,
            "metadata_col": {"discovery_source": "aws_synthetic"}
        }
    ]

    target_health = [
        {
            "load_balancer_id": alb_id,
            "target_id": ec2_app_1,
            "target_group_arn": f"arn:aws:elasticloadbalancing:{region}:123456789012:targetgroup/prod-app-tg",
            "port": 8080,
            "protocol": "HTTP",
            "state": "healthy"
        },
        {
            "load_balancer_id": alb_id,
            "target_id": ec2_app_2,
            "target_group_arn": f"arn:aws:elasticloadbalancing:{region}:123456789012:targetgroup/prod-app-tg",
            "port": 8080,
            "protocol": "HTTP",
            "state": "healthy"
        }
    ]

    security_group_rules = {
        sg_web: {
            "inbound": [
                {"from_port": 443, "to_port": 443, "protocol": "tcp", "allowed_security_groups": []}
            ],
            "vpc_id": vpc_id
        },
        sg_db: {
            "inbound": [
                {"from_port": 5432, "to_port": 5432, "protocol": "tcp", "allowed_security_groups": [sg_web]}
            ],
            "vpc_id": vpc_id
        }
    }

    iam_instance_profiles = {
        "ProdAppInstanceRole": {
            "role_name": "ProdAppInstanceRole",
            "allowed_s3_buckets": [s3_id, "enterprise-datalake-prod"],
            "actions": ["s3:GetObject", "s3:PutObject"]
        }
    }

    builder = AWSDependencyGraphBuilder(components)
    dependencies = builder.build_all(
        target_health_records=target_health,
        security_group_rules=security_group_rules,
        iam_instance_profiles=iam_instance_profiles
    )

    summary = {
        "vpcs": 1,
        "subnets": 3,
        "security_groups": 2,
        "ec2_instances": 2,
        "rds_databases": 1,
        "load_balancers": 1,
        "s3_buckets": 1,
        "total_components": len(components),
        "total_dependencies": len(dependencies)
    }
    return components, dependencies, summary


def sync_aws_to_db(
    db,
    mode: str = "merge",
    use_synthetic: bool = False,
    region: Optional[str] = None
) -> Dict[str, Any]:
    """
    Coordinates AWS collection and writes normalized infrastructure data into SQLite.
    - Preserves existing on-prem/seed data if mode='merge'.
    - If credentials are valid, queries real AWS APIs.
    - If credentials are not present and use_synthetic=True, uses synthetic AWS dataset.
    """
    session = get_boto3_session(region)
    auth_status = check_aws_credentials(session)

    if auth_status["authenticated"]:
        collector = AWSInfrastructureCollector(session, region)
        raw_components, raw_dependencies, summary = collector.collect_all()
        data_source = "aws_api"
        account_id = auth_status.get("account_id")
    elif use_synthetic:
        logger.info("Using synthetic AWS provider (offline mode)")
        raw_components, raw_dependencies, summary = generate_synthetic_aws_data(region or "us-east-1")
        data_source = "aws_synthetic"
        account_id = "synthetic-123456789012"
    else:
        return {
            "success": False,
            "message": f"AWS Authentication failed: {auth_status.get('error')}. Pass use_synthetic=True for offline demo.",
            "data_source": "none",
            "account_id": None,
            "region": session.region_name,
            "components_added": 0,
            "components_updated": 0,
            "dependencies_added": 0,
            "total_components": db.query(models.Component).count(),
            "total_dependencies": db.query(models.Dependency).count(),
        }

    # Upsert or replace in database
    components_added = 0
    components_updated = 0
    dependencies_added = 0

    if mode == "replace":
        # Full clean wipe of previous environment data for complete isolation
        db.query(models.MetricSnapshot).delete(synchronize_session=False)
        db.query(models.Dependency).delete(synchronize_session=False)
        db.query(models.Component).delete(synchronize_session=False)
        db.commit()

    # Upsert components
    now_iso = datetime.now(timezone.utc).isoformat()
    for comp_data in raw_components:
        comp_data["discovery_source"] = data_source
        comp_data["account_id"] = account_id
        comp_data["updated_at"] = now_iso
        existing = db.query(models.Component).filter_by(id=comp_data["id"]).first()
        if existing:
            for k, v in comp_data.items():
                setattr(existing, k, v)
            components_updated += 1
        else:
            comp = models.Component(**comp_data)
            db.add(comp)
            components_added += 1

    db.commit()

    # Insert dependencies (avoid duplicates and verify foreign keys)
    for dep_data in raw_dependencies:
        src_id = dep_data.get("source_component_id") or dep_data.get("source_id")
        tgt_id = dep_data.get("target_component_id") or dep_data.get("target_id")
        rel_type = dep_data.get("relationship_type")
        if hasattr(rel_type, "value"):
            rel_type = rel_type.value

        source_exists = db.query(models.Component).filter_by(id=src_id).first()
        target_exists = db.query(models.Component).filter_by(id=tgt_id).first()
        if not source_exists or not target_exists:
            continue

        existing_dep = db.query(models.Dependency).filter(
            (
                (models.Dependency.source_component_id == src_id) |
                (models.Dependency.source_id == src_id)
            ),
            (
                (models.Dependency.target_component_id == tgt_id) |
                (models.Dependency.target_id == tgt_id)
            ),
            models.Dependency.relationship_type == rel_type
        ).first()

        if not existing_dep:
            dep = models.Dependency(
                source_component_id=src_id,
                target_component_id=tgt_id,
                source_id=src_id,
                target_id=tgt_id,
                relationship_type=rel_type,
                criticality=dep_data.get("criticality", models.Criticality.medium),
                source=dep_data.get("source", dep_data.get("discovery_source", data_source)),
                discovery_source=dep_data.get("source", dep_data.get("discovery_source", data_source)),
                metadata_col=dep_data.get("metadata", dep_data.get("metadata_col", {}))
            )
            db.add(dep)
            dependencies_added += 1

    db.commit()

    # Update persistent twin_state in SQLite
    try:
        state = db.query(models.TwinState).filter_by(id=1).first()
        if not state:
            state = models.TwinState(id=1)
            db.add(state)
        state.mode = "live" if data_source == "aws_api" else "demo"
        state.account_id = account_id
        state.arn = auth_status.get("arn") if auth_status.get("authenticated") else None
        state.region = session.region_name
        state.discovery_status = "completed" if len(raw_components) > 0 else "empty"
        state.discovery_summary = summary
        state.last_sync = now_iso
        state.error = None
        db.commit()
    except Exception as state_err:
        logger.warning("Could not update twin_state table: %s", str(state_err))

    # Automatic initial metrics ingestion
    if len(raw_components) > 0:
        try:
            import metrics_collector
            metrics_collector.collect_and_store_metrics(
                db=db,
                use_synthetic=(data_source == "aws_synthetic"),
                region=session.region_name
            )
        except Exception as m_err:
            logger.debug("Initial metrics collection after discovery: %s", str(m_err))

    total_comps = db.query(models.Component).count()
    total_deps = db.query(models.Dependency).count()

    return {
        "success": True,
        "message": f"Successfully synchronized {len(raw_components)} AWS components into Digital Twin.",
        "data_source": data_source,
        "account_id": account_id,
        "region": session.region_name,
        "components_added": components_added,
        "components_updated": components_updated,
        "dependencies_added": dependencies_added,
        "total_components": total_comps,
        "total_dependencies": total_deps,
        "summary": summary
    }

