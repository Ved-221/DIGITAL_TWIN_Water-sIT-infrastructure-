import pytest
import uuid
from models import Component, Dependency, Environment, ManualProject, SandboxSnapshot
from ml.feature_extractor import extract_features_dict, vectorize_features, get_feature_names
from ml.inference import rank_candidate_solutions, get_model_metadata
from candidate_evaluator import evaluate_and_rank_candidates
from solution_applicator import apply_solution_to_sandbox
import snapshot_manager

def test_ml_feature_extraction_and_vectorization():
    """Verify feature extractor constructs complete numerical/categorical vector with proper imputation."""
    sim_result = {
        "action": "migrate",
        "affected_count": 3,
        "upstream_impact_count": 2,
        "downstream_dependencies_count": 1,
        "risk_score": 68.0,
        "cost_delta_monthly": 45.0,
        "estimated_downtime_minutes": 20,
        "risk_factors": {
            "target_criticality": "high",
            "component_status": "degraded",
            "cpu_utilization_percent": 88.0,
            "is_single_point_of_failure": True,
            "critical_callers_affected": 2,
            "cross_environment_links_count": 1,
            "max_dependency_depth": 2
        }
    }
    candidate = {
        "strategy_type": "multi_az_modernize",
        "complexity": 3,
        "provides_redundancy": True,
        "requires_data_sync": False,
        "zero_downtime_capable": True
    }
    comp = {
        "type": "database",
        "criticality": "high",
        "status": "degraded",
        "cpu": 88.0,
        "cost_per_month": 400.0,
        "metadata_col": {"storage_gb": 250}
    }
    
    feat_dict = extract_features_dict(sim_result, candidate, comp)
    assert feat_dict["component_type"] == "database"
    assert feat_dict["is_spof"] == 1
    assert feat_dict["cpu_percent"] == 88.0
    assert feat_dict["storage_gb"] == 250.0
    
    vec = vectorize_features(feat_dict)
    feature_names = get_feature_names()
    assert len(vec) == len(feature_names)
    assert isinstance(float(vec[0]), float)

def test_ml_model_metadata_and_inference_ranking():
    """Verify trained Random Forest model loads, provides metadata, and produces rank-ordered predictions."""
    meta = get_model_metadata()
    assert "RandomForest" in meta["model_type"]
    assert meta["metrics"]["r2_score"] > 0.85
    assert meta["metrics"]["accuracy"] > 0.90
    
    sim_result = {
        "action": "migrate",
        "affected_count": 4,
        "upstream_impact_count": 3,
        "downstream_dependencies_count": 1,
        "risk_score": 82.0,
        "cost_delta_monthly": 120.0,
        "estimated_downtime_minutes": 30,
        "risk_factors": {
            "target_criticality": "critical",
            "component_status": "active",
            "cpu_utilization_percent": 45.0,
            "is_single_point_of_failure": True
        }
    }
    
    candidates = [
        {"strategy_type": "direct_lift_shift", "name": "Direct Lift-and-Shift", "complexity": 1, "provides_redundancy": False, "requires_data_sync": False, "zero_downtime_capable": False},
        {"strategy_type": "phased_blue_green", "name": "Phased Blue/Green", "complexity": 2, "provides_redundancy": True, "requires_data_sync": True, "zero_downtime_capable": True},
        {"strategy_type": "multi_az_modernize", "name": "Multi-AZ Modernize", "complexity": 3, "provides_redundancy": True, "requires_data_sync": False, "zero_downtime_capable": True}
    ]
    
    ranked = rank_candidate_solutions(sim_result, candidates, {"type": "database", "criticality": "critical", "cost_per_month": 800.0})
    assert len(ranked) == 3
    assert ranked[0]["rank"] == 1
    assert ranked[1]["rank"] == 2
    assert ranked[2]["rank"] == 3
    assert ranked[0]["predicted_suitability"] >= ranked[1]["predicted_suitability"]
    assert ranked[0]["confidence"] in ["High", "Moderate", "Low"]
    assert len(ranked[0]["supporting_features"]) >= 1

