import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
# pyrefly: ignore [missing-import]
from fastapi.testclient import TestClient
from main import app
import risk_engine, cost_engine, downtime_engine

client = TestClient(app)

def test_get_health_endpoint():
    """Verify /api/health reports system status, uptime, and database connection."""
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["version"] == "1.0.0"
    assert "uptime_seconds" in data
    assert data["database_connected"] is True
    assert "total_components" in data
    assert "aws_authenticated" in data
    assert "data_source" in data

def test_aws_connect_invalid_credentials_rejected():
    """Verify /api/aws/connect properly rejects invalid credentials without throwing 500."""
    res = client.post("/api/aws/connect", json={
        "access_key_id": "AKIAIOSFODNN7EXAMPLE",
        "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        "region": "us-east-1"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["authenticated"] is False
    assert data["account_id"] is None
    assert data["error"] is not None

def test_standard_metrics_and_recommendations_aliases():
    """Verify /api/metrics/{id} and /api/recommendations/{id} standard aliases work."""
    # Seed or get a component
    comps_res = client.get("/api/twin/components")
    assert comps_res.status_code == 200
    comps = comps_res.json()
    assert len(comps) > 0
    cid = comps[0]["id"]

    # Metrics alias
    m_res = client.get(f"/api/metrics/{cid}")
    assert m_res.status_code == 200
    assert isinstance(m_res.json(), list)

    # Recommendations alias
    r_res = client.get(f"/api/recommendations/{cid}")
    assert r_res.status_code == 200
    r_data = r_res.json()
    assert "recommended_action" in r_data
    assert "confidence" in r_data

def test_cost_engine_ec2_scale_compute():
    """Verify cost_engine looks up instance pricing and computes valid tier delta."""
    component = {
        "id": "i-test",
        "name": "API-Server",
        "type": "server",
        "cost_per_month": 30.37,
        "metadata_col": {"instance_type": "t3.medium"}
    }
    cost = cost_engine.calculate_cost_impact(component, "SCALE_COMPUTE")
    assert cost.cost_impact > 0
    assert cost.is_estimated is True
    assert "t3.large" in cost.calculation_formula
    assert cost.projected_monthly_cost > cost.current_monthly_cost

def test_cost_engine_ebs_expand_storage():
    """Verify cost_engine calculates EBS gp3 rate ($0.08/GB-mo)."""
    component = {"name": "SAN", "type": "storage", "cost_per_month": 100.0}
    cost = cost_engine.calculate_cost_impact(component, "EXPAND_STORAGE")
    assert cost.cost_impact == 8.0 # 100GB * 0.08
    assert "gp3" in cost.pricing_basis

def test_downtime_engine_multi_az_vs_single_az():
    """Verify downtime_engine models Multi-AZ failover (2m) vs Single-AZ reboot (12m)."""
    multi_az_db = {"id": "rds-prod", "type": "database", "metadata_col": {"multi_az": True}}
    single_az_db = {"id": "rds-dev", "type": "database", "metadata_col": {"multi_az": False}}

    d_multi = downtime_engine.calculate_downtime_estimate(multi_az_db, "SCALE_COMPUTE")
    d_single = downtime_engine.calculate_downtime_estimate(single_az_db, "SCALE_COMPUTE")

    assert d_multi.estimated_downtime_minutes == 2
    assert d_single.estimated_downtime_minutes == 12

def test_risk_engine_transparent_factors():
    """Verify risk_engine returns score, level, and transparent factor list."""
    target_node = {
        "id": "srv_db_01",
        "name": "On-prem DB Server",
        "type": "server",
        "criticality": "critical",
        "environment": "on_prem"
    }
    affected_nodes = [
        {"id": "app_empower", "name": "Empower", "criticality": "critical"},
        {"id": "srv_app_01", "name": "App Server", "criticality": "high"}
    ]
    assessment = risk_engine.calculate_risk_assessment(
        target_node=target_node,
        action="SCALE_COMPUTE",
        affected_nodes=affected_nodes,
        total_components_count=10
    )
    assert assessment["risk_score"] > 50
    assert assessment["risk_level"] in ["HIGH", "CRITICAL"]
    assert len(assessment["risk_factors"]) >= 3
    # Check factor breakdown
    factor_names = [f.factor for f in assessment["risk_factors"]]
    assert "Target Criticality" in factor_names
    assert "Topological Blast Radius" in factor_names
    assert "Downstream Critical Services" in factor_names
