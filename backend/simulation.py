import networkx as nx
import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
import models

logger = logging.getLogger("infratwin.simulation")

def build_graph(db: Session, mode: Optional[str] = None) -> nx.DiGraph:
    G = nx.DiGraph()
    state = db.query(models.TwinState).filter_by(id=1).first()
    if mode is None and state:
        mode = state.mode

    if mode == "manual":
        components = db.query(models.Component).filter_by(discovery_source="manual").all()
        dependencies = db.query(models.Dependency).filter_by(source="manual").all()
    elif mode in ["live", "demo"]:
        components = db.query(models.Component).filter(models.Component.discovery_source.in_(["aws_api", "hybrid", "aws_synthetic", "proposed"])).all()
        dependencies = db.query(models.Dependency).filter(models.Dependency.source.in_(["aws_api", "hybrid", "aws_synthetic", "proposed"])).all()
    else:
        components = db.query(models.Component).all()
        dependencies = db.query(models.Dependency).all()

    for c in components:
        ctype = c.type.value if hasattr(c.type, "value") else str(c.type)
        cenv = c.environment.value if hasattr(c.environment, "value") else str(c.environment)
        ccrit = c.criticality.value if hasattr(c.criticality, "value") else str(c.criticality)
        cstat = c.status.value if hasattr(c.status, "value") else str(c.status)
        G.add_node(c.id, **{
            "name": c.name,
            "type": ctype,
            "environment": cenv,
            "criticality": ccrit,
            "cost_per_month": float(c.cost_per_month or 0.0),
            "status": cstat,
            "discovery_source": getattr(c, "discovery_source", "manual")
        })
        
    for d in dependencies:
        src = getattr(d, "source_component_id", None) or getattr(d, "source_id", None)
        tgt = getattr(d, "target_component_id", None) or getattr(d, "target_id", None)
        rel = d.relationship_type
        if hasattr(rel, "value"):
            rel = rel.value
        crit = d.criticality.value if hasattr(d.criticality, "value") else str(d.criticality)
        if src and tgt:
            G.add_edge(src, tgt, relationship=rel, criticality=crit)
        
    return G