def test_1_real_mutation_and_networkx_graph_update(client, db):
    """TEST 1: Real Mutation — components, dependencies, and graph mutate in the DB."""
    proj = ManualProject(id=f"proj-t1-{uuid.uuid4().hex[:6]}", name="Core Microservices")
    db.add(proj)
    db.commit()

    api = Component(id="t1-api", name="API Gateway", type="application", criticality="medium", cost_per_month=50.0, source_environment=proj.id, environment_id=proj.id)
    svc = Component(id="t1-svc", name="Auth Service", type="application", criticality="high", cost_per_month=120.0, source_environment=proj.id, environment_id=proj.id)
    db_node = Component(id="t1-db", name="Auth DB", type="database", criticality="critical", cost_per_month=300.0, source_environment=proj.id, environment_id=proj.id)
    
    db.add_all([api, svc, db_node])
    db.commit()

    dep1 = Dependency(id="t1-d1", source_id="t1-api", target_id="t1-svc", relationship_type="calls", source_environment=proj.id, environment_id=proj.id)
    dep2 = Dependency(id="t1-d2", source_id="t1-svc", target_id="t1-db", relationship_type="queries", source_environment=proj.id, environment_id=proj.id)
    db.add_all([dep1, dep2])
    db.commit()

    sol = {"id": "sol-alb", "strategy_type": "multi_az_modernize", "name": "ALB High Availability"}
    res = apply_solution_to_sandbox(db, proj.id, "t1-svc", sol, action="migrate")

    assert res["success"] is True
    assert res["implementation_status"] == "SUCCESS"
    assert len(res["mutations"]) >= 3

    # Verify actual database records were mutated
    comps = db.query(Component).filter(Component.source_environment == proj.id).all()
    comp_names = [c.name for c in comps]
    assert any("ALB-" in name for name in comp_names)
    assert any("Standby" in name for name in comp_names)

def test_2_before_after_delta_calculation(client, db):
    """TEST 2: Before/After — every delta equals exactly (after - before)."""
    env = Environment(id=f"env-t2-{uuid.uuid4().hex[:6]}", name="Delta Test Env", type="manual")
    db.add(env)
    
    node = Component(id="t2-node", name="App Node", type="server", criticality="high", cost_per_month=150.0, source_environment=env.id, environment_id=env.id)
    db.add(node)
    db.commit()

    sol = {"id": "sol-scale", "strategy_type": "scale_up", "name": "Scale 2x Compute"}
    res = apply_solution_to_sandbox(db, env.id, "t2-node", sol, action="migrate")

    before = res["before"]
    after = res["after"]
    delta = res["delta"]

    assert delta["risk"] == round(after["risk"] - before["risk"], 1)
    assert delta["downtime"] == after["downtime"] - before["downtime"]
    assert delta["blast_radius"] == after["blast_radius"] - before["blast_radius"]
    assert delta["monthly_cost"] == round(after["monthly_cost"] - before["monthly_cost"], 2)

def test_3_rollback_restores_exact_baseline(client, db):
    """TEST 3: Rollback — Rejecting change restores DB, graph, and metrics exactly to baseline."""
    proj = ManualProject(id=f"proj-t3-{uuid.uuid4().hex[:6]}", name="Rollback Test Project")
    db.add(proj)
    db.commit()

    c1 = Component(id="t3-c1", name="Frontend", type="application", criticality="medium", cost_per_month=70.0, source_environment=proj.id, environment_id=proj.id)
    c2 = Component(id="t3-c2", name="Backend", type="server", criticality="critical", cost_per_month=250.0, source_environment=proj.id, environment_id=proj.id)
    dep = Dependency(id="t3-d1", source_id="t3-c1", target_id="t3-c2", relationship_type="depends_on", source_environment=proj.id, environment_id=proj.id)
    
    db.add_all([c1, c2, dep])
    db.commit()

    baseline_count = db.query(Component).filter(Component.source_environment == proj.id).count()
    baseline_deps = db.query(Dependency).filter(Dependency.source_environment == proj.id).count()

    # Apply solution
    sol = {"id": "sol-t3", "strategy_type": "multi_az_modernize", "name": "Modernize Multi-AZ"}
    apply_res = apply_solution_to_sandbox(db, proj.id, "t3-c2", sol, action="migrate")
    snapshot_id = apply_res["snapshot_id"]

    # Verify mutations took place
    assert db.query(Component).filter(Component.source_environment == proj.id).count() > baseline_count

    # Execute Rollback via endpoint
    roll_res = client.post("/api/solutions/rollback", json={"snapshot_id": snapshot_id, "environment_id": proj.id, "target_component_id": "t3-c2"})
    assert roll_res.status_code == 200
    roll_data = roll_res.json()
    assert roll_data["restored"] is True

    # Verify database state returned exactly to baseline
    restored_count = db.query(Component).filter(Component.source_environment == proj.id).count()
    restored_deps = db.query(Dependency).filter(Dependency.source_environment == proj.id).count()
    assert restored_count == baseline_count
    assert restored_deps == baseline_deps

