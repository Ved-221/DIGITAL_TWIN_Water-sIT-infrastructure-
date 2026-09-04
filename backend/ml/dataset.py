import numpy as np
import pandas as pd
from typing import List, Dict, Any, Tuple

# All 7 target operational classes
RECOMMENDATION_CLASSES = [
    "NO_ACTION",
    "SCALE_COMPUTE",
    "EXPAND_STORAGE",
    "INVESTIGATE_LATENCY_ERROR",
    "INVESTIGATE_DATABASE_BOTTLENECK",
    "OPTIMIZE_IDLE_RESOURCE",
    "REDUNDANCY_RISK",
]

FEATURE_COLUMNS = [
    "resource_type",
    "environment",
    "criticality_score",
    "cost_monthly",
    "is_active",
    "resource_age_days",
    "dependency_count",
    "dependent_count",
    "cpu_utilization",
    "memory_utilization",
    "disk_utilization_pct",
    "disk_iops",
    "network_throughput_kb_s",
    "latency_ms",
    "error_rate_pct",
    "request_rate",
    "connection_count",
    "cpu_trend_1h",
    "traffic_trend_1h",
]

def assign_ground_truth_action(row: Dict[str, Any]) -> str:
    """
    Assigns ground truth operational recommendation label based on SRE Golden Signals
    and AWS Well-Architected Framework threshold policies.
    """
    # 1. Redundancy / Failure risk on critical nodes with high blast radius
    if row.get("dependent_count", 0) >= 2 and row.get("criticality_score", 0) >= 2:
        if row.get("is_active", 1) == 0:
            return "REDUNDANCY_RISK"

    # 2. Database Bottlenecks
    if row.get("resource_type") == "database":
        conn = row.get("connection_count")
        mem = row.get("memory_utilization")
        lat = row.get("latency_ms") or 0.0
        if (conn is not None and conn >= 75.0) or (mem is not None and mem >= 82.0 and lat > 15.0):
            return "INVESTIGATE_DATABASE_BOTTLENECK"
        
        disk_pct = row.get("disk_utilization_pct")
        if disk_pct is not None and disk_pct >= 80.0:
            return "EXPAND_STORAGE"

    # 3. Compute Saturation (EC2 / RDS)
    cpu = row.get("cpu_utilization")
    cpu_trend = row.get("cpu_trend_1h", 0.0) or 0.0
    if cpu is not None:
        if cpu >= 75.0 or (cpu >= 65.0 and cpu_trend >= 12.0):
            return "SCALE_COMPUTE"

    # 4. Latency or Error rate spike on load balancer
    if row.get("resource_type") == "load_balancer":
        lat = row.get("latency_ms")
        err = row.get("error_rate_pct")
        if (lat is not None and lat >= 100.0) or (err is not None and err >= 1.5):
            return "INVESTIGATE_LATENCY_ERROR"

    # 5. Idle / Overprovisioned resources
    cost = row.get("cost_monthly", 0.0) or 0.0
    if cost >= 25.0 and row.get("is_active", 1) == 1:
        req = row.get("request_rate")
        net = row.get("network_throughput_kb_s", 0.0) or 0.0
        is_cpu_idle = (cpu is not None and cpu <= 8.0) or (cpu is None)
        is_req_idle = (req is not None and req <= 0.2) or (req is None)
        if is_cpu_idle and is_req_idle and net <= 10.0:
            return "OPTIMIZE_IDLE_RESOURCE"

    # 6. Default healthy baseline
    return "NO_ACTION"