def simulate_change(
    db: Session,
    target_component_id: str,
    change_action: Optional[str] = "migrate",
    destination_env: Optional[str] = None,
    use_ml_recommendation: bool = False
) -> Dict[str, Any]:
    """
    Executes an infrastructure change simulation by integrating:
    1. ML Recommendation Engine (determines the suggested operational action & confidence)
    2. Actual Dependency Graph (determines affected components & topological blast radius)
    3. Deterministic Simulation Engine (computes risk, downtime, cost impact, and warnings)
    
    All numerical risk and impact calculations are 100% deterministic code based on the graph.
    """
    G = build_graph(db)
    
    if target_component_id not in G:
        raise ValueError(f"Component {target_component_id} not found in graph.")
        
    target_node = G.nodes[target_component_id]

    # --- Step 1: Determine Action (ML Recommendation vs Manual Action) ---
    recommended_action = None
    ml_confidence = None
    ml_reasoning = None

    try:
        from ml import recommender
        ml_pred = recommender.predict_component_action(target_component_id, db, G)
        recommended_action = ml_pred.get("recommended_action")
        ml_confidence = ml_pred.get("confidence")
        ml_reasoning = ml_pred.get("reasoning_features", [])
    except Exception as e:
        logger.warning("ML recommender unavailable during simulation: %s", str(e))

    # If ML was requested or action is auto/empty, adopt the ML-recommended action
    if use_ml_recommendation or change_action in ["auto", "ml", "ML", None, ""]:
        resolved_action = recommended_action or "SCALE_COMPUTE"
    else:
        resolved_action = change_action

    # --- Step 2: Determine Blast Radius from Actual Dependency Graph ---
    # Upstream dependents (services that depend on target_component_id)
    dependents = set(nx.ancestors(G, target_component_id))
    # Downstream dependencies (services that target_component_id depends upon)
    dependencies = set(nx.descendants(G, target_component_id))
    
    affected_components = list(dependents.union(dependencies))
    blast_radius = len(affected_components)

    # --- Step 3: Deterministic Risk, Downtime & Cost Calculation via Dedicated Engines ---
    import risk_engine, cost_engine, downtime_engine

    # Cross-environment boundary detection (if migration action)
    cross_env_risks = 0
    if resolved_action in ["migrate", "MIGRATE"] and destination_env:
        for comp_id in affected_components:
            comp = G.nodes[comp_id]
            if comp.get("environment") != destination_env:
                cross_env_risks += 1

    state = db.query(models.TwinState).filter_by(id=1).first()
    comp_record = db.query(models.Component).filter_by(id=target_component_id).first()
    is_manual = (state and state.mode == "manual") or ((comp_record and getattr(comp_record, "discovery_source", None) == "manual") if comp_record else False)
    assumptions = (comp_record.metadata_col or {}).get("assumptions", {}) if comp_record else {}

    # Fetch latest metrics for target component if available
    latest_metric = db.query(models.MetricSnapshot).filter_by(resource_id=target_component_id)\
        .order_by(models.MetricSnapshot.timestamp.desc()).first()

    cpu_val = latest_metric.cpu if (latest_metric and latest_metric.cpu is not None) else assumptions.get("cpu", comp_record.cpu if comp_record else None)
    mem_val = latest_metric.memory if (latest_metric and latest_metric.memory is not None) else assumptions.get("memory", comp_record.memory if comp_record else None)
    lat_val = latest_metric.latency if (latest_metric and latest_metric.latency is not None) else assumptions.get("latency")
    err_val = latest_metric.error_rate if (latest_metric and latest_metric.error_rate is not None) else assumptions.get("error_rate")

    metric_dict = {
        "cpu": cpu_val,
        "memory": mem_val,
        "latency": lat_val,
        "error_rate": err_val,
    } if (latest_metric or assumptions or (comp_record and (comp_record.cpu is not None or comp_record.memory is not None))) else None

    # Deterministic multi-factor risk assessment
    total_components_count = len(G.nodes)
    affected_nodes_list = [G.nodes[cid] for cid in affected_components]
    risk_assessment = risk_engine.calculate_risk_assessment(
        target_node=target_node,
        action=resolved_action,
        affected_nodes=affected_nodes_list,
        total_components_count=total_components_count,
        metrics=metric_dict,
        destination_env=destination_env
    )
    risk_score = risk_assessment["risk_score"]
    risk_level = risk_assessment["risk_level"]
    risk_factors = risk_assessment["risk_factors"]

    # Deterministic AWS pricing cost impact
    cost_breakdown = cost_engine.calculate_cost_impact(target_node, resolved_action)
    cost_impact = cost_breakdown.cost_impact

    # Deterministic AWS operational downtime estimation
    downtime_estimate = downtime_engine.calculate_downtime_estimate(target_node, resolved_action)
    downtime_min = downtime_estimate.estimated_downtime_minutes

    # Generate critical warnings based on blast radius, dependencies, and action
    critical_warnings = []
    if cross_env_risks > 0:
        critical_warnings.append(f"{cross_env_risks} cross-environment dependency boundary crossing(s) detected.")
    if resolved_action == "SCALE_COMPUTE":
        critical_warnings.append(
            f"Compute resize on {target_node['name']} requires instance reboot ({downtime_min}m). {len(dependents)} upstream dependent(s) may experience transient connection resets."
        )
    elif resolved_action == "EXPAND_STORAGE":
        critical_warnings.append(
            f"Storage capacity expansion on {target_node['name']}; volume performance will optimize online without extended downtime."
        )
    elif resolved_action == "OPTIMIZE_IDLE_RESOURCE":
        critical_warnings.append(
            f"Downsizing underutilized resource {target_node['name']} will save approximately ${abs(cost_impact):.2f}/month."
        )
    elif resolved_action == "REDUNDANCY_RISK":
        critical_warnings.append(
            f"Single Point of Failure (SPOF) on critical component {target_node['name']}. Unplanned outage directly threatens {len(dependents)} service(s)."
        )
    elif resolved_action in ["INVESTIGATE_DATABASE_BOTTLENECK", "INVESTIGATE_LATENCY_ERROR"]:
        critical_warnings.append(
            f"Active performance degradation on {target_node['name']}. Review downstream target health descriptions."
        )

    affected_details = [
        {
            "id": cid,
            "name": G.nodes[cid].get("name", cid),
            "type": G.nodes[cid].get("type", "unknown"),
            "criticality": G.nodes[cid].get("criticality", "medium"),
            "environment": G.nodes[cid].get("environment", "unknown")
        }
        for cid in affected_components
    ]

    result = {
        "target_component_id": target_component_id,
        "target_component": target_node["name"],
        "target_component_type": target_node.get("type", "unknown"),
        "action": resolved_action,
        "change_action": resolved_action,
        "recommended_action": recommended_action,
        "destination": destination_env,
        "affected_count": blast_radius,
        "blast_radius": blast_radius,
        "affected_components": affected_components,
        "affected_components_details": affected_details,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "risk_factors": [rf.model_dump() if hasattr(rf, "model_dump") else rf for rf in risk_factors],
        "estimated_downtime_minutes": downtime_min,
        "downtime_estimate": downtime_estimate.model_dump() if hasattr(downtime_estimate, "model_dump") else downtime_estimate,
        "cost_delta_monthly": cost_impact,
        "cost_impact": cost_impact,
        "cost_breakdown": cost_breakdown.model_dump() if hasattr(cost_breakdown, "model_dump") else cost_breakdown,
        "critical_flags": critical_warnings,
        "ml_confidence": ml_confidence,
        "ml_reasoning_features": ml_reasoning,
        "environment_source": "manual" if is_manual else "aws_api",
        "is_manual": is_manual,
        "configured_assumptions": assumptions
    }
    
    # AI Explanation Layer (Gemini converts authoritative data into human explanation)
    try:
        import ai_engine
        explanation, recommendation, structured = ai_engine.generate_explanation(result)
        result["ai_explanation"] = explanation
        result["ai_recommendation"] = recommendation
        result["structured_explanation"] = structured
    except Exception as e:
        logger.warning("AI explanation generation encountered issue: %s", str(e))
        result["ai_explanation"] = None
        result["ai_recommendation"] = None
        result["structured_explanation"] = None
    
    return result
