"""
test_ml_candidate_ranking.py — Test Suite for ML-Based Candidate Ranking

Tests:
1. Feature extraction from actual Twin data.
2. Missing data handling (null with _data_available=False, never arbitrary numbers).
3. Candidate ranking interface (rank_candidates contract).
4. ML unavailable fallback (ranking_status="unavailable", deterministic results preserved).
5. Model inference failure fallback (exception handled gracefully, no crash or fabricated score).
6. Multiple candidates receiving independent feature sets.
7. No fabricated numerical values.
8. Recommendation references an existing candidate.
9. Original Twin remains unchanged in DB.
10. Deterministic simulation results remain unchanged by ML.
"""

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from ml.candidate_ranker import (
    extract_candidate_features,
    rank_candidates,
    build_structured_recommendation_object,
    RANKING_METHOD_PROTOTYPE,
)
import what_if_engine


# ─── Test Helpers ────────────────────────────────────────────────────────────

def _create_standard_topology(client: TestClient):
    """
    Build a standard Twin:
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
    raise AssertionError(f"Component containing '{name_fragment}' not found.")


# ─── Test 1: Feature extraction from actual Twin data ────────────────────────

def test_feature_extraction_from_actual_twin_data(client):
    _create_standard_topology(client)
    pg_id = _get_component_id_by_name(client, "postgres")

    resp = client.post("/api/twin/what-if/candidates", json={
        "target_component_id": pg_id,
        "action": "fail",
    })
    assert resp.status_code == 200
    data = resp.json()

    extracted_features = data.get("extracted_features", [])
    assert len(extracted_features) >= 2, "Expected features for at least 2 candidates"

    for feat in extracted_features:
        assert "candidate_id" in feat
        assert "strategy_type" in feat
        assert "affected_component_count" in feat
        assert "dependency_depth" in feat
        assert "critical_dependency_count" in feat
        assert "spof_indicator" in feat
        assert "topology_change_size" in feat
        assert "cost_data_available" in feat
        assert "downtime_data_available" in feat
        assert "risk_score_available" in feat
        assert "provides_redundancy" in feat
        assert "zero_downtime_capable" in feat
        assert "feasibility" in feat

        # Verify affected_component_count matches simulation blast_radius
        matching_cand = next(c for c in data["candidates"] if c["candidate_id"] == feat["candidate_id"])
        assert feat["affected_component_count"] == matching_cand["simulation_result"]["blast_radius"]
        assert feat["provides_redundancy"] == matching_cand["provides_redundancy"]


# ─── Test 2: Missing data handling ───────────────────────────────────────────

def test_missing_data_handling():
    """
    Explicit missing data must produce null values and _data_available=False,
    NEVER fabricated arbitrary numbers.
    """
    candidate_mock = {
        "candidate_id": "cand-test-01",
        "strategy_type": "direct_lift_shift",
        "proposed_changes": [],
        "affected_components": [],
        "simulation_result": {
            "blast_radius": 2,
            "upstream_impact_count": 1,
            "downstream_dependencies_count": 1,
            "cost_delta_monthly": None,           # Missing cost
            "estimated_downtime_minutes": None,   # Missing downtime
            "risk_score": 45.0,
            "spof_eliminated": False,
            "vs_baseline": {"blast_radius_delta": 0, "risk_score_delta": 0.0},
        },
        "available_metrics": [],
        "missing_data": ["cost_per_month"],
        "feasibility": "unknown",
        "provides_redundancy": False,
        "zero_downtime_capable": False,
        "complexity": 1,
    }
    baseline_mock = {
        "action": "fail",
        "is_single_point_of_failure": True,
        "topology": {"node_count": 3, "edge_count": 2},
    }

    feat = extract_candidate_features(
        candidate=candidate_mock,
        baseline=baseline_mock,
        component=None,
        component_data=None,
    )

    assert feat["cost_delta"] is None, "Missing cost must be None"
    assert feat["cost_data_available"] is False
    assert feat["estimated_downtime_minutes"] is None, "Missing downtime must be None"
    assert feat["downtime_data_available"] is False
    assert "cost_per_month" in feat["missing_data"]


# ─── Test 3: Candidate ranking interface ─────────────────────────────────────

def test_candidate_ranking_interface(client):
    _create_standard_topology(client)
    pg_id = _get_component_id_by_name(client, "postgres")

    resp = client.post("/api/twin/what-if/candidates", json={
        "target_component_id": pg_id,
        "action": "fail",
    })
    assert resp.status_code == 200
    data = resp.json()

    ranking = data.get("ml_ranking", [])
    assert len(ranking) >= 2, "Expected multiple ranked candidate items"

    ranks = [r["rank"] for r in ranking]
    assert ranks == list(range(1, len(ranking) + 1)), "Ranks must be contiguous 1-indexed"

    top_item = ranking[0]
    assert top_item["rank"] == 1
    assert top_item["recommendation"] is True
    assert top_item["ranking_method"] == RANKING_METHOD_PROTOTYPE
    assert isinstance(top_item["features_used"], list)
    assert len(top_item["features_used"]) > 0
    assert isinstance(top_item["explanation"], str)

    # Non-top items must have recommendation=False
    for non_top in ranking[1:]:
        assert non_top["recommendation"] is False


# ─── Test 4: ML unavailable fallback ─────────────────────────────────────────

def test_ml_unavailable_fallback(client):
    """
    When ML model is unavailable, ranking_status='unavailable', no fake
    recommendation is fabricated, and independently simulated candidates are returned.
    """
    _create_standard_topology(client)
    pg_id = _get_component_id_by_name(client, "postgres")

    with patch("what_if_engine.rank_candidates") as mock_rank:
        mock_rank.return_value = {
            "ranking_status": "unavailable",
            "ranking_method": "none",
            "ranked_candidates": [],
            "recommended_candidate_id": None,
            "evidence": ["ML model not available."],
            "limitations": ["ML model is unavailable; returning deterministic candidates without ML ranking."],
            "missing_data": [],
        }

        resp = client.post("/api/twin/what-if/candidates", json={
            "target_component_id": pg_id,
            "action": "fail",
        })
        assert resp.status_code == 200
        data = resp.json()

        assert data["ranking_status"] == "unavailable"
        assert data["recommended_candidate_id"] is None
        assert data["recommendation"] is None
        assert data["ml_ranking"] == []
        # Candidates and deterministic simulation results must still be returned!
        assert len(data["candidates"]) >= 2
        for c in data["candidates"]:
            assert "simulation_result" in c


# ─── Test 5: Model inference failure fallback ────────────────────────────────

def test_model_inference_failure_fallback(client):
    """
    If ML inference raises an exception, the system catches it, returns
    ranking_status='unavailable', does not crash, and does not fabricate scores.
    """
    candidates_with_feat = [
        {
            "candidate_id": "cand-01",
            "strategy_type": "direct_lift_shift",
            "affected_component_count": 2,
            "upstream_impact_count": 1,
            "downstream_dependencies_count": 1,
            "dependency_depth": 1,
            "critical_dependency_count": 0,
            "spof_indicator": True,
            "spof_eliminated": False,
            "topology_change_size": 0,
            "dependency_change_count": 0,
            "cost_delta": None,
            "cost_data_available": False,
            "estimated_downtime_minutes": None,
            "downtime_data_available": False,
            "risk_score": 50.0,
            "risk_score_available": True,
            "blast_radius_delta": 0,
            "risk_score_delta": 0.0,
            "provides_redundancy": False,
            "zero_downtime_capable": False,
            "complexity": 1,
            "feasibility": "unknown",
            "missing_data": [],
        }
    ]
    raw_candidates = [{"candidate_id": "cand-01", "strategy_type": "direct_lift_shift"}]
    baseline = {"action": "fail", "is_single_point_of_failure": True}

    res = rank_candidates(
        candidates_with_features=candidates_with_feat,
        candidates_raw=raw_candidates,
        baseline=baseline,
        simulate_inference_failure=True,
    )

    assert res["ranking_status"] == "unavailable"
    assert res["recommended_candidate_id"] is None
    assert res["ranked_candidates"] == []
    assert "ML model inference failed" in res["limitations"][0]


# ─── Test 6: Multiple candidates receive independent feature sets ─────────────

def test_multiple_candidates_independent_features(client):
    _create_standard_topology(client)
    pg_id = _get_component_id_by_name(client, "postgres")

    resp = client.post("/api/twin/what-if/candidates", json={
        "target_component_id": pg_id,
        "action": "fail",
    })
    assert resp.status_code == 200
    features = resp.json()["extracted_features"]

    # Compare features across candidates
    strat_types = [f["strategy_type"] for f in features]
    change_sizes = [f["topology_change_size"] for f in features]
    redundancies = [f["provides_redundancy"] for f in features]

    # Verify diversity across candidates
    assert len(set(strat_types)) >= 2, "Candidates must have different strategy types"
    assert max(change_sizes) > min(change_sizes), "Candidates must have different topology change sizes"
    assert any(redundancies) and not all(redundancies), "Redundancy flag must vary across candidates"


# ─── Test 7: No fabricated numerical values ──────────────────────────────────

def test_no_fabricated_numerical_values(client):
    """
    When components have no telemetry and no cost metrics, extracted features
    must strictly report cost_delta=None (not 500 or 0.0) and cost_data_available=False.
    """
    _create_standard_topology(client)
    pg_id = _get_component_id_by_name(client, "postgres")

    resp = client.post("/api/twin/what-if/candidates", json={
        "target_component_id": pg_id,
        "action": "fail",
    })
    assert resp.status_code == 200
    features = resp.json()["extracted_features"]

    for feat in features:
        # In natural language description, cost_per_month is not supplied
        assert feat["cost_delta"] is None, (
            f"Fabricated cost detected: {feat['cost_delta']}! Must be None when unsupplied."
        )
        assert feat["cost_data_available"] is False


# ─── Test 8: Recommendation references an existing candidate ─────────────────

def test_recommendation_references_existing_candidate(client):
    _create_standard_topology(client)
    pg_id = _get_component_id_by_name(client, "postgres")

    resp = client.post("/api/twin/what-if/candidates", json={
        "target_component_id": pg_id,
        "action": "fail",
    })
    assert resp.status_code == 200
    data = resp.json()

    candidate_ids = {c["candidate_id"] for c in data["candidates"]}
    rec_id = data.get("recommended_candidate_id")

    assert rec_id is not None, "A candidate should be recommended when data is ranked"
    assert rec_id in candidate_ids, (
        f"Recommended ID '{rec_id}' not found among candidate IDs: {candidate_ids}"
    )

    if data.get("recommendation"):
        assert data["recommendation"]["recommended_candidate_id"] == rec_id


# ─── Test 9: Original Twin remains unchanged ─────────────────────────────────

def test_original_twin_unchanged_after_ml_ranking(client):
    _create_standard_topology(client)
    pg_id = _get_component_id_by_name(client, "postgres")

    before_comps = client.get("/api/twin/components").json()
    before_deps = client.get("/api/twin/dependencies").json()

    # Run What-If with ML ranking
    resp = client.post("/api/twin/what-if/candidates", json={
        "target_component_id": pg_id,
        "action": "fail",
    })
    assert resp.status_code == 200

    after_comps = client.get("/api/twin/components").json()
    after_deps = client.get("/api/twin/dependencies").json()

    assert len(before_comps) == len(after_comps)
    assert {c["id"] for c in before_comps} == {c["id"] for c in after_comps}
    assert len(before_deps) == len(after_deps)
    assert {d["id"] for d in before_deps} == {d["id"] for d in after_deps}


# ─── Test 10: Deterministic simulation results unchanged by ML ───────────────

def test_deterministic_simulation_results_unchanged_by_ml(client):
    """
    ML ranking must never rewrite deterministic simulation results.
    The simulation results returned must match what was calculated on the graphs.
    """
    _create_standard_topology(client)
    pg_id = _get_component_id_by_name(client, "postgres")

    resp = client.post("/api/twin/what-if/candidates", json={
        "target_component_id": pg_id,
        "action": "fail",
    })
    assert resp.status_code == 200
    data = resp.json()

    for cand in data["candidates"]:
        sim = cand["simulation_result"]
        # Blast radius must equal upstream + downstream counts
        assert sim["blast_radius"] == sim["upstream_impact_count"] + sim["downstream_dependencies_count"]
        # vs_baseline delta must equal candidate blast_radius minus baseline blast_radius
        base_blast = data["original_baseline"]["blast_radius"]
        assert sim["vs_baseline"]["blast_radius_delta"] == sim["blast_radius"] - base_blast
