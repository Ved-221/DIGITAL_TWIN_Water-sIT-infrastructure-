import pytest
from models import Component, Dependency, Environment
from simulation import simulate_change, build_graph

def test_dynamic_pipeline_scenarios_a_b_c_d(client, db):
    """
    Test Scenarios:
    A. Manual environment with a simple dependency graph.
    B. Same graph with one dependency added (verifying graph-derived blast radius & risk update).
    C. Same graph with one critical component changed (verifying risk level dynamic update).
    D. AWS environment isolation and handling.
    """
    # SCENARIO A: Simple 2-tier manual environment (Web -> DB)
    env_a = Environment(id="env-dyn-sim-a", name="Dynamic Sim Env A", type="manual")
    db.add(env_a)
    
    web_a = Component(
        id="comp-web-a",
        environment_id=env_a.id,
        source_environment=env_a.id,
        name="web-frontend",
        type="application",
        criticality="low",
        cost_per_month=50.0,
        metadata_col={"storage_gb": 10, "transfer_rate_mbps": 100}
    )
    db_a = Component(
        id="comp-db-a",
        environment_id=env_a.id,
        source_environment=env_a.id,
        name="primary-db",
        type="database",
        criticality="medium",
        cost_per_month=200.0,
        metadata_col={"storage_gb": 100, "transfer_rate_mbps": 50, "target_cost_per_month": 260.0}
    )
    dep_a = Dependency(
        id="dep-a-1",
        environment_id=env_a.id,
        source_environment=env_a.id,
        source_id="comp-web-a",
        target_id="comp-db-a",
        relationship_type="depends_on"
    )
    db.add_all([web_a, db_a, dep_a])
    db.commit()
    
    sim_a = simulate_change(db, target_component_id="comp-db-a", action="migrate", source_environment=env_a.id)
    assert sim_a["upstream_impact_count"] == 1
    assert sim_a["cost_delta_monthly"] == 60.0  # target_cost (260) - actual_cost (200)
    assert sim_a["financial_summary"]["status"] == "Caution"
    assert sim_a["financial_summary"]["cost_delta_monthly"] == 60.0
    initial_risk_score = sim_a["risk_score"]
    
    # SCENARIO B: Same graph with one dependency added (API -> DB)
    api_b = Component(
        id="comp-api-b",
        environment_id=env_a.id,
        source_environment=env_a.id,
        name="analytics-api",
        type="server",
        criticality="high",
        cost_per_month=150.0
    )
    dep_b = Dependency(
        id="dep-b-2",
        environment_id=env_a.id,
        source_environment=env_a.id,
        source_id="comp-api-b",
        target_id="comp-db-a",
        relationship_type="queries"
    )
    db.add_all([api_b, dep_b])
    db.commit()
    
    sim_b = simulate_change(db, target_component_id="comp-db-a", action="migrate", source_environment=env_a.id)
    assert sim_b["upstream_impact_count"] == 2  # Increased callers
    assert sim_b["risk_score"] > initial_risk_score  # Increased blast radius elevates risk score
    
    # SCENARIO C: Change target component criticality to 'critical' and status to 'degraded'
    db_a_comp = db.query(Component).filter(Component.id == "comp-db-a").first()
    db_a_comp.criticality = "critical"
    db_a_comp.status = "degraded"
    db_a_comp.cpu = 92.0
    db.commit()
    
    sim_c = simulate_change(db, target_component_id="comp-db-a", action="migrate", source_environment=env_a.id)
    assert sim_c["risk_score"] > sim_b["risk_score"]
    assert sim_c["risk_level"] in ["CRITICAL", "HIGH"]
    assert sim_c["risk_summary"]["status"] == "High Risk"
    assert sim_c["architect_summary"]["status"] in ["Blocked", "Conditional"]
    assert any("Health hazard" in f for f in sim_c["critical_flags"])
    
    # SCENARIO D: Environment Isolation
    env_aws = Environment(id="aws", name="AWS Production", type="aws")
    db.add(env_aws)
    aws_comp = Component(id="aws-i-12345", environment_id="aws", source_environment="aws", name="aws-prod-ec2", type="server", cost_per_month=80.0)
    db.add(aws_comp)
    db.commit()
    
    G_aws = build_graph(db, "aws")
    assert "aws-i-12345" in G_aws
    assert "comp-db-a" not in G_aws  # Strict multi-environment isolation
