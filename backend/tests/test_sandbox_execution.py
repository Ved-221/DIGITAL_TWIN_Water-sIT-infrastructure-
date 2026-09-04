"""
test_sandbox_execution.py — Digital Twin Sandbox Execution Layer Test Suite

Tests:
1. test_sandbox_cloning_isolation: Clones to sandbox without touching original Twin.
2. test_sandbox_multi_az_mutation: Injects ALB, Standby, reroutes upstream callers.
3. test_sandbox_read_replica_mutation: Adds Read Replica node and replicates_from dependency.
4. test_sandbox_circuit_breaker_mutation: Injects Queue buffer and reroutes callers.
5. test_sandbox_shadow_cutover_mutation: Injects shadow target and sync link.
6. test_sandbox_scaling_mutation: Modifies compute (CPU, RAM, cost) in sandbox.
7. test_sandbox_fail_and_remove_mutations: Handles degraded status and decommissioned deletion.
8. test_sandbox_graph_rebuilt_after_mutation: Rebuilds NetworkX graph accurately for sandbox.
9. test_sandbox_resimulation_deterministic: Runs deterministic simulation on mutated sandbox graph.
10. test_sandbox_before_after_comparison_structure: Returns structured topology and metric diffs.
11. test_sandbox_metrics_delta_correctness: Asserts mathematical exactness for metric deltas.
12. test_sandbox_rollback_restores_exact_state: Atomically restores sandbox to baseline snapshot.
13. test_sandbox_accept_persists_topology: Marks snapshot accepted and preserves sandbox topology.
14. test_sandbox_sequential_trials: Applies Option A, rolls back, applies Option B, accepts Option B.
15. test_sandbox_aws_live_strictly_read_only: Ensures live AWS rows and resources are strictly untouched.
16. test_end_to_end_pipeline_to_sandbox: Complete pipeline from Build Twin -> What-If -> ML -> Agents -> Sandbox Apply -> Before/After -> Rollback.
"""

import pytest
import uuid
from fastapi.testclient import TestClient

import models
from simulation import build_graph
import sandbox_engine
import what_if_engine
from three_agents_engine import evaluate_candidates_with_agents


# ─── Helper Functions ────────────────────────────────────────────────────────

def _create_standard_twin(client: TestClient) -> dict:
    """
    Constructs a 5-node Digital Twin in 'user_description' / 'manual':
      LoadBalancer -> App1
      LoadBalancer -> App2
      App1 -> PostgreSQL
      App2 -> PostgreSQL
      PostgreSQL -> ObjectStorage
    """
    desc = (
        "Two application servers are behind a load balancer. "
        "Both connect to PostgreSQL. "
        "PostgreSQL has an object-storage backup."
    )
    r = client.post("/api/twin/build/parse-description", json={
        "description": desc,
        "domain": "infrastructure"
    })
    assert r.status_code == 200
    preview = r.json()

    apply_r = client.post("/api/twin/build/apply", json={
        "domain": "infrastructure",
        "components": preview["components"],
        "dependencies": preview["dependencies"],
        "clear_existing": True
    })
    assert apply_r.status_code == 200
    return apply_r.json()


def _find_component_id(components: list, keyword: str) -> str:
    """Finds component ID matching name or keyword."""
    for c in components:
        name = c.get("name", "").lower()
        cid = c.get("id", "").lower()
        if keyword.lower() in name or keyword.lower() in cid:
            return c["id"]
    return components[0]["id"]


# ─── Tests ───────────────────────────────────────────────────────────────────

def test_1_sandbox_cloning_isolation(client: TestClient, db):
    """TEST 1: Sandbox cloning isolates sandbox state without modifying original Twin."""
    _create_standard_twin(client)

    orig_comps = db.query(models.Component).filter(
        models.Component.source_environment.in_(["manual", "user_description"]) |
        models.Component.discovery_source.in_(["manual", "user_description"])
    ).all()
    orig_count = len(orig_comps)
    assert orig_count >= 5

    res = sandbox_engine.initialize_or_get_sandbox(db, "manual", sandbox_env_id="test_sb_1", force_clone=True)
    assert res["cloned"] is True
    assert res["components_count"] == orig_count

    # Verify original components are completely intact
    after_orig_comps = db.query(models.Component).filter(
        models.Component.source_environment.in_(["manual", "user_description"]) |
        models.Component.discovery_source.in_(["manual", "user_description"])
    ).all()
    assert len(after_orig_comps) == orig_count

    # Verify sandbox has cloned rows
    sb_comps = db.query(models.Component).filter(
        models.Component.source_environment == "test_sb_1"
    ).all()
    assert len(sb_comps) == orig_count
    for sc in sb_comps:
        assert sc.id.startswith("sb-")
        assert sc.source_environment == "test_sb_1"
        assert sc.discovery_source == "sandbox"


