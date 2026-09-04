import pytest
import sys
import os
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# pyrefly: ignore [missing-import]
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import Base
from main import app, get_db
from ml import dataset, feature_extractor, trainer, recommender

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


def test_generate_training_dataset():
    """Verify dataset generator creates expected columns and balanced classes."""
    df = dataset.generate_training_dataset(num_samples_per_class=30, random_seed=42)
    assert len(df) == 30 * 7
    for col in dataset.FEATURE_COLUMNS:
        assert col in df.columns
    assert "recommended_action" in df.columns

    # Verify all 7 classes are present
    class_counts = df["recommended_action"].value_counts().to_dict()
    assert len(class_counts) == 7
    for cls_name in dataset.RECOMMENDATION_CLASSES:
        assert class_counts[cls_name] == 30


def test_assign_ground_truth_action_policies():
    """Verify ground truth policy logic assigns correct operational classes."""
    # 1. High CPU -> SCALE_COMPUTE
    row_scale = {"resource_type": "server", "cpu_utilization": 88.0, "cpu_trend_1h": 5.0, "is_active": 1}
    assert dataset.assign_ground_truth_action(row_scale) == "SCALE_COMPUTE"

    # 2. High Disk -> EXPAND_STORAGE
    row_storage = {"resource_type": "database", "disk_utilization_pct": 89.0, "is_active": 1}
    assert dataset.assign_ground_truth_action(row_storage) == "EXPAND_STORAGE"

    # 3. ALB Latency -> INVESTIGATE_LATENCY_ERROR
    row_lat = {"resource_type": "load_balancer", "latency_ms": 220.0, "is_active": 1}
    assert dataset.assign_ground_truth_action(row_lat) == "INVESTIGATE_LATENCY_ERROR"

    # 4. DB Connections -> INVESTIGATE_DATABASE_BOTTLENECK
    row_conn = {"resource_type": "database", "connection_count": 95.0, "is_active": 1}
    assert dataset.assign_ground_truth_action(row_conn) == "INVESTIGATE_DATABASE_BOTTLENECK"

    # 5. Idle server -> OPTIMIZE_IDLE_RESOURCE
    row_idle = {"resource_type": "server", "cpu_utilization": 3.0, "network_throughput_kb_s": 1.0, "cost_monthly": 80.0, "is_active": 1}
    assert dataset.assign_ground_truth_action(row_idle) == "OPTIMIZE_IDLE_RESOURCE"

    # 6. Degraded critical resource -> REDUNDANCY_RISK
    row_fail = {"dependent_count": 3, "criticality_score": 3, "is_active": 0}
    assert dataset.assign_ground_truth_action(row_fail) == "REDUNDANCY_RISK"

    # 7. Normal baseline -> NO_ACTION
    row_norm = {"resource_type": "server", "cpu_utilization": 35.0, "is_active": 1, "cost_monthly": 70.0}
    assert dataset.assign_ground_truth_action(row_norm) == "NO_ACTION"


def test_feature_extractor_from_db():
    """Verify feature extractor pulls all 18 features from DB component, metrics, and graph."""
    db = TestingSessionLocal()
    feats = feature_extractor.extract_features_for_component(db, "app_core_api")

    assert feats["resource_type"] == "application"
    assert "criticality_score" in feats
    assert "dependency_count" in feats
    assert "dependent_count" in feats
    assert "cpu_utilization" in feats
    assert "network_throughput_kb_s" in feats
    assert "is_active" in feats


def test_train_and_evaluate_pipeline():
    """Verify RandomForest model trains, evaluates without fabricated metrics, and saves artifacts."""
    pipeline, metadata = trainer.train_and_evaluate(num_samples_per_class=40, random_seed=42)

    assert os.path.exists(metadata["model_file"])
    assert metadata["model_type"] == "RandomForestClassifier"
    assert metadata["test_macro_f1"] > 0.85
    assert metadata["test_accuracy"] > 0.85
    assert len(metadata["classes"]) == 7
    assert len(metadata["top_feature_importances"]) > 0


def test_predict_component_action():
    """Verify model inference returns structured prediction with confidence and reasoning."""
    db = TestingSessionLocal()
    pred = recommender.predict_component_action("app_core_api", db)

    assert "resource_id" in pred
    assert pred["resource_id"] == "app_core_api"
    assert "recommended_action" in pred
    assert pred["recommended_action"] in dataset.RECOMMENDATION_CLASSES
    assert 0.0 <= pred["confidence"] <= 1.0
    assert len(pred["reasoning_features"]) > 0
    assert pred["is_trained_model"] is True


def test_ml_api_endpoints():
    """Verify /api/ml endpoints return valid JSON predictions, status, and retraining."""
    client = TestClient(app)

    # 1. Model status
    status_res = client.get("/api/ml/model/status")
    assert status_res.status_code == 200
    sdata = status_res.json()
    assert sdata["is_trained"] is True
    assert sdata["model_type"] == "RandomForestClassifier"

    # 2. Recommendation for single component
    rec_res = client.get("/api/ml/recommend/app_core_api")
    assert rec_res.status_code == 200
    rdata = rec_res.json()
    assert rdata["resource_id"] == "app_core_api"
    assert rdata["recommended_action"] in dataset.RECOMMENDATION_CLASSES
    assert len(rdata["reasoning_features"]) > 0

    # 3. Recommendations for all components
    all_res = client.get("/api/ml/recommendations")
    assert all_res.status_code == 200
    all_recs = all_res.json()
    assert len(all_recs) >= 1
    assert "recommended_action" in all_recs[0]
