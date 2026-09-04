import numpy as np
from typing import Dict, Any, List, Optional

# Feature column definitions for consistent vectorization
CATEGORICAL_FEATURES = {
    "component_type": ["server", "database", "application", "lambda", "container", "storage", "other"],
    "criticality": ["critical", "high", "medium", "low"],
    "status": ["active", "degraded", "warning", "stopped"],
    "action": ["migrate", "scale", "restart", "fail", "deploy"],
    "strategy_type": [
        "direct_lift_shift",
        "phased_blue_green",
        "multi_az_modernize",
        "read_replica_offload",
        "auto_scaling_group",
        "dependency_circuit_breaker"
    ]
}

NUMERICAL_FEATURES = [
    "upstream_callers_count",
    "downstream_deps_count",
    "total_affected_count",
    "critical_callers_count",
    "max_dependency_depth",
    "is_spof",
    "cross_env_links",
    "cpu_percent",
    "has_cpu_telemetry",
    "storage_gb",
    "has_storage_telemetry",
    "cost_per_month",
    "risk_score",
    "simulated_downtime_minutes",
    "has_downtime_metric",
    "simulated_cost_delta",
    "has_cost_metric",
    "strategy_complexity",
    "provides_redundancy",
    "requires_data_sync",
    "zero_downtime_capable"
]