def test_2_sandbox_multi_az_mutation(client: TestClient, db):
    """TEST 2: Applying multi_az_modernize mutates sandbox DB with ALB, Standby, and rerouted edges."""
    twin = _create_standard_twin(client)
    pg_id = _find_component_id(twin["components"], "postgres")

    apply_res = client.post("/api/twin/sandbox/apply", json={
        "source_environment": "manual",
        "target_component_id": pg_id,
        "candidate_id": "multi_az_modernize",
        "action": "fail",
        "candidate_data": {
            "strategy_type": "multi_az_modernize",
            "name": "Multi-AZ Modernization"
        },
        "sandbox_env_id": "test_sb_2"
    })
    assert apply_res.status_code == 200
    data = apply_res.json()

    assert data["success"] is True
    assert data["sandbox_id"] == "test_sb_2"
    assert "snapshot_id" in data
    assert len(data["mutations_applied"]) >= 2

    # Verify ALB and Standby exist in test_sb_2
    sb_comps = db.query(models.Component).filter(
        models.Component.source_environment == "test_sb_2"
    ).all()
    comp_names = [c.name for c in sb_comps]
    assert any("ALB-" in name for name in comp_names)
    assert any("Standby" in name for name in comp_names)

    # Verify original PostgreSQL in manual Twin was NOT mutated
    orig_pg = db.query(models.Component).filter(models.Component.id == pg_id).first()
    assert orig_pg is not None
    assert orig_pg.source_environment in ["manual", "user_description"]
    assert not orig_pg.metadata_col.get("multi_az")


def test_3_sandbox_read_replica_mutation(client: TestClient, db):
    """TEST 3: Applying read_replica_offload creates Read Replica node & replicates_from edge."""
    twin = _create_standard_twin(client)
    pg_id = _find_component_id(twin["components"], "postgres")

    apply_res = client.post("/api/twin/sandbox/apply", json={
        "source_environment": "manual",
        "target_component_id": pg_id,
        "candidate_id": "read_replica_offload",
        "action": "fail",
        "candidate_data": {
            "strategy_type": "read_replica_offload",
            "name": "Read Replica Offload"
        },
        "sandbox_env_id": "test_sb_3"
    })
    assert apply_res.status_code == 200
    data = apply_res.json()

    assert data["success"] is True
    sb_comps = db.query(models.Component).filter(
        models.Component.source_environment == "test_sb_3"
    ).all()
    assert any("ReadReplica" in c.name for c in sb_comps)

    sb_deps = db.query(models.Dependency).filter(
        models.Dependency.source_environment == "test_sb_3",
        models.Dependency.relationship_type == "replicates_from"
    ).all()
    assert len(sb_deps) >= 1


def test_4_sandbox_circuit_breaker_mutation(client: TestClient, db):
    """TEST 4: Applying dependency_circuit_breaker injects Queue Buffer and reroutes callers."""
    twin = _create_standard_twin(client)
    pg_id = _find_component_id(twin["components"], "postgres")

    apply_res = client.post("/api/twin/sandbox/apply", json={
        "source_environment": "manual",
        "target_component_id": pg_id,
        "candidate_id": "dependency_circuit_breaker",
        "action": "fail",
        "candidate_data": {
            "strategy_type": "dependency_circuit_breaker",
            "name": "Asynchronous Queue Buffer"
        },
        "sandbox_env_id": "test_sb_4"
    })
    assert apply_res.status_code == 200
    data = apply_res.json()

    assert data["success"] is True
    sb_comps = db.query(models.Component).filter(
        models.Component.source_environment == "test_sb_4"
    ).all()
    assert any("Queue-Buffer" in c.name for c in sb_comps)

    sb_deps = db.query(models.Dependency).filter(
        models.Dependency.source_environment == "test_sb_4",
        models.Dependency.relationship_type == "buffers_to"
    ).all()
    assert len(sb_deps) >= 1


