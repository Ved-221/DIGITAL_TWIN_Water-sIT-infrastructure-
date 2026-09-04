"""
test_three_agents_decision.py — Three-Agent Decision & Explanation Layer Test Suite

Tests:
1. Financial Analyst receives only available financial data.
2. Risk Analyst receives actual topology/simulation facts.
3. Architect receives actual candidate topology.
4. Agents do not create new dependencies.
5. Agents do not fabricate numerical values.
6. Agent failure is handled safely.
7. Missing financial information becomes unknown.
8. Missing telemetry becomes unknown.
9. Consensus references an existing candidate.
10. Agent disagreement is preserved.
11. ML ranking remains unchanged by agent interpretation.
12. Original Twin remains unchanged.
13. Full pipeline end-to-end test.
"""

import pytest
from fastapi.testclient import TestClient

from three_agents_engine import (
    run_financial_analyst,
    run_risk_analyst,
    run_architect_analyst,
    build_agent_consensus,
    evaluate_candidates_with_agents,
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


# ─── Test 1: Financial Analyst receives only available financial data ────────

def test_financial_analyst_receives_only_available_data(client):
    _create_standard_topology(client)
    pg_id = _get_component_id_by_name(client, "postgres")

    resp = client.post("/api/twin/what-if/candidates", json={
        "target_component_id": pg_id,
        "action": "fail",
    })
    assert resp.status_code == 200
    data = resp.json()

    fin = data.get("financial_analyst")
    assert fin is not None
    assert fin["agent"] == "financial_analyst"
    assert fin["status"] in ("complete", "unavailable")

    # In natural language description, cost was unsupplied
    assert fin["cost_status"] == "unknown"
    assert "Cost information is unavailable" in fin["summary"]
    assert "cost_per_month" in fin["unknowns"]


# ─── Test 2: Risk Analyst receives actual topology/simulation facts ──────────

def test_risk_analyst_receives_actual_topology_facts(client):
    _create_standard_topology(client)
    pg_id = _get_component_id_by_name(client, "postgres")

    resp = client.post("/api/twin/what-if/candidates", json={
        "target_component_id": pg_id,
        "action": "fail",
    })
    assert resp.status_code == 200
    data = resp.json()

    risk = data.get("risk_analyst")
    assert risk is not None
    assert risk["agent"] == "risk_analyst"
    assert risk["status"] == "complete"

    base_blast = data["original_baseline"]["blast_radius"]
    base_risk = data["original_baseline"]["risk_score"]

    # Evidence must directly reference actual blast radius and risk score
    evidence_str = " ".join(risk["evidence"])
    assert str(base_blast) in evidence_str
    assert str(base_risk) in evidence_str


# ─── Test 3: Architect receives actual candidate topology ────────────────────

def test_architect_receives_actual_candidate_topology(client):
    _create_standard_topology(client)
    pg_id = _get_component_id_by_name(client, "postgres")

    resp = client.post("/api/twin/what-if/candidates", json={
        "target_component_id": pg_id,
        "action": "fail",
    })
    assert resp.status_code == 200
    data = resp.json()

    arch = data.get("system_architect")
    assert arch is not None
    assert arch["agent"] == "system_architect"
    assert arch["status"] == "complete"

    # Evidence must reference proposed mutations
    assert len(arch["evidence"]) > 0
    assert any("Proposed mutation" in e or "redundancy" in e.lower() for e in arch["evidence"])


# ─── Test 4: Agents do not create new dependencies ───────────────────────────

def test_agents_do_not_create_new_dependencies(client):
    _create_standard_topology(client)
    pg_id = _get_component_id_by_name(client, "postgres")

    before_deps = client.get("/api/twin/dependencies").json()
    before_dep_ids = {d["id"] for d in before_deps}

    resp = client.post("/api/twin/what-if/candidates", json={
        "target_component_id": pg_id,
        "action": "fail",
    })
    assert resp.status_code == 200

    after_deps = client.get("/api/twin/dependencies").json()
    after_dep_ids = {d["id"] for d in after_deps}

    assert before_dep_ids == after_dep_ids, "Agents must not create dependencies in the DB"


# ─── Test 5: Agents do not fabricate numerical values ────────────────────────

def test_agents_do_not_fabricate_numerical_values(client):
    _create_standard_topology(client)
    pg_id = _get_component_id_by_name(client, "postgres")

    resp = client.post("/api/twin/what-if/candidates", json={
        "target_component_id": pg_id,
        "action": "fail",
    })
    assert resp.status_code == 200
    data = resp.json()

    # Risk Analyst should not invent failure probabilities or percentages
    risk = data["risk_analyst"]
    combined_risk_text = (risk["summary"] + " " + " ".join(risk["findings"])).lower()
    assert "99.9%" not in combined_risk_text
    assert "probability of failure" not in combined_risk_text

    # Financial Analyst should not fabricate dollar numbers when cost is missing
    fin = data["financial_analyst"]
    if fin["cost_status"] == "unknown":
        assert "$500" not in fin["summary"]
        assert fin["recommended_candidate_id"] is None


# ─── Test 6: Agent failure is handled safely ─────────────────────────────────

def test_agent_failure_handled_safely(client):
    """
    If one agent fails, its status='unavailable', other agents proceed,
    and the pipeline does not crash.
    """
    candidates_mock = [
        {
            "candidate_id": "cand-01",
            "name": "Direct Lift and Shift",
            "strategy_type": "direct_lift_shift",
            "proposed_changes": [],
            "simulation_result": {"blast_radius": 2, "risk_score": 45.0, "spof_eliminated": False},
        },
        {
            "candidate_id": "cand-02",
            "name": "Multi-AZ Modernization",
            "strategy_type": "multi_az_modernize",
            "proposed_changes": ["Added ALB"],
            "simulation_result": {"blast_radius": 1, "risk_score": 20.0, "spof_eliminated": True},
        },
    ]
    baseline_mock = {"blast_radius": 3, "risk_score": 60.0, "is_single_point_of_failure": True}

    eval_result = evaluate_candidates_with_agents(
        candidates=candidates_mock,
        baseline=baseline_mock,
        fail_agent="financial",
    )

    assert eval_result["financial"]["status"] == "unavailable"
    assert eval_result["financial"]["recommended_candidate_id"] is None
    assert eval_result["risk"]["status"] == "complete"
    assert eval_result["architect"]["status"] == "complete"
    assert eval_result["consensus"]["candidate_id"] is not None


# ─── Test 7: Missing financial information becomes unknown ───────────────────

def test_missing_financial_information_becomes_unknown():
    candidates = [
        {
            "candidate_id": "cand-01",
            "name": "Direct Lift",
            "simulation_result": {"cost_delta_monthly": None},
        }
    ]
    baseline = {"action": "fail"}
    comp_data = {"name": "Database", "cost_per_month": None}

    report = run_financial_analyst(candidates, baseline, comp_data)

    assert report["cost_status"] == "unknown"
    assert "cost_per_month" in report["unknowns"]
    assert report["recommended_candidate_id"] is None
    assert "Cost information is unavailable" in report["summary"]


# ─── Test 8: Missing telemetry becomes unknown ───────────────────────────────

def test_missing_telemetry_becomes_unknown():
    candidates = [
        {
            "candidate_id": "cand-01",
            "name": "Direct Lift",
            "simulation_result": {"blast_radius": 2, "risk_score": 40.0, "spof_eliminated": False},
        }
    ]
    baseline = {"blast_radius": 3, "risk_score": 60.0, "is_single_point_of_failure": True}
    comp_data = {"name": "Server", "cpu": None, "memory": None}

    report = run_risk_analyst(candidates, baseline, comp_data)

    assert "live_cpu_telemetry" in report["unknowns"]
    assert "live_memory_telemetry" in report["unknowns"]


# ─── Test 9: Consensus references an existing candidate ──────────────────────

def test_consensus_references_existing_candidate(client):
    _create_standard_topology(client)
    pg_id = _get_component_id_by_name(client, "postgres")

    resp = client.post("/api/twin/what-if/candidates", json={
        "target_component_id": pg_id,
        "action": "fail",
    })
    assert resp.status_code == 200
    data = resp.json()

    consensus = data.get("consensus")
    assert consensus is not None
    assert consensus["candidate_id"] is not None

    cand_ids = {c["candidate_id"] for c in data["candidates"]}
    assert consensus["candidate_id"] in cand_ids, (
        f"Consensus ID '{consensus['candidate_id']}' must match an existing candidate in {cand_ids}"
    )


# ─── Test 10: Agent disagreement is preserved ────────────────────────────────

def test_agent_disagreement_preserved():
    """
    When financial analyst prefers low cost and risk analyst prefers high resilience,
    conflicts and trade-offs are explicitly exposed in consensus.
    """
    candidates = [
        {
            "candidate_id": "cand-cheap",
            "name": "Direct Lift and Shift",
            "strategy_type": "direct_lift_shift",
            "simulation_result": {"cost_delta_monthly": 0.0, "risk_score": 60.0, "spof_eliminated": False},
        },
        {
            "candidate_id": "cand-resilient",
            "name": "Multi-AZ Modernization",
            "strategy_type": "multi_az_modernize",
            "simulation_result": {"cost_delta_monthly": 50.0, "risk_score": 15.0, "spof_eliminated": True},
        },
    ]
    fin_report = {
        "agent": "financial_analyst",
        "recommended_candidate_id": "cand-cheap",
        "summary": "Prefer cand-cheap",
    }
    risk_report = {
        "agent": "risk_analyst",
        "recommended_candidate_id": "cand-resilient",
        "summary": "Prefer cand-resilient",
    }
    arch_report = {
        "agent": "system_architect",
        "recommended_candidate_id": "cand-resilient",
        "summary": "Prefer cand-resilient",
    }

    consensus = build_agent_consensus(
        financial_report=fin_report,
        risk_report=risk_report,
        architect_report=arch_report,
        candidates=candidates,
    )

    assert consensus["agreement"] == "majority"
    assert len(consensus["conflicts"]) > 0
    assert consensus["conflicts"][0]["dimension"] == "Cost vs Resilience"
    assert "cand-cheap" in consensus["conflicts"][0]["financial_view"]
    assert "cand-resilient" in consensus["conflicts"][0]["risk_view"]
    assert consensus["candidate_id"] in ("cand-resilient", "cand-cheap")


# ─── Test 11: ML ranking remains unchanged by agent interpretation ──────────

def test_ml_ranking_remains_unchanged_by_agents(client):
    _create_standard_topology(client)
    pg_id = _get_component_id_by_name(client, "postgres")

    resp = client.post("/api/twin/what-if/candidates", json={
        "target_component_id": pg_id,
        "action": "fail",
    })
    assert resp.status_code == 200
    data = resp.json()

    ml_ranking = data["ml_ranking"]
    assert len(ml_ranking) >= 2
    # Ranks must be contiguous 1..N
    assert [r["rank"] for r in ml_ranking] == list(range(1, len(ml_ranking) + 1))
    assert ml_ranking[0]["rank"] == 1
    assert ml_ranking[0]["recommendation"] is True


# ─── Test 12: Original Twin remains unchanged ────────────────────────────────

def test_original_twin_remains_unchanged(client):
    _create_standard_topology(client)
    pg_id = _get_component_id_by_name(client, "postgres")

    before_comps = client.get("/api/twin/components").json()
    before_deps = client.get("/api/twin/dependencies").json()

    resp = client.post("/api/twin/what-if/candidates", json={
        "target_component_id": pg_id,
        "action": "fail",
    })
    assert resp.status_code == 200

    after_comps = client.get("/api/twin/components").json()
    after_deps = client.get("/api/twin/dependencies").json()

    assert len(before_comps) == len(after_comps)
    assert len(before_deps) == len(after_deps)


# ─── Test 13: Full pipeline end-to-end ───────────────────────────────────────

def test_full_pipeline_end_to_end(client):
    """
    Verify complete pipeline flow:
    Digital Twin → Scenario → Candidates → Simulation → Features → ML Ranking → 3 Agents → Consensus
    """
    _create_standard_topology(client)
    pg_id = _get_component_id_by_name(client, "postgres")

    resp = client.post("/api/twin/what-if/candidates", json={
        "target_component_id": pg_id,
        "action": "fail",
    })
    assert resp.status_code == 200
    data = resp.json()

    # 1. Pipeline outputs exist
    assert "scenario" in data
    assert "candidates" in data
    assert "simulation_results" in data
    assert "extracted_features" in data
    assert "ml_ranking" in data
    assert "financial_analyst" in data
    assert "risk_analyst" in data
    assert "system_architect" in data
    assert "consensus" in data

    # 2. Consensus matches an existing candidate
    assert data["consensus"]["candidate_id"] in [c["candidate_id"] for c in data["candidates"]]

    # 3. All agents have structured output
    for agent_key in ["financial_analyst", "risk_analyst", "system_architect"]:
        agent = data[agent_key]
        assert "summary" in agent
        assert "findings" in agent
        assert "evidence" in agent
        assert "unknowns" in agent
        assert "status" in agent
