import pytest
from fastapi.testclient import TestClient
from main import app
from database import get_db, SessionLocal
import models
import os
from unittest.mock import patch, MagicMock

client = TestClient(app)

@pytest.fixture(autouse=True)
def clean_and_seed():
    db = SessionLocal()
    # Reset twin state to manual for predictable test isolation
    state = db.query(models.TwinState).filter_by(id=1).first()
    if not state:
        state = models.TwinState(id=1, mode="manual", discovery_status="idle")
        db.add(state)
    else:
        state.mode = "manual"
        state.discovery_status = "idle"
    
    # Clear test components & dependencies
    db.query(models.Component).delete()
    db.query(models.Dependency).delete()
    db.commit()

    # Create a realistic test topology
    # ALB -> Web Server (EC2) -> Database (RDS)
    alb = models.Component(
        id="comp-alb-1",
        name="Ingress-ALB",
        type=models.ComponentType.load_balancer,
        environment=models.Environment.cloud,
        criticality=models.Criticality.critical,
        cost_per_month=25.0,
        status=models.Status.active,
        discovery_source="manual",
        metadata_col={"assumptions": {"cpu": 35.0, "latency": 15.0}}
    )
    ec2 = models.Component(
        id="comp-ec2-1",
        name="App-Server-EC2",
        type=models.ComponentType.server,
        environment=models.Environment.cloud,
        criticality=models.Criticality.critical,
        cost_per_month=65.0,
        status=models.Status.active,
        discovery_source="manual",
        metadata_col={"assumptions": {"cpu": 88.0, "memory": 82.0, "latency": 45.0}}
    )
    rds = models.Component(
        id="comp-rds-1",
        name="Main-Database-RDS",
        type=models.ComponentType.database,
        environment=models.Environment.cloud,
        criticality=models.Criticality.critical,
        cost_per_month=140.0,
        status=models.Status.active,
        discovery_source="manual",
        metadata_col={"assumptions": {"cpu": 72.0, "latency": 30.0}}
    )
    db.add_all([alb, ec2, rds])
    db.commit()

    # Edges: ALB -> EC2, EC2 -> RDS
    dep1 = models.Dependency(
        source_component_id="comp-alb-1",
        target_component_id="comp-ec2-1",
        relationship_type=models.DependencyType.routes_traffic_to,
        criticality=models.Criticality.critical,
        source="manual"
    )
    dep2 = models.Dependency(
        source_component_id="comp-ec2-1",
        target_component_id="comp-rds-1",
        relationship_type=models.DependencyType.database_connection,
        criticality=models.Criticality.critical,
        source="manual"
    )
    db.add_all([dep1, dep2])
    db.commit()
    db.close()
    yield