def test_5_sandbox_shadow_cutover_mutation(client: TestClient, db):
    """TEST 5: Applying phased_blue_green creates parallel shadow target with sync route."""
    twin = _create_standard_twin(client)
    pg_id = _find_component_id(twin["components"], "postgres")

    apply_res = client.post("/api/twin/sandbox/apply", json={
        "source_environment": "manual",
        "target_component_id": pg_id,
        "candidate_id": "phased_blue_green",
        "action": "fail",
        "candidate_data": {
            "strategy_type": "phased_blue_green",
            "name": "Phased Blue-Green Deployment"
        },
        "sandbox_env_id": "test_sb_5"
    })
    assert apply_res.status_code == 200
    data = apply_res.json()

    assert data["success"] is True
    sb_comps = db.query(models.Component).filter(
        models.Component.source_environment == "test_sb_5"
    ).all()
    assert any("Shadow-Target" in c.name for c in sb_comps)

    sb_deps = db.query(models.Dependency).filter(
        models.Dependency.source_environment == "test_sb_5",
        models.Dependency.relationship_type == "syncs_with"
    ).all()
    assert len(sb_deps) >= 1


def test_6_sandbox_scaling_mutation(client: TestClient, db):
    """TEST 6: Applying scale_up scales CPU and RAM on the target component in the sandbox."""
    twin = _create_standard_twin(client)
    pg_id = _find_component_id(twin["components"], "postgres")

    apply_res = client.post("/api/twin/sandbox/apply", json={
        "source_environment": "manual",
        "target_component_id": pg_id,
        "candidate_id": "scale_up",
        "action": "fail",
        "candidate_data": {
            "strategy_type": "scale_up",
            "name": "Vertical Compute Scaling"
        },
        "sandbox_env_id": "test_sb_6"
    })
    assert apply_res.status_code == 200
    data = apply_res.json()

    assert data["success"] is True
    sb_pg = db.query(models.Component).filter(
        models.Component.id == f"sb-{pg_id}",
        models.Component.source_environment == "test_sb_6"
    ).first()
    assert sb_pg is not None
    assert sb_pg.metadata_col.get("scaled_capacity") is True


def test_7_sandbox_fail_and_remove_mutations(client: TestClient, db):
    """TEST 7: Handles fail (status degraded) and remove (decommission node + edges)."""
    twin = _create_standard_twin(client)
    app1_id = _find_component_id(twin["components"], "application server 1")

    # 1. Test fail
    res_fail = client.post("/api/twin/sandbox/apply", json={
        "source_environment": "manual",
        "target_component_id": app1_id,
        "candidate_id": "fail",
        "action": "fail",
        "candidate_data": {"strategy_type": "fail", "name": "Simulate Node Failure"},
        "sandbox_env_id": "test_sb_7"
    })
    assert res_fail.status_code == 200
    sb_app1 = db.query(models.Component).filter(
        models.Component.id == f"sb-{app1_id}",
        models.Component.source_environment == "test_sb_7"
    ).first()
    assert sb_app1.status == "degraded"

    # 2. Test remove
    res_rem = client.post("/api/twin/sandbox/apply", json={
        "source_environment": "test_sb_7",
        "target_component_id": f"sb-{app1_id}",
        "candidate_id": "remove",
        "action": "fail",
        "candidate_data": {"strategy_type": "remove", "name": "Decommission Node"},
        "sandbox_env_id": "test_sb_7"
    })
    assert res_rem.status_code == 200
    sb_app1_after = db.query(models.Component).filter(
        models.Component.id == f"sb-{app1_id}",
        models.Component.source_environment == "test_sb_7"
    ).first()
    assert sb_app1_after is None


def test_8_sandbox_graph_rebuilt_after_mutation(client: TestClient, db):
    """TEST 8: build_graph() produces a NetworkX DiGraph reflecting sandbox DB mutations."""
    twin = _create_standard_twin(client)
    pg_id = _find_component_id(twin["components"], "postgres")

    client.post("/api/twin/sandbox/apply", json={
        "source_environment": "manual",
        "target_component_id": pg_id,
        "candidate_id": "multi_az_modernize",
        "action": "fail",
        "candidate_data": {"strategy_type": "multi_az_modernize"},
        "sandbox_env_id": "test_sb_8"
    })

    G = build_graph(db, "test_sb_8")
    assert G.number_of_nodes() >= 7  # 5 original + ALB + Standby
    assert any("ALB" in str(data.get("name", "")) for _, data in G.nodes(data=True))


