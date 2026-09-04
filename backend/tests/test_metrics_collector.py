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
import metrics_collector
from main import app, get_db

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


def test_build_metric_queries_ec2():
    """Verify EC2 queries request valid CloudWatch metrics and do NOT request unavailable OS memory."""
    collector = metrics_collector.AWSMetricsCollector(region_name="us-east-1")
    components = [
        {"id": "i-09f182c81a2b", "type": "server", "metadata_col": {}}
    ]
    queries, qmap = collector.build_metric_queries(components)

    metric_names = [q["MetricStat"]["Metric"]["MetricName"] for q in queries]
    assert "CPUUtilization" in metric_names
    assert "NetworkIn" in metric_names
    assert "DiskReadBytes" in metric_names
    assert "StatusCheckFailed" in metric_names
    # Critical rule: Do NOT request OS memory from standard EC2 hypervisor CloudWatch
    assert "MemoryUtilization" not in metric_names
    assert len(queries) == 8


def test_build_metric_queries_rds():
    """Verify RDS queries request available metrics including FreeableMemory, FreeStorageSpace, Connections, and Latency."""
    collector = metrics_collector.AWSMetricsCollector(region_name="us-east-1")
    components = [
        {"id": "rds-prod-analytics-db", "type": "database", "metadata_col": {"db_class": "db.m5.xlarge"}}
    ]
    queries, qmap = collector.build_metric_queries(components)

    metric_names = [q["MetricStat"]["Metric"]["MetricName"] for q in queries]
    assert "CPUUtilization" in metric_names
    assert "FreeableMemory" in metric_names
    assert "FreeStorageSpace" in metric_names
    assert "DatabaseConnections" in metric_names
    assert "ReadLatency" in metric_names
    assert "WriteLatency" in metric_names
    assert len(queries) == 10


def test_build_metric_queries_alb():
    """Verify ALB queries request RequestCount, TargetResponseTime, 5XX counts, ActiveConnections."""
    collector = metrics_collector.AWSMetricsCollector(region_name="us-east-1")
    components = [
        {
            "id": "alb-prod-ingress",
            "type": "load_balancer",
            "arn": "arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/prod-alb/50dc6c495c0c9188"
        }
    ]
    queries, qmap = collector.build_metric_queries(components)

    metric_names = [q["MetricStat"]["Metric"]["MetricName"] for q in queries]
    assert "RequestCount" in metric_names
    assert "TargetResponseTime" in metric_names
    assert "HTTPCode_Target_5XX_Count" in metric_names
    assert "ActiveConnectionCount" in metric_names
    assert len(queries) == 6


def test_normalize_ec2_metrics():
    """Verify EC2 metrics are correctly normalized and memory remains None."""
    collector = metrics_collector.AWSMetricsCollector(region_name="us-east-1")
    comp = {
        "id": "i-09f182c81a2b",
        "type": "server",
        "status": "active",
        "metadata_col": {"launch_time": "2026-07-20T10:00:00Z"}
    }
    raw = {
        "CPUUtilization": 35.5,
        "NetworkIn": 300000.0,
        "NetworkOut": 600000.0,
        "DiskReadBytes": 150000.0,
        "DiskWriteBytes": 300000.0,
        "DiskReadOps": 60.0,
        "DiskWriteOps": 120.0,
        "StatusCheckFailed": 0.0
    }
    snapshot = collector.normalize_resource_metrics(comp, raw, period_seconds=300, timestamp_str="2026-09-03T12:00:00Z")

    assert snapshot["resource_id"] == "i-09f182c81a2b"
    assert snapshot["resource_type"] == "server"
    assert snapshot["cpu"] == 35.5
    assert snapshot["memory"] is None  # Authentic: EC2 hypervisor does not give RAM
    assert snapshot["disk"]["read_bytes_sec"] == 500.0
    assert snapshot["disk"]["write_bytes_sec"] == 1000.0
    assert snapshot["network"]["in_bytes_sec"] == 1000.0
    assert snapshot["network"]["out_bytes_sec"] == 2000.0
    assert snapshot["latency"] is None
    assert snapshot["error_rate"] is None
    assert snapshot["status"] == "active"
    assert snapshot["age_days"] is not None


