import pytest
from tests.conftest import TestingSessionLocal
from models import Component, Dependency, ManualProject
from simulation import find_spofs


def test_environment_isolation(client):
    """Verify components created in a manual environment are NEVER visible in AWS environment."""
    db = TestingSessionLocal()
    
    # 1. Create a manual project
    proj = ManualProject(id="manual_corp", name="Corporate On-Prem")
    db.add(proj)
    
    # 2. Add a component to manual_corp
    comp_manual = Component(
        name="onprem-core-router",
        type="network",
        environment="on_prem",
        criticality="critical",
        status="active",
        cost_per_month=1200.0,
        currency="USD",
        location="ap-south-1",
        owner="NetOps",
        source_environment="manual_corp"
    )
    db.add(comp_manual)
    
    # 3. Add an AWS component
    comp_aws = Component(
        name="aws-ec2-api-gateway",
        type="server",
        environment="cloud",
        criticality="high",
        status="active",
        cost_per_month=350.0,
        currency="USD",
        location="ap-south-1",
        owner="CloudOps",
        source_environment="aws"
    )
    db.add(comp_aws)
    db.commit()
    
    # Query via API for aws
    res_aws = client.get("/api/twin/components?source_environment=aws")
    assert res_aws.status_code == 200
    data_aws = res_aws.json()
    assert len(data_aws) == 1
    assert data_aws[0]["name"] == "aws-ec2-api-gateway"
    assert data_aws[0]["source_environment"] == "aws"
    
    # Query via API for manual_corp
    res_manual = client.get("/api/twin/components?source_environment=manual_corp")
    assert res_manual.status_code == 200
    data_manual = res_manual.json()
    assert len(data_manual) == 1
    assert data_manual[0]["name"] == "onprem-core-router"
    assert data_manual[0]["source_environment"] == "manual_corp"
    
    # Query an empty environment
    res_empty = client.get("/api/twin/components?source_environment=new_empty_env")
    assert res_empty.status_code == 200
    assert len(res_empty.json()) == 0
    
    db.close()

def test_component_and_dependency_crud(client):
    """Verify CRUD lifecycle for manual components and dependencies with position updates."""
    # Create component via API
    payload = {
        "name": "payment-microservice",
        "type": "application",
        "environment": "cloud",
        "criticality": "critical",
        "status": "active",
        "cost_per_month": 450.0,
        "currency": "USD",
        "location": "ap-south-1",
        "owner": "Payments Team",
        "source_environment": "manual_env_1"
    }
    create_res = client.post("/api/manual/components", json=payload)
    assert create_res.status_code == 200
    created_comp = create_res.json()
    comp_id = created_comp["id"]
    assert created_comp["name"] == "payment-microservice"
    
    # Create target component
    db_payload = {
        "name": "payment-postgres-db",
        "type": "database",
        "environment": "cloud",
        "criticality": "critical",
        "status": "active",
        "cost_per_month": 800.0,
        "currency": "USD",
        "location": "ap-south-1",
        "owner": "DBA Team",
        "source_environment": "manual_env_1"
    }
    db_res = client.post("/api/manual/components", json=db_payload)
    assert db_res.status_code == 200
    target_id = db_res.json()["id"]
    
    # Create dependency
    dep_payload = {
        "source_id": comp_id,
        "target_id": target_id,
        "relationship_type": "depends_on",
        "criticality": "critical",
        "source_environment": "manual_env_1"
    }
    dep_res = client.post("/api/manual/dependencies", json=dep_payload)
    assert dep_res.status_code == 200
    dep_data = dep_res.json()
    assert dep_data["source_id"] == comp_id
    assert dep_data["target_id"] == target_id
    
    # Update position
    pos_res = client.patch(f"/api/twin/components/{comp_id}/position", json={"position_x": 150.0, "position_y": 320.0})
    assert pos_res.status_code == 200
    assert pos_res.json()["position_x"] == 150.0
    assert pos_res.json()["position_y"] == 320.0
    
    # Delete dependency
    del_dep = client.delete(f"/api/manual/dependencies/{dep_data['id']}")
    assert del_dep.status_code == 200
    
    # Verify dependency deleted
    deps_check = client.get("/api/twin/dependencies?source_environment=manual_env_1")
    assert len(deps_check.json()) == 0
    
    # Delete component
    del_comp = client.delete(f"/api/manual/components/{comp_id}")
    assert del_comp.status_code == 200

