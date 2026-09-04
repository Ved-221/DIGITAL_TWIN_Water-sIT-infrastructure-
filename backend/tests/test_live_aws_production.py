import pytest
from unittest.mock import MagicMock, patch
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient

import aws_collector
import cost_engine
import metrics_collector
from main import app

client = TestClient(app)

def test_s3_get_bucket_location_normalization():
    """Verify GetBucketLocation normalizes None/empty to us-east-1 and EU to eu-west-1."""
    mock_s3 = MagicMock()
    mock_s3.list_buckets.return_value = {
        "Buckets": [
            {"Name": "bucket-us-east"},
            {"Name": "bucket-ireland"},
            {"Name": "bucket-tokyo"}
        ]
    }

    def mock_location(Bucket):
        if Bucket == "bucket-us-east":
            return {"LocationConstraint": None} # AWS quirk: us-east-1 returns None
        elif Bucket == "bucket-ireland":
            return {"LocationConstraint": "EU"} # AWS legacy: eu-west-1 returns EU
        else:
            return {"LocationConstraint": "ap-northeast-1"}

    mock_s3.get_bucket_location.side_effect = mock_location

    mock_session = MagicMock()
    mock_session.client.return_value = mock_s3
    mock_session.region_name = "us-east-1"

    collector = aws_collector.AWSInfrastructureCollector(session=mock_session, region_name="us-east-1")
    buckets = collector.collect_s3_buckets()

    assert len(buckets) == 3
    b_map = {b["id"]: b for b in buckets}
    assert b_map["s3-bucket-us-east"]["aws_region"] == "us-east-1"
    assert b_map["s3-bucket-us-east"]["location"] == "us-east-1"
    assert b_map["s3-bucket-ireland"]["aws_region"] == "eu-west-1"
    assert b_map["s3-bucket-tokyo"]["aws_region"] == "ap-northeast-1"

def test_aws_pricing_cache_sqlite():
    """Verify live pricing cache stores and retrieves rates without re-querying network."""
    cost_engine.set_cached_price("AmazonEC2:c5.xlarge:us-east-1", 0.17, 124.10, "AWS Price List API")
    cached = cost_engine.get_cached_price("AmazonEC2:c5.xlarge:us-east-1")

    assert cached is not None
    assert cached["hourly_rate"] == 0.17
    assert cached["monthly_rate"] == 124.10
    assert cached["pricing_source"] == "AWS Price List API"

def test_aws_cost_explorer_endpoint():
    """Verify /api/aws/cost endpoint returns valid AWSCostReport schema."""
    resp = client.get("/api/aws/cost")
    assert resp.status_code == 200
    data = resp.json()
    assert "authenticated" in data
    assert "spend_available" in data
    assert "total_month_to_date_cost" in data
    assert "service_breakdown" in data
    assert "pricing_source" in data

def test_aws_health_endpoint_support_plan_handling():
    """Verify AWS Health handles SubscriptionRequiredException gracefully without fabricating data."""
    mock_health = MagicMock()
    mock_health.describe_events.side_effect = ClientError(
        error_response={"Error": {"Code": "SubscriptionRequiredException", "Message": "Subscription required"}},
        operation_name="DescribeEvents"
    )

    mock_session = MagicMock()
    mock_session.client.return_value = mock_health

    with patch.object(aws_collector, "check_aws_credentials", return_value={"authenticated": True}):
        report = aws_collector.collect_health_events(mock_session)

    assert report["authenticated"] is True
    assert report["health_available"] is False
    assert report["support_plan_required"] is True
    assert report["open_events_count"] == 0
    assert len(report["events"]) == 0
    assert "Business or Enterprise Support" in report["error"]

def test_strict_live_mode_rejects_synthetic_fallback():
    """Verify live mode fails explicitly when unauthenticated and NEVER generates synthetic components."""
    with patch.object(aws_collector, "check_aws_credentials", return_value={"authenticated": False, "error": "No credentials"}):
        mock_db = MagicMock()
        result = aws_collector.sync_aws_to_db(db=mock_db, mode="replace", use_synthetic=False)

    assert result["success"] is False
    assert result["data_source"] == "none"
    assert "AWS Authentication failed" in result["message"]
    # Ensure no components were inserted
    assert mock_db.add.call_count == 0

def test_strict_live_metrics_rejects_synthetic_fallback():
    """Verify live metrics collection returns UNAVAILABLE states rather than synthetic random numbers."""
    mock_db = MagicMock()
    mock_comp = MagicMock()
    mock_comp.id = "i-12345"
    mock_comp.name = "EC2: App-Server"
    mock_comp.type.value = "server"
    mock_comp.status.value = "active"
    mock_comp.arn = "arn:aws:ec2:us-east-1:1234:instance/i-12345"
    mock_comp.cpu = None
    mock_comp.memory = None
    mock_comp.metadata_col = {}
    mock_db.query.return_value.all.return_value = [mock_comp]

    with patch.object(metrics_collector, "check_aws_credentials", return_value={"authenticated": False, "error": "Missing creds"}):
        snapshots, data_source = metrics_collector.collect_and_store_metrics(mock_db, use_synthetic=False)

    assert data_source == "aws_cloudwatch_unavailable"
    assert len(snapshots) == 1
    assert snapshots[0]["status"] == "UNAVAILABLE"
    assert snapshots[0]["cpu"] is None
    assert snapshots[0]["raw_metrics"]["status"] == "NO_DATA"