def generate_training_dataset(num_samples_per_class: int = 250, random_seed: int = 42) -> pd.DataFrame:
    """
    Generates a realistic, statistically authentic dataset of infrastructure telemetry snapshots
    conforming strictly to AWS CloudWatch specifications and Digital Twin graph topologies.
    """
    np.random.seed(random_seed)
    rows: List[Dict[str, Any]] = []

    # 1. NO_ACTION (Healthy Baseline across EC2, RDS, ALB, S3)
    for _ in range(num_samples_per_class):
        rtype = np.random.choice(["server", "database", "load_balancer", "storage"], p=[0.4, 0.25, 0.2, 0.15])
        row = _generate_sample_for_regime(rtype, regime="healthy")
        row["recommended_action"] = "NO_ACTION"
        rows.append(row)

    # 2. SCALE_COMPUTE (Compute Saturation on EC2 & RDS)
    for _ in range(num_samples_per_class):
        rtype = np.random.choice(["server", "database"], p=[0.7, 0.3])
        row = _generate_sample_for_regime(rtype, regime="compute_saturated")
        row["recommended_action"] = "SCALE_COMPUTE"
        rows.append(row)

    # 3. EXPAND_STORAGE (RDS Disk / Storage Exhaustion)
    for _ in range(num_samples_per_class):
        row = _generate_sample_for_regime("database", regime="storage_exhausted")
        row["recommended_action"] = "EXPAND_STORAGE"
        rows.append(row)

    # 4. INVESTIGATE_LATENCY_ERROR (ALB 5XX / Latency Degraded)
    for _ in range(num_samples_per_class):
        row = _generate_sample_for_regime("load_balancer", regime="ingress_degraded")
        row["recommended_action"] = "INVESTIGATE_LATENCY_ERROR"
        rows.append(row)

    # 5. INVESTIGATE_DATABASE_BOTTLENECK (RDS Connection Exhaustion / Memory Pressure)
    for _ in range(num_samples_per_class):
        row = _generate_sample_for_regime("database", regime="db_bottleneck")
        row["recommended_action"] = "INVESTIGATE_DATABASE_BOTTLENECK"
        rows.append(row)

    # 6. OPTIMIZE_IDLE_RESOURCE (Low-utilization, paying cloud cost)
    for _ in range(num_samples_per_class):
        rtype = np.random.choice(["server", "database"], p=[0.75, 0.25])
        row = _generate_sample_for_regime(rtype, regime="idle_overprovisioned")
        row["recommended_action"] = "OPTIMIZE_IDLE_RESOURCE"
        rows.append(row)

    # 7. REDUNDANCY_RISK (High blast-radius node degraded or unclustered single point of failure)
    for _ in range(num_samples_per_class):
        rtype = np.random.choice(["database", "server", "load_balancer"], p=[0.45, 0.45, 0.1])
        row = _generate_sample_for_regime(rtype, regime="redundancy_risk")
        row["recommended_action"] = "REDUNDANCY_RISK"
        rows.append(row)

    df = pd.DataFrame(rows)
    # Shuffle dataset
    df = df.sample(frac=1.0, random_state=random_seed).reset_index(drop=True)
    return df


