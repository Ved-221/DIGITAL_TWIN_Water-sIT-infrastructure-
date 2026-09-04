import pytest
from fastapi.testclient import TestClient
from main import app
import models, database

client = TestClient(app)

def setup_function():
    """Ensure clean slate for tests."""
    db = next(database.get_db())
    db.query(models.Dependency).delete()
    db.query(models.Component).delete()
    state = db.query(models.TwinState).filter_by(id=1).first()
    if not state:
        state = models.TwinState(id=1)
        db.add(state)
    state.mode = "unconnected"
    db.commit()

def test_manual_environment_starts_completely_empty():
    """Scenario 1: Starting manual environment must be 100% empty (0 nodes, 0 edges)."""
    res = client.post("/api/manual/start")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["mode"] == "manual"
    assert data["total_components"] == 0
    assert data["total_dependencies"] == 0

    state = client.get("/api/twin/state").json()
    assert state["mode"] == "manual"
    assert state["total_components"] == 0

    comps = client.get("/api/twin/components").json()
    assert comps == []

    deps = client.get("/api/twin/dependencies").json()
    assert deps == []

def test_dynamic_add_and_count_resources():
    """Scenarios 2 & 3: Dynamically add 1 and 5 resources, verifying counts and properties."""
    client.post("/api/manual/start")

    # Add 1 resource
    res1 = client.post("/api/manual/components", json={
        "name": "Auth Microservice",
        "type": "server",
        "criticality": "high",
        "cost_per_month": 48.0,
        "assumptions": {"cpu": 65.0, "memory": 50.0, "latency": 120.0}
    })
    assert res1.status_code == 200
    c1 = res1.json()
    assert c1["name"] == "Auth Microservice"
    assert c1["type"] == "server"
    assert c1["discovery_source"] == "manual"
    assert c1["cost_per_month"] == 48.0

    comps_after_1 = client.get("/api/twin/components").json()
    assert len(comps_after_1) == 1

    # Add 4 more resources to reach 5
    client.post("/api/manual/components", json={"id": "vpc-core", "name": "Core Network VPC", "type": "vpc", "criticality": "high"})
    client.post("/api/manual/components", json={"id": "alb-ingress", "name": "Ingress ALB", "type": "load_balancer", "criticality": "critical", "cost_per_month": 32.0})
    client.post("/api/manual/components", json={"id": "db-primary", "name": "Primary PostgreSQL", "type": "database", "criticality": "critical", "cost_per_month": 120.0})
    client.post("/api/manual/components", json={"id": "s3-assets", "name": "Asset Bucket", "type": "storage", "criticality": "low", "cost_per_month": 5.0})

    comps_after_5 = client.get("/api/twin/components").json()
    assert len(comps_after_5) == 5

    stats = client.get("/api/twin/stats").json()
    assert stats["total_components"] == 5
    assert stats["critical_services_count"] == 2
    assert stats["total_monthly_cost"] == 205.0

def test_manual_dependency_creation_and_deletion():
    """Scenarios 4 & 5: Connect resources manually and delete a dependency."""
    client.post("/api/manual/start")

    # Create EC2-A, EC2-B, RDS-A
    client.post("/api/manual/components", json={"id": "ec2-a", "name": "Web Frontend", "type": "server"})
    client.post("/api/manual/components", json={"id": "ec2-b", "name": "API Gateway Worker", "type": "server"})
    client.post("/api/manual/components", json={"id": "rds-a", "name": "Orders DB", "type": "database", "criticality": "critical"})

    # Connect EC2-A -> EC2-B
    dep1_res = client.post("/api/manual/dependencies", json={
        "source_component_id": "ec2-a",
        "target_component_id": "ec2-b",
        "relationship_type": "routes_traffic_to",
        "criticality": "high"
    })
    assert dep1_res.status_code == 200
    dep1 = dep1_res.json()

    # Connect EC2-B -> RDS-A
    dep2_res = client.post("/api/manual/dependencies", json={
        "source_component_id": "ec2-b",
        "target_component_id": "rds-a",
        "relationship_type": "database_connection",
        "criticality": "critical"
    })
    assert dep2_res.status_code == 200
    dep2 = dep2_res.json()

    # Verify exactly those 2 dependencies exist
    deps = client.get("/api/twin/dependencies").json()
    assert len(deps) == 2
    assert {d["source_component_id"] for d in deps} == {"ec2-a", "ec2-b"}
    assert {d["target_component_id"] for d in deps} == {"ec2-b", "rds-a"}

    # Delete 1 dependency
    del_res = client.delete(f"/api/manual/dependencies/{dep1['id']}")
    assert del_res.status_code == 200

    deps_after_del = client.get("/api/twin/dependencies").json()
    assert len(deps_after_del) == 1
    assert deps_after_del[0]["source_component_id"] == "ec2-b"

def test_delete_resource_cascades_dependencies():
    """Scenario 6: Deleting a resource cascades to remove any dependent edges."""
    client.post("/api/manual/start")

    client.post("/api/manual/components", json={"id": "node-1", "name": "Node 1", "type": "server"})
    client.post("/api/manual/components", json={"id": "node-2", "name": "Node 2", "type": "server"})
    client.post("/api/manual/components", json={"id": "node-3", "name": "Node 3", "type": "server"})

    client.post("/api/manual/dependencies", json={"source_component_id": "node-1", "target_component_id": "node-2"})
    client.post("/api/manual/dependencies", json={"source_component_id": "node-2", "target_component_id": "node-3"})

    assert len(client.get("/api/twin/dependencies").json()) == 2

    # Delete node-2 (which has 1 incoming edge from node-1 and 1 outgoing edge to node-3)
    del_res = client.delete("/api/manual/components/node-2")
    assert del_res.status_code == 200

    comps = client.get("/api/twin/components").json()
    assert len(comps) == 2
    assert "node-2" not in [c["id"] for c in comps]

    # Both edges touching node-2 must have been deleted
    deps = client.get("/api/twin/dependencies").json()
    assert len(deps) == 0

