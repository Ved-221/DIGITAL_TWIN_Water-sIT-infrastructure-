import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from main import app
import aws_collector, models, database

client = TestClient(app)

def test_reset_and_clean_unconnected_state():
    """Verify /api/twin/reset resets the environment to unconnected with 0 components."""
    res = client.post("/api/twin/reset")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["mode"] == "unconnected"

    state_res = client.get("/api/twin/state")
    assert state_res.status_code == 200
    state = state_res.json()
    assert state["mode"] == "unconnected"
    assert state["total_components"] == 0
    assert state["total_dependencies"] == 0
    assert state["discovery_status"] == "idle"

    # Verify components and dependencies are empty
    comps_res = client.get("/api/twin/components")
    assert comps_res.json() == []

    deps_res = client.get("/api/twin/dependencies")
    assert deps_res.json() == []

def test_aws_connect_sets_live_awaiting_discovery_without_premature_nodes():
    """Verify AWS authentication transitions state to LIVE awaiting discovery without inventing nodes."""
    # Reset first
    client.post("/api/twin/reset")

    with patch.object(aws_collector, "check_aws_credentials", return_value={
        "authenticated": True,
        "account_id": "999888777666",
        "arn": "arn:aws:iam::999888777666:user/sre-lead",
        "region": "us-east-1"
    }):
        res = client.post("/api/aws/connect", json={
            "access_key_id": "AKIAIOSFODNN7REALKEY",
            "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYREALKEY",
            "region": "us-east-1"
        })
        assert res.status_code == 200
        data = res.json()
        assert data["authenticated"] is True
        assert data["account_id"] == "999888777666"

        # Check twin state: must be LIVE, but discovery_status is idle and total components is 0
        state_res = client.get("/api/twin/state")
        state = state_res.json()
        assert state["mode"] == "live"
        assert state["authenticated"] is True
        assert state["account_id"] == "999888777666"
        assert state["discovery_status"] == "idle"
        assert state["total_components"] == 0

        # Verify no premature nodes or fake edges were created
        comps = client.get("/api/twin/components").json()
        assert len(comps) == 0

def test_live_mode_rejects_synthetic_metrics_when_empty():
    """Verify in LIVE mode, empty metrics table returns empty list, never synthetic numbers."""
    client.post("/api/twin/reset")
    with patch.object(aws_collector, "check_aws_credentials", return_value={"authenticated": True}):
        # Set state to live
        db = next(database.get_db())
        state = db.query(models.TwinState).filter_by(id=1).first()
        state.mode = "live"
        db.commit()

        # Request latest metrics
        m_res = client.get("/api/twin/metrics/latest")
        assert m_res.status_code == 200
        # Must be empty, NOT synthetic records
        assert m_res.json() == []

def test_explicit_demo_mode_launch_and_tagging():
    """Verify demo mode is only launched on explicit request and is clearly tagged."""
    client.post("/api/twin/reset")

    demo_res = client.post("/api/twin/demo", json={"region": "us-east-1"})
    assert demo_res.status_code == 200
    data = demo_res.json()
    assert data["success"] is True
    assert data["data_source"] == "aws_synthetic"

    state = client.get("/api/twin/state").json()
    assert state["mode"] == "demo"
    assert state["discovery_status"] == "completed"
    assert state["total_components"] > 0

    comps = client.get("/api/twin/components").json()
    assert len(comps) > 0
    # Every component must have discovery_source == aws_synthetic
    for c in comps:
        assert c["discovery_source"] == "aws_synthetic"

