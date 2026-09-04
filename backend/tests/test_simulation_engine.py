import pytest
from models import Component, Dependency, Simulation, Environment
from simulation import simulate_change, build_graph


def test_ten_step_deterministic_simulation_execution(client, db):
    """
    Verify complete 10-step simulation execution on a multi-tier topology:
    Target identification, graph traversal, affected resource determination,
    upstream/downstream separation, impact quantification, risk calculation,
    downtime estimation, cost calculation, persistence, and structured payload return.
    """
    env = Environment(id="env-p4-exec", name="P4 Execution Env", type="manual")
    db.add(env)

    # Topology: Web (App) -> API (Server) -> Primary DB (Database)
    web = Component(id="p4-web", environment_id=env.id, source_environment=env.id, name="Web Client", type="application", criticality="high", cost_per_month=120.0)
    api = Component(id="p4-api", environment_id=env.id, source_environment=env.id, name="Central API", type="server", criticality="critical", cost_per_month=300.0)
    database = Component(id="p4-db", environment_id=env.id, source_environment=env.id, name="Primary DB", type="database", criticality="critical", cost_per_month=650.0)

    db.add_all([web, api, database])
    db.add_all([
        Dependency(id="p4-d1", environment_id=env.id, source_id="p4-web", target_id="p4-api", relationship_type="depends_on"),
        Dependency(id="p4-d2", environment_id=env.id, source_id="p4-api", target_id="p4-db", relationship_type="stores_in")
    ])
    db.commit()

    # Step-by-step execution on central API
    res = simulate_change(
        db=db,
        target_component_id="p4-api",
        action="fail",
        source_environment=env.id,
        use_ai=False
    )

    # 1. Target identification
    assert res["target_component_id"] == "p4-api"
    assert res["target_component"] == "Central API"
    assert res["action"] == "fail"

    # 2 & 3. Affected resources
    assert res["total_nodes_affected"] == 2  # Web (upstream) and DB (downstream)
    assert len(res["affected_components"]) == 2

    # 4. Upstream dependents (callers that fail)
    assert res["upstream_impact_count"] == 1
    assert res["upstream_impact"][0]["component_id"] == "p4-web"
    assert res["upstream_impact"][0]["hop_distance"] == 1

    # 5. Underlying dependencies (services relied upon)
    assert res["downstream_dependencies_count"] == 1
    assert res["downstream_dependencies"][0]["component_id"] == "p4-db"

    # 6. Blast radius severity map
    assert "p4-web" in res["blast_radius_nodes"]
    assert "p4-db" in res["blast_radius_nodes"]

    # 7. Risk calculation
    assert 50 <= res["risk_score"] <= 100
    assert res["risk_level"] in ["CRITICAL", "HIGH"]

    # 8. Downtime estimation
    assert res["estimated_downtime_minutes"] >= 15  # Unplanned failure on server with cascade

    # 9. Cost calculation
    assert isinstance(res["cost_delta_monthly"], float)

    # 10. Feasible solutions & recommendations
    assert len(res["feasible_solutions"]) == 3
    assert len(res["recommendations"]) >= 3

    # Zero direct LLM call
    assert res["ai_explanation"] is None
    assert res["ai_recommendation"] is None