def extract_features_dict(
    simulation_result: Dict[str, Any],
    candidate_strategy: Dict[str, Any],
    component_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Extracts a structured, dictionary-based feature map from actual Digital Twin simulation
    and a candidate strategy option. Explicitly handles missing data.
    """
    comp = component_data or {}
    meta = comp.get("metadata_col", {}) or {}
    telemetry = comp.get("telemetry", {}) or {}
    risk_factors = simulation_result.get("risk_factors", {}) or {}
    
    # 1. Topology features
    upstream_count = int(simulation_result.get("upstream_impact_count", len(simulation_result.get("upstream_impact", []))))
    downstream_count = int(simulation_result.get("downstream_dependencies_count", len(simulation_result.get("downstream_dependencies", []))))
    total_affected = int(simulation_result.get("total_nodes_affected", simulation_result.get("affected_count", 0)))
    crit_callers = int(risk_factors.get("critical_callers_affected", 0))
    max_depth = int(risk_factors.get("max_dependency_depth", 0))
    is_spof = 1 if risk_factors.get("is_single_point_of_failure", False) else 0
    cross_env = int(risk_factors.get("cross_environment_links_count", 0))
    
    # 2. Component & Telemetry features
    comp_type = str(comp.get("type", "server")).lower()
    if comp_type not in CATEGORICAL_FEATURES["component_type"]:
        comp_type = "other"
        
    crit_str = str(comp.get("criticality", risk_factors.get("target_criticality", "medium"))).lower()
    if crit_str not in CATEGORICAL_FEATURES["criticality"]:
        crit_str = "medium"
        
    status_str = str(comp.get("status", risk_factors.get("component_status", "active"))).lower()
    if status_str not in CATEGORICAL_FEATURES["status"]:
        status_str = "active"
        
    cpu_val = comp.get("cpu", risk_factors.get("cpu_utilization_percent"))
    if cpu_val is not None:
        cpu_percent = float(cpu_val)
        has_cpu = 1
    else:
        cpu_percent = -1.0
        has_cpu = 0
        
    storage_val = meta.get("storage_gb") or meta.get("db_size_gb") or telemetry.get("storage_size_gb")
    if storage_val is not None:
        storage_gb = float(storage_val)
        has_storage = 1
    else:
        storage_gb = -1.0
        has_storage = 0
        
    cost_month = float(comp.get("cost_per_month", 0.0) or 0.0)
    
    # 3. Simulation output features
    action_str = str(simulation_result.get("action", "migrate")).lower()
    if action_str not in CATEGORICAL_FEATURES["action"]:
        action_str = "migrate"
        
    risk_score = float(simulation_result.get("risk_score", 0.0))
    
    dt_val = simulation_result.get("estimated_downtime_minutes")
    if dt_val is not None:
        sim_dt = float(dt_val)
        has_dt = 1
    else:
        sim_dt = -1.0
        has_dt = 0
        
    cost_delta_val = simulation_result.get("cost_delta_monthly")
    if cost_delta_val is not None:
        sim_cost_delta = float(cost_delta_val)
        has_cost = 1
    else:
        sim_cost_delta = 0.0
        has_cost = 0
        
    # 4. Strategy candidate features
    strat_type = str(candidate_strategy.get("strategy_type", "direct_lift_shift")).lower()
    if strat_type not in CATEGORICAL_FEATURES["strategy_type"]:
        strat_type = "direct_lift_shift"
        
    strat_complexity = int(candidate_strategy.get("complexity", 1))
    provides_red = 1 if candidate_strategy.get("provides_redundancy", False) else 0
    requires_sync = 1 if candidate_strategy.get("requires_data_sync", False) else 0
    zero_dt = 1 if candidate_strategy.get("zero_downtime_capable", False) else 0
    
    return {
        # Categoricals
        "component_type": comp_type,
        "criticality": crit_str,
        "status": status_str,
        "action": action_str,
        "strategy_type": strat_type,
        # Numericals
        "upstream_callers_count": upstream_count,
        "downstream_deps_count": downstream_count,
        "total_affected_count": total_affected,
        "critical_callers_count": crit_callers,
        "max_dependency_depth": max_depth,
        "is_spof": is_spof,
        "cross_env_links": cross_env,
        "cpu_percent": cpu_percent,
        "has_cpu_telemetry": has_cpu,
        "storage_gb": storage_gb,
        "has_storage_telemetry": has_storage,
        "cost_per_month": cost_month,
        "risk_score": risk_score,
        "simulated_downtime_minutes": sim_dt,
        "has_downtime_metric": has_dt,
        "simulated_cost_delta": sim_cost_delta,
        "has_cost_metric": has_cost,
        "strategy_complexity": strat_complexity,
        "provides_redundancy": provides_red,
        "requires_data_sync": requires_sync,
        "zero_downtime_capable": zero_dt
    }

def get_feature_names() -> List[str]:
    """Returns the ordered list of one-hot encoded and numerical feature column names."""
    names = []
    # Add one-hot category columns
    for cat_col, values in CATEGORICAL_FEATURES.items():
        for val in values:
            names.append(f"{cat_col}_{val}")
    # Add numerical columns
    names.extend(NUMERICAL_FEATURES)
    return names

def vectorize_features(features_dict: Dict[str, Any]) -> np.ndarray:
    """Converts a feature dictionary into a 1D numpy vector matching get_feature_names()."""
    row = []
    # One-hot encode categoricals
    for cat_col, values in CATEGORICAL_FEATURES.items():
        current_val = features_dict.get(cat_col)
        for val in values:
            row.append(1.0 if current_val == val else 0.0)
            
    # Append numericals
    for num_col in NUMERICAL_FEATURES:
        val = features_dict.get(num_col, 0.0)
        row.append(float(val if val is not None else 0.0))
        
    return np.array(row, dtype=np.float32)

def extract_features_for_component(
    db,
    component_id: str,
    graph: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Extracts telemetry and graph features for a component for the recommender model.
    """
    import models
    import simulation
    comp = db.query(models.Component).filter_by(id=component_id).first()
    if not comp:
        raise ValueError(f"Component {component_id} not found in database.")

    if graph is None:
        graph = simulation.build_graph(db)

    dep_count = graph.out_degree(component_id) if component_id in graph else 0
    dep_on_count = graph.in_degree(component_id) if component_id in graph else 0

    latest_snap = db.query(models.MetricSnapshot)\
        .filter_by(resource_id=component_id)\
        .order_by(models.MetricSnapshot.timestamp.desc())\
        .first()

    rtype = comp.type.value if hasattr(comp.type, "value") else str(comp.type)
    env = comp.environment.value if hasattr(comp.environment, "value") else str(comp.environment)
    crit_str = comp.criticality.value if hasattr(comp.criticality, "value") else str(comp.criticality)
    crit_map = {"critical": 3, "high": 2, "medium": 1, "low": 0}
    crit_score = crit_map.get(crit_str.lower(), 1)
    status_str = comp.status.value if hasattr(comp.status, "value") else str(comp.status)
    is_active = 1 if status_str == "active" else 0
    cost = float(comp.cost_per_month or 0.0)

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
            lat_ms = float(latest_snap.latency * 1000.0)
        if latest_snap.error_rate is not None:
            err_pct = float(latest_snap.error_rate)
        if latest_snap.request_rate is not None:
            req_rate = float(latest_snap.request_rate)
        if latest_snap.connections is not None:
            conn_count = float(latest_snap.connections)
        if latest_snap.age_days is not None:
            age_days = float(latest_snap.age_days)

        if latest_snap.disk:
            disk_dict = latest_snap.disk
            if "utilization_pct" in disk_dict and disk_dict["utilization_pct"] is not None:
                disk_pct = float(disk_dict["utilization_pct"])
            riops = disk_dict.get("read_iops", 0.0) or 0.0
            wiops = disk_dict.get("write_iops", 0.0) or 0.0
            disk_iops = float(riops + wiops)

        if latest_snap.network:
            net_dict = latest_snap.network
            total_bytes = net_dict.get("total_bytes_sec", 0.0) or 0.0
            net_kb = float(total_bytes / 1024.0)

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