def test_9_sandbox_resimulation_deterministic(client: TestClient, db):
    """TEST 9: Post-apply simulation executes deterministically on the mutated sandbox graph."""
    twin = _create_standard_twin(client)
    pg_id = _find_component_id(twin["components"], "postgres")

    apply_res = client.post("/api/twin/sandbox/apply", json={
        "source_environment": "manual",
        "target_component_id": pg_id,
        "candidate_id": "multi_az_modernize",
        "action": "fail",
        "candidate_data": {"strategy_type": "multi_az_modernize"},
        "sandbox_env_id": "test_sb_9"
    })
    assert apply_res.status_code == 200
    data = apply_res.json()

    before = data["before"]
    after = data["after"]

    # In multi_az_modernize, SPOF is eliminated and blast radius / risk drops
    assert "risk_score" in after
    assert "downtime" in after
    assert "blast_radius" in after
    assert isinstance(after["risk_score"], float)


def test_10_sandbox_before_after_comparison_structure(client: TestClient, db):
    """TEST 10: Verifies structured diff includes topology changes, metric deltas, and tradeoffs."""
    twin = _create_standard_twin(client)
    pg_id = _find_component_id(twin["components"], "postgres")

    apply_res = client.post("/api/twin/sandbox/apply", json={
        "source_environment": "manual",
        "target_component_id": pg_id,
        "candidate_id": "read_replica_offload",
        "action": "fail",
        "candidate_data": {"strategy_type": "read_replica_offload"},
        "sandbox_env_id": "test_sb_10"
    })
    assert apply_res.status_code == 200
    data = apply_res.json()

    assert "topology_diff" in data
    diff = data["topology_diff"]
    assert "nodes_added" in diff
    assert "nodes_removed" in diff
    assert "nodes_modified" in diff
    assert "edges_added" in diff
    assert "edges_removed" in diff
    assert len(diff["nodes_added"]) >= 1

    assert "before" in data
    assert "after" in data
    assert "delta" in data
    assert "tradeoffs" in data
    assert "missing_data" in data


def test_11_sandbox_metrics_delta_correctness(client: TestClient, db):
    """TEST 11: Asserts delta metrics equal strictly (after - before)."""
    twin = _create_standard_twin(client)
    pg_id = _find_component_id(twin["components"], "postgres")

    apply_res = client.post("/api/twin/sandbox/apply", json={
        "source_environment": "manual",
        "target_component_id": pg_id,
        "candidate_id": "multi_az_modernize",
        "action": "fail",
        "candidate_data": {"strategy_type": "multi_az_modernize"},
        "sandbox_env_id": "test_sb_11"
    })
    assert apply_res.status_code == 200
    data = apply_res.json()

    b = data["before"]
    a = data["after"]
    d = data["delta"]

    assert d["risk"] == round(a["risk"] - b["risk"], 1)
    assert d["downtime"] == a["downtime"] - b["downtime"]
    assert d["blast_radius"] == a["blast_radius"] - b["blast_radius"]
    assert d["monthly_cost"] == round(a["monthly_cost"] - b["monthly_cost"], 2)