def test_simulation_on_manual_topology():
    """Scenario 8: Simulation uses the actual manually created graph and assumptions."""
    client.post("/api/manual/start")

    # Build EC2-A -> EC2-B -> RDS-A
    client.post("/api/manual/components", json={
        "id": "ec2-a",
        "name": "Web Proxy",
        "type": "server",
        "cost_per_month": 40.0,
        "assumptions": {"cpu": 82.0, "latency": 150.0}
    })
    client.post("/api/manual/components", json={"id": "ec2-b", "name": "App Core", "type": "server", "cost_per_month": 80.0})
    client.post("/api/manual/components", json={"id": "rds-a", "name": "Cluster DB", "type": "database", "criticality": "critical", "cost_per_month": 150.0})

    client.post("/api/manual/dependencies", json={"source_component_id": "ec2-a", "target_component_id": "ec2-b", "relationship_type": "routes_traffic_to"})
    client.post("/api/manual/dependencies", json={"source_component_id": "ec2-b", "target_component_id": "rds-a", "relationship_type": "database_connection"})

    # Simulate degradation / failure on ec2-a
    sim_res = client.post("/api/simulate", json={
        "target_component_id": "ec2-a",
        "action": "SCALE_COMPUTE"
    })
    assert sim_res.status_code == 200
    sim_data = sim_res.json()

    # Downstream dependencies: ec2-b and rds-a
    assert set(sim_data["affected_components"]) == {"ec2-b", "rds-a"}
    assert sim_data["blast_radius"] == 2
    assert sim_data["target_component"] == "Web Proxy"
    assert sim_data["environment_source"] == "manual"
    assert "configured_assumptions" in sim_data
    assert sim_data["configured_assumptions"]["cpu"] == 82.0

    # AI explanation must exist and recognize manual topology
    ai_exp = sim_data.get("ai_explanation")
    assert ai_exp is not None
    assert "manually configured" in ai_exp.lower() or "user-defined" in ai_exp.lower()

def test_ml_recommendations_target_actual_manual_resources():
    """Scenario 9: ML recommendations target user-created resources without hallucinating fake nodes."""
    client.post("/api/manual/start")

    # Create a critical node with 3 dependents pointing to it (Single Point of Failure pattern)
    client.post("/api/manual/components", json={"id": "svc-critical", "name": "Central Auth Service", "type": "server", "criticality": "critical"})
    client.post("/api/manual/components", json={"id": "client-1", "name": "Portal", "type": "server"})
    client.post("/api/manual/components", json={"id": "client-2", "name": "Mobile Backend", "type": "server"})
    client.post("/api/manual/components", json={"id": "client-3", "name": "Partner API", "type": "server"})

    client.post("/api/manual/dependencies", json={"source_component_id": "client-1", "target_component_id": "svc-critical"})
    client.post("/api/manual/dependencies", json={"source_component_id": "client-2", "target_component_id": "svc-critical"})
    client.post("/api/manual/dependencies", json={"source_component_id": "client-3", "target_component_id": "svc-critical"})

    recs_res = client.get("/api/ml/recommendations")
    assert recs_res.status_code == 200
    recs = recs_res.json()
    assert len(recs) > 0

    # Ensure recommendations only target the user's actual manual component IDs
    valid_ids = {"svc-critical", "client-1", "client-2", "client-3"}
    for r in recs:
        assert r["resource_id"] in valid_ids

def test_environment_isolation_and_switching():
    """Scenarios 11 & 12: Switch to AWS (manual resources hidden), switch back (manual resources restored)."""
    # 1. Start Manual and create 2 manual components
    client.post("/api/manual/start")
    client.post("/api/manual/components", json={"id": "custom-srv-1", "name": "Custom Server 1", "type": "server"})
    client.post("/api/manual/components", json={"id": "custom-db-1", "name": "Custom DB 1", "type": "database"})
    client.post("/api/manual/dependencies", json={"source_component_id": "custom-srv-1", "target_component_id": "custom-db-1"})

    assert len(client.get("/api/twin/components").json()) == 2

    # 2. Switch to AWS Mode
    act_aws = client.post("/api/aws/activate")
    assert act_aws.status_code == 200
    state_aws = client.get("/api/twin/state").json()
    assert state_aws["mode"] == "live"

    # In AWS mode, the manual resources must NOT appear
    aws_comps = client.get("/api/twin/components").json()
    assert aws_comps == []

    # 3. Switch back to Manual Mode
    act_manual = client.post("/api/manual/activate")
    assert act_manual.status_code == 200
    state_manual = client.get("/api/twin/state").json()
    assert state_manual["mode"] == "manual"

    # In Manual mode, the user's manual resources & dependencies are RESTORED
    restored_comps = client.get("/api/twin/components").json()
    assert len(restored_comps) == 2
    assert {c["id"] for c in restored_comps} == {"custom-srv-1", "custom-db-1"}

    restored_deps = client.get("/api/twin/dependencies").json()
    assert len(restored_deps) == 1
    assert restored_deps[0]["source_component_id"] == "custom-srv-1"
    assert restored_deps[0]["target_component_id"] == "custom-db-1"