def test_switching_from_demo_to_live_purges_all_demo_data():
    """Verify connecting LIVE AWS while in Demo mode wipes all synthetic data."""
    # First launch demo
    client.post("/api/twin/demo")
    assert len(client.get("/api/twin/components").json()) > 0

    # Now connect live AWS
    with patch.object(aws_collector, "check_aws_credentials", return_value={
        "authenticated": True,
        "account_id": "111222333444",
        "arn": "arn:aws:iam::111222333444:user/cloud-architect",
        "region": "us-west-2"
    }):
        connect_res = client.post("/api/aws/connect", json={
            "access_key_id": "AKIAIOSFODNN7LIVEKEY",
            "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYLIVEKEY",
            "region": "us-west-2"
        })
        assert connect_res.status_code == 200

        # Verify all demo components and dependencies are wiped clean
        comps = client.get("/api/twin/components").json()
        assert len(comps) == 0

        state = client.get("/api/twin/state").json()
        assert state["mode"] == "live"
        assert state["account_id"] == "111222333444"
        assert state["discovery_status"] == "idle"
        assert state["total_components"] == 0

def test_live_discovery_creates_twin_only_from_returned_resources():
    """Verify live discovery populates only the returned AWS resources."""
    mock_collector = MagicMock()
    # Mock AWS returning only 1 VPC, 1 Subnet, 1 EC2 instance (no RDS, no ALB, no S3)
    mock_components = [
        {"id": "vpc-test1234", "name": "VPC-Prod", "type": "vpc", "environment": "cloud", "location": "us-east-1", "criticality": "high", "cost_per_month": 0.0, "discovery_source": "aws_api", "arn": "arn:aws:ec2:us-east-1:123:vpc/vpc-test1234", "metadata_col": {}},
        {"id": "subnet-test1234", "name": "Subnet-App", "type": "subnet", "environment": "cloud", "location": "us-east-1", "criticality": "high", "cost_per_month": 0.0, "discovery_source": "aws_api", "arn": "arn:aws:ec2:us-east-1:123:subnet/subnet-test1234", "metadata_col": {"vpc_id": "vpc-test1234"}},
        {"id": "i-testec2instance", "name": "API-Worker", "type": "server", "environment": "cloud", "location": "us-east-1", "criticality": "high", "cost_per_month": 45.0, "discovery_source": "aws_api", "arn": "arn:aws:ec2:us-east-1:123:instance/i-testec2instance", "metadata_col": {"vpc_id": "vpc-test1234", "subnet_id": "subnet-test1234"}}
    ]
    mock_dependencies = [
        {"source_component_id": "subnet-test1234", "target_component_id": "vpc-test1234", "relationship_type": "member_of_vpc", "source": "aws_api", "criticality": "high"},
        {"source_component_id": "i-testec2instance", "target_component_id": "subnet-test1234", "relationship_type": "enclosed_in_subnet", "source": "aws_api", "criticality": "high"}
    ]
    mock_summary = {"vpcs": 1, "subnets": 1, "ec2_instances": 1, "rds_databases": 0, "load_balancers": 0, "s3_buckets": 0, "total_components": 3, "total_dependencies": 2}
    mock_collector.collect_all.return_value = (mock_components, mock_dependencies, mock_summary)

    with patch.object(aws_collector, "check_aws_credentials", return_value={"authenticated": True, "account_id": "123456789012", "region": "us-east-1"}), \
         patch.object(aws_collector, "AWSInfrastructureCollector", return_value=mock_collector):

        sync_res = client.post("/api/aws/sync", json={"mode": "replace", "use_synthetic": False, "region": "us-east-1"})
        assert sync_res.status_code == 200

        state = client.get("/api/twin/state").json()
        assert state["mode"] == "live"
        assert state["discovery_status"] == "completed"
        assert state["total_components"] == 3
        assert state["total_dependencies"] == 2
        assert state["discovery_summary"]["rds_databases"] == 0
        assert state["discovery_summary"]["load_balancers"] == 0

        comps = client.get("/api/twin/components").json()
        types = [c["type"] for c in comps]
        # Crucial requirement: RDS and Load Balancer MUST NOT exist if not returned by AWS
        assert "database" not in types
        assert "load_balancer" not in types
        assert "storage" not in types
        assert set(types) == {"vpc", "subnet", "server"}
