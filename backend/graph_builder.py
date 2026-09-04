import logging
from typing import List, Dict, Any, Optional, Set, Tuple
from models import Criticality, DependencyType

logger = logging.getLogger("infratwin.graph_builder")

class AWSDependencyGraphBuilder:
    """
    Deterministic Dependency Graph Builder for AWS Infrastructure.
    
    CRITICAL RULE:
    DO NOT use ML, Gemini, embeddings, similarity, or heuristic prediction.
    All edges are constructed strictly from verified AWS configurations:
    - Target Group Health descriptions (ALB -> EC2)
    - Security Group ingress authorization rules matching EC2 SGs (EC2 -> RDS)
    - IAM Instance Profile policy statements granting S3 ARN access (EC2 -> S3)
    - Network interface placement and subnet groups (EC2/RDS/ALB -> Subnet/VPC)
    - Security group associations (EC2/RDS/ALB -> Security Group)
    """

    def __init__(self, components: List[Dict[str, Any]]):
        self.components = components
        self.component_ids: Set[str] = {c["id"] for c in components}
        self.components_by_id: Dict[str, Dict[str, Any]] = {c["id"]: c for c in components}
        self.dependencies: List[Dict[str, Any]] = []
        self._seen_edges: Set[Tuple[str, str, str]] = set()

    def add_edge(
        self,
        source_component_id: str,
        target_component_id: str,
        relationship_type: str,
        source: str,
        metadata: Optional[Dict[str, Any]] = None,
        criticality: Optional[Criticality] = None
    ) -> bool:
        """
        Adds a normalized dependency if and only if both endpoints exist in the Digital Twin.
        Eliminates duplicate edges.
        """
        if not source_component_id or not target_component_id:
            return False

        if source_component_id not in self.component_ids or target_component_id not in self.component_ids:
            logger.debug(
                "Skipping edge (%s -> %s): endpoint missing from registered components",
                source_component_id, target_component_id
            )
            return False

        edge_key = (source_component_id, target_component_id, relationship_type)
        if edge_key in self._seen_edges:
            return False

        self._seen_edges.add(edge_key)

        # Derive edge criticality if not explicitly provided
        if criticality is None:
            target_crit = self.components_by_id[target_component_id].get("criticality", Criticality.medium)
            if relationship_type in ["database_connection", "stores_in"]:
                criticality = Criticality.critical if target_crit == Criticality.critical else Criticality.high
            elif relationship_type in ["routes_traffic_to", "routes_to"]:
                criticality = Criticality.high
            else:
                criticality = target_crit

        dep = {
            "source_component_id": source_component_id,
            "target_component_id": target_component_id,
            "relationship_type": relationship_type,
            "source": source,
            "criticality": criticality,
            "metadata": metadata or {},
            # Backward compatibility fields
            "source_id": source_component_id,
            "target_id": target_component_id,
            "discovery_source": source
        }
        self.dependencies.append(dep)
        return True

    def build_network_containment(self):
        """
        Extracts structural containment relationships:
        - Subnet -> VPC (member_of_vpc)
        - Security Group -> VPC (member_of_vpc)
        - EC2 -> Subnet (enclosed_in_subnet)
        - EC2 -> VPC (member_of_vpc)
        - EC2 -> Security Groups (protected_by_security_group)
        - RDS -> Subnet (enclosed_in_subnet)
        - RDS -> VPC (member_of_vpc)
        - RDS -> Security Groups (protected_by_security_group)
        - ALB -> Subnet (deployed_in_subnet)
        - ALB -> VPC (member_of_vpc)
        - ALB -> Security Groups (protected_by_security_group)
        """
        for comp in self.components:
            cid = comp["id"]
            ctype = comp.get("type")
            meta = comp.get("metadata_col", {})

            # Subnet -> VPC
            if ctype == "subnet":
                vpc_id = meta.get("vpc_id")
                if vpc_id:
                    self.add_edge(
                        source_component_id=cid,
                        target_component_id=vpc_id,
                        relationship_type="member_of_vpc",
                        source="aws:ec2:describe_subnets",
                        metadata={"cidr_block": meta.get("cidr_block"), "az": meta.get("az")},
                        criticality=Criticality.high
                    )

            # Security Group -> VPC
            elif ctype == "security_group":
                vpc_id = meta.get("vpc_id")
                if vpc_id:
                    self.add_edge(
                        source_component_id=cid,
                        target_component_id=vpc_id,
                        relationship_type="member_of_vpc",
                        source="aws:ec2:describe_security_groups",
                        metadata={"description": meta.get("description")},
                        criticality=Criticality.medium
                    )

            # EC2 instance topology
            elif ctype == "server" and cid.startswith("i-"):
                subnet_id = meta.get("subnet_id")
                if subnet_id:
                    self.add_edge(
                        source_component_id=cid,
                        target_component_id=subnet_id,
                        relationship_type="enclosed_in_subnet",
                        source="aws:ec2:describe_instances",
                        metadata={"private_ip": meta.get("private_ip"), "az": comp.get("location")},
                        criticality=Criticality.high
                    )

                vpc_id = meta.get("vpc_id")
                if vpc_id:
                    self.add_edge(
                        source_component_id=cid,
                        target_component_id=vpc_id,
                        relationship_type="member_of_vpc",
                        source="aws:ec2:describe_instances",
                        metadata={"private_ip": meta.get("private_ip")},
                        criticality=Criticality.high
                    )

                for sg_id in meta.get("security_groups", []):
                    self.add_edge(
                        source_component_id=cid,
                        target_component_id=sg_id,
                        relationship_type="protected_by_security_group",
                        source="aws:ec2:describe_instances:security_groups",
                        metadata={"role": "attached_security_group"},
                        criticality=Criticality.medium
                    )

            # RDS instance topology
            elif ctype == "database" and (cid.startswith("rds-") or comp.get("arn", "").startswith("arn:aws:rds")):
                vpc_id = meta.get("vpc_id")
                if vpc_id:
                    self.add_edge(
                        source_component_id=cid,
                        target_component_id=vpc_id,
                        relationship_type="member_of_vpc",
                        source="aws:rds:describe_db_instances",
                        metadata={"engine": meta.get("engine")},
                        criticality=Criticality.critical
                    )

                for sub_id in meta.get("subnet_ids", []):
                    self.add_edge(
                        source_component_id=cid,
                        target_component_id=sub_id,
                        relationship_type="enclosed_in_subnet",
                        source="aws:rds:describe_db_instances:subnet_group",
                        metadata={"db_subnet_group": meta.get("db_subnet_group_name")},
                        criticality=Criticality.critical
                    )

                for sg_id in meta.get("security_groups", []):
                    self.add_edge(
                        source_component_id=cid,
                        target_component_id=sg_id,
                        relationship_type="protected_by_security_group",
                        source="aws:rds:describe_db_instances:vpc_security_groups",
                        metadata={"role": "attached_security_group"},
                        criticality=Criticality.critical
                    )

            # Load Balancer topology
            elif ctype == "load_balancer":
                vpc_id = meta.get("vpc_id")
                if vpc_id:
                    self.add_edge(
                        source_component_id=cid,
                        target_component_id=vpc_id,
                        relationship_type="member_of_vpc",
                        source="aws:elbv2:describe_load_balancers",
                        metadata={"scheme": meta.get("scheme"), "dns_name": meta.get("dns_name")},
                        criticality=Criticality.high
                    )

                for sub_id in meta.get("subnet_ids", []):
                    self.add_edge(
                        source_component_id=cid,
                        target_component_id=sub_id,
                        relationship_type="enclosed_in_subnet",
                        source="aws:elbv2:describe_load_balancers:subnets",
                        metadata={"scheme": meta.get("scheme")},
                        criticality=Criticality.high
                    )

                for sg_id in meta.get("security_groups", []):
                    self.add_edge(
                        source_component_id=cid,
                        target_component_id=sg_id,
                        relationship_type="protected_by_security_group",
                        source="aws:elbv2:describe_load_balancers:security_groups",
                        metadata={"role": "attached_security_group"},
                        criticality=Criticality.high
                    )

    def build_alb_target_routes(self, target_health_records: List[Dict[str, Any]]):
        """
        Extracts Load Balancer -> EC2 Target routes based on actual Target Group Health.
        API: elbv2.describe_target_health(TargetGroupArn=...)
        """
        for record in target_health_records:
            alb_id = record.get("load_balancer_id")
            target_id = record.get("target_id")
            tg_arn = record.get("target_group_arn")
            port = record.get("port")
            protocol = record.get("protocol", "HTTP")
            state = record.get("state", "healthy")

            if alb_id and target_id:
                self.add_edge(
                    source_component_id=alb_id,
                    target_component_id=target_id,
                    relationship_type="routes_traffic_to",
                    source="aws:elbv2:target_health",
                    metadata={
                        "target_group_arn": tg_arn,
                        "port": port,
                        "protocol": protocol,
                        "health_state": state
                    },
                    criticality=Criticality.high
                )

    def build_ec2_to_rds_connections(self, security_group_rules: Dict[str, Any]):
        """
        Deterministically verifies EC2 -> RDS connections through actual Security Group rules.
        In AWS, an EC2 can reach an RDS instance within the VPC if the RDS DB's security group
        has an inbound authorization rule (IpPermissions) explicitly referencing an EC2 security group
        on the database port (e.g. 5432 for Postgres, 3306 for MySQL, 1433 for SQLServer, 1521 for Oracle).
        
        APIs:
        - ec2.describe_security_groups() (IpPermissions.UserIdGroupPairs)
        - rds.describe_db_instances() (VpcSecurityGroups)
        - ec2.describe_instances() (SecurityGroups)
        """
        # Map security groups to EC2 instances
        sg_to_ec2s: Dict[str, List[Dict[str, Any]]] = {}
        for comp in self.components:
            if comp.get("type") == "server" and comp["id"].startswith("i-"):
                meta = comp.get("metadata_col", {})
                for sg_id in meta.get("security_groups", []):
                    sg_to_ec2s.setdefault(sg_id, []).append(comp)

        # Iterate over RDS databases
        for comp in self.components:
            if comp.get("type") == "database" and (comp["id"].startswith("rds-") or comp.get("arn", "").startswith("arn:aws:rds")):
                rds_id = comp["id"]
                rds_meta = comp.get("metadata_col", {})
                rds_sgs = rds_meta.get("security_groups", [])
                rds_vpc = rds_meta.get("vpc_id")
                db_port = rds_meta.get("port", 5432)
                engine = rds_meta.get("engine", "postgres")
                endpoint = rds_meta.get("endpoint", "")

                for rds_sg_id in rds_sgs:
                    # Inbound permissions on the RDS security group
                    rules = security_group_rules.get(rds_sg_id, {}).get("inbound", [])
                    for rule in rules:
                        rule_from_port = rule.get("from_port")
                        rule_to_port = rule.get("to_port")
                        protocol = rule.get("protocol", "tcp")

                        # Check if port matches DB port or all ports (-1)
                        port_matches = False
                        if rule_from_port is None or rule_from_port == -1:
                            port_matches = True
                        elif rule_from_port <= db_port <= (rule_to_port or rule_from_port):
                            port_matches = True

                        if not port_matches:
                            continue

                        # Check allowed source security groups
                        for source_sg_id in rule.get("allowed_security_groups", []):
                            matching_ec2s = sg_to_ec2s.get(source_sg_id, [])
                            for ec2 in matching_ec2s:
                                ec2_id = ec2["id"]
                                ec2_vpc = ec2.get("metadata_col", {}).get("vpc_id")

                                # Verify both are in same VPC or routable
                                if ec2_vpc and rds_vpc and ec2_vpc != rds_vpc:
                                    continue

                                self.add_edge(
                                    source_component_id=ec2_id,
                                    target_component_id=rds_id,
                                    relationship_type="database_connection",
                                    source="aws:ec2:security_group_rule",
                                    metadata={
                                        "port": db_port,
                                        "protocol": protocol,
                                        "rds_security_group": rds_sg_id,
                                        "ec2_security_group": source_sg_id,
                                        "engine": engine,
                                        "endpoint": endpoint,
                                        "verification": "security_group_ingress_rule"
                                    },
                                    criticality=Criticality.critical
                                )

    def build_ec2_to_s3_storage_access(self, iam_instance_profiles: Dict[str, Any]):
        """
        Deterministically verifies EC2 -> S3 storage access through actual IAM Instance Profiles
        and IAM Role policies granting access to specific S3 bucket ARNs.
        
        APIs:
        - ec2.describe_instances() -> IamInstanceProfile
        - iam.get_instance_profile() -> RoleName
        - iam.list_role_policies() / iam.get_role_policy() -> Statement[].Resource == s3_bucket_arn
        """
        # Find all S3 components
        s3_components: Dict[str, Dict[str, Any]] = {}
        for comp in self.components:
            if comp.get("type") == "storage" and (comp["id"].startswith("s3-") or comp.get("arn", "").startswith("arn:aws:s3")):
                s3_id = comp["id"]
                bucket_name = s3_id.replace("s3-", "") if s3_id.startswith("s3-") else comp.get("name", "")
                s3_components[bucket_name] = comp
                s3_components[s3_id] = comp

        for comp in self.components:
            if comp.get("type") == "server" and comp["id"].startswith("i-"):
                ec2_id = comp["id"]
                meta = comp.get("metadata_col", {})
                profile_name = meta.get("iam_instance_profile") or meta.get("iam_role")

                if not profile_name:
                    continue

                profile_data = iam_instance_profiles.get(profile_name, {})
                allowed_buckets = profile_data.get("allowed_s3_buckets", [])
                role_name = profile_data.get("role_name", profile_name)
                actions = profile_data.get("actions", ["s3:GetObject", "s3:PutObject"])

                for bucket_id_or_name in allowed_buckets:
                    matched_s3 = s3_components.get(bucket_id_or_name)
                    if matched_s3:
                        self.add_edge(
                            source_component_id=ec2_id,
                            target_component_id=matched_s3["id"],
                            relationship_type="storage_access",
                            source="aws:iam:instance_profile_policy",
                            metadata={
                                "role_name": role_name,
                                "actions": actions,
                                "bucket": matched_s3["id"],
                                "verification": "iam_instance_profile_permission"
                            },
                            criticality=Criticality.high
                        )

    def build_security_group_rules(self, security_group_rules: Dict[str, Any]):
        """
        Discovers explicit authorization edges between security groups:
        If SG_A authorizes inbound traffic from SG_B, creates edge SG_A -> SG_B.
        """
        for sg_id, data in security_group_rules.items():
            for rule in data.get("inbound", []):
                from_port = rule.get("from_port")
                to_port = rule.get("to_port")
                protocol = rule.get("protocol", "tcp")
                for source_sg_id in rule.get("allowed_security_groups", []):
                    if source_sg_id != sg_id: # avoid self-loop noise
                        self.add_edge(
                            source_component_id=sg_id,
                            target_component_id=source_sg_id,
                            relationship_type="authorizes_traffic_from",
                            source="aws:ec2:describe_security_groups:rules",
                            metadata={
                                "from_port": from_port,
                                "to_port": to_port,
                                "protocol": protocol
                            },
                            criticality=Criticality.medium
                        )

    def build_all(
        self,
        target_health_records: Optional[List[Dict[str, Any]]] = None,
        security_group_rules: Optional[Dict[str, Any]] = None,
        iam_instance_profiles: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Runs the full deterministic topology and relationship discovery pipeline.
        Returns the list of normalized dependency dictionaries.
        """
        # 1. Structural network containment
        self.build_network_containment()

        # 2. ALB -> EC2 traffic forwarding
        if target_health_records:
            self.build_alb_target_routes(target_health_records)

        # 3. EC2 -> RDS database connections via Security Group authorization
        if security_group_rules:
            self.build_ec2_to_rds_connections(security_group_rules)
            self.build_security_group_rules(security_group_rules)

        # 4. EC2 -> S3 storage access via IAM Instance Profile policies
        if iam_instance_profiles:
            self.build_ec2_to_s3_storage_access(iam_instance_profiles)

        logger.info(
            "Built deterministic dependency graph: %d relationships derived across %d components.",
            len(self.dependencies), len(self.components)
        )
        return self.dependencies
