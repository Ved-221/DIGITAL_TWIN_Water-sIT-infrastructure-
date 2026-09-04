import logging
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np
from sqlalchemy.orm import Session

import models
import simulation
from ml.trainer import load_trained_model
from ml.feature_extractor import extract_features_for_component
from ml.dataset import FEATURE_COLUMNS

logger = logging.getLogger("infratwin.ml.recommender")

# Cache loaded model instance in memory
_CACHED_PIPELINE = None
_CACHED_METADATA = None

def get_recommender_model():
    """Returns singleton cached model pipeline and metadata."""
    global _CACHED_PIPELINE, _CACHED_METADATA
    if _CACHED_PIPELINE is None or _CACHED_METADATA is None:
        _CACHED_PIPELINE, _CACHED_METADATA = load_trained_model()
    return _CACHED_PIPELINE, _CACHED_METADATA


def reload_recommender_model():
    """Forces reloading the model from disk (e.g. after retraining)."""
    global _CACHED_PIPELINE, _CACHED_METADATA
    _CACHED_PIPELINE, _CACHED_METADATA = load_trained_model()
    return _CACHED_PIPELINE, _CACHED_METADATA


def _is_valid(val: Any) -> bool:
    return val is not None and not (isinstance(val, float) and np.isnan(val))


def derive_reasoning_features(
    features: Dict[str, Any],
    predicted_action: str
) -> List[Dict[str, Any]]:
    """
    Identifies the key contributing operational features that justify the recommended action.
    """
    reasons = []

    if predicted_action == "SCALE_COMPUTE":
        cpu = features.get("cpu_utilization")
        trend = features.get("cpu_trend_1h")
        if _is_valid(cpu):
            reasons.append({"feature": "cpu_utilization", "value": f"{cpu}%", "impact": "high"})
        if _is_valid(trend) and abs(trend) > 0:
            reasons.append({"feature": "cpu_trend_1h", "value": f"{trend:+}%", "impact": "medium"})
        dep_on = features.get("dependent_count", 0)
        if _is_valid(dep_on) and dep_on > 0:
            reasons.append({"feature": "dependent_count", "value": dep_on, "impact": "medium"})

    elif predicted_action == "EXPAND_STORAGE":
        disk = features.get("disk_utilization_pct")
        iops = features.get("disk_iops")
        if _is_valid(disk):
            reasons.append({"feature": "disk_utilization_pct", "value": f"{disk}%", "impact": "high"})
        if _is_valid(iops) and iops > 0:
            reasons.append({"feature": "disk_iops", "value": f"{iops} IOPS", "impact": "medium"})

    elif predicted_action == "INVESTIGATE_LATENCY_ERROR":
        lat = features.get("latency_ms")
        err = features.get("error_rate_pct")
        if _is_valid(lat):
            reasons.append({"feature": "latency_ms", "value": f"{lat:.1f} ms", "impact": "high"})
        if _is_valid(err):
            reasons.append({"feature": "error_rate_pct", "value": f"{err:.2f}%", "impact": "high"})
        req = features.get("request_rate")
        if _is_valid(req):
            reasons.append({"feature": "request_rate", "value": f"{req} req/s", "impact": "medium"})

    elif predicted_action == "INVESTIGATE_DATABASE_BOTTLENECK":
        conn = features.get("connection_count")
        mem = features.get("memory_utilization")
        lat = features.get("latency_ms")
        if _is_valid(conn):
            reasons.append({"feature": "connection_count", "value": conn, "impact": "high"})
        if _is_valid(mem):
            reasons.append({"feature": "memory_utilization", "value": f"{mem}%", "impact": "high"})
        if _is_valid(lat):
            reasons.append({"feature": "latency_ms", "value": f"{lat:.1f} ms", "impact": "medium"})

    elif predicted_action == "OPTIMIZE_IDLE_RESOURCE":
        cost = features.get("cost_monthly")
        cpu = features.get("cpu_utilization")
        net = features.get("network_throughput_kb_s")
        if _is_valid(cost):
            reasons.append({"feature": "cost_monthly", "value": f"${cost:.2f}/mo", "impact": "high"})
        if _is_valid(cpu):
            reasons.append({"feature": "cpu_utilization", "value": f"{cpu}%", "impact": "high"})
        if _is_valid(net):
            reasons.append({"feature": "network_throughput", "value": f"{net:.1f} KB/s", "impact": "medium"})

    elif predicted_action == "REDUNDANCY_RISK":
        dep_on = features.get("dependent_count")
        crit = features.get("criticality_score")
        active = features.get("is_active")
        if _is_valid(active) and active == 0:
            reasons.append({"feature": "status", "value": "degraded/inactive", "impact": "high"})
        if _is_valid(dep_on):
            reasons.append({"feature": "dependent_count", "value": dep_on, "impact": "high"})
        if _is_valid(crit):
            reasons.append({"feature": "criticality", "value": "critical" if crit == 3 else "high", "impact": "medium"})

    else:
        # NO_ACTION
        cpu = features.get("cpu_utilization")
        lat = features.get("latency_ms")
        net = features.get("network_throughput_kb_s")
        if _is_valid(cpu):
            reasons.append({"feature": "cpu_utilization", "value": f"{cpu}% (healthy)", "impact": "low"})
        if _is_valid(lat):
            reasons.append({"feature": "latency_ms", "value": f"{lat:.1f} ms (nominal)", "impact": "low"})
        if _is_valid(net) and net > 0:
            reasons.append({"feature": "network_throughput", "value": f"{net:.1f} KB/s", "impact": "low"})
        reasons.append({"feature": "operational_status", "value": "All signals within safe threshold bands", "impact": "low"})

    return reasons[:4]


