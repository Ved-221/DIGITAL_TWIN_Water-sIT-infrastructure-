import pytest
from tests.conftest import TestingSessionLocal
from models import Component, Dependency, Simulation
from simulation import build_graph, simulate_change


def test_scoped_graph_construction():
    """Verify build_graph only loads nodes and edges belonging to the specified source_environment."""
    db = TestingSessionLocal()
    
    # Environment A
    cA1 = Component(name="app-a1", type="application", source_environment="env_a")
    cA2 = Component(name="db-a2", type="database", source_environment="env_a")
    db.add_all([cA1, cA2])
    db.commit()
    db.refresh(cA1)
    db.refresh(cA2)
    db.add(Dependency(source_id=cA1.id, target_id=cA2.id, source_environment="env_a"))
    
    # Environment B
    cB1 = Component(name="app-b1", type="application", source_environment="env_b")
    db.add(cB1)
    db.commit()
    
    # Build graph for env_a
    graph_a = build_graph(db, source_environment="env_a")
    assert len(graph_a.nodes()) == 2
    assert cA1.id in graph_a.nodes()
    assert cA2.id in graph_a.nodes()
    assert cB1.id not in graph_a.nodes()
    assert len(graph_a.edges()) == 1
    
    # Build graph for env_b
    graph_b = build_graph(db, source_environment="env_b")
    assert len(graph_b.nodes()) == 1
    assert cB1.id in graph_b.nodes()
    assert len(graph_b.edges()) == 0
    
    db.close()

def test_blast_radius_multi_hop_simulation():
    """Verify simulate_change propagates failure downstream through multi-hop dependencies."""
    db = TestingSessionLocal()
    env = "sim_test_env"
    
    # Pipeline: Auth Service (Root) -> API Gateway (Hop 1) -> Payment Service (Hop 2) -> Ledger DB (Hop 3)
    c_auth = Component(name="auth-service", type="application", criticality="critical", cost_per_month=100.0, source_environment=env)
    c_gw = Component(name="api-gateway", type="server", criticality="high", cost_per_month=150.0, source_environment=env)
    c_pay = Component(name="payment-service", type="application", criticality="critical", cost_per_month=200.0, source_environment=env)
    c_db = Component(name="ledger-db", type="database", criticality="critical", cost_per_month=400.0, source_environment=env)
    
    db.add_all([c_auth, c_gw, c_pay, c_db])
    db.commit()
    for c in [c_auth, c_gw, c_pay, c_db]:
        db.refresh(c)
        
    db.add(Dependency(source_id=c_auth.id, target_id=c_gw.id, criticality="critical", source_environment=env))
    db.add(Dependency(source_id=c_gw.id, target_id=c_pay.id, criticality="critical", source_environment=env))
    db.add(Dependency(source_id=c_pay.id, target_id=c_db.id, criticality="critical", source_environment=env))
    db.commit()
    
    # Run failure simulation on auth-service
    result = simulate_change(
        db=db,
        component_id=c_auth.id,
        action="fail",
        source_environment=env,
        target_environment=None
    )
    
    assert result.component_id == c_auth.id
    assert result.action == "fail"
    assert result.risk_level in ["CRITICAL", "HIGH"]
    assert result.total_nodes_affected == 3
    
    # Check affected component IDs
    affected_ids = [comp["id"] for comp in result.affected_components]
    assert c_gw.id in affected_ids
    assert c_pay.id in affected_ids
    assert c_db.id in affected_ids
    
    # Check hop distances
    hop_map = {comp["id"]: comp["hop_distance"] for comp in result.affected_components}
    assert hop_map[c_gw.id] == 1
    assert hop_map[c_pay.id] == 2
    assert hop_map[c_db.id] == 3
    
    # Verify recommendations and feasible solutions generated
    assert len(result.feasible_solutions) >= 1
    assert len(result.recommendations) >= 1
    
    db.close()

def test_simulation_persistence_and_history(client):
    """Verify simulations are persisted to the database and can be queried via REST API."""
    db = TestingSessionLocal()
    env = "persist_env"
    
    node = Component(name="web-frontend", type="application", criticality="medium", cost_per_month=120.0, source_environment=env)
    db.add(node)
    db.commit()
    db.refresh(node)
    
    # Simulate via API
    sim_payload = {
        "component_id": node.id,
        "action": "migrate",
        "source_environment": env,
        "target_environment": "cloud"
    }
    res = client.post("/api/twin/simulate", json=sim_payload)
    assert res.status_code == 200
    sim_data = res.json()
    assert sim_data["action"] == "migrate"
    assert "feasible_solutions" in sim_data
    
    # Check database persistence
    saved_sims = db.query(Simulation).filter(Simulation.source_environment == env).all()
    assert len(saved_sims) == 1
    saved_sim = saved_sims[0]
    assert saved_sim.component_id == node.id
    assert saved_sim.action == "migrate"
    assert saved_sim.target_environment == "cloud"
    
    # Check API history endpoints
    hist_res = client.get(f"/api/simulations?source_environment={env}")
    assert hist_res.status_code == 200
    hist_data = hist_res.json()
    assert len(hist_data) == 1
    assert hist_data[0]["id"] == saved_sim.id
    
    detail_res = client.get(f"/api/simulations/{saved_sim.id}")
    assert detail_res.status_code == 200
    assert detail_res.json()["component_id"] == node.id
    
    db.close()