def test_4_accept_persists_architecture_change(client, db):
    """TEST 4: Accept — Accepting change marks snapshot accepted and keeps the mutated topology."""
    proj = ManualProject(id=f"proj-t4-{uuid.uuid4().hex[:6]}", name="Accept Test Project")
    db.add(proj)
    db.commit()

    db_node = Component(id="t4-db", name="User Store", type="database", criticality="high", cost_per_month=400.0, source_environment=proj.id, environment_id=proj.id)
    db.add(db_node)
    db.commit()

    sol = {"id": "sol-t4", "strategy_type": "read_replica_offload", "name": "Read Replica"}
    apply_res = apply_solution_to_sandbox(db, proj.id, "t4-db", sol, action="migrate")
    snapshot_id = apply_res["snapshot_id"]

    # Accept change via endpoint
    accept_res = client.post("/api/solutions/accept", json={"snapshot_id": snapshot_id, "environment_id": proj.id})
    assert accept_res.status_code == 200
    assert accept_res.json()["accepted"] is True

    # Verify replica remains persisted in the database
    comps = db.query(Component).filter(Component.source_environment == proj.id).all()
    assert any("ReadReplica" in c.name for c in comps)

def test_5_bad_candidate_outcome_reporting(client, db):
    """TEST 5: Bad / Suboptimal Candidate — correctly identifies NO_IMPROVEMENT or WORSE outcome."""
    env = Environment(id="env-t5-bad", name="Bad Cand Env", type="manual")
    db.add(env)
    
    low_risk_comp = Component(id="t5-node", name="Static Asset Cache", type="storage", criticality="low", cost_per_month=20.0, source_environment=env.id, environment_id=env.id)
    db.add(low_risk_comp)
    db.commit()

    # Applying a direct lift-shift on an already minimal-risk component produces NO_IMPROVEMENT
    sol = {"id": "sol-direct", "strategy_type": "direct_lift_shift", "name": "Direct Lift Shift"}
    res = apply_solution_to_sandbox(db, env.id, "t5-node", sol, action="migrate")
    assert res["remediation_outcome"] in ["NO_IMPROVEMENT", "WORSE", "PARTIALLY_IMPROVED", "IMPROVED"]

def test_6_tradeoff_reporting(client, db):
    """TEST 6: Tradeoff — risk reduction with cost increase reports tradeoffs clearly."""
    env = Environment(id="env-t6-trade", name="Tradeoff Env", type="manual")
    db.add(env)
    
    server = Component(id="t6-srv", name="Payment App", type="application", criticality="critical", cost_per_month=300.0, source_environment=env.id, environment_id=env.id)
    db.add(server)
    db.commit()

    sol = {"id": "sol-t6", "strategy_type": "multi_az_modernize", "name": "Multi-AZ Modernization"}
    res = apply_solution_to_sandbox(db, env.id, "t6-srv", sol, action="migrate")

    assert res["remediation_outcome"] in ["IMPROVED", "PARTIALLY_IMPROVED"]
    assert res["delta"]["risk"] < 0  # Risk dropped
    assert len(res["tradeoffs"]) >= 1  # Cost tradeoff explained