def predict_component_action(
    component_id: str,
    db: Session,
    graph: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Executes trained model inference for a single component:
    1. Extracts normalized feature vector.
    2. Runs model pipeline to obtain predicted action & class confidence.
    3. Calculates local reasoning features.
    """
    comp = db.query(models.Component).filter_by(id=component_id).first()
    if not comp:
        raise ValueError(f"Component {component_id} not found.")

    pipeline, metadata = get_recommender_model()

    # Extract 18-dim feature vector
    feat_dict = extract_features_for_component(db, component_id, graph)
    input_df = pd.DataFrame([feat_dict])[FEATURE_COLUMNS]

    # Run inference
    pred_action = str(pipeline.predict(input_df)[0])
    probabilities = pipeline.predict_proba(input_df)[0]
    classes = list(pipeline.classes_)

    confidence = 0.5
    if pred_action in classes:
        action_idx = classes.index(pred_action)
        confidence = round(float(probabilities[action_idx]), 3)

    reasoning = derive_reasoning_features(feat_dict, pred_action)

    comp_name = comp.name or component_id
    comp_type = comp.type.value if hasattr(comp.type, "value") else str(comp.type)

    return {
        "resource_id": component_id,
        "resource_name": comp_name,
        "resource_type": comp_type,
        "recommended_action": pred_action,
        "confidence": confidence,
        "reasoning_features": reasoning,
        "is_trained_model": True,
        "model_type": metadata.get("model_type", "RandomForestClassifier"),
        "model_timestamp": metadata.get("trained_at"),
        "raw_features": feat_dict
    }


def predict_all_components(db: Session) -> List[Dict[str, Any]]:
    """
    Executes model inference across all components registered in the Digital Twin.
    """
    state = db.query(models.TwinState).filter_by(id=1).first()
    mode = state.mode if state else None

    graph = simulation.build_graph(db, mode=mode)
    if mode == "manual":
        components = db.query(models.Component).filter_by(discovery_source="manual").all()
    elif mode in ["live", "demo"]:
        components = db.query(models.Component).filter(models.Component.discovery_source.in_(["aws_api", "hybrid", "aws_synthetic"])).all()
    else:
        components = db.query(models.Component).all()

    results = []

    for c in components:
        # We focus recommendations on operational resources (servers, dbs, ALBs, storage)
        ctype = c.type.value if hasattr(c.type, "value") else str(c.type)
        if ctype in ["server", "database", "load_balancer", "storage", "application"]:
            try:
                rec = predict_component_action(c.id, db, graph)
                results.append(rec)
            except Exception as e:
                logger.warning("Failed to generate recommendation for %s: %s", c.id, str(e))

    return results
