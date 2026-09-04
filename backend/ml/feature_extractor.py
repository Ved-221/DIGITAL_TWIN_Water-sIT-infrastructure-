import numpy as np
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

import models
import simulation

CRITICALITY_MAP = {
    "critical": 3,
    "high": 2,
    "medium": 1,
    "low": 0
}

def extract_features_for_component(
    db: Session,
    component_id: str,
    graph: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Extracts the normalized 18-dimensional feature vector for a specific component
    by combining component properties, latest metric snapshot, and topology graph degrees.
    """
    comp = db.query(models.Component).filter_by(id=component_id).first()
    if not comp:
        raise ValueError(f"Component {component_id} not found in database.")

    # 1. Graph topological degrees
    if graph is None:
        graph = simulation.build_graph(db)

    dep_count = graph.out_degree(component_id) if component_id in graph else 0
    dep_on_count = graph.in_degree(component_id) if component_id in graph else 0

    # 2. Latest metric snapshot
    latest_snap = db.query(models.MetricSnapshot)\
        .filter_by(resource_id=component_id)\
        .order_by(models.MetricSnapshot.timestamp.desc())\
        .first()

    # 3. Component base attributes
    rtype = comp.type.value if hasattr(comp.type, "value") else str(comp.type)
    env = comp.environment.value if hasattr(comp.environment, "value") else str(comp.environment)
    crit_str = comp.criticality.value if hasattr(comp.criticality, "value") else str(comp.criticality)
    crit_score = CRITICALITY_MAP.get(crit_str.lower(), 1)
    status_str = comp.status.value if hasattr(comp.status, "value") else str(comp.status)
    is_active = 1 if status_str == "active" else 0
    cost = float(comp.cost_per_month or 0.0)

    # 4. Metric attributes
    cpu = np.nan
    mem = np.nan
    disk_pct = np.nan
    disk_iops = 0.0
    net_kb = 0.0
    lat_ms = np.nan
    err_pct = np.nan
    req_rate = np.nan
    conn_count = np.nan
    age_days = 30.0
    cpu_trend = 0.0
    traffic_trend = 0.0

    if latest_snap:
        if latest_snap.cpu is not None:
            cpu = float(latest_snap.cpu)
        if latest_snap.memory is not None:
            mem = float(latest_snap.memory)
        if latest_snap.latency is not None:
            lat_ms = float(latest_snap.latency * 1000.0) # convert seconds to ms
        if latest_snap.error_rate is not None:
            err_pct = float(latest_snap.error_rate)
        if latest_snap.request_rate is not None:
            req_rate = float(latest_snap.request_rate)
        if latest_snap.connections is not None:
            conn_count = float(latest_snap.connections)
        if latest_snap.age_days is not None:
            age_days = float(latest_snap.age_days)

        # Disk features
        if latest_snap.disk:
            disk_dict = latest_snap.disk
            if "utilization_pct" in disk_dict and disk_dict["utilization_pct"] is not None:
                disk_pct = float(disk_dict["utilization_pct"])
            riops = disk_dict.get("read_iops", 0.0) or 0.0
            wiops = disk_dict.get("write_iops", 0.0) or 0.0
            disk_iops = float(riops + wiops)

        # Network features
        if latest_snap.network:
            net_dict = latest_snap.network
            total_bytes = net_dict.get("total_bytes_sec", 0.0) or 0.0
            net_kb = float(total_bytes / 1024.0)

        # Compute trends if earlier snapshots exist
        earlier_snaps = db.query(models.MetricSnapshot)\
            .filter_by(resource_id=component_id)\
            .order_by(models.MetricSnapshot.timestamp.desc())\
            .limit(3)\
            .all()

        if len(earlier_snaps) >= 2:
            prev = earlier_snaps[1]
            if latest_snap.cpu is not None and prev.cpu is not None:
                cpu_trend = round(float(latest_snap.cpu - prev.cpu), 2)
            curr_bytes = latest_snap.network.get("total_bytes_sec", 0.0) if latest_snap.network else 0.0
            prev_bytes = prev.network.get("total_bytes_sec", 0.0) if prev.network else 0.0
            if prev_bytes > 0:
                traffic_trend = round(((curr_bytes - prev_bytes) / prev_bytes) * 100.0, 2)

    return {
        "resource_type": rtype,
        "environment": env,
        "criticality_score": crit_score,
        "cost_monthly": cost,
        "is_active": is_active,
        "resource_age_days": age_days,
        "dependency_count": dep_count,
        "dependent_count": dep_on_count,
        "cpu_utilization": cpu,
        "memory_utilization": mem,
        "disk_utilization_pct": disk_pct,
        "disk_iops": disk_iops,
        "network_throughput_kb_s": net_kb,
        "latency_ms": lat_ms,
        "error_rate_pct": err_pct,
        "request_rate": req_rate,
        "connection_count": conn_count,
        "cpu_trend_1h": cpu_trend,
        "traffic_trend_1h": traffic_trend,
    }
