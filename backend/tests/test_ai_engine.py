import pytest
import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# pyrefly: ignore [missing-import]
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import Base
from main import app, get_db
import ai_engine

TEST_DB_URL = "sqlite:///:memory:"
test_engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

@pytest.fixture(autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()
    import seed
    seed.seed_data(db)
    app.dependency_overrides[get_db] = override_get_db
    yield
    Base.metadata.drop_all(bind=test_engine)
    app.dependency_overrides.pop(get_db, None)


def test_ai_engine_deterministic_fallback_facets():
    """Verify that the explanation layer strictly covers the 6 required facets without inventing numbers."""
    sim_data = {
        "target_component_id": "i-09f182c81a2b",
        "target_component": "EC2: WatersConnect-API-01",
        "target_component_type": "server",
        "action": "SCALE_COMPUTE",
        "blast_radius": 4,
        "affected_components": ["rds-db", "alb-ingress", "sg-app", "vpc-main"],
        "affected_components_details": [
            {"id": "rds-db", "name": "RDS: prod-analytics-postgres", "type": "database"},
            {"id": "alb-ingress", "name": "ALB: prod-ingress-alb", "type": "load_balancer"},
        ],
        "risk_score": 60,
        "risk_level": "HIGH",
        "estimated_downtime_minutes": 10,
        "cost_impact": 70.08,
        "critical_warnings": [
            "Compute resize requires instance reboot (~10m). 2 upstream dependent(s) may experience transient connection resets."
        ],
        "ml_confidence": 0.89,
        "ml_reasoning_features": [
            {"feature": "cpu_utilization", "value": "88.4%", "impact": "high"},
            {"feature": "cpu_trend_1h", "value": "+14.0%", "impact": "medium"}
        ]
    }

    # Ensure no GEMINI_API_KEY in this unit test
    with patch.dict(os.environ, {}, clear=True):
        full_md, exec_rec, structured = ai_engine.generate_explanation(sim_data)

    assert full_md is not None
    assert exec_rec is not None
    assert structured is not None

    # Verify all 6 facets are addressed
    assert "what_is_happening" in structured
    assert "why_ml_recommended" in structured
    assert "affected_components_summary" in structured
    assert "simulation_prediction" in structured
    assert "key_risks" in structured
    assert "engineer_considerations" in structured

    # Verify ground truth numbers are preserved exactly without invention
    assert "EC2: WatersConnect-API-01" in structured["what_is_happening"]
    assert "88.4%" in structured["why_ml_recommended"]
    assert "89%" in structured["why_ml_recommended"]
    assert "4 component(s)" in structured["affected_components_summary"]
    assert "10 minute(s)" in structured["simulation_prediction"]
    assert "+$70.08/mo" in structured["simulation_prediction"]
    assert "HIGH" in structured["key_risks"]
    assert "60/100" in structured["key_risks"]
    assert len(structured["engineer_considerations"]) >= 3


def test_ai_engine_mock_gemini_api_call():
    """Verify Gemini client parsing when GEMINI_API_KEY is present."""
    mock_response_json = {
        "what_is_happening": "Scaling EC2 instance WatersConnect-API-01 to handle elevated load.",
        "why_ml_recommended": "The ML model recommended SCALE_COMPUTE due to 88.4% CPU utilization and upward trend.",
        "affected_components_summary": "4 components in blast radius: RDS Postgres, ALB Ingress, and network groups.",
        "simulation_prediction": "10 minutes of rolling downtime and +$70.08/month cost increase.",
        "key_risks": "High risk due to transient disconnects on dependent services during reboot.",
        "engineer_considerations": [
            "Schedule during maintenance window.",
            "Verify database connection pool timeouts."
        ],
        "full_markdown_explanation": "### AI Explanation: Scale EC2\nDetailed analysis...",
        "executive_recommendation": "Execute scaling during off-peak maintenance window."
    }

    sim_data = {
        "target_component": "EC2: WatersConnect-API-01",
        "action": "SCALE_COMPUTE",
        "blast_radius": 4,
        "risk_score": 60,
        "risk_level": "HIGH",
        "estimated_downtime_minutes": 10,
        "cost_impact": 70.08
    }

    mock_client = MagicMock()
    mock_model_response = MagicMock()
    import json
    mock_model_response.text = json.dumps(mock_response_json)
    mock_client.models.generate_content.return_value = mock_model_response

    import sys
    mock_genai_mod = MagicMock()
    mock_genai_mod.Client.return_value = mock_client
    mock_types_mod = MagicMock()

    with patch.dict(os.environ, {"GEMINI_API_KEY": "fake_test_key"}):
        with patch.dict(sys.modules, {"google.genai": mock_genai_mod, "google.genai.types": mock_types_mod}):
            full_md, exec_rec, structured = ai_engine.generate_explanation(sim_data)

    assert "AI Explanation: Scale EC2" in full_md
    assert "Execute scaling" in exec_rec
    assert structured["what_is_happening"] == mock_response_json["what_is_happening"]
    assert structured["simulation_prediction"] == mock_response_json["simulation_prediction"]


def test_simulation_endpoint_returns_structured_explanation():
    """Verify that /api/simulate returns enriched ai_explanation and structured_explanation."""
    client = TestClient(app)

    res = client.post("/api/simulate", json={
        "target_component_id": "app_core_api",
        "use_ml_recommendation": True
    })

    assert res.status_code == 200
    data = res.json()

    assert data["ai_explanation"] is not None
    assert "Recommended Action:" in data["ai_explanation"]
    assert "Why (ML Model Rationale):" in data["ai_explanation"]
    assert "Impact (Infrastructure Topology & Blast Radius):" in data["ai_explanation"]
    assert "Simulation Forecast:" in data["ai_explanation"]
    assert "Risk & Critical Warnings:" in data["ai_explanation"]
    assert "Engineer Pre-Change Checklist:" in data["ai_explanation"]

    assert data["structured_explanation"] is not None
    assert "what_is_happening" in data["structured_explanation"]
    assert "why_ml_recommended" in data["structured_explanation"]
    assert len(data["structured_explanation"]["engineer_considerations"]) >= 3
