import networkx as nx
from typing import List, Dict, Any
from sqlalchemy.orm import Session
import models

def build_graph(db: Session) -> nx.DiGraph:
    G = nx.DiGraph()
    
    components = db.query(models.Component).all()
    for c in components:
        G.add_node(c.id, **{
            "name": c.name,
            "type": c.type,
            "environment": c.environment,
            "criticality": c.criticality,
            "cost_per_month": c.cost_per_month,
            "status": c.status,
            "source_environment": c.source_environment,
        })
        
    dependencies = db.query(models.Dependency).all()
    for d in dependencies:
        G.add_edge(d.source_id, d.target_id, relationship=d.relationship_type, criticality=d.criticality)
        
    return G

def simulate_change(db: Session, target_component_id: str, change_action: str, destination_env: str = None, use_ai: bool = False) -> Dict[str, Any]:
    G = build_graph(db)
    
    if target_component_id not in G:
        raise ValueError("Component not found")
        
    target_node = G.nodes[target_component_id]
    
    # Forward and backward traversal to find blast radius
    # In a dependency graph (A depends on B), if B goes down, A is affected (reverse traversal from B)
    # If A is migrated, things A depends on (B) might experience cross-env latency (forward traversal from A)
    
    affected_components = set()
    
    # 1. Dependents (things that depend on this component)
    dependents = nx.ancestors(G, target_component_id) # A -> B, ancestors of B are A
    affected_components.update(dependents)
    
    # 2. Dependencies (things this component depends on)
    dependencies = nx.descendants(G, target_component_id) # A -> B, descendants of A are B
    affected_components.update(dependencies)
    
    # Calculate risks
    risk_score = 0
    critical_flags = []
    
    # Base risk for the component being changed
    if target_node["criticality"] == "critical":
        risk_score += 40
    elif target_node["criticality"] == "high":
        risk_score += 20
        
    # Analyze blast radius
    high_critical_affected = 0
    cross_env_risks = 0
    
    for comp_id in affected_components:
        comp = G.nodes[comp_id]
        if comp["criticality"] in ["high", "critical"]:
            high_critical_affected += 1
            
        # Check cross-environment dependency if migrating
        if change_action == "migrate" and destination_env:
            if comp["environment"] != destination_env:
                cross_env_risks += 1
                critical_flags.append(f"Cross-environment dependency with {comp['name']} ({comp['environment']})")

    risk_score += min(high_critical_affected * 10, 40)
    risk_score += min(cross_env_risks * 15, 20)
    
    # Downtime estimation (dynamic heuristic based on dependencies)
    base_downtime = 30
    if target_node["type"] in ["database", "storage"]:
        base_downtime = 120
    elif target_node["type"] in ["network", "identity"]:
        base_downtime = 60
    
    # Add 15 mins for every dependency that needs reconfiguration
    downtime_min = base_downtime + (len(affected_components) * 15)
        
    # Cost delta estimation
    cost_delta = 0
    base_cost = target_node.get("cost_per_month", 0)
    
    # Fallback dynamic cost if Cost Explorer is pending/returns 0
    if not base_cost or base_cost == 0:
        if target_node["type"] in ["database", "storage"]:
            base_cost = 850.0
        elif target_node["type"] == "server":
            base_cost = 250.0
        elif target_node["type"] == "application":
            base_cost = 500.0
        else:
            base_cost = 100.0
            
    if change_action == "migrate" and destination_env == "cloud":
        cost_delta = (base_cost * 0.15) # 15% increase for cloud migration lift-and-shift heuristic

    # SPOF Check (Very basic: if target is critical and has no siblings of same type)
    # Skipped for brevity, but could check degree.
        
    risk_level = "LOW"
    if risk_score > 75:
        risk_level = "CRITICAL"
    elif risk_score > 50:
        risk_level = "HIGH"
    elif risk_score > 25:
        risk_level = "MEDIUM"

    result = {
        "change_action": change_action,
        "target_component": target_node["name"],
        "destination": destination_env,
        "affected_count": len(affected_components),
        "affected_components": list(affected_components),
        "affected_component_names": [G.nodes[c]["name"] for c in affected_components],
        "risk_score": min(risk_score, 100),
        "risk_level": risk_level,
        "estimated_downtime_minutes": downtime_min,
        "cost_delta_monthly": cost_delta,
        "critical_flags": critical_flags
    }
    
    # By default, use AI only if in AWS env or explicitly requested
    should_run_ai = use_ai or target_node.get("source_environment", "aws") == "aws"
    
    if not should_run_ai:
        # Bypass AI/ML logic for Manual Environment
        result["financial_analysis"] = None
        result["risk_analysis"] = None
        result["architect_recommendation"] = None
    else:
        import multi_agent_system
        agent_reports = multi_agent_system.run_multi_agent_analysis(result)
        result["financial_analysis"] = agent_reports.get("financial", "Financial Analysis unavailable.")
        result["risk_analysis"] = agent_reports.get("risk", "Risk Analysis unavailable.")
        result["architect_recommendation"] = agent_reports.get("architect", "Recommendation unavailable.")
        result["recommended_actions"] = agent_reports.get("recommended_actions", [])
    
    return result
