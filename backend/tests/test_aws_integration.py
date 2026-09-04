import pytest
import sys
import os

# Add backend directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# pyrefly: ignore [missing-import]
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import models
from database import Base
import aws_collector
from main import app, get_db

# Use an in-memory SQLite database with StaticPool for fast, shared in-memory tests
TEST_DB_URL = "sqlite:///:memory:"
test_engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

@pytest.fixture(autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()
    import seed
    seed.seed_data(db)
    app.dependency_overrides[get_db] = override_get_db
    yield
    Base.metadata.drop_all(bind=test_engine)
    app.dependency_overrides.pop(get_db, None)

def test_credentials_check_handles_gracefully():
    """Verify check_aws_credentials returns a structured dict without raising unhandled exceptions."""
    result = aws_collector.check_aws_credentials()
    assert isinstance(result, dict)
    assert "authenticated" in result
    assert "region" in result
    assert "error" in result

def test_criticality_and_cost_heuristics():
    """Verify tags and resource types derive appropriate criticality and monthly cost estimates."""
    crit_prod_db = aws_collector._derive_criticality({"Environment": "prod"}, "database")
    assert crit_prod_db == models.Criticality.critical

    crit_dev_app = aws_collector._derive_criticality({"Environment": "dev"}, "server")
    assert crit_dev_app == models.Criticality.low

    cost_m5 = aws_collector._get_estimated_cost("ec2", "m5.large")
    assert cost_m5 > 50.0

def test_synthetic_aws_data_structure():
    """Verify synthetic AWS generator produces deterministic components and topological edges."""
    comps, deps, summary = aws_collector.generate_synthetic_aws_data(region="us-east-1")
    assert summary["vpcs"] >= 1
    assert summary["subnets"] >= 2
    assert summary["ec2_instances"] >= 2
    assert summary["rds_databases"] >= 1
    assert summary["load_balancers"] >= 1
    assert summary["s3_buckets"] >= 1

    # Verify ALB -> EC2 route exists
    routes = [d for d in deps if d["relationship_type"] in [models.DependencyType.routes_to, "routes_traffic_to"]]
    assert len(routes) >= 1

    # Verify EC2 -> RDS database_connection exists (verified via Security Group rules)
    db_conns = [d for d in deps if d["relationship_type"] == "database_connection"]
    assert len(db_conns) >= 2
    assert db_conns[0]["source"] == "aws:ec2:security_group_rule"
    assert db_conns[0]["metadata"]["port"] == 5432

    # Verify EC2 -> S3 storage_access exists (verified via IAM Instance Profile policies)
    storage_deps = [d for d in deps if d["relationship_type"] == "storage_access"]
    assert len(storage_deps) >= 2
    assert storage_deps[0]["source"] == "aws:iam:instance_profile_policy"

    # Verify Network containment exists (member_of_vpc, enclosed_in_subnet, protected_by_security_group)
    containment = [d for d in deps if d["relationship_type"] in ["member_of_vpc", "enclosed_in_subnet", "protected_by_security_group", models.DependencyType.hosted_on]]
    assert len(containment) >= 5

def test_sync_aws_merge_preserves_seed_data():
    """Verify that syncing AWS in merge mode preserves baseline on-prem seed data."""
    db = TestingSessionLocal()
    initial_comp_count = db.query(models.Component).count()
    assert initial_comp_count >= 15 # baseline seed

    sync_result = aws_collector.sync_aws_to_db(db, mode="merge", use_synthetic=True, region="us-east-1")
    assert sync_result["success"] is True
    assert sync_result["components_added"] > 0

    # Ensure Core API app from seed is still intact
    core_api = db.query(models.Component).filter_by(id="app_core_api").first()
    assert core_api is not None
    assert core_api.name == "Core Microservices API"

    # Ensure new AWS components are present
    vpc = db.query(models.Component).filter_by(id="vpc-0a81729b14c3").first()
    assert vpc is not None
    assert vpc.type == models.ComponentType.vpc
    assert vpc.arn is not None

    db.close()

def test_api_aws_status_endpoint():
    """Verify GET /api/aws/status endpoint returns valid status schema."""
    client = TestClient(app)
    response = client.get("/api/aws/status")
    assert response.status_code == 200
    data = response.json()
    assert "authenticated" in data
    assert "region" in data
    assert "total_components_count" in data

def test_api_aws_sync_endpoint():
    """Verify POST /api/aws/sync endpoint successfully synchronizes infrastructure."""
    client = TestClient(app)
    response = client.post("/api/aws/sync", json={"mode": "merge", "use_synthetic": True, "region": "us-east-1"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["components_added"] > 0
    assert data["data_source"] == "aws_synthetic"

    # Verify components endpoint reflects new AWS components
    comps_resp = client.get("/api/twin/components")
    assert comps_resp.status_code == 200
    all_comps = comps_resp.json()
    comp_types = [c["type"] for c in all_comps]
    assert "vpc" in comp_types
    assert "subnet" in comp_types
    assert "load_balancer" in comp_types

def test_simulate_with_aws_components():
    """Verify that the simulation engine can run on newly synchronized AWS resources."""
    client = TestClient(app)
    # Sync synthetic AWS components
    client.post("/api/aws/sync", json={"mode": "merge", "use_synthetic": True, "region": "us-east-1"})

    # Simulate change on EC2 instance i-09f182c81a2b
    sim_resp = client.post("/api/simulate", json={
        "target_component_id": "i-09f182c81a2b",
        "action": "migrate",
        "destination_env": "cloud"
    })
    assert sim_resp.status_code == 200
    sim_data = sim_resp.json()
    assert sim_data["target_component"] == "EC2: Prod-API-Cluster-01"
    assert "affected_count" in sim_data
    assert "risk_score" in sim_data
