import pytest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import Base
from main import app, get_db
import simulation

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


def test_simulation_manual_action():
    """Verify simulation handles user-selected manual action and computes graph blast radius."""
    client = TestClient(app)

    payload = {
        "target_component_id": "app_core_api",
        "action": "migrate",
        "destination_env": "cloud",
        "use_ml_recommendation": False
    }

    res = client.post("/api/simulate", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert "Core Microservices API" in data["target_component"]
    assert data["action"] == "migrate"
    assert data["change_action"] == "migrate"
    assert data["blast_radius"] > 0
    assert data["affected_count"] == data["blast_radius"]
    assert len(data["affected_components"]) == data["blast_radius"]
    assert 0 <= data["risk_score"] <= 100
    assert data["estimated_downtime_minutes"] > 0
    assert "critical_warnings" in data
    assert "critical_flags" in data


def test_simulation_ml_recommended_action():
    """Verify simulation invokes ML recommendation engine, uses suggested action, and derives graph impact."""
    client = TestClient(app)

    payload = {
        "target_component_id": "app_core_api",
        "use_ml_recommendation": True
    }

    res = client.post("/api/simulate", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert "Core Microservices API" in data["target_component"]
    assert data["recommended_action"] is not None
    assert data["action"] == data["recommended_action"]
    assert data["ml_confidence"] is not None
    assert 0.0 <= data["ml_confidence"] <= 1.0
    assert data["ml_reasoning_features"] is not None
    assert len(data["ml_reasoning_features"]) > 0

    # Graph determines blast radius
    assert data["blast_radius"] > 0
    assert len(data["affected_components"]) == data["blast_radius"]

    # Simulation engine determines risk, downtime, cost
    assert 0 <= data["risk_score"] <= 100
    assert isinstance(data["risk_level"], str)
    assert isinstance(data["estimated_downtime_minutes"], int)
    assert "cost_impact" in data


def test_simulation_numerical_calculations_are_deterministic():
    """Verify that risk scores and downtimes are 100% deterministic and do not fluctuate."""
    db = TestingSessionLocal()

    res1 = simulation.simulate_change(
        db=db,
        target_component_id="srv_app_01",
        change_action="SCALE_COMPUTE",
        use_ml_recommendation=False
    )

    res2 = simulation.simulate_change(
        db=db,
        target_component_id="srv_app_01",
        change_action="SCALE_COMPUTE",
        use_ml_recommendation=False
    )

    assert res1["risk_score"] == res2["risk_score"]
    assert res1["estimated_downtime_minutes"] == res2["estimated_downtime_minutes"]
    assert res1["cost_impact"] == res2["cost_impact"]
    assert res1["blast_radius"] == res2["blast_radius"]
    assert set(res1["affected_components"]) == set(res2["affected_components"])


def test_simulation_invalid_component():
    """Verify 400 error is returned when an invalid component ID is simulated."""
    client = TestClient(app)
    res = client.post("/api/simulate", json={"target_component_id": "non_existent_id"})
    assert res.status_code == 400
