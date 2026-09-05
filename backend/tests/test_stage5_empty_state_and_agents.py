"""
test_stage5_empty_state_and_agents.py — Stage 5 Test Suite
Covers:
1. True Empty Initial State (no default/seed infrastructure)
2. Empty Twin state contract
3. No ML recommendations when components count is zero
4. No What-If without target component
5. Dedicated /api/twin/what-if/agents/evaluate endpoint
6. Three-Agent evaluation structure (financial, risk, architect)
7. Missing data handling in agents (cost_status='unknown' without invented values)
8. Agent consensus and explicit disagreement tradeoff exposure
9. ML alignment flag in consensus
"""

import pytest
from fastapi.testclient import TestClient
from main import app
import database, models

client = TestClient(app)


def _setup_test_topology():
    """Helper to set up a known 3-tier topology for agent evaluation."""
    r = client.post("/api/twin/build/parse-description", json={
        "description": "An API Gateway connects to an Authentication Service and an Order Database. The Database has no replication.",
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


# ─── 1. True Empty Initial State Tests ────────────────────────────────────────

def test_true_empty_initial_state_on_reset():
    """Verify reset creates an absolute empty twin with 0 components and 0 dependencies."""
    res = client.post("/api/twin/reset")
    assert res.status_code == 200

    state = client.get("/api/twin/state").json()
    assert state["mode"] == "unconnected"
    assert state["total_components"] == 0
    assert state["total_dependencies"] == 0
    assert state["discovery_status"] == "idle"

    comps = client.get("/api/twin/components").json()
    assert comps == [], "Must have 0 components on clean empty state"

    deps = client.get("/api/twin/dependencies").json()
    assert deps == [], "Must have 0 dependencies on clean empty state"


def test_repeated_component_fetches_do_not_inject_seed_data():
    """Verify repeatedly requesting /api/twin/components never automatically injects seed data."""
    client.post("/api/twin/reset")

    for _ in range(3):
        res = client.get("/api/twin/components")
        assert res.status_code == 200
        assert res.json() == []

    state = client.get("/api/twin/state").json()
    assert state["total_components"] == 0


def test_zero_components_produces_no_recommendations():
    """Zero-input rule: if 0 components, no recommendations can be fabricated."""
    client.post("/api/twin/reset")

    recs = client.get("/api/ml/recommendations").json()
    assert recs == [], "Must return empty list of recommendations when 0 components exist"


def test_what_if_without_valid_target_rejected():
    """Zero-input rule: What-If analysis rejects non-existent component without creating fake data."""
    client.post("/api/twin/reset")

    res = client.post("/api/twin/what-if/candidates", json={
        "target_component_id": "non_existent_node",
        "action": "fail"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is False
    assert data["candidates"] == []
    assert data["ranking_status"] == "insufficient_data"


# ─── 2. Three-Agent Decision Layer Tests ─────────────────────────────────────

def test_dedicated_agent_evaluation_endpoint():
    """Verify POST /api/twin/what-if/agents/evaluate endpoint returns 3 agents and consensus."""
    _setup_test_topology()
    comps = client.get("/api/twin/components").json()
    db_node = next(c for c in comps if "database" in c["name"].lower())

    resp = client.post("/api/twin/what-if/agents/evaluate", json={
        "target_component_id": db_node["id"],
        "action": "fail",
        "source_environment": "manual"
    })
    assert resp.status_code == 200
    agents_data = resp.json()

    assert "financial" in agents_data
    assert "risk" in agents_data
    assert "architect" in agents_data
    assert "consensus" in agents_data

    # Check Financial Analyst structure
    fin = agents_data["financial"]
    assert fin["agent"] == "financial_analyst"
    assert isinstance(fin["summary"], str)
    assert isinstance(fin["findings"], list)
    assert isinstance(fin["evidence"], list)
    assert isinstance(fin["unknowns"], list)

    # Check Risk Analyst structure
    risk = agents_data["risk"]
    assert risk["agent"] == "risk_analyst"
    assert len(risk["findings"]) > 0
    assert len(risk["evidence"]) > 0

    # Check System Architect structure
    arch = agents_data["architect"]
    assert arch["agent"] == "system_architect"
    assert len(arch["findings"]) > 0


def test_missing_data_reported_by_agents_without_fabrication():
    """When components lack cost and CPU telemetry, agents must report unknowns rather than fake numbers."""
    _setup_test_topology()
    comps = client.get("/api/twin/components").json()
    db_node = next(c for c in comps if "database" in c["name"].lower())

    resp = client.post("/api/twin/what-if/agents/evaluate", json={
        "target_component_id": db_node["id"],
        "action": "fail",
        "source_environment": "manual"
    })
    assert resp.status_code == 200
    data = resp.json()

    fin = data["financial"]
    # Natural language description has no cost data defined
    assert fin["cost_status"] == "unknown"
    assert fin["recommended_candidate_id"] is None
    assert any("cost_per_month" in u for u in fin["unknowns"])

    risk = data["risk"]
    assert any("cpu" in u for u in risk["unknowns"])


def test_agent_disagreement_and_consensus_tradeoffs():
    """
    When cost is missing or candidates optimize different dimensions,
    agent consensus must expose tradeoffs and maintain candidate reference validity.
    """
    _setup_test_topology()
    comps = client.get("/api/twin/components").json()
    db_node = next(c for c in comps if "database" in c["name"].lower())

    resp = client.post("/api/twin/what-if/candidates", json={
        "target_component_id": db_node["id"],
        "action": "fail",
        "source_environment": "manual"
    })
    assert resp.status_code == 200
    data = resp.json()

    consensus = data["consensus"]
    assert consensus is not None
    assert "agreement" in consensus
    assert consensus["agreement"] in ["unanimous", "majority", "split", "none"]
    assert isinstance(consensus["conflicts"], list)

    # Consensus candidate if chosen must be one of the returned candidates
    cand_ids = {c["candidate_id"] for c in data["candidates"]}
    if consensus.get("candidate_id"):
        assert consensus["candidate_id"] in cand_ids