def test_normalize_rds_metrics():
    """Verify RDS metrics calculate memory % and disk utilization % against allocated capacity."""
    collector = metrics_collector.AWSMetricsCollector(region_name="us-east-1")
    comp = {
        "id": "rds-prod-analytics-db",
        "type": "database",
        "status": "active",
        "metadata_col": {
            "db_class": "db.m5.xlarge", # 16 GB total RAM
            "allocated_storage_gb": 100
        }
    }
    raw = {
        "CPUUtilization": 24.2,
        "FreeableMemory": 8 * (1024 ** 3), # 8 GB free -> 50% used
        "FreeStorageSpace": 40 * (1024 ** 3), # 40 GB free of 100 GB -> 60% used
        "DatabaseConnections": 15.0,
        "ReadLatency": 0.002,
        "WriteLatency": 0.004,
        "ReadIOPS": 50.0,
        "WriteIOPS": 120.0
    }
    snapshot = collector.normalize_resource_metrics(comp, raw, period_seconds=300, timestamp_str="2026-09-03T12:00:00Z")

    assert snapshot["cpu"] == 24.2
    assert snapshot["memory"] == 50.0 # 50% RAM utilization
    assert snapshot["disk"]["utilization_pct"] == 60.0 # 60% storage utilization
    assert snapshot["disk"]["read_iops"] == 50.0
    assert snapshot["connections"] == 15.0
    assert snapshot["latency"] == 0.003 # Average of 2ms + 4ms


def test_normalize_alb_metrics():
    """Verify ALB metrics calculate request rate, latency, and 5xx error rate."""
    collector = metrics_collector.AWSMetricsCollector(region_name="us-east-1")
    comp = {
        "id": "alb-prod-ingress",
        "type": "load_balancer",
        "status": "active",
        "metadata_col": {}
    }
    raw = {
        "RequestCount": 30000.0,
        "TargetResponseTime": 0.015,
        "HTTPCode_Target_5XX_Count": 15.0,
        "HTTPCode_ELB_5XX_Count": 0.0,
        "ActiveConnectionCount": 42.0,
        "ProcessedBytes": 60000000.0
    }
    snapshot = collector.normalize_resource_metrics(comp, raw, period_seconds=300, timestamp_str="2026-09-03T12:00:00Z")

    assert snapshot["request_rate"] == 100.0 # 30000 / 300 = 100 req/s
    assert snapshot["latency"] == 0.015 # 15ms
    assert snapshot["error_rate"] == 0.05 # 15 / 30000 * 100 = 0.05%
    assert snapshot["connections"] == 42.0
    assert snapshot["cpu"] is None # Managed ALB has no CPU metric


def test_missing_metrics_handled_gracefully():
    """Verify that absent metrics are safely represented as None without exceptions."""
    collector = metrics_collector.AWSMetricsCollector(region_name="us-east-1")
    comp = {"id": "i-empty", "type": "server", "metadata_col": {}}
    raw = {} # Empty CloudWatch response
    snapshot = collector.normalize_resource_metrics(comp, raw, period_seconds=300, timestamp_str="2026-09-03T12:00:00Z")

    assert snapshot["cpu"] is None
    assert snapshot["memory"] is None
    assert snapshot["disk"] is None
    assert snapshot["network"] is None
    assert snapshot["latency"] is None
    assert snapshot["error_rate"] is None
    assert snapshot["request_rate"] is None
    assert snapshot["connections"] is None
    assert snapshot["status"] == "active"


def test_collect_and_store_metrics_db():
    """Verify metrics collector saves records into SQLite and associates with components."""
    db = TestingSessionLocal()
    snapshots, source = metrics_collector.collect_and_store_metrics(db, use_synthetic=True)

    assert len(snapshots) >= 1
    assert source == "aws_synthetic_cloudwatch"

    db_records = db.query(models.MetricSnapshot).all()
    assert len(db_records) == len(snapshots)
    assert db_records[0].resource_id is not None
    assert db_records[0].timestamp is not None


def test_api_metrics_endpoints():
    """Verify /api/twin/metrics and /api/twin/metrics/{id} endpoints return structured data."""
    client = TestClient(app)

    # 1. Trigger collection
    collect_res = client.post("/api/twin/metrics/collect", json={"use_synthetic": True, "period_seconds": 300})
    assert collect_res.status_code == 200
    cdata = collect_res.json()
    assert cdata["success"] is True
    assert cdata["metrics_collected"] > 0

    # 2. Get latest metrics for all resources
    latest_res = client.get("/api/twin/metrics")
    assert latest_res.status_code == 200
    metrics_list = latest_res.json()
    assert len(metrics_list) > 0

    sample = metrics_list[0]
    assert "resource_id" in sample
    assert "timestamp" in sample
    assert "resource_type" in sample
    assert "status" in sample

    # 3. Get metrics for specific resource
    target_id = sample["resource_id"]
    detail_res = client.get(f"/api/twin/metrics/{target_id}")
    assert detail_res.status_code == 200
    detail_list = detail_res.json()
    assert len(detail_list) >= 1
    assert detail_list[0]["resource_id"] == target_id