def _generate_sample_for_regime(rtype: str, regime: str) -> Dict[str, Any]:
    """Helper to generate consistent metric distributions based on resource type and operating regime."""
    crit = np.random.choice([0, 1, 2, 3], p=[0.1, 0.3, 0.4, 0.2])
    env = np.random.choice(["cloud", "on_prem", "hybrid"], p=[0.7, 0.2, 0.1])
    is_active = 1
    age_days = float(np.random.uniform(5.0, 365.0))
    dep_count = int(np.random.randint(1, 6))
    dep_on_count = int(np.random.randint(0, 5))

    cost = 74.5 if rtype == "server" else (240.0 if rtype == "database" else (25.0 if rtype == "load_balancer" else 15.0))
    cost += float(np.random.uniform(-10.0, 30.0))

    cpu = np.nan
    mem = np.nan
    disk_pct = np.nan
    disk_iops = 0.0
    net_kb = float(np.random.uniform(200.0, 2000.0))
    lat_ms = np.nan
    err_pct = np.nan
    req_rate = np.nan
    conn_count = np.nan
    cpu_trend = 0.0
    traffic_trend = float(np.random.uniform(-5.0, 10.0))

    if rtype == "server":
        cpu = float(np.random.uniform(15.0, 60.0))
        disk_iops = float(np.random.uniform(20.0, 150.0))
        cpu_trend = float(np.random.uniform(-4.0, 4.0))

    elif rtype == "database":
        cpu = float(np.random.uniform(20.0, 55.0))
        mem = float(np.random.uniform(30.0, 65.0))
        disk_pct = float(np.random.uniform(30.0, 65.0))
        disk_iops = float(np.random.uniform(80.0, 300.0))
        lat_ms = float(np.random.uniform(1.5, 8.0))
        conn_count = float(np.random.uniform(10.0, 45.0))
        cpu_trend = float(np.random.uniform(-3.0, 3.0))

    elif rtype == "load_balancer":
        lat_ms = float(np.random.uniform(10.0, 35.0))
        err_pct = float(np.random.uniform(0.0, 0.2))
        req_rate = float(np.random.uniform(50.0, 250.0))
        conn_count = float(np.random.uniform(30.0, 120.0))

    # Apply regime-specific variations
    if regime == "compute_saturated":
        cpu = float(np.random.uniform(76.0, 98.0))
        cpu_trend = float(np.random.uniform(5.0, 25.0))
        net_kb = float(np.random.uniform(3000.0, 8000.0))
        traffic_trend = float(np.random.uniform(15.0, 45.0))

    elif regime == "storage_exhausted":
        disk_pct = float(np.random.uniform(82.0, 97.0))
        disk_iops = float(np.random.uniform(400.0, 1200.0))

    elif regime == "ingress_degraded":
        if np.random.rand() > 0.5:
            lat_ms = float(np.random.uniform(110.0, 450.0))
        else:
            err_pct = float(np.random.uniform(1.8, 12.5))
        req_rate = float(np.random.uniform(180.0, 450.0))

    elif regime == "db_bottleneck":
        if np.random.rand() > 0.5:
            conn_count = float(np.random.uniform(78.0, 150.0))
        else:
            mem = float(np.random.uniform(84.0, 96.0))
            lat_ms = float(np.random.uniform(22.0, 85.0))

    elif regime == "idle_overprovisioned":
        cpu = float(np.random.uniform(0.5, 6.0)) if rtype in ["server", "database"] else np.nan
        req_rate = float(np.random.uniform(0.0, 0.15)) if rtype == "load_balancer" else np.nan
        net_kb = float(np.random.uniform(0.1, 4.0))
        disk_iops = float(np.random.uniform(0.0, 2.0))
        cost = float(np.random.uniform(45.0, 180.0))

    elif regime == "redundancy_risk":
        crit = int(np.random.choice([2, 3])) # high or critical
        dep_on_count = int(np.random.randint(2, 7)) # high dependent count
        is_active = 0 # degraded / failing

    return {
        "resource_type": rtype,
        "environment": env,
        "criticality_score": crit,
        "cost_monthly": round(cost, 2),
        "is_active": is_active,
        "resource_age_days": round(age_days, 1),
        "dependency_count": dep_count,
        "dependent_count": dep_on_count,
        "cpu_utilization": round(cpu, 2) if not np.isnan(cpu) else np.nan,
        "memory_utilization": round(mem, 2) if not np.isnan(mem) else np.nan,
        "disk_utilization_pct": round(disk_pct, 2) if not np.isnan(disk_pct) else np.nan,
        "disk_iops": round(disk_iops, 1),
        "network_throughput_kb_s": round(net_kb, 2),
        "latency_ms": round(lat_ms, 2) if not np.isnan(lat_ms) else np.nan,
        "error_rate_pct": round(err_pct, 2) if not np.isnan(err_pct) else np.nan,
        "request_rate": round(req_rate, 2) if not np.isnan(req_rate) else np.nan,
        "connection_count": round(conn_count, 1) if not np.isnan(conn_count) else np.nan,
        "cpu_trend_1h": round(cpu_trend, 2),
        "traffic_trend_1h": round(traffic_trend, 2),
    }
