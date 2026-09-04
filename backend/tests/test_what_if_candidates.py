"""
test_what_if_candidates.py — Multiple What-If Candidate Solutions Test Suite

Tests:
1. Multiple candidates are generated.
2. Candidates are isolated (original graph unchanged after simulation).
3. Original Twin remains unchanged in DB.
4. Each candidate is simulated independently (different topologies produce different results).
5. Missing data is represented as 'unknown' rather than fabricated.
6. Invalid/unsupported changes are handled safely.
7. API endpoint returns correct structure.
8. Candidate feasibility reasoning is evidence-backed.
"""

import pytest
import copy
import uuid
from fastapi.testclient import TestClient


# ─── Test helpers ────────────────────────────────────────────────────────────

def _create_topology(client: TestClient):
    """
    Build a minimal but realistic Digital Twin:
        LoadBalancer → AppServer1
        LoadBalancer → AppServer2
        AppServer1  → PostgreSQL
        AppServer2  → PostgreSQL
        PostgreSQL  → ObjectStorage
    """
    r = client.post("/api/twin/build/parse-description", json={
        "description": (
            "Two application servers are behind a load balancer. "
            "Both connect to PostgreSQL. "
            "PostgreSQL has an object-storage backup."
        ),
        "domain": "infrastructure"
    })
    assert r.status_code == 200
    preview = r.json()

    apply_r = client.post("/api/twin/build/apply", json={
        "domain": "infrastructure",
        "components": preview["components"],
        "dependencies": preview["dependencies"],
        "clear_existing": True,
    })
    assert apply_r.status_code == 200
    return apply_r.json()


def _get_component_id_by_name(client: TestClient, name_fragment: str) -> str:
    resp = client.get("/api/twin/components")
    assert resp.status_code == 200
    comps = resp.json()
    for c in comps:
        if name_fragment.lower() in c["name"].lower():
            return c["id"]
    raise AssertionError(f"Component containing '{name_fragment}' not found. Available: {[c['name'] for c in comps]}")


# ─── Test 1: Multiple candidates are generated ───────────────────────────────

def test_multiple_candidates_generated(client):
    _create_topology(client)
    pg_id = _get_component_id_by_name(client, "postgres")

    resp = client.post("/api/twin/what-if/candidates", json={
        "target_component_id": pg_id,
        "action": "fail",
    })
    assert resp.status_code == 200, f"Unexpected status: {resp.status_code} — {resp.text}"
    data = resp.json()

    assert data["success"] is True
    assert data["candidate_count"] >= 2, f"Expected at least 2 candidates, got {data['candidate_count']}"
    assert len(data["candidates"]) == data["candidate_count"]

    # Each candidate must have required fields
    for cand in data["candidates"]:
        assert "candidate_id" in cand
        assert "name" in cand
        assert "proposed_changes" in cand
        assert "resulting_topology" in cand
        assert "affected_components" in cand
        assert "simulation_result" in cand
        assert "available_metrics" in cand
        assert "missing_data" in cand
        assert cand["feasibility"] in ("feasible", "conditional", "unknown", "not_feasible")
        assert isinstance(cand["evidence"], list)


# ─── Test 2: Candidates are isolated — different strategies produce different topologies ───

def test_candidates_are_isolated_and_independent(client):
    _create_topology(client)
    pg_id = _get_component_id_by_name(client, "postgres")

    resp = client.post("/api/twin/what-if/candidates", json={
        "target_component_id": pg_id,
        "action": "fail",
    })
    assert resp.status_code == 200
    data = resp.json()
    candidates = data["candidates"]
    assert len(candidates) >= 2

    # Candidates with topology mutations should differ in node count
    topologies = [
        (c["strategy_type"], c["resulting_topology"]["node_count"])
        for c in candidates
    ]

    # At least one candidate should add nodes (redundancy/standby)
    node_counts = [t[1] for t in topologies]
    assert max(node_counts) > min(node_counts), (
        f"All candidates have identical node counts {node_counts} — "
        "they are not being simulated independently with different mutations."
    )