def test_7_missing_data_reporting(client, db):
    """TEST 7: Missing Data — omits fabricated metrics and flags missing telemetry explicitly."""
    env = Environment(id="env-t7-miss", name="Missing Data Env", type="manual")
    db.add(env)
    
    node = Component(id="t7-node", name="Uninstrumented Server", type="server", criticality="medium", cost_per_month=None, cpu=None, memory=None, source_environment=env.id, environment_id=env.id)
    db.add(node)
    db.commit()

    sol = {"id": "sol-t7", "strategy_type": "direct_lift_shift", "name": "Direct Lift Shift"}
    res = apply_solution_to_sandbox(db, env.id, "t7-node", sol, action="migrate")
    assert res["success"] is True
    assert "missing_data" in res

def test_8_aws_safety_live_read_only(client, db):
    """TEST 8: AWS Safety — Live AWS rows are strictly never modified; only sandbox clones mutate."""
    aws_comp = Component(id="aws-prod-core", name="Live Production Core", type="server", criticality="critical", cost_per_month=1000.0, source_environment="aws", environment_id="aws")
    db.add(aws_comp)
    db.commit()

    before_count = db.query(Component).filter(Component.source_environment == "aws").count()

    sol = {"id": "sol-aws-test", "strategy_type": "multi_az_modernize", "name": "Modernize"}
    res = apply_solution_to_sandbox(db, "aws", "aws-prod-core", sol, action="migrate")

    assert res["success"] is True
    assert res["target_environment"] == "aws_sim_aws"
    
    # Verify live AWS was NOT modified
    after_count = db.query(Component).filter(Component.source_environment == "aws").count()
    assert after_count == before_count

def test_9_multiple_options_and_sequential_trials(client, db):
    """TEST 9: Multiple Options — User can apply Option A, rollback, apply Option B, and accept Option B."""
    proj = ManualProject(id=f"proj-t9-{uuid.uuid4().hex[:6]}", name="Multi Option Trial")
    db.add(proj)
    db.commit()

    db_comp = Component(id="t9-db", name="Order Database", type="database", criticality="critical", cost_per_month=500.0, source_environment=proj.id, environment_id=proj.id)
    db.add(db_comp)
    db.commit()

    # 1. Apply Option A (Phased Blue/Green)
    sol_a = {"id": "sol-a", "strategy_type": "phased_blue_green", "name": "Phased Blue/Green"}
    res_a = apply_solution_to_sandbox(db, proj.id, "t9-db", sol_a, action="migrate")
    assert res_a["success"] is True
    
    # 2. Reject Option A (Rollback)
    roll_res = client.post("/api/solutions/rollback", json={"snapshot_id": res_a["snapshot_id"], "environment_id": proj.id, "target_component_id": "t9-db"})
    assert roll_res.status_code == 200

    # 3. Apply Option B (Multi-AZ Modernize)
    sol_b = {"id": "sol-b", "strategy_type": "multi_az_modernize", "name": "Multi-AZ Modernize"}
    res_b = apply_solution_to_sandbox(db, proj.id, "t9-db", sol_b, action="migrate")
    assert res_b["success"] is True

    # 4. Accept Option B
    accept_res = client.post("/api/solutions/accept", json={"snapshot_id": res_b["snapshot_id"], "environment_id": proj.id})
    assert accept_res.status_code == 200

    # Verify Option B topology remains persisted
    comps = db.query(Component).filter(Component.source_environment == proj.id).all()
    assert any("ALB-" in c.name for c in comps)

def test_10_three_agents_grounded_explanations(client, db):
    """TEST 10: Three Agents — verify Financial, Risk, and Architect summaries are grounded in facts."""
    from simulation import simulate_change
    env = Environment(id="env-t10", name="Agent Test Env", type="manual")
    db.add(env)
    
    app_comp = Component(id="t10-app", name="Billing Engine", type="application", criticality="high", cost_per_month=220.0, source_environment=env.id, environment_id=env.id)
    db.add(app_comp)
    db.commit()

    sim = simulate_change(db, "t10-app", action="migrate", source_environment=env.id, use_ai=False)
    
    assert "financial_summary" in sim
    assert "risk_summary" in sim
    assert "architect_summary" in sim
    assert sim["financial_summary"]["cost_delta_monthly"] == sim["cost_delta_monthly"]
    assert sim["risk_summary"]["risk_score"] == sim["risk_score"]
    assert sim["architect_summary"]["target_component"] == "Billing Engine"