def test_single_point_of_failure_spof_detection(client):
    """Verify find_spofs correctly identifies bridge nodes and critical articulation points."""
    db = TestingSessionLocal()
    env = "test_spof_env"
    
    # Create a topology:
    # A (Client) -> B (Central API Gateway / Bridge) -> C (Database 1)
    #                                                -> D (Database 2)
    # B is the articulation point / SPOF.
    c_a = Component(name="Client Gateway", type="application", criticality="medium", status="active", source_environment=env)
    c_b = Component(name="Central Bridge", type="server", criticality="critical", status="active", source_environment=env)
    c_c = Component(name="DB Primary", type="database", criticality="critical", status="active", source_environment=env)
    c_d = Component(name="DB Replica", type="database", criticality="high", status="active", source_environment=env)
    
    db.add_all([c_a, c_b, c_c, c_d])
    db.commit()
    for c in [c_a, c_b, c_c, c_d]:
        db.refresh(c)
        
    d1 = Dependency(source_id=c_a.id, target_id=c_b.id, relationship_type="calls", criticality="high", source_environment=env)
    d2 = Dependency(source_id=c_b.id, target_id=c_c.id, relationship_type="queries", criticality="critical", source_environment=env)
    d3 = Dependency(source_id=c_b.id, target_id=c_d.id, relationship_type="replicates", criticality="high", source_environment=env)
    
    db.add_all([d1, d2, d3])
    db.commit()
    
    spof_result = find_spofs(db, source_environment=env)
    assert "spof_nodes" in spof_result
    assert spof_result["spof_count"] >= 1
    
    spof_ids = [s["id"] for s in spof_result["spof_nodes"]]
    assert c_b.id in spof_ids
    
    # Test through REST API endpoint
    api_res = client.get(f"/api/twin/spof?source_environment={env}")
    assert api_res.status_code == 200
    api_data = api_res.json()
    if isinstance(api_data, list):
        assert len(api_data) >= 1
        assert any(s["id"] == c_b.id or s.get("component_id") == c_b.id for s in api_data)
    else:
        assert api_data["spof_count"] >= 1
        assert any(s["id"] == c_b.id for s in api_data["spof_nodes"])
    
    db.close()

def test_phase1_data_model_foundation(client):
    """Verify Phase 1 data model representations: Environment, Component, Dependency, Simulation."""
    from models import Environment, Simulation
    from migrations import run_migrations
    from tests.conftest import test_engine

    # 1. Verify schema migration execution
    run_migrations(test_engine)

    db = TestingSessionLocal()
    
    # 2. ENVIRONMENT model verification
    env = Environment(
        id="env_mumbai_cloud",
        name="Mumbai Cloud Production",
        type="cloud",
        region="ap-south-1"
    )
    db.add(env)
    db.commit()
    db.refresh(env)

    assert env.id == "env_mumbai_cloud"
    assert env.name == "Mumbai Cloud Production"
    assert env.type == "cloud"
    assert env.region == "ap-south-1"
    assert env.created_at is not None
    assert env.updated_at is not None

    # Test via REST API
    env_res = client.get("/api/environments")
    assert env_res.status_code == 200
    envs_list = env_res.json()
    assert any(e["id"] == "env_mumbai_cloud" for e in envs_list)

    # 3. INFRASTRUCTURE COMPONENT model verification
    comp = Component(
        name="k8s-ingress-controller",
        type="network",
        environment="kubernetes",
        provider="aws",
        region="ap-south-1",
        location="ap-south-1",
        status="active",
        criticality="critical",
        owner="InfraOps",
        cpu=4.0,
        memory=16.0,
        cost_per_month=185.50,
        currency="INR",
        position_x=220.0,
        position_y=350.0,
        telemetry={"p99_latency_ms": 12.4, "health": "healthy"},
        metadata_col={"cluster": "eks-prod-mumbai", "namespace": "ingress-nginx"},
        source_environment="env_mumbai_cloud"
    )
    db.add(comp)
    db.commit()
    db.refresh(comp)

    assert comp.environment_id == "env_mumbai_cloud"
    assert comp.provider == "aws"
    assert comp.region == "ap-south-1"
    assert comp.status == "active"
    assert comp.criticality == "critical"
    assert comp.cost_per_month == 185.50
    assert comp.currency == "INR"
    assert comp.position_x == 220.0
    assert comp.position_y == 350.0
    assert comp.telemetry["health"] == "healthy"
    assert comp.metadata_info["cluster"] == "eks-prod-mumbai"
    assert comp.created_at is not None
    assert comp.updated_at is not None

    # 4. DEPENDENCY model verification
    comp_target = Component(
        name="auth-service-pod",
        type="application",
        environment="kubernetes",
        provider="aws",
        region="ap-south-1",
        source_environment="env_mumbai_cloud"
    )
    db.add(comp_target)
    db.commit()
    db.refresh(comp_target)

    dep = Dependency(
        source_id=comp.id,
        target_id=comp_target.id,
        relationship_type="routes_to",
        criticality="critical",
        source_environment="env_mumbai_cloud",
        metadata_col={"protocol": "gRPC", "port": 50051}
    )
    db.add(dep)
    db.commit()
    db.refresh(dep)

    assert dep.environment_id == "env_mumbai_cloud"
    assert dep.relationship_type == "routes_to"
    assert dep.criticality == "critical"
    assert dep.metadata_col["protocol"] == "gRPC"
    assert dep.created_at is not None

    # 5. SIMULATION model verification
    sim = Simulation(
        source_environment="env_mumbai_cloud",
        target_component_id=comp.id,
        action="fail",
        destination_env="cloud",
        affected_components=[comp_target.id],
        risk_score=85,
        risk_level="CRITICAL",
        estimated_downtime_minutes=30,
        cost_delta_monthly=0.0,
        status="completed"
    )
    db.add(sim)
    db.commit()
    db.refresh(sim)

    assert sim.environment_id == "env_mumbai_cloud"
    assert sim.component_id == comp.id
    assert sim.action == "fail"
    assert sim.affected_components == [comp_target.id]
    assert sim.risk_score == 85
    assert sim.risk_level == "CRITICAL"
    assert sim.estimated_downtime_minutes == 30
    assert sim.result_status == "completed"
    assert sim.created_at is not None

    db.close()