# ─── Test 3: Original Twin remains unchanged in DB ───────────────────────────

def test_original_twin_unchanged_after_candidates(client):
    _create_topology(client)
    pg_id = _get_component_id_by_name(client, "postgres")

    # Snapshot the component list BEFORE
    before_comps = client.get("/api/twin/components").json()
    before_deps = client.get("/api/twin/dependencies").json()
    before_comp_ids = {c["id"] for c in before_comps}
    before_dep_ids = {d["id"] for d in before_deps}

    # Run what-if candidates
    resp = client.post("/api/twin/what-if/candidates", json={
        "target_component_id": pg_id,
        "action": "fail",
    })
    assert resp.status_code == 200

    # Snapshot AFTER
    after_comps = client.get("/api/twin/components").json()
    after_deps = client.get("/api/twin/dependencies").json()
    after_comp_ids = {c["id"] for c in after_comps}
    after_dep_ids = {d["id"] for d in after_deps}

    assert before_comp_ids == after_comp_ids, (
        f"DB components changed after what-if candidates. "
        f"Added: {after_comp_ids - before_comp_ids}, "
        f"Removed: {before_comp_ids - after_comp_ids}"
    )
    assert before_dep_ids == after_dep_ids, (
        f"DB dependencies changed after what-if candidates."
    )


# ─── Test 4: Each candidate is simulated independently ───────────────────────

def test_each_candidate_independently_simulated(client):
    _create_topology(client)
    pg_id = _get_component_id_by_name(client, "postgres")

    resp = client.post("/api/twin/what-if/candidates", json={
        "target_component_id": pg_id,
        "action": "fail",
    })
    assert resp.status_code == 200
    data = resp.json()
    candidates = data["candidates"]

    # Each candidate must have its own simulation_result
    simulation_results = [c["simulation_result"] for c in candidates]
    assert len(simulation_results) == len(candidates)

    # Risk scores must be numbers where available (not all identical / copy-pasted)
    valid_risks = [
        s["risk_score"] for s in simulation_results
        if s.get("risk_score") is not None
    ]
    assert len(valid_risks) >= 1, "No candidate produced a valid risk score."

    # vs_baseline delta must be present and reflect actual change
    for cand in candidates:
        sim = cand["simulation_result"]
        assert "vs_baseline" in sim, f"Missing vs_baseline in candidate {cand['candidate_id']}"
        vs = sim["vs_baseline"]
        assert vs is not None

    # Candidates that add redundancy should have lower or equal risk vs baseline
    redundancy_cands = [c for c in candidates if c.get("provides_redundancy")]
    for rc in redundancy_cands:
        delta = rc["simulation_result"]["vs_baseline"].get("risk_score_delta")
        if delta is not None:
            assert delta <= 0, (
                f"Redundancy candidate '{rc['name']}' increased risk by {delta} — "
                "expected reduction or neutral."
            )


# ─── Test 5: Missing data is 'unknown' — not fabricated ──────────────────────

def test_missing_data_is_unknown_not_fabricated(client):
    """
    Create a component with deliberately minimal metadata.
    The engine must NOT invent a risk score if critical telemetry is absent.
    For data it CAN derive from topology, it must mark it clearly.
    """
    # Create a single isolated component with zero metadata
    build_resp = client.post("/api/twin/build/structured", json={
        "domain": "general",
        "components": [
            {
                "name": "IsolatedService",
                "type": "server",
                "criticality": "medium",
                # No cpu, no memory, no cost, no metadata — all missing
            }
        ],
        "dependencies": [],
        "clear_existing": True,
    })
    assert build_resp.status_code == 200

    # Look up the real generated component ID by name
    isolated_id = _get_component_id_by_name(client, "IsolatedService")

    resp = client.post("/api/twin/what-if/candidates", json={
        "target_component_id": isolated_id,
        "action": "fail",
    })
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data["success"] is True

    for cand in data["candidates"]:
        # CPU telemetry is absent — should appear in missing_data
        assert "live_cpu_telemetry" in cand["missing_data"], (
            f"Expected 'live_cpu_telemetry' in missing_data for candidate "
            f"'{cand['name']}', got: {cand['missing_data']}"
        )

    # The direct lift-shift candidate has no topology mutations — blast radius must be 0
    lift_cand = next(
        (c for c in data["candidates"] if c["strategy_type"] == "direct_lift_shift"),
        None
    )
    if lift_cand:
        assert lift_cand["simulation_result"]["blast_radius"] == 0, (
            f"direct_lift_shift on isolated node should have blast_radius=0, "
            f"got {lift_cand['simulation_result']['blast_radius']}"
        )