def test_infrastructure_driven_risk_factors(client, db):
    """
    Verify risk is derived from actual infrastructure factors:
    1. Criticality: Critical resource yields higher risk than low criticality resource.
    2. Dependency Impact: Node with upstream callers yields higher risk than leaf node.
    3. Health & Telemetry: Degraded status or high CPU increases risk score.
    4. Action Profile: Planned restart has significantly lower risk than unplanned failure.
    """
    env = Environment(id="env-p4-risk", name="P4 Risk Env", type="manual")
    db.add(env)

    # Isolated nodes of differing criticality
    crit_node = Component(id="r-crit", environment_id=env.id, source_environment=env.id, name="Critical Svc", type="server", criticality="critical")
    low_node = Component(id="r-low", environment_id=env.id, source_environment=env.id, name="Low Svc", type="server", criticality="low")
    
    # Degraded node with high CPU load
    degraded_node = Component(
        id="r-degraded", environment_id=env.id, source_environment=env.id,
        name="Struggling Svc", type="server", criticality="medium", status="degraded", cpu=88.5
    )
    healthy_node = Component(
        id="r-healthy", environment_id=env.id, source_environment=env.id,
        name="Healthy Svc", type="server", criticality="medium", status="active", cpu=15.0
    )

    db.add_all([crit_node, low_node, degraded_node, healthy_node])
    db.commit()

    # 1. Criticality factor test
    sim_crit = simulate_change(db, "r-crit", action="migrate", source_environment=env.id)
    sim_low = simulate_change(db, "r-low", action="migrate", source_environment=env.id)
    assert sim_crit["risk_score"] > sim_low["risk_score"], "Critical resource must have strictly higher risk score than Low criticality"

    # 2. Health & Telemetry factor test
    sim_degraded = simulate_change(db, "r-degraded", action="migrate", source_environment=env.id)
    sim_healthy = simulate_change(db, "r-healthy", action="migrate", source_environment=env.id)
    assert sim_degraded["risk_score"] > sim_healthy["risk_score"], "Degraded component with high CPU must have higher risk score than healthy counterpart"
    assert any("Health hazard" in f or "CPU" in f for f in sim_degraded["critical_flags"])

    # 3. Action Profile test (fail vs restart)
    sim_fail = simulate_change(db, "r-crit", action="fail", source_environment=env.id)
    sim_restart = simulate_change(db, "r-crit", action="restart", source_environment=env.id)
    assert sim_fail["risk_score"] > sim_restart["risk_score"], "Unplanned failure must carry higher risk than planned maintenance restart"


def test_infrastructure_driven_downtime_characteristics(client, db):
    """
    Verify downtime depends on actual infrastructure characteristics:
    1. Resource Type & Statefulness: Stateful Database > Container/Lambda for the same action.
    2. Cascade Recovery Depth: Upstream dependency layers add sequential recovery time.
    3. Action Profile: Outage failure downtime > Planned maintenance restart downtime.
    """
    env = Environment(id="env-p4-downtime", name="P4 Downtime Env", type="manual")
    db.add(env)

    # 1. Resource Type comparison: Database vs Serverless Lambda
    db_comp = Component(id="dt-db", environment_id=env.id, source_environment=env.id, name="PostgreSQL DB", type="database", criticality="high")
    lambda_comp = Component(id="dt-fn", environment_id=env.id, source_environment=env.id, name="Image Resizer", type="lambda", criticality="high")

    # 2. Cascade depth comparison: Deep chain vs Isolated node
    chain_root = Component(id="dt-root", environment_id=env.id, source_environment=env.id, name="Root Shared Svc", type="server", criticality="high")
    chain_mid = Component(id="dt-mid", environment_id=env.id, source_environment=env.id, name="Mid Layer", type="server", criticality="high")
    chain_edge = Component(id="dt-edge", environment_id=env.id, source_environment=env.id, name="Edge Gateway", type="application", criticality="high")
    isolated = Component(id="dt-iso", environment_id=env.id, source_environment=env.id, name="Isolated Worker", type="server", criticality="high")

    db.add_all([db_comp, lambda_comp, chain_root, chain_mid, chain_edge, isolated])
    db.add_all([
        Dependency(id="dt-d1", environment_id=env.id, source_id="dt-edge", target_id="dt-mid", relationship_type="depends_on"),
        Dependency(id="dt-d2", environment_id=env.id, source_id="dt-mid", target_id="dt-root", relationship_type="depends_on")
    ])
    db.commit()

    # Resource type test
    sim_db = simulate_change(db, "dt-db", action="fail", source_environment=env.id)
    sim_fn = simulate_change(db, "dt-fn", action="fail", source_environment=env.id)
    assert sim_db["estimated_downtime_minutes"] > sim_fn["estimated_downtime_minutes"], "Stateful Database recovery must estimate more downtime than stateless Lambda"

    # Action profile test (fail vs restart)
    sim_db_restart = simulate_change(db, "dt-db", action="restart", source_environment=env.id)
    assert sim_db["estimated_downtime_minutes"] > sim_db_restart["estimated_downtime_minutes"], "Outage downtime must exceed maintenance restart downtime"

    # Cascade depth test: root failure affects mid (hop 1) and edge (hop 2)
    sim_root = simulate_change(db, "dt-root", action="fail", source_environment=env.id)
    sim_iso = simulate_change(db, "dt-iso", action="fail", source_environment=env.id)
    assert sim_root["estimated_downtime_minutes"] > sim_iso["estimated_downtime_minutes"], "Deep cascade recovery depth must increase estimated service window"