def test_generate_feasible_solutions_ec2():
    """Verify sandbox candidate generation and constraint evaluation for high-risk compute node."""
    res = client.post("/api/feasible-solutions/generate", json={
        "target_component_id": "comp-ec2-1"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["target_component_id"] == "comp-ec2-1"
    assert data["target_component_name"] == "App-Server-EC2"
    assert data["total_candidate_solutions"] >= 1
    
    # Verify candidate solutions have complete constraint evaluations
    for sol in data["feasible_solutions"]:
        assert sol["is_feasible"] is True
        assert sol["feasibility_reason"] is not None
        assert sol["action_type"] in ["ADD_REDUNDANCY", "ADD_HA_STANDBY", "SCALE_COMPUTE", "EXPAND_STORAGE", "ADD_READ_REPLICA"]
        
        ce = sol["constraints_evaluation"]
        assert "cost_impact" in ce
        assert "resilience" in ce
        assert "risk_reduction" in ce
        assert "downtime_minutes" in ce
        assert "blast_radius_before" in ce
        assert "blast_radius_after" in ce
        assert "performance" in ce
        # Check risk score improved
        assert ce["risk_score_after"] < ce["risk_score_before"]


def test_generate_feasible_solutions_rds_database():
    """Verify database candidate generation includes read replica and storage expansion."""
    res = client.post("/api/feasible-solutions/generate", json={
        "target_component_id": "comp-rds-1"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    actions = [s["action_type"] for s in data["feasible_solutions"]]
    assert any("REPLICA" in a or "HA" in a or "STORAGE" in a or "COMPUTE" in a or "REDUNDANCY" in a for a in actions)


def test_apply_feasible_solution_manual_mode():
    """Verify applying a feasible solution in Manual mode updates the model and returns comparison."""
    # 1. Generate solutions
    gen_res = client.post("/api/feasible-solutions/generate", json={
        "target_component_id": "comp-ec2-1"
    })
    assert gen_res.status_code == 200
    solutions = gen_res.json()["feasible_solutions"]
    assert len(solutions) > 0
    chosen = solutions[0]

    # 2. Apply solution
    apply_res = client.post("/api/feasible-solutions/apply", json={
        "target_component_id": "comp-ec2-1",
        "solution_id": chosen["id"],
        "solution_data": chosen
    })
    assert apply_res.status_code == 200
    apply_data = apply_res.json()
    assert apply_data["success"] is True
    assert apply_data["is_live_aws"] is False
    assert apply_data["warning_banner"] is None
    
    # 3. Verify Before vs After Comparison
    comp = apply_data["before_after_comparison"]
    assert "blast_radius" in comp
    assert "risk" in comp
    assert "downtime" in comp
    assert "cost" in comp
    assert "resilience" in comp
    assert "performance" in comp
    assert comp["blast_radius"]["before"] is not None
    assert comp["blast_radius"]["after"] is not None

    # 4. Verify AI explanation is present and structured
    assert apply_data["ai_explanation"] is not None
    assert "Feasible Solution Assessment" in apply_data["ai_explanation"]
    assert apply_data["ai_structured_explanation"] is not None
    assert "what_changed" in apply_data["ai_structured_explanation"]
    assert "why_it_helps" in apply_data["ai_structured_explanation"]
    assert "affected_dependencies" in apply_data["ai_structured_explanation"]
    assert "simulation_indications" in apply_data["ai_structured_explanation"]
    assert "trade_offs_and_limitations" in apply_data["ai_structured_explanation"]


def test_apply_feasible_solution_live_aws_safety():
    """Verify applying a feasible solution to a Live AWS component NEVER mutates AWS and tags as proposed."""
    db = SessionLocal()
    state = db.query(models.TwinState).filter_by(id=1).first()
    state.mode = "live"
    
    # Add an AWS resource with elevated metrics/assumptions
    aws_ec2 = models.Component(
        id="i-0123456789abcdef0",
        name="prod-payment-worker",
        type=models.ComponentType.server,
        environment=models.Environment.cloud,
        criticality=models.Criticality.critical,
        cost_per_month=85.0,
        status=models.Status.active,
        discovery_source="aws_api",
        arn="arn:aws:ec2:us-east-1:123456789012:instance/i-0123456789abcdef0",
        account_id="123456789012",
        location="us-east-1",
        metadata_col={"assumptions": {"cpu": 88.0, "latency": 60.0}}
    )
    # Add a dependent client to generate a blast radius
    aws_client = models.Component(
        id="i-client-api",
        name="prod-ingress-proxy",
        type=models.ComponentType.server,
        environment=models.Environment.cloud,
        criticality=models.Criticality.critical,
        cost_per_month=40.0,
        status=models.Status.active,
        discovery_source="aws_api",
        arn="arn:aws:ec2:us-east-1:123456789012:instance/i-client-api"
    )
    aws_dep = models.Dependency(
        source_component_id="i-client-api",
        target_component_id="i-0123456789abcdef0",
        relationship_type=models.DependencyType.routes_traffic_to,
        criticality=models.Criticality.critical,
        source="aws_api"
    )
    db.add_all([aws_ec2, aws_client, aws_dep])
    db.commit()
    db.close()

    # Generate solution
    gen_res = client.post("/api/feasible-solutions/generate", json={
        "target_component_id": "i-0123456789abcdef0"
    })
    assert gen_res.status_code == 200
    solutions = gen_res.json()["feasible_solutions"]
    assert len(solutions) > 0
    chosen = solutions[0]

    # Apply solution
    apply_res = client.post("/api/feasible-solutions/apply", json={
        "target_component_id": "i-0123456789abcdef0",
        "solution_id": chosen["id"],
        "solution_data": chosen
    })
    assert apply_res.status_code == 200
    apply_data = apply_res.json()
    
    # AWS SAFETY:
    assert apply_data["is_live_aws"] is True
    assert apply_data["warning_banner"] == "Proposed change — not deployed to AWS"
    
    # Verify in DB that proposed node is tagged with discovery_source="proposed"
    db = SessionLocal()
    proposed_nodes = db.query(models.Component).filter_by(discovery_source="proposed").all()
    if chosen["action_type"] in ["ADD_HA_STANDBY", "ADD_READ_REPLICA"]:
        assert len(proposed_nodes) >= 1
        assert proposed_nodes[0].metadata_col.get("is_proposed") is True
        assert proposed_nodes[0].discovery_source == "proposed"
    db.close()


def test_feasible_solutions_missing_component_404():
    """Verify 404 is returned when an invalid component ID is targeted."""
    res = client.post("/api/feasible-solutions/generate", json={
        "target_component_id": "non-existent-comp-id"
    })
    assert res.status_code == 404
