import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Tuple
import boto3
from botocore.exceptions import ClientError, BotoCoreError

import models
from aws_collector import get_boto3_session, check_aws_credentials

logger = logging.getLogger("infratwin.metrics")

# Estimated total RAM by instance class in gigabytes (for calculating memory utilization when FreeableMemory is known)
RDS_RAM_TABLE: Dict[str, float] = {
    "db.t3.micro": 1.0,
    "db.t3.small": 2.0,
    "db.t3.medium": 4.0,
    "db.t4g.micro": 1.0,
    "db.t4g.small": 2.0,
    "db.t4g.medium": 4.0,
    "db.m5.large": 8.0,
    "db.m5.xlarge": 16.0,
    "db.m5.2xlarge": 32.0,
    "db.r5.large": 16.0,
    "db.r5.xlarge": 32.0,
}

class AWSMetricsCollector:
    """
    Collects real performance & utilization metrics from AWS CloudWatch.
    
    CRITICAL RULES:
    1. Do NOT guess or invent metrics that AWS CloudWatch does not natively provide.
       - Standard EC2 CloudWatch does NOT provide RAM / Memory utilization without CloudWatch Agent.
       - ALB does NOT provide CPU/Memory/Disk.
       - S3 provides storage size and object counts, but not CPU/RAM/Latency.
    2. Batch metrics queries via cloudwatch.get_metric_data() to minimize API calls (up to 500 queries per call).
    3. Normalize into an ML-ready feature structure with consistent units.
    """

    def __init__(self, session: Optional[boto3.Session] = None, region_name: Optional[str] = None):
        self.session = session or get_boto3_session(region_name)
        self.region = self.session.region_name or "us-east-1"

    def _compute_age_days(self, launch_time_str: Optional[str]) -> Optional[float]:
        """Calculates resource age in days from ISO or AWS timestamp string."""
        if not launch_time_str:
            return None
        try:
            # Handle standard ISO strings or UTC formats
            clean_str = launch_time_str.replace("Z", "+00:00")
            dt = datetime.fromisoformat(clean_str)
            now = datetime.now(timezone.utc)
            delta = now - dt
            return round(max(0.0, delta.total_seconds() / 86400.0), 2)
        except Exception:
            return None

    def build_metric_queries(
        self,
        components: List[Dict[str, Any]],
        period_seconds: int = 300
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
        """
        Builds a batched list of MetricDataQueries for cloudwatch.get_metric_data().
        Maps query IDs to resource context for fast O(1) post-processing.
        """
        queries = []
        query_map: Dict[str, Dict[str, Any]] = {}
        counter = 0

        for comp in components:
            cid = comp["id"]
            ctype = comp.get("type")

            # 1. EC2 Instances
            if ctype == "server" and cid.startswith("i-"):
                metric_specs = [
                    ("CPUUtilization", "AWS/EC2", "InstanceId", cid, "Average"),
                    ("NetworkIn", "AWS/EC2", "InstanceId", cid, "Sum"),
                    ("NetworkOut", "AWS/EC2", "InstanceId", cid, "Sum"),
                    ("DiskReadBytes", "AWS/EC2", "InstanceId", cid, "Sum"),
                    ("DiskWriteBytes", "AWS/EC2", "InstanceId", cid, "Sum"),
                    ("DiskReadOps", "AWS/EC2", "InstanceId", cid, "Sum"),
                    ("DiskWriteOps", "AWS/EC2", "InstanceId", cid, "Sum"),
                    ("StatusCheckFailed", "AWS/EC2", "InstanceId", cid, "Maximum"),
                ]
                for mname, ns, dname, dval, stat in metric_specs:
                    qid = f"q_{counter}"
                    counter += 1
                    queries.append({
                        "Id": qid,
                        "MetricStat": {
                            "Metric": {
                                "Namespace": ns,
                                "MetricName": mname,
                                "Dimensions": [{"Name": dname, "Value": dval}]
                            },
                            "Period": period_seconds,
                            "Stat": stat
                        },
                        "ReturnData": True
                    })
                    query_map[qid] = {"resource_id": cid, "metric_name": mname, "type": "ec2"}

            # 2. RDS Databases
            elif ctype == "database" and (cid.startswith("rds-") or comp.get("arn", "").startswith("arn:aws:rds")):
                db_identifier = cid.replace("rds-", "") if cid.startswith("rds-") else cid
                metric_specs = [
                    ("CPUUtilization", "AWS/RDS", "DBInstanceIdentifier", db_identifier, "Average"),
                    ("FreeableMemory", "AWS/RDS", "DBInstanceIdentifier", db_identifier, "Average"),
                    ("FreeStorageSpace", "AWS/RDS", "DBInstanceIdentifier", db_identifier, "Average"),
                    ("DatabaseConnections", "AWS/RDS", "DBInstanceIdentifier", db_identifier, "Average"),
                    ("ReadIOPS", "AWS/RDS", "DBInstanceIdentifier", db_identifier, "Average"),
                    ("WriteIOPS", "AWS/RDS", "DBInstanceIdentifier", db_identifier, "Average"),
                    ("ReadLatency", "AWS/RDS", "DBInstanceIdentifier", db_identifier, "Average"),
                    ("WriteLatency", "AWS/RDS", "DBInstanceIdentifier", db_identifier, "Average"),
                    ("NetworkReceiveThroughput", "AWS/RDS", "DBInstanceIdentifier", db_identifier, "Average"),
                    ("NetworkTransmitThroughput", "AWS/RDS", "DBInstanceIdentifier", db_identifier, "Average"),
                ]
                for mname, ns, dname, dval, stat in metric_specs:
                    qid = f"q_{counter}"
                    counter += 1
                    queries.append({
                        "Id": qid,
                        "MetricStat": {
                            "Metric": {
                                "Namespace": ns,
                                "MetricName": mname,
                                "Dimensions": [{"Name": dname, "Value": dval}]
                            },
                            "Period": period_seconds,
                            "Stat": stat
                        },
                        "ReturnData": True
                    })
                    query_map[qid] = {"resource_id": cid, "metric_name": mname, "type": "rds"}

            # 3. Application Load Balancers
            elif ctype == "load_balancer":
                arn = comp.get("arn", "")
                if "loadbalancer/" in arn:
                    app_dimension = arn.split("loadbalancer/")[-1]
                    metric_specs = [
                        ("RequestCount", "AWS/ApplicationELB", "LoadBalancer", app_dimension, "Sum"),
                        ("TargetResponseTime", "AWS/ApplicationELB", "LoadBalancer", app_dimension, "Average"),
                        ("HTTPCode_Target_5XX_Count", "AWS/ApplicationELB", "LoadBalancer", app_dimension, "Sum"),
                        ("HTTPCode_ELB_5XX_Count", "AWS/ApplicationELB", "LoadBalancer", app_dimension, "Sum"),
                        ("ActiveConnectionCount", "AWS/ApplicationELB", "LoadBalancer", app_dimension, "Average"),
                        ("ProcessedBytes", "AWS/ApplicationELB", "LoadBalancer", app_dimension, "Sum"),
                    ]
                    for mname, ns, dname, dval, stat in metric_specs:
                        qid = f"q_{counter}"
                        counter += 1
                        queries.append({
                            "Id": qid,
                            "MetricStat": {
                                "Metric": {
                                "Namespace": ns,
                                "MetricName": mname,
                                "Dimensions": [{"Name": dname, "Value": dval}]
                            },
                            "Period": period_seconds,
                            "Stat": stat
                        },
                        "ReturnData": True
                    })
                    query_map[qid] = {"resource_id": cid, "metric_name": mname, "type": "alb"}

            # 4. S3 Storage Buckets
            elif ctype == "storage" and (cid.startswith("s3-") or comp.get("arn", "").startswith("arn:aws:s3")):
                bname = cid.replace("s3-", "") if cid.startswith("s3-") else comp.get("name", "")
                metric_specs = [
                    ("BucketSizeBytes", "AWS/S3", "BucketName", bname, "Average"),
                    ("NumberOfObjects", "AWS/S3", "BucketName", bname, "Average"),
                ]
                for mname, ns, dname, dval, stat in metric_specs:
                    qid = f"q_{counter}"
                    counter += 1
                    queries.append({
                        "Id": qid,
                        "MetricStat": {
                            "Metric": {
                                "Namespace": ns,
                                "MetricName": mname,
                                "Dimensions": [
                                    {"Name": dname, "Value": dval},
                                    {"Name": "StorageType", "Value": "StandardStorage"}
                                ]
                            },
                            "Period": 86400, # S3 daily metrics
                            "Stat": stat
                        },
                        "ReturnData": True
                    })
                    query_map[qid] = {"resource_id": cid, "metric_name": mname, "type": "s3"}

        return queries, query_map

    def collect_cloudwatch_metrics(
        self,
        components: List[Dict[str, Any]],
        period_seconds: int = 300
    ) -> List[Dict[str, Any]]:
        """
        Batches CloudWatch GetMetricData queries and transforms into normalized ML feature representations.
        """
        cw = self.session.client("cloudwatch")
        queries, query_map = self.build_metric_queries(components, period_seconds)

        if not queries:
            logger.info("No queryable CloudWatch resources found in components list.")
            return []

        now = datetime.now(timezone.utc)
        start_time = now - timedelta(seconds=max(period_seconds * 2, 3600))
        end_time = now

        # Raw values mapped by resource_id -> metric_name -> float value
        resource_metrics: Dict[str, Dict[str, float]] = {}

        # Batch in chunks of 500 (CloudWatch limit per request)
        BATCH_SIZE = 500
        for i in range(0, len(queries), BATCH_SIZE):
            chunk = queries[i:i + BATCH_SIZE]
            try:
                res = cw.get_metric_data(
                    MetricDataQueries=chunk,
                    StartTime=start_time,
                    EndTime=end_time,
                    ScanBy="TimestampDescending"
                )
                for item in res.get("MetricDataResults", []):
                    qid = item.get("Id")
                    values = item.get("Values", [])
                    if values and qid in query_map:
                        meta = query_map[qid]
                        rid = meta["resource_id"]
                        mname = meta["metric_name"]
                        resource_metrics.setdefault(rid, {})[mname] = float(values[0])
            except (ClientError, BotoCoreError) as e:
                logger.error("Error executing CloudWatch GetMetricData batch: %s", str(e))

        # Normalize results into feature representations
        snapshots = []
        comp_map = {c["id"]: c for c in components}

        for cid, comp in comp_map.items():
            raw = resource_metrics.get(cid, {})
            snapshot = self.normalize_resource_metrics(comp, raw, period_seconds, now.isoformat())
            snapshots.append(snapshot)

        return snapshots

    def normalize_resource_metrics(
        self,
        component: Dict[str, Any],
        raw: Dict[str, float],
        period_seconds: int,
        timestamp_str: str
    ) -> Dict[str, Any]:
        """
        Transforms raw CloudWatch datapoints into the normalized ML feature representation.
        Missing metrics are left as None.
        """
        cid = component["id"]
        ctype = component.get("type", "cloud_resource")
        meta = component.get("metadata_col", {})
        status = component.get("status", "active")
        if hasattr(status, "value"):
            status = status.value

        age_days = self._compute_age_days(meta.get("launch_time"))

        cpu = None
        memory = None
        disk = None
        network = None
        latency = None
        error_rate = None
        request_rate = None
        connections = None

        if ctype == "server":
            # EC2
            if "CPUUtilization" in raw:
                cpu = round(raw["CPUUtilization"], 2)

            # RAM is NOT available from standard EC2 hypervisor CloudWatch without CWAgent
            memory = None

            # Disk throughput & IOPS
            read_bytes_sec = round(raw.get("DiskReadBytes", 0.0) / period_seconds, 2) if "DiskReadBytes" in raw else None
            write_bytes_sec = round(raw.get("DiskWriteBytes", 0.0) / period_seconds, 2) if "DiskWriteBytes" in raw else None
            read_iops = round(raw.get("DiskReadOps", 0.0) / period_seconds, 2) if "DiskReadOps" in raw else None
            write_iops = round(raw.get("DiskWriteOps", 0.0) / period_seconds, 2) if "DiskWriteOps" in raw else None
            
            if any(v is not None for v in [read_bytes_sec, write_bytes_sec, read_iops, write_iops]):
                disk = {
                    "read_bytes_sec": read_bytes_sec,
                    "write_bytes_sec": write_bytes_sec,
                    "read_iops": read_iops,
                    "write_iops": write_iops
                }

            # Network
            in_bytes_sec = round(raw.get("NetworkIn", 0.0) / period_seconds, 2) if "NetworkIn" in raw else None
            out_bytes_sec = round(raw.get("NetworkOut", 0.0) / period_seconds, 2) if "NetworkOut" in raw else None
            if in_bytes_sec is not None or out_bytes_sec is not None:
                network = {
                    "in_bytes_sec": in_bytes_sec or 0.0,
                    "out_bytes_sec": out_bytes_sec or 0.0,
                    "total_bytes_sec": (in_bytes_sec or 0.0) + (out_bytes_sec or 0.0)
                }

            # Health status check
            if raw.get("StatusCheckFailed", 0.0) > 0:
                status = "degraded"

        elif ctype == "database":
            # RDS
            if "CPUUtilization" in raw:
                cpu = round(raw["CPUUtilization"], 2)

            # Freeable memory -> Compute utilization if total RAM known
            db_class = meta.get("db_class", "")
            total_ram_gb = RDS_RAM_TABLE.get(db_class)
            if "FreeableMemory" in raw:
                free_gb = raw["FreeableMemory"] / (1024 ** 3)
                if total_ram_gb and total_ram_gb > 0:
                    used_gb = max(0.0, total_ram_gb - free_gb)
                    memory = round(min(100.0, (used_gb / total_ram_gb) * 100.0), 2)
                else:
                    memory = round(free_gb, 2) # fallback: free GB

            # Free storage space -> Calculate disk utilization %
            alloc_storage_gb = meta.get("allocated_storage_gb", 20)
            if "FreeStorageSpace" in raw and alloc_storage_gb:
                total_bytes = alloc_storage_gb * (1024 ** 3)
                free_bytes = raw["FreeStorageSpace"]
                used_pct = max(0.0, min(100.0, ((total_bytes - free_bytes) / total_bytes) * 100.0))
                disk = {
                    "utilization_pct": round(used_pct, 2),
                    "read_iops": round(raw.get("ReadIOPS", 0.0), 2),
                    "write_iops": round(raw.get("WriteIOPS", 0.0), 2),
                    "free_storage_gb": round(free_bytes / (1024 ** 3), 2)
                }

            # Network throughput
            in_rate = round(raw.get("NetworkReceiveThroughput", 0.0), 2) if "NetworkReceiveThroughput" in raw else None
            out_rate = round(raw.get("NetworkTransmitThroughput", 0.0), 2) if "NetworkTransmitThroughput" in raw else None
            if in_rate is not None or out_rate is not None:
                network = {
                    "in_bytes_sec": in_rate or 0.0,
                    "out_bytes_sec": out_rate or 0.0,
                    "total_bytes_sec": (in_rate or 0.0) + (out_rate or 0.0)
                }

            # Latency (seconds)
            read_lat = raw.get("ReadLatency", 0.0)
            write_lat = raw.get("WriteLatency", 0.0)
            if "ReadLatency" in raw or "WriteLatency" in raw:
                latency = round((read_lat + write_lat) / 2.0, 4)

            # Connections
            if "DatabaseConnections" in raw:
                connections = round(raw["DatabaseConnections"], 0)

        elif ctype == "load_balancer":
            # ALB
            if "RequestCount" in raw:
                request_rate = round(raw["RequestCount"] / period_seconds, 2)

            if "TargetResponseTime" in raw:
                latency = round(raw["TargetResponseTime"], 4)

            # Error rate: (5XX / RequestCount) * 100
            req_count = raw.get("RequestCount", 0.0)
            target_5xx = raw.get("HTTPCode_Target_5XX_Count", 0.0)
            elb_5xx = raw.get("HTTPCode_ELB_5XX_Count", 0.0)
            if req_count > 0:
                error_rate = round(((target_5xx + elb_5xx) / req_count) * 100.0, 2)
            elif "RequestCount" in raw:
                error_rate = 0.0

            if "ActiveConnectionCount" in raw:
                connections = round(raw["ActiveConnectionCount"], 0)

            if "ProcessedBytes" in raw:
                network = {
                    "in_bytes_sec": round(raw["ProcessedBytes"] / period_seconds, 2),
                    "out_bytes_sec": round(raw["ProcessedBytes"] / period_seconds, 2),
                    "total_bytes_sec": round((raw["ProcessedBytes"] * 2) / period_seconds, 2)
                }

        elif ctype == "storage":
            # S3
            if "BucketSizeBytes" in raw or "NumberOfObjects" in raw:
                disk = {
                    "bucket_size_bytes": int(raw.get("BucketSizeBytes", 0)),
                    "object_count": int(raw.get("NumberOfObjects", 0))
                }

        return {
            "id": str(uuid.uuid4()),
            "resource_id": cid,
            "timestamp": timestamp_str,
            "resource_type": ctype,
            "cpu": cpu,
            "memory": memory,
            "disk": disk,
            "network": network,
            "latency": latency,
            "error_rate": error_rate,
            "request_rate": request_rate,
            "connections": connections,
            "status": status,
            "age_days": age_days,
            "raw_metrics": raw
        }


def generate_synthetic_metrics(components: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Generates authentic, statistically grounded metrics conforming strictly to AWS CloudWatch specifications.
    Reflects genuine CloudWatch characteristics:
    - EC2: CPU, network, disk IOPS, and memory=None (since standard CloudWatch does not provide OS memory).
    - RDS: CPU, freeable memory %, storage disk %, IOPS, database connections, and latency.
    - ALB: Request rate, target response time latency, 5xx error rate, active connections, and cpu=None.
    - S3: Bucket size bytes and object count.
    """
    now = datetime.now(timezone.utc)
    timestamp_str = now.isoformat()
    snapshots = []

    for comp in components:
        cid = comp["id"]
        ctype = comp.get("type", "server")
        if hasattr(ctype, "value"):
            ctype = ctype.value
        status = comp.get("status", "active")
        if hasattr(status, "value"):
            status = status.value

        if cid == "i-09f182c81a2b": # WatersConnect-API-01
            snapshots.append({
                "id": str(uuid.uuid4()),
                "resource_id": cid,
                "timestamp": timestamp_str,
                "resource_type": "server",
                "cpu": 28.4,
                "memory": None, # Genuine AWS rule: No OS memory from EC2 hypervisor
                "disk": {
                    "read_bytes_sec": 14200.0,
                    "write_bytes_sec": 85400.0,
                    "read_iops": 18.2,
                    "write_iops": 45.6
                },
                "network": {
                    "in_bytes_sec": 428000.0,
                    "out_bytes_sec": 892000.0,
                    "total_bytes_sec": 1320000.0
                },
                "latency": None,
                "error_rate": None,
                "request_rate": None,
                "connections": None,
                "status": "active",
                "age_days": 42.5,
                "raw_metrics": {
                    "CPUUtilization": 28.4,
                    "NetworkIn": 128400000.0,
                    "NetworkOut": 267600000.0,
                    "DiskWriteBytes": 25620000.0,
                    "StatusCheckFailed": 0.0
                }
            })

        elif cid == "i-03a89e1b2c3d": # WatersConnect-API-02
            snapshots.append({
                "id": str(uuid.uuid4()),
                "resource_id": cid,
                "timestamp": timestamp_str,
                "resource_type": "server",
                "cpu": 31.8,
                "memory": None, # Genuine AWS rule: No OS memory from EC2 hypervisor
                "disk": {
                    "read_bytes_sec": 16500.0,
                    "write_bytes_sec": 92100.0,
                    "read_iops": 21.0,
                    "write_iops": 49.2
                },
                "network": {
                    "in_bytes_sec": 445000.0,
                    "out_bytes_sec": 915000.0,
                    "total_bytes_sec": 1360000.0
                },
                "latency": None,
                "error_rate": None,
                "request_rate": None,
                "connections": None,
                "status": "active",
                "age_days": 42.5,
                "raw_metrics": {
                    "CPUUtilization": 31.8,
                    "NetworkIn": 133500000.0,
                    "NetworkOut": 274500000.0,
                    "DiskWriteBytes": 27630000.0,
                    "StatusCheckFailed": 0.0
                }
            })

        elif cid == "rds-prod-analytics-db":
            snapshots.append({
                "id": str(uuid.uuid4()),
                "resource_id": cid,
                "timestamp": timestamp_str,
                "resource_type": "database",
                "cpu": 22.5,
                "memory": 48.6, # Computed from FreeableMemory vs db.m5.xlarge (16 GB)
                "disk": {
                    "utilization_pct": 36.4,
                    "read_iops": 64.0,
                    "write_iops": 182.5,
                    "free_storage_gb": 63.6
                },
                "network": {
                    "in_bytes_sec": 384000.0,
                    "out_bytes_sec": 760000.0,
                    "total_bytes_sec": 1144000.0
                },
                "latency": 0.0028, # 2.8ms average query latency
                "error_rate": None,
                "request_rate": None,
                "connections": 24.0,
                "status": "active",
                "age_days": 90.0,
                "raw_metrics": {
                    "CPUUtilization": 22.5,
                    "FreeableMemory": 8820000000.0,
                    "FreeStorageSpace": 68287848448.0,
                    "DatabaseConnections": 24.0,
                    "ReadIOPS": 64.0,
                    "WriteIOPS": 182.5,
                    "ReadLatency": 0.0021,
                    "WriteLatency": 0.0035
                }
            })

        elif cid == "alb-prod-ingress":
            snapshots.append({
                "id": str(uuid.uuid4()),
                "resource_id": cid,
                "timestamp": timestamp_str,
                "resource_type": "load_balancer",
                "cpu": None, # ALB does not expose CPU
                "memory": None, # ALB does not expose Memory
                "disk": None, # ALB does not expose Disk
                "network": {
                    "in_bytes_sec": 890000.0,
                    "out_bytes_sec": 1820000.0,
                    "total_bytes_sec": 2710000.0
                },
                "latency": 0.0165, # 16.5ms TargetResponseTime
                "error_rate": 0.04, # 0.04% 5XX error rate
                "request_rate": 142.5, # requests per second
                "connections": 58.0, # ActiveConnectionCount
                "status": "active",
                "age_days": 60.0,
                "raw_metrics": {
                    "RequestCount": 42750.0,
                    "TargetResponseTime": 0.0165,
                    "HTTPCode_Target_5XX_Count": 17.0,
                    "HTTPCode_ELB_5XX_Count": 0.0,
                    "ActiveConnectionCount": 58.0,
                    "ProcessedBytes": 267000000.0
                }
            })

        elif cid == "s3-enterprise-datalake":
            snapshots.append({
                "id": str(uuid.uuid4()),
                "resource_id": cid,
                "timestamp": timestamp_str,
                "resource_type": "storage",
                "cpu": None,
                "memory": None,
                "disk": {
                    "bucket_size_bytes": 4617089843200, # ~4.2 TB
                    "object_count": 1420800
                },
                "network": None,
                "latency": None,
                "error_rate": None,
                "request_rate": None,
                "connections": None,
                "status": "active",
                "age_days": 180.0,
                "raw_metrics": {
                    "BucketSizeBytes": 4617089843200.0,
                    "NumberOfObjects": 1420800.0
                }
            })

        else:
            # Baseline component (e.g. on-prem or VPC/Subnet)
            snapshots.append({
                "id": str(uuid.uuid4()),
                "resource_id": cid,
                "timestamp": timestamp_str,
                "resource_type": ctype,
                "cpu": comp.get("cpu"),
                "memory": comp.get("memory"),
                "disk": None,
                "network": None,
                "latency": None,
                "error_rate": None,
                "request_rate": None,
                "connections": None,
                "status": status,
                "age_days": None,
                "raw_metrics": {}
            })

    return snapshots


def collect_and_store_metrics(
    db,
    use_synthetic: bool = False,
    period_seconds: int = 300,
    region: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], str]:
    """
    Orchestrates metric collection (live CloudWatch or synthetic) and persists snapshots in SQLite.
    Returns (snapshots, data_source).
    """
    components = db.query(models.Component).all()
    comp_dicts = [
        {
            "id": c.id,
            "name": c.name,
            "type": c.type.value if hasattr(c.type, "value") else str(c.type),
            "status": c.status.value if hasattr(c.status, "value") else str(c.status),
            "arn": c.arn,
            "cpu": c.cpu,
            "memory": c.memory,
            "metadata_col": c.metadata_col or {}
        }
        for c in components
    ]

    session = get_boto3_session(region)
    auth = check_aws_credentials(session)

    if auth["authenticated"] and not use_synthetic:
        collector = AWSMetricsCollector(session, region)
        snapshots = collector.collect_cloudwatch_metrics(comp_dicts, period_seconds)
        data_source = "aws_cloudwatch"
    elif use_synthetic:
        snapshots = generate_synthetic_metrics(comp_dicts)
        data_source = "aws_synthetic_cloudwatch"
    else:
        # Live mode requested but credentials not authenticated - never fabricate telemetry
        snapshots = []
        now_iso = datetime.now(timezone.utc).isoformat()
        for c in comp_dicts:
            snapshots.append({
                "id": str(uuid.uuid4()),
                "resource_id": c["id"],
                "timestamp": now_iso,
                "resource_type": c["type"],
                "cpu": None,
                "memory": None,
                "disk": None,
                "network": None,
                "latency": None,
                "error_rate": None,
                "request_rate": None,
                "connections": None,
                "status": "UNAVAILABLE",
                "age_days": None,
                "raw_metrics": {"status": "NO_DATA", "error": auth.get("error") or "CloudWatch credentials unavailable"}
            })
        data_source = "aws_cloudwatch_unavailable"

    # Store in database
    for snap in snapshots:
        record = models.MetricSnapshot(
            id=snap["id"],
            resource_id=snap["resource_id"],
            timestamp=snap["timestamp"],
            resource_type=snap["resource_type"],
            cpu=snap["cpu"],
            memory=snap["memory"],
            disk=snap["disk"],
            network=snap["network"],
            latency=snap["latency"],
            error_rate=snap["error_rate"],
            request_rate=snap["request_rate"],
            connections=snap["connections"],
            status=snap["status"],
            age_days=snap["age_days"],
            raw_metrics=snap["raw_metrics"]
        )
        db.add(record)

    db.commit()
    return snapshots, data_source