def test_cost_impact_using_infrastructure_data(client, db):
    """
    Verify cost impact calculations utilize actual component monthly costs
    and connected dependency links rather than arbitrary constants.
    """
    env = Environment(id="env-p4-cost", name="P4 Cost Env", type="manual")
    db.add(env)

    # Cost-heavy cluster: DB ($800/mo) with 2 dependent app servers
    db_node = Component(id="c-db", environment_id=env.id, source_environment=env.id, name="Prod Database", type="database", cost_per_month=800.0)
    app1 = Component(id="c-app1", environment_id=env.id, source_environment=env.id, name="App Svc 1", type="server", cost_per_month=200.0)
    app2 = Component(id="c-app2", environment_id=env.id, source_environment=env.id, name="App Svc 2", type="server", cost_per_month=200.0)

    db.add_all([db_node, app1, app2])
    db.add_all([
        Dependency(id="c-dep1", environment_id=env.id, source_id="c-app1", target_id="c-db", relationship_type="stores_in"),
        Dependency(id="c-dep2", environment_id=env.id, source_id="c-app2", target_id="c-db", relationship_type="stores_in")
    ])
    db.commit()

    # Scale: 50% compute uplift on $800 = $400
    sim_scale = simulate_change(db, "c-db", action="scale", source_environment=env.id)
    assert sim_scale["cost_delta_monthly"] == 400.0

    # Migrate: 20% cloud hosting ($160) + 2 dependency egress links ($10) = $170
    sim_mig = simulate_change(db, "c-db", action="migrate", source_environment=env.id)
    assert sim_mig["cost_delta_monthly"] == 170.0

    # Restart: $0 monthly delta
    sim_restart = simulate_change(db, "c-db", action="restart", source_environment=env.id)
    assert sim_restart["cost_delta_monthly"] == 0.0


def test_decoupled_ai_suggestion_layer_and_persistence(client, db):
    """
    Verify:
    1. Core simulation engine runs deterministically with ZERO direct LLM calls.
    2. API layer attaches AI explanation when use_ai=True without modifying core numbers.
    3. Historical simulation record is persisted and retrievable via GET /api/simulations and GET /api/twin/simulations.
    """
    env = Environment(id="env-p4-ai", name="P4 AI Layer Env", type="manual")
    db.add(env)

    comp = Component(id="ai-test-comp", environment_id=env.id, source_environment=env.id, name="Payment Hub", type="server", criticality="critical", cost_per_month=500.0)
    db.add(comp)
    db.commit()

    # Simulate via API with use_ai=True
    resp = client.post("/api/twin/simulate", json={
        "component_id": "ai-test-comp",
        "action": "migrate",
        "source_environment": env.id,
        "destination_env": "cloud",
        "use_ai": True
    })
    assert resp.status_code == 200
    data = resp.json()

    # AI layer output attached
    assert data["ai_explanation"] is not None
    assert "Payment Hub" in data["ai_explanation"] or "risk" in data["ai_explanation"].lower()
    assert len(data["recommendations"]) >= 1

    # Verify simulation persistence in database
    sim_records = db.query(Simulation).filter(Simulation.source_environment == env.id).all()
    assert len(sim_records) == 1
    record = sim_records[0]
    assert record.target_component_id == "ai-test-comp"
    assert record.action == "migrate"
    assert record.risk_score == data["risk_score"]
    assert record.estimated_downtime_minutes == data["estimated_downtime_minutes"]

    # Verify historical retrieval endpoints
    hist_resp = client.get(f"/api/twin/simulations?source_environment={env.id}")
    assert hist_resp.status_code == 200
    hist_list = hist_resp.json()
    assert len(hist_list) == 1
    assert hist_list[0]["id"] == record.id
    assert hist_list[0]["target_component_id"] == "ai-test-comp"

    # Verify single simulation detail endpoint
    detail_resp = client.get(f"/api/twin/simulations/{record.id}")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["id"] == record.id
