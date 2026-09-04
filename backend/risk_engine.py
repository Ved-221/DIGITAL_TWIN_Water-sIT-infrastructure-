import logging
from typing import Dict, Any, List, Set
from schemas import RiskFactor

logger = logging.getLogger("infratwin.risk_engine")

def calculate_risk_assessment(
    target_node: Dict[str, Any],
    action: str,
    affected_nodes: List[Dict[str, Any]],
    total_components_count: int,
    metrics: Dict[str, Any] = None,
    destination_env: str = None
) -> Dict[str, Any]:
    """
    Computes a transparent, multi-factor risk assessment for an infrastructure change.
    Never uses arbitrary random numbers or opaque heuristic additions.
    Returns:
    - risk_score: int (0-100)
    - risk_level: str ("LOW", "MEDIUM", "HIGH", "CRITICAL")
    - risk_factors: List[RiskFactor] with clear explanation for each point scored
    """
    risk_score = 0
    factors: List[RiskFactor] = []

    # 1. Target Component Criticality Factor (Up to 30 points)
    crit = target_node.get("criticality", "medium")
    if hasattr(crit, "value"):
        crit = crit.value
    crit = str(crit).lower()

    if crit == "critical":
        impact = 30
        risk_score += impact
        factors.append(RiskFactor(
            factor="Target Criticality",
            score_impact=impact,
            explanation=f"Target resource '{target_node.get('name')}' is classified as Mission-Critical (Tier 1)."
        ))
    elif crit == "high":
        impact = 20
        risk_score += impact
        factors.append(RiskFactor(
            factor="Target Criticality",
            score_impact=impact,
            explanation=f"Target resource '{target_node.get('name')}' is classified as High Priority (Tier 2)."
        ))
    elif crit == "medium":
        impact = 10
        risk_score += impact
        factors.append(RiskFactor(
            factor="Target Criticality",
            score_impact=impact,
            explanation=f"Target resource '{target_node.get('name')}' is classified as Medium Priority (Tier 3)."
        ))
    else:
        impact = 5
        risk_score += impact
        factors.append(RiskFactor(
            factor="Target Criticality",
            score_impact=impact,
            explanation=f"Target resource '{target_node.get('name')}' is classified as Low Priority (Tier 4)."
        ))

    # 2. Topological Blast Radius Factor (Up to 25 points)
    blast_radius = len(affected_nodes)
    if blast_radius > 0:
        ratio = blast_radius / max(total_components_count, 1)
        radius_pts = min(int(ratio * 20) + min(blast_radius * 2, 10), 25)
        risk_score += radius_pts
        factors.append(RiskFactor(
            factor="Topological Blast Radius",
            score_impact=radius_pts,
            explanation=f"Change impacts {blast_radius} dependent/upstream infrastructure node(s) ({round(ratio * 100, 1)}% of total estate)."
        ))

    # 3. Critical Dependencies in Blast Radius (Up to 25 points)
    critical_in_radius = [
        n for n in affected_nodes
        if str(n.get("criticality", "")).lower() in ["critical", "high"]
    ]
    if critical_in_radius:
        crit_pts = min(len(critical_in_radius) * 8, 25)
        risk_score += crit_pts
        names_sample = ", ".join([n.get("name", "Node") for n in critical_in_radius[:3]])
        factors.append(RiskFactor(
            factor="Downstream Critical Services",
            score_impact=crit_pts,
            explanation=f"{len(critical_in_radius)} critical/high-priority resource(s) lie in the dependency path ({names_sample})."
        ))

    # 4. Action Volatility & Maintenance Mechanism (Up to 15 points)
    if action in ["migrate", "MIGRATE"]:
        dest = destination_env or "cloud"
        source_env = target_node.get("environment", "")
        if hasattr(source_env, "value"):
            source_env = source_env.value
        impact = 15
        risk_score += impact
        factors.append(RiskFactor(
            factor="Cross-Environment Migration",
            score_impact=impact,
            explanation=f"Workload repositioning from {source_env} to {dest} requires network rerouting, DNS propagation, and protocol handoff."
        ))
    elif action == "SCALE_COMPUTE":
        comp_type = str(target_node.get("type", "")).lower()
        if "database" in comp_type:
            impact = 15
            risk_score += impact
            factors.append(RiskFactor(
                factor="Stateful Database Modification",
                score_impact=impact,
                explanation="Scaling compute on a stateful database instance introduces transaction queue risk during reboot/failover."
            ))
        else:
            impact = 10
            risk_score += impact
            factors.append(RiskFactor(
                factor="Instance Reboot Required",
                score_impact=impact,
                explanation="Vertical compute resize requires instance stop-modify-start maintenance window."
            ))
    elif action in ["INVESTIGATE_DATABASE_BOTTLENECK", "INVESTIGATE_LATENCY_ERROR"]:
        impact = 10
        risk_score += impact
        factors.append(RiskFactor(
            factor="Active Performance Degradation",
            score_impact=impact,
            explanation="Resource currently demonstrates active latency, error rate, or connection saturation telemetry."
        ))

    # 5. Current Telemetry Health Signals (Up to 10 points)
    if metrics:
        err_rate = metrics.get("error_rate") or 0.0
        cpu_val = metrics.get("cpu") or 0.0
        if err_rate > 2.0 or cpu_val > 85.0:
            health_pts = 10
            risk_score += health_pts
            factors.append(RiskFactor(
                factor="Elevated Operating Telemetry",
                score_impact=health_pts,
                explanation=f"Resource operating under stress: CPU={cpu_val}%, ErrorRate={err_rate}%."
            ))

    # Clamp total score between 0 and 100
    risk_score = min(max(risk_score, 5), 100)

    # Determine risk category
    if risk_score >= 75:
        risk_level = "CRITICAL"
    elif risk_score >= 55:
        risk_level = "HIGH"
    elif risk_score >= 25:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    return {
        "risk_score": risk_score,
        "risk_level": risk_level,
        "risk_factors": factors
    }
