import pytest
from simulation import generate_feasible_solutions
from ai_engine import get_ai_recommendation, analyze_simulation_with_ai, chat_with_twin
from models import Component

def test_feasible_solutions_three_candidate_options():
    """Verify generate_feasible_solutions produces 3 distinct candidates with quantitative metrics."""
    component = Component(
        id="comp-101",
        name="sap-erp-central",
        type="server",
        environment="on_prem",
        criticality="critical",
        status="active",
        cost_per_month=3200.0,
        currency="USD",
        location="ap-south-1",
        owner="Enterprise Apps"
    )
    
    affected_components = [
        {"id": "comp-102", "name": "reporting-db", "type": "database", "criticality": "high", "hop_distance": 1},
        {"id": "comp-103", "name": "finance-api", "type": "application", "criticality": "critical", "hop_distance": 1}
    ]
    
    # Test migration scenario
    solutions_mig = generate_feasible_solutions(
        component=component,
        action="migrate",
        affected_components=affected_components,
        risk_score=75.0,
        currency="USD"
    )
    
    assert len(solutions_mig) == 3
    
    # Verify all 3 options have complete schema attributes
    for idx, sol in enumerate(solutions_mig):
        assert sol.id.startswith("opt-")
        assert len(sol.name) > 0
        assert len(sol.description) > 0
        assert sol.risk_level in ["LOW", "MODERATE", "HIGH", "CRITICAL"]
        assert sol.estimated_downtime_minutes >= 0
        assert isinstance(sol.cost_delta_monthly, float)
        assert 0.0 <= sol.feasibility_score <= 1.0
        assert len(sol.pros) >= 1
        assert len(sol.cons) >= 1
        assert len(sol.implementation_steps) >= 1
        
    # Verify diversity across the 3 options
    names = [s.name for s in solutions_mig]
    assert len(set(names)) == 3  # All 3 names are unique
    
    # Option 1 (Direct Lift-and-Shift) vs Option 2 (Phased) vs Option 3 (Cloud-Native)
    assert any("Lift-and-Shift" in s.name for s in solutions_mig)
    assert any("Phased" in s.name for s in solutions_mig)
    assert any("Modernization" in s.name for s in solutions_mig)

def test_ai_engine_deterministic_fallback():
    """Verify AI engine gracefully falls back to deterministic rule-based intelligence when no API keys are present."""
    component_data = {
        "name": "core-auth-service",
        "type": "application",
        "environment": "cloud",
        "criticality": "critical",
        "cost_per_month": 500.0
    }
    simulation_data = {
        "action": "fail",
        "risk_level": "CRITICAL",
        "risk_score": 85.0,
        "blast_radius_nodes": 4,
        "affected_critical_nodes": 2,
        "affected_components": [
            {"name": "gateway", "type": "server", "criticality": "high"},
            {"name": "db-auth", "type": "database", "criticality": "critical"}
        ]
    }
    
    # Test fallback recommendation
    recommendation = get_ai_recommendation(component_data, simulation_data)
    assert isinstance(recommendation, str)
    assert len(recommendation) > 20
    assert "CRITICAL" in recommendation or "fail" in recommendation.lower() or "action" in recommendation.lower()
    
    # Test fallback analysis
    analysis = analyze_simulation_with_ai(component_data, simulation_data)
    assert isinstance(analysis, str)
    assert len(analysis) > 50

def test_chat_with_twin_offline_rule_intelligence():
    """Verify chat_with_twin returns contextually relevant answers using twin context."""
    twin_context = {
        "active_environment": "manual_waters",
        "total_nodes": 18,
        "total_edges": 17,
        "spof_nodes": ["SAP ERP Primary", "Core Switch 1"],
        "total_monthly_cost": 25400.0,
        "currency": "USD"
    }
    
    # Ask about SPOF
    res_spof = chat_with_twin("What are the single points of failure in this environment?", twin_context)
    assert "SAP ERP Primary" in res_spof or "Core Switch 1" in res_spof or "SPOF" in res_spof or "failure" in res_spof.lower()
    
    # Ask about cost
    res_cost = chat_with_twin("How much does the infrastructure cost per month?", twin_context)
    assert "25" in res_cost or "cost" in res_cost.lower()