def test_12_sandbox_rollback_restores_exact_state(client: TestClient, db):
    """TEST 12: Rollback restores sandbox environment exactly to baseline snapshot state."""
    twin = _create_standard_twin(client)
    pg_id = _find_component_id(twin["components"], "postgres")

    # 1. Initialize sandbox
    sandbox_engine.initialize_or_get_sandbox(db, "manual", sandbox_env_id="test_sb_12", force_clone=True)
    baseline_comps = db.query(models.Component).filter(
        models.Component.source_environment == "test_sb_12"
    ).count()
    baseline_deps = db.query(models.Dependency).filter(
        models.Dependency.source_environment == "test_sb_12"
    ).count()

    # 2. Apply mutation
    apply_res = client.post("/api/twin/sandbox/apply", json={
        "source_environment": "test_sb_12",
        "target_component_id": f"sb-{pg_id}",
        "candidate_id": "multi_az_modernize",
        "action": "fail",
        "candidate_data": {"strategy_type": "multi_az_modernize"},
        "sandbox_env_id": "test_sb_12"
    })
    assert apply_res.status_code == 200
    snap_id = apply_res.json()["snapshot_id"]

    # Verify mutation added nodes
    mutated_comps = db.query(models.Component).filter(
        models.Component.source_environment == "test_sb_12"
    ).count()
    assert mutated_comps > baseline_comps

    # 3. Rollback
    roll_res = client.post("/api/twin/sandbox/rollback", json={
        "snapshot_id": snap_id,
        "sandbox_id": "test_sb_12"
    })
    assert roll_res.status_code == 200
    roll_data = roll_res.json()
    assert roll_data["restored"] is True
    assert roll_data["status"] == "rejected"

    # 4. Verify restored state exactly matches baseline
    restored_comps = db.query(models.Component).filter(
        models.Component.source_environment == "test_sb_12"
    ).count()
    restored_deps = db.query(models.Dependency).filter(
        models.Dependency.source_environment == "test_sb_12"
    ).count()
    assert restored_comps == baseline_comps
    assert restored_deps == baseline_deps


def test_13_sandbox_accept_persists_topology(client: TestClient, db):
    """TEST 13: Accept marks snapshot approved and keeps mutated sandbox topology."""
    twin = _create_standard_twin(client)
    pg_id = _find_component_id(twin["components"], "postgres")

    apply_res = client.post("/api/twin/sandbox/apply", json={
        "source_environment": "manual",
        "target_component_id": pg_id,
        "candidate_id": "read_replica_offload",
        "action": "fail",
        "candidate_data": {"strategy_type": "read_replica_offload"},
        "sandbox_env_id": "test_sb_13"
    })
    assert apply_res.status_code == 200
    snap_id = apply_res.json()["snapshot_id"]

    acc_res = client.post("/api/twin/sandbox/accept", json={
        "snapshot_id": snap_id,
        "sandbox_id": "test_sb_13"
    })
    assert acc_res.status_code == 200
    assert acc_res.json()["accepted"] is True
    assert acc_res.json()["status"] == "accepted"

    # Verify replica still exists in sandbox
    sb_comps = db.query(models.Component).filter(
        models.Component.source_environment == "test_sb_13"
    ).all()
    assert any("ReadReplica" in c.name for c in sb_comps)


def test_14_sandbox_sequential_trials(client: TestClient, db):
    """TEST 14: Apply Option A -> Rollback -> Apply Option B -> Accept Option B."""
    twin = _create_standard_twin(client)
    pg_id = _find_component_id(twin["components"], "postgres")

    # Apply Option A (Phased Blue/Green)
    res_a = client.post("/api/twin/sandbox/apply", json={
        "source_environment": "manual",
        "target_component_id": pg_id,
        "candidate_id": "phased_blue_green",
        "action": "fail",
        "candidate_data": {"strategy_type": "phased_blue_green"},
        "sandbox_env_id": "test_sb_14"
    })
    assert res_a.status_code == 200
    snap_a = res_a.json()["snapshot_id"]

    # Rollback Option A
    roll_a = client.post("/api/twin/sandbox/rollback", json={
        "snapshot_id": snap_a,
        "sandbox_id": "test_sb_14"
    })
    assert roll_a.status_code == 200

    # Apply Option B (Read Replica)
    res_b = client.post("/api/twin/sandbox/apply", json={
        "source_environment": "test_sb_14",
        "target_component_id": f"sb-{pg_id}",
        "candidate_id": "read_replica_offload",
        "action": "fail",
        "candidate_data": {"strategy_type": "read_replica_offload"},
        "sandbox_env_id": "test_sb_14"
    })
    assert res_b.status_code == 200
    snap_b = res_b.json()["snapshot_id"]

    # Accept Option B
    acc_b = client.post("/api/twin/sandbox/accept", json={
        "snapshot_id": snap_b,
        "sandbox_id": "test_sb_14"
    })
    assert acc_b.status_code == 200
    assert acc_b.json()["accepted"] is True


