import pytest
from graph_builder import AWSDependencyGraphBuilder
from models import Criticality

def test_alb_to_ec2_target_health_route():
    """Verify Load Balancer -> EC2 route is created from Target Group health records."""
    components = [
        {"id": "alb-app", "type": "load_balancer", "criticality": Criticality.high, "metadata_col": {}},
        {"id": "i-12345", "type": "server", "criticality": Criticality.high, "metadata_col": {}}
    ]
    target_health = [
        {
            "load_balancer_id": "alb-app",
            "target_id": "i-12345",
            "target_group_arn": "arn:aws:elbv2:us-east-1:123:targetgroup/tg-1",
            "port": 8080,
            "protocol": "HTTP",
            "state": "healthy"
        }
    ]

    builder = AWSDependencyGraphBuilder(components)
    deps = builder.build_all(target_health_records=target_health)

    routes = [d for d in deps if d["relationship_type"] == "routes_traffic_to"]
    assert len(routes) == 1
    assert routes[0]["source_component_id"] == "alb-app"
    assert routes[0]["target_component_id"] == "i-12345"
    assert routes[0]["source"] == "aws:elbv2:target_health"
    assert routes[0]["metadata"]["port"] == 8080
    assert routes[0]["metadata"]["protocol"] == "HTTP"


def test_ec2_to_rds_via_security_group_rule():
    """Verify EC2 -> RDS database_connection is discovered when RDS SG authorizes EC2 SG."""
    components = [
        {
            "id": "i-app-01",
            "type": "server",
            "criticality": Criticality.high,
            "metadata_col": {
                "vpc_id": "vpc-100",
                "security_groups": ["sg-app"]
            }
        },
        {
            "id": "rds-postgres-01",
            "type": "database",
            "criticality": Criticality.critical,
            "metadata_col": {
                "vpc_id": "vpc-100",
                "port": 5432,
                "engine": "postgres",
                "endpoint": "postgres.internal.aws.corp",
                "security_groups": ["sg-database"]
            }
        }
    ]

    sg_rules = {
        "sg-database": {
            "inbound": [
                {
                    "from_port": 5432,
                    "to_port": 5432,
                    "protocol": "tcp",
                    "allowed_security_groups": ["sg-app"]
                }
            ],
            "vpc_id": "vpc-100"
        }
    }

    builder = AWSDependencyGraphBuilder(components)
    deps = builder.build_all(security_group_rules=sg_rules)

    db_conns = [d for d in deps if d["relationship_type"] == "database_connection"]
    assert len(db_conns) == 1
    assert db_conns[0]["source_component_id"] == "i-app-01"
    assert db_conns[0]["target_component_id"] == "rds-postgres-01"
    assert db_conns[0]["source"] == "aws:ec2:security_group_rule"
    assert db_conns[0]["metadata"]["port"] == 5432
    assert db_conns[0]["metadata"]["rds_security_group"] == "sg-database"
    assert db_conns[0]["metadata"]["ec2_security_group"] == "sg-app"


def test_no_security_group_rule_no_guess():
    """Verify CRITICAL RULE: If no security group authorizes access, no dependency is guessed."""
    components = [
        {
            "id": "i-unrelated",
            "type": "server",
            "criticality": Criticality.low,
            "metadata_col": {
                "vpc_id": "vpc-100",
                "security_groups": ["sg-other"]
            }
        },
        {
            "id": "rds-isolated",
            "type": "database",
            "criticality": Criticality.critical,
            "metadata_col": {
                "vpc_id": "vpc-100",
                "port": 5432,
                "security_groups": ["sg-database"]
            }
        }
    ]

    sg_rules = {
        "sg-database": {
            "inbound": [
                # Only authorizes sg-authorized, not sg-other
                {"from_port": 5432, "to_port": 5432, "protocol": "tcp", "allowed_security_groups": ["sg-authorized"]}
            ],
            "vpc_id": "vpc-100"
        }
    }

    builder = AWSDependencyGraphBuilder(components)
    deps = builder.build_all(security_group_rules=sg_rules)

    # Must NOT invent any connection
    db_conns = [d for d in deps if d["relationship_type"] == "database_connection"]
    assert len(db_conns) == 0


def test_ec2_to_s3_storage_access_via_iam_profile():
    """Verify EC2 -> S3 storage_access is discovered from IAM instance profile policies."""
    components = [
        {
            "id": "i-processor",
            "type": "server",
            "criticality": Criticality.high,
            "metadata_col": {
                "iam_instance_profile": "DataProcessorRole"
            }
        },
        {
            "id": "s3-raw-data-bucket",
            "type": "storage",
            "criticality": Criticality.medium,
            "metadata_col": {}
        }
    ]

    iam_profiles = {
        "DataProcessorRole": {
            "role_name": "DataProcessorRole",
            "allowed_s3_buckets": ["s3-raw-data-bucket"],
            "actions": ["s3:GetObject", "s3:PutObject"]
        }
    }

    builder = AWSDependencyGraphBuilder(components)
    deps = builder.build_all(iam_instance_profiles=iam_profiles)

    s3_access = [d for d in deps if d["relationship_type"] == "storage_access"]
    assert len(s3_access) == 1
    assert s3_access[0]["source_component_id"] == "i-processor"
    assert s3_access[0]["target_component_id"] == "s3-raw-data-bucket"
    assert s3_access[0]["source"] == "aws:iam:instance_profile_policy"
    assert "s3:GetObject" in s3_access[0]["metadata"]["actions"]


def test_missing_endpoint_rejected():
    """Verify edges are rejected if either endpoint is not present in the component registry."""
    components = [
        {"id": "i-exists", "type": "server", "criticality": Criticality.low, "metadata_col": {}}
    ]

    builder = AWSDependencyGraphBuilder(components)
    added = builder.add_edge(
        source_component_id="i-exists",
        target_component_id="non-existent-component",
        relationship_type="database_connection",
        source="aws:ec2:security_group_rule"
    )
    assert added is False
    assert len(builder.dependencies) == 0


def test_normalized_dependency_schema():
    """Verify all required normalized fields exist on generated dependencies."""
    components = [
        {
            "id": "subnet-01",
            "type": "subnet",
            "criticality": Criticality.medium,
            "metadata_col": {"vpc_id": "vpc-01", "cidr_block": "10.0.1.0/24"}
        },
        {
            "id": "vpc-01",
            "type": "vpc",
            "criticality": Criticality.high,
            "metadata_col": {}
        }
    ]

    builder = AWSDependencyGraphBuilder(components)
    deps = builder.build_all()

    assert len(deps) == 1
    dep = deps[0]
    assert "source_component_id" in dep
    assert "target_component_id" in dep
    assert "relationship_type" in dep
    assert "source" in dep
    assert "metadata" in dep
    assert dep["source_component_id"] == "subnet-01"
    assert dep["target_component_id"] == "vpc-01"
    assert dep["relationship_type"] == "member_of_vpc"