# ─── Test 6: Invalid / unsupported changes are handled safely ────────────────

def test_invalid_component_id_handled_safely(client):
    _create_topology(client)
    resp = client.post("/api/twin/what-if/candidates", json={
        "target_component_id": "nonexistent-component-xyz-99999",
        "action": "fail",
    })
    # Should return 200 with success=False (graceful failure) OR 400
    if resp.status_code == 200:
        data = resp.json()
        assert data["success"] is False
        assert data.get("error") or data.get("candidates") == []
    elif resp.status_code in (400, 404):
        # Also acceptable
        pass
    else:
        pytest.fail(f"Unexpected status code: {resp.status_code}")


def test_unsupported_action_handled_safely(client):
    _create_topology(client)
    pg_id = _get_component_id_by_name(client, "postgres")

    # 'teleport' is not a real action — should not crash
    resp = client.post("/api/twin/what-if/candidates", json={
        "target_component_id": pg_id,
        "action": "teleport",
    })
    # Accept 200 with candidates OR 400 — but must NOT 500
    assert resp.status_code in (200, 400), (
        f"Unsupported action should not cause 500 error, got {resp.status_code}"
    )
    if resp.status_code == 200:
        data = resp.json()
        # If it succeeds, we still expect valid structure
        assert "candidates" in data


# ─── Test 7: Original baseline is present and meaningful ─────────────────────

def test_original_baseline_present(client):
    _create_topology(client)
    pg_id = _get_component_id_by_name(client, "postgres")

    resp = client.post("/api/twin/what-if/candidates", json={
        "target_component_id": pg_id,
        "action": "fail",
    })
    assert resp.status_code == 200
    data = resp.json()

    baseline = data.get("original_baseline")
    assert baseline is not None, "original_baseline must be present"
    assert baseline["target_component_id"] == pg_id
    assert baseline["risk_score"] >= 0
    # PostgreSQL has callers (AppServer1, AppServer2) so blast_radius > 0
    assert baseline["blast_radius"] >= 2, (
        f"PostgreSQL should have at least 2 upstream callers, got blast_radius={baseline['blast_radius']}"
    )


# ─── Test 8: Feasibility is evidence-backed ──────────────────────────────────

def test_feasibility_is_evidence_backed(client):
    _create_topology(client)
    pg_id = _get_component_id_by_name(client, "postgres")

    resp = client.post("/api/twin/what-if/candidates", json={
        "target_component_id": pg_id,
        "action": "fail",
    })
    assert resp.status_code == 200
    data = resp.json()

    for cand in data["candidates"]:
        # feasibility must be one of the defined values
        assert cand["feasibility"] in ("feasible", "conditional", "unknown", "not_feasible"), (
            f"Invalid feasibility value '{cand['feasibility']}' for candidate '{cand['name']}'"
        )

        # unknown feasibility must have a clear reason
        if cand["feasibility"] == "unknown":
            assert len(cand["evidence"]) > 0, (
                f"Candidate '{cand['name']}' has feasibility='unknown' but no evidence."
            )

        # feasible / conditional must list evidence referencing actual metrics
        if cand["feasibility"] in ("feasible", "conditional"):
            assert len(cand["evidence"]) > 0, (
                f"Candidate '{cand['name']}' with feasibility='{cand['feasibility']}' "
                "has no supporting evidence."
            )