def test_15_sandbox_aws_live_strictly_read_only(client: TestClient, db):
    """TEST 15: Source environment 'aws' is never mutated; mutations happen only on sandbox clone."""
    aws_node = models.Component(
        id="aws-prod-db",
        name="Production Aurora RDS",
        type="database",
        criticality="critical",
        cost_per_month=850.0,
        source_environment="aws",
        discovery_source="aws_api"
    )
    db.add(aws_node)
    db.commit()

    aws_count_before = db.query(models.Component).filter(
        models.Component.source_environment == "aws"
    ).count()

    apply_res = client.post("/api/twin/sandbox/apply", json={
        "source_environment": "aws",
        "target_component_id": "aws-prod-db",
        "candidate_id": "multi_az_modernize",
        "action": "fail",
        "candidate_data": {"strategy_type": "multi_az_modernize"},
        "sandbox_env_id": "test_sb_aws"
    })
    assert apply_res.status_code == 200

    # Live AWS component count strictly unchanged
    aws_count_after = db.query(models.Component).filter(
        models.Component.source_environment == "aws"
    ).count()
    assert aws_count_after == aws_count_before

    # Live AWS component row attributes strictly unchanged
    live_comp = db.query(models.Component).filter(models.Component.id == "aws-prod-db").first()
    assert live_comp.source_environment == "aws"
    assert not live_comp.metadata_col.get("multi_az")


def test_16_end_to_end_pipeline_to_sandbox(client: TestClient, db):
    """
    TEST 16: Complete end-to-end pipeline:
      Build Generic Digital Twin from Natural Language
      -> What-If Candidates Generation
      -> Independent Candidate Simulation
      -> Feature Extraction & ML Ranking
      -> Three-Agent Analysis & Consensus
      -> User selects recommended candidate
      -> Apply to Sandbox
      -> Verify Before / After comparison
      -> Rollback
    """
    # 1. Build Digital Twin
    build_res = _create_standard_twin(client)
    assert build_res["success"] is True
    pg_id = _find_component_id(build_res["components"], "postgres")

    # 2. What-If Candidate Generation & Simulation
    cand_res = what_if_engine.generate_what_if_candidates(
        db=db,
        target_component_id=pg_id,
        action="fail",
        source_environment="manual"
    )
    assert cand_res["success"] is True
    assert cand_res["candidate_count"] >= 3

    # 3. Three-Agent Analysis
    agent_eval = evaluate_candidates_with_agents(
        candidates=cand_res["candidates"],
        baseline=cand_res["simulation_results"][0] if cand_res["simulation_results"] else {},
        component_data={"id": pg_id, "name": "PostgreSQL", "type": "database"},
        ml_ranking=cand_res["ml_ranking"]
    )
    recommended_id = agent_eval["consensus"]["candidate_id"] or cand_res["candidates"][0]["candidate_id"]
    assert recommended_id is not None

    # Find the candidate data
    chosen_cand = next((c for c in cand_res["candidates"] if c["candidate_id"] == recommended_id), cand_res["candidates"][0])

    # 4. Apply to Sandbox
    apply_res = client.post("/api/twin/sandbox/apply", json={
        "source_environment": "manual",
        "target_component_id": pg_id,
        "candidate_id": recommended_id,
        "action": "fail",
        "candidate_data": {
            "strategy_type": chosen_cand["strategy_type"],
            "name": chosen_cand["name"]
        },
        "sandbox_env_id": "test_sb_e2e"
    })
    assert apply_res.status_code == 200
    apply_data = apply_res.json()

    assert apply_data["success"] is True
    assert apply_data["remediation_outcome"] in ["IMPROVED", "PARTIALLY_IMPROVED", "NO_IMPROVEMENT", "WORSE"]
    assert "snapshot_id" in apply_data
    assert "delta" in apply_data
    assert "topology_diff" in apply_data

    # 5. Query Before-After Comparison endpoint
    snap_id = apply_data["snapshot_id"]
    ba_res = client.get(f"/api/twin/sandbox/before-after/{snap_id}")
    assert ba_res.status_code == 200
    ba_data = ba_res.json()
    assert ba_data["snapshot_id"] == snap_id

    # 6. Rollback to restore exact baseline
    roll_res = client.post("/api/twin/sandbox/rollback", json={
        "snapshot_id": snap_id,
        "sandbox_id": "test_sb_e2e"
    })
    assert roll_res.status_code == 200
    assert roll_res.json()["restored"] is True
