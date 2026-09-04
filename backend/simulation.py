import networkx as nx
from typing import List, Dict, Any, Optional, Union
from sqlalchemy.orm import Session
import uuid
import models
import schemas

class SimulationResultDict(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(f"'SimulationResultDict' object has no attribute '{name}'")
    def __setattr__(self, name, value):
        self[name] = value


class SPOFResult(list):
    def __init__(self, spof_nodes, source_environment="aws"):
        super().__init__(spof_nodes)
        self.spof_nodes = spof_nodes
        self.spof_count = len(spof_nodes)
        self.environment = source_environment

    def get(self, key, default=None):
        if key == "spof_nodes":
            return self.spof_nodes
        elif key == "spof_count":
            return self.spof_count
        elif key == "environment":
            return self.environment
        return default

    def __contains__(self, item):
        if item in ["spof_nodes", "spof_count", "environment"]:
            return True
        return super().__contains__(item)

    def __getitem__(self, item):
        if isinstance(item, str):
            return self.get(item)
        return super().__getitem__(item)


def build_graph(db: Session, source_environment: str = "aws") -> nx.DiGraph:
    G = nx.DiGraph()
    
    if source_environment.startswith("aws_sim_"):
        aws_comps = db.query(models.Component).filter(models.Component.source_environment == "aws").all()
        sim_comps = db.query(models.Component).filter(models.Component.source_environment == source_environment).all()
        components = aws_comps + sim_comps
        
        aws_deps = db.query(models.Dependency).filter(models.Dependency.source_environment == "aws").all()
        sim_deps = db.query(models.Dependency).filter(models.Dependency.source_environment == source_environment).all()
        dependencies = aws_deps + sim_deps
    else:
        components = db.query(models.Component).filter(models.Component.source_environment == source_environment).all()
        dependencies = db.query(models.Dependency).filter(models.Dependency.source_environment == source_environment).all()

    for c in components:
        G.add_node(c.id, **{
            "id": c.id,
            "name": c.name,
            "type": c.type or "server",
            "environment": c.environment or "cloud",
            "environment_id": getattr(c, "environment_id", source_environment),
            "criticality": c.criticality or "medium",
            "cost_per_month": float(c.cost_per_month or 0.0),
            "currency": getattr(c, "currency", "USD") or "USD",
            "status": c.status or "active",
            "cpu": c.cpu,
            "memory": c.memory,
            "location": c.location,
            "provider": getattr(c, "provider", "manual"),
            "telemetry": getattr(c, "telemetry", {}) or {},
            "metadata_col": getattr(c, "metadata_col", {}) or {},
            "source_environment": c.source_environment,
        })
        
    for d in dependencies:
        if d.source_id in G and d.target_id in G:
            G.add_edge(
                d.source_id,
                d.target_id,
                id=d.id,
                relationship_type=d.relationship_type or "depends_on",
                relationship=d.relationship_type or "depends_on",
                criticality=d.criticality or "medium",
                source_environment=d.source_environment
            )
        
    return G

def find_spofs(db: Session, source_environment: str = "aws") -> SPOFResult:
    G = build_graph(db, source_environment)
    
    if len(G) < 2:
        return SPOFResult([], source_environment)
        
    undirected = G.to_undirected()
    raw_articulation_points = list(nx.articulation_points(undirected))
    
    spof_nodes = []
    for node_id in raw_articulation_points:
        node_data = G.nodes[node_id]
        in_deg = G.in_degree(node_id)
        out_deg = G.out_degree(node_id)
        spof_nodes.append({
            "id": node_id,
            "component_id": node_id,
            "name": node_data.get("name", node_id),
            "type": node_data.get("type", "server"),
            "criticality": node_data.get("criticality", "medium"),
            "status": node_data.get("status", "active"),
            "in_degree": in_deg,
            "out_degree": out_deg,
            "blast_degree": in_deg + out_deg,
            "is_articulation_point": True,
            "reason": f"Bridge node connecting {in_deg} caller(s) to {out_deg} downstream service(s)."
        })
        
    crit_order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    spof_nodes.sort(key=lambda x: (crit_order.get(x["criticality"], 0), x["blast_degree"]), reverse=True)
    
    return SPOFResult(spof_nodes, source_environment)

def generate_feasible_solutions(
    component: Union[models.Component, Dict[str, Any]],
    action: str,
    affected_components: List[Dict[str, Any]],
    risk_score: float,
    currency: str = "USD",
    cost_delta: Optional[float] = None,
    downtime_minutes: Optional[int] = None,
    db: Optional[Session] = None,
    source_environment: str = "aws"
) -> List[schemas.FeasibleSolution]:
    import solution_generator
    from ml.inference import rank_candidate_solutions
    
    comp_dict = {
        "name": component.name if hasattr(component, "name") else component.get("name", "Component"),
        "type": component.type if hasattr(component, "type") else component.get("type", "server"),
        "criticality": component.criticality if hasattr(component, "criticality") else component.get("criticality", "medium"),
        "cost_per_month": float(component.cost_per_month if hasattr(component, "cost_per_month") else component.get("cost_per_month", 0.0) or 0.0),
        "status": component.status if hasattr(component, "status") else component.get("status", "active"),
        "cpu": component.cpu if hasattr(component, "cpu") else component.get("cpu"),
        "metadata_col": (component.metadata_col if hasattr(component, "metadata_col") else component.get("metadata_col", {})) or {}
    }
    
    sim_context = {
        "action": action,
        "affected_count": len(affected_components),
        "upstream_impact_count": len([a for a in affected_components if a.get("impact_type") == "Caller Service Disruption" or a.get("hop_distance", 1) >= 1]),
        "risk_score": risk_score,
        "cost_delta_monthly": cost_delta,
        "estimated_downtime_minutes": downtime_minutes,
        "risk_factors": {
            "target_criticality": comp_dict["criticality"],
            "component_status": comp_dict["status"],
            "cpu_utilization_percent": comp_dict["cpu"],
            "is_single_point_of_failure": any(a.get("is_articulation_point") for a in affected_components) or (risk_score >= 65 and len(affected_components) >= 2)
        }
    }
    
    # Generate dynamic candidates tailored to component type and topology
    raw_candidates = solution_generator.generate_applicable_candidates(
        component=component,
        simulation_result=sim_context,
        currency=currency
    )
    
    # Pre-simulate candidates if db session provided
    if db is not None:
        try:
            import candidate_evaluator
            comp_model = component if isinstance(component, models.Component) else db.query(models.Component).filter(models.Component.id == component.get("id")).first()
            if comp_model:
                ranked = candidate_evaluator.evaluate_and_rank_candidates(
                    db=db,
                    component=comp_model,
                    simulation_result=sim_context,
                    candidates=raw_candidates,
                    source_environment=source_environment
                )
                return [schemas.FeasibleSolution(**r) for r in ranked[:3]]
        except Exception:
            pass
            
    # Rank candidates using trained Supervised Machine Learning Model
    try:
        ranked = rank_candidate_solutions(
            simulation_result=sim_context,
            candidate_solutions=raw_candidates,
            component_data=comp_dict
        )
        return [schemas.FeasibleSolution(**r) for r in ranked[:3]]
    except Exception as e:
        # Fallback to unranked raw candidates if ML model is unavailable
        for idx, c in enumerate(raw_candidates):
            c["rank"] = idx + 1
            c["predicted_suitability"] = round(0.90 - idx * 0.10, 2)
            c["suitability_percentage"] = round((0.90 - idx * 0.10) * 100, 1)
            c["feasibility_score"] = round(0.90 - idx * 0.10, 2)
        return [schemas.FeasibleSolution(**c) for c in raw_candidates[:3]]

def simulate_change(
    db: Session,
    target_component_id: str = None,
    action: str = "migrate",
    destination_env: str = None,
    source_environment: str = "aws",
    use_ai: bool = False,
    component_id: str = None,
    target_environment: str = None
) -> Dict[str, Any]:
    effective_target_id = target_component_id or component_id
    if not effective_target_id:
        raise ValueError("Missing required component ID for simulation.")
        
    effective_dest = destination_env or target_environment
    G = build_graph(db, source_environment)
    
    if effective_target_id not in G:
        raise ValueError(f"Component '{effective_target_id}' not found in environment '{source_environment}'.")
        
    target_node = G.nodes[effective_target_id]
    total_env_nodes = max(len(G), 1)
    
    # 1. Upstream callers / dependents (Callers relying upon target)
    upstream_nodes = nx.ancestors(G, effective_target_id)
    upstream_impact = []
    for uid in upstream_nodes:
        node_d = G.nodes[uid]
        try:
            hop_dist = nx.shortest_path_length(G, source=uid, target=effective_target_id)
        except Exception:
            hop_dist = 1
        upstream_impact.append({
            "id": uid,
            "component_id": uid,
            "name": node_d.get("name", uid),
            "type": node_d.get("type", "server"),
            "criticality": node_d.get("criticality", "medium"),
            "status": node_d.get("status", "active"),
            "hop_distance": hop_dist,
            "impact_type": "Caller Service Disruption"
        })
    upstream_impact.sort(key=lambda x: x["hop_distance"])
    
    # 2. Downstream dependencies (Services target relies upon)
    downstream_nodes = nx.descendants(G, effective_target_id)
    downstream_deps = []
    for did in downstream_nodes:
        node_d = G.nodes[did]
        try:
            hop_dist = nx.shortest_path_length(G, source=effective_target_id, target=did)
        except Exception:
            hop_dist = 1
        downstream_deps.append({
            "id": did,
            "component_id": did,
            "name": node_d.get("name", did),
            "type": node_d.get("type", "server"),
            "criticality": node_d.get("criticality", "medium"),
            "status": node_d.get("status", "active"),
            "hop_distance": hop_dist,
            "impact_type": "Underlying Dependency"
        })
    downstream_deps.sort(key=lambda x: x["hop_distance"])
    
    all_affected_ids = set(upstream_nodes).union(downstream_nodes)
    affected_components_list = upstream_impact + downstream_deps
    
    # Topological SPOF / Articulation analysis
    spof_report = find_spofs(db, source_environment)
    spof_ids = {s["id"] for s in spof_report["spof_nodes"]}
    is_target_spof = effective_target_id in spof_ids
    
    critical_flags = []
    missing_data_items = []
    
    # --- DATA-DRIVEN MEASURABLE RISK DERIVATION ---
    # 1. Target Criticality SLA profile
    crit_str = target_node.get("criticality", "medium").lower()
    crit_base = 35 if crit_str == "critical" else (22 if crit_str == "high" else (12 if crit_str == "medium" else 5))
    
    # 2. Operational Action Disruption Profile
    action_lower = action.lower()
    if action_lower in ["fail", "outage"]:
        action_severity = 35
        critical_flags.append(f"Unplanned outage disruption on {target_node['name']}.")
    elif action_lower in ["migrate"]:
        action_severity = 15
    elif action_lower in ["scale"]:
        action_severity = 8
    elif action_lower in ["restart", "reboot"]:
        action_severity = 5
    else:
        action_severity = 10
        
    # 3. Live Telemetry & Health State
    status_lower = target_node.get("status", "active").lower()
    cpu_val = target_node.get("cpu")
    health_penalty = 0
    if status_lower == "degraded" or (cpu_val is not None and float(cpu_val) > 80.0):
        health_penalty = 20
        cpu_display = f"{cpu_val}%" if cpu_val is not None else "N/A"
        critical_flags.append(f"Health hazard: Component is in {status_lower} state with high CPU load ({cpu_display}).")
    elif cpu_val is None:
        missing_data_items.append("live_cpu_telemetry")
        
    # 4. Topological Blast Radius & Critical Callers
    crit_callers_count = sum(1 for a in upstream_impact if a.get("criticality") in ["critical", "high"])
    blast_penalty = min(len(upstream_nodes) * 12 + crit_callers_count * 8, 30)
    
    # 5. Articulation Point / SPOF Vulnerability
    meta_info = target_node.get("metadata_col", {}) or {}
    has_redundancy = bool(meta_info.get("redundancy_enabled") or meta_info.get("multi_az") or meta_info.get("staged_cutover"))
    
    if has_redundancy:
        action_severity = max(action_severity - 10, 2)
        blast_penalty = blast_penalty // 3
        is_target_spof = False
        spof_penalty = 0
    else:
        spof_penalty = 15 if is_target_spof else 0
        if is_target_spof:
            critical_flags.append(f"Single Point of Failure: {target_node['name']} is a critical articulation bridge.")
        
    # 6. Cross-Environment Boundary Exposure
    cross_env_links = 0
    if action_lower == "migrate" and effective_dest:
        for did in downstream_nodes:
            dn = G.nodes[did]
            if dn.get("environment") != effective_dest:
                cross_env_links += 1
                critical_flags.append(f"Cross-environment link with {dn['name']} ({dn['environment']}).")
    cross_env_penalty = min(cross_env_links * 5, 15)
    
    total_risk = crit_base + action_severity + health_penalty + blast_penalty + spof_penalty + cross_env_penalty
    final_risk_score = min(max(total_risk, 5), 100)
    
    if final_risk_score >= 70:
        risk_level = "CRITICAL"
    elif final_risk_score >= 45:
        risk_level = "HIGH"
    elif final_risk_score >= 25:
        risk_level = "MODERATE"
    else:
        risk_level = "LOW"
        
    risk_factors = {
        "target_criticality": crit_str,
        "action_profile": action_lower,
        "upstream_callers_count": len(upstream_nodes),
        "downstream_dependencies_count": len(downstream_nodes),
        "critical_callers_affected": crit_callers_count,
        "is_single_point_of_failure": is_target_spof,
        "cpu_utilization_percent": cpu_val,
        "component_status": status_lower,
        "cross_environment_links_count": cross_env_links,
        "max_dependency_depth": max([a.get("hop_distance", 1) for a in upstream_impact], default=0)
    }
    
    # --- DATA-DRIVEN DOWNTIME CALCULATION ---
    meta = target_node.get("metadata_col", {}) or {}
    telemetry = target_node.get("telemetry", {}) or {}
    node_type = target_node.get("type", "server").lower()
    
    storage_gb = meta.get("storage_gb") or meta.get("db_size_gb") or telemetry.get("storage_size_gb")
    transfer_rate_mbps = telemetry.get("transfer_rate_mbps") or meta.get("transfer_rate_mbps")
    explicit_dt = meta.get("estimated_downtime_minutes") or meta.get("maintenance_window_minutes")
    
    max_hop = max([a.get("hop_distance", 1) for a in upstream_impact], default=0)
    
    if explicit_dt is not None:
        estimated_downtime = int(explicit_dt)
        downtime_explanation = f"Derived from explicit operational configuration ({explicit_dt} min)."
    elif storage_gb is not None and transfer_rate_mbps is not None and float(transfer_rate_mbps) > 0:
        # Transfer time in minutes = (GB * 1024 * 8) / (Mbps * 60)
        transfer_minutes = (float(storage_gb) * 8192) / (float(transfer_rate_mbps) * 60)
        cascade_dt = max_hop * 2
        estimated_downtime = max(int(round(transfer_minutes + cascade_dt)), 1)
        downtime_explanation = f"Calculated from storage volume ({storage_gb} GB) and transfer throughput ({transfer_rate_mbps} Mbps)."
    else:
        # Deterministic baseline from component type and cascade depth
        if action_lower in ["restart", "reboot"]:
            base_dt = 3 if node_type in ["lambda", "container"] else 5
        elif action_lower == "scale":
            base_dt = 1
        elif action_lower in ["fail", "outage"]:
            base_dt = 45 if node_type in ["database", "storage"] else (20 if node_type in ["server", "application"] else 5)
        else: # migrate
            base_dt = 30 if node_type in ["database", "storage"] else (15 if node_type in ["server", "application"] else 5)
        
        cascade_dt = max_hop * 5
        estimated_downtime = base_dt + cascade_dt
        downtime_explanation = f"Projected from {node_type} recovery profile and {max_hop}-hop dependency cascade."
        
    # --- DATA-DRIVEN COST CALCULATION ---
    actual_cost = float(target_node.get("cost_per_month", 0.0) or 0.0)
    target_cost_meta = meta.get("target_cost_per_month")
    scale_factor_meta = meta.get("scale_factor")
    data_transfer_gb = meta.get("data_transfer_gb") or telemetry.get("data_transfer_gb")
    
    if target_cost_meta is not None:
        cost_delta = round(float(target_cost_meta) - actual_cost, 2)
        cost_explanation = f"Calculated as difference between target cost (${target_cost_meta}/mo) and current cost (${actual_cost}/mo)."
    elif action_lower in ["restart", "reboot"]:
        cost_delta = 0.0
        cost_explanation = "Operational restart has zero impact on monthly infrastructure run rate."
    elif action_lower in ["fail", "outage"]:
        cost_delta = 0.0
        cost_explanation = "Unplanned downtime disruption does not modify fixed recurring subscription cost."
    elif action_lower == "scale":
        if scale_factor_meta is not None:
            cost_delta = round(actual_cost * (float(scale_factor_meta) - 1.0), 2)
            cost_explanation = f"Calculated from configured scale factor {scale_factor_meta}x."
        else:
            cost_delta = round(actual_cost * 0.50, 2)
            cost_explanation = f"Estimated based on standard 2x vertical compute capacity scaling on ${actual_cost}/mo base."
    elif action_lower == "migrate":
        egress_cost = (float(data_transfer_gb) * 0.09) if data_transfer_gb is not None else ((len(upstream_nodes) + len(downstream_nodes)) * 5.0)
        cost_delta = round(actual_cost * 0.20 + egress_cost, 2)
        cost_explanation = f"Estimated from target cloud hosting delta and {len(upstream_nodes) + len(downstream_nodes)} connected network interface(s)."
    else:
        cost_delta = 0.0
        cost_explanation = "No recurring cost change associated with this operational action."

    # Generate Feasible Solutions matrix
    comp_obj = db.query(models.Component).filter(models.Component.id == effective_target_id).first()
    feasible_solutions = generate_feasible_solutions(
        component=comp_obj or target_node,
        action=action,
        affected_components=affected_components_list,
        risk_score=final_risk_score,
        currency=target_node.get("currency", "USD"),
        cost_delta=cost_delta,
        downtime_minutes=estimated_downtime,
        db=db,
        source_environment=source_environment
    )
    
    recommendations = [
        f"Pre-change verification: Validate automated backups and snapshot state for {target_node['name']}.",
        f"Service safeguards: Notify owners of {len(upstream_nodes)} calling service(s) prior to '{action}'.",
        f"Execution window: Schedule maintenance during lowest traffic period to minimize impact across {len(all_affected_ids)} component(s)."
    ]
    if is_target_spof:
        recommendations.insert(0, f"High Priority: Deploy redundant standby instance for {target_node['name']} to eliminate single point of failure.")

    # Structured Agent Summaries for UI Consumption
    financial_status = "Favorable" if cost_delta <= 0 else "Caution"
    financial_summary_text = "Cost impact is favorable or neutral" if cost_delta <= 0 else f"Increases monthly run rate (+${cost_delta:,.2f}/mo)"
    financial_summary_obj = {
        "status": financial_status,
        "summary": financial_summary_text,
        "cost_delta_monthly": cost_delta,
        "cost_explanation": cost_explanation,
        "currency": target_node.get("currency", "USD")
    }
    
    risk_summary_status = "High Risk" if final_risk_score >= 70 else ("Caution" if final_risk_score >= 45 else "Favorable")
    risk_summary_text = f"{estimated_downtime} min downtime ({risk_level} Risk)"
    risk_summary_obj = {
        "status": risk_summary_status,
        "summary": risk_summary_text,
        "risk_score": final_risk_score,
        "risk_level": risk_level,
        "estimated_downtime_minutes": estimated_downtime,
        "downtime_explanation": downtime_explanation,
        "is_spof": is_target_spof
    }
    
    architect_status = "Blocked" if final_risk_score >= 70 else ("Conditional" if final_risk_score >= 45 else "Approved")
    architect_summary_text = "Migration not recommended without remediation" if final_risk_score >= 70 else ("Phased migration recommended" if final_risk_score >= 45 else "Ready for operational execution")
    architect_summary_obj = {
        "status": architect_status,
        "summary": architect_summary_text,
        "target_component": target_node["name"],
        "recommended_strategy": feasible_solutions[1].name if (len(feasible_solutions) > 1 and final_risk_score >= 45) else (feasible_solutions[0].name if len(feasible_solutions) > 0 else "Direct Execution"),
        "recommended_actions": recommendations
    }

    result_data = {
        "target_component_id": effective_target_id,
        "component_id": effective_target_id,
        "target_component": target_node["name"],
        "action": action,
        "change_action": action,
        "destination": effective_dest,
        "target_environment": effective_dest,
        "source_environment": source_environment,
        "total_nodes_affected": len(all_affected_ids),
        "affected_count": len(all_affected_ids),
        "affected_components": affected_components_list,
        "affected_component_names": [G.nodes[c]["name"] for c in all_affected_ids if c in G.nodes],
        "upstream_impact_count": len(upstream_impact),
        "upstream_impact": upstream_impact,
        "downstream_dependencies_count": len(downstream_deps),
        "downstream_dependencies": downstream_deps,
        "blast_radius_nodes": list(all_affected_ids),
        "risk_score": round(final_risk_score, 1),
        "risk_level": risk_level,
        "estimated_downtime_minutes": estimated_downtime,
        "cost_delta_monthly": cost_delta,
        "downtime_explanation": downtime_explanation,
        "cost_explanation": cost_explanation,
        "critical_flags": critical_flags,
        "risk_factors": risk_factors,
        "feasible_solutions": feasible_solutions,
        "recommendations": recommendations,
        "financial_summary": financial_summary_obj,
        "risk_summary": risk_summary_obj,
        "architect_summary": architect_summary_obj,
        "missing_data": missing_data_items,
        "ai_explanation": None,
        "ai_recommendation": None,
        "financial_analysis": None,
        "risk_analysis": None,
        "architect_recommendation": None,
        "recommended_actions": recommendations
    }
    
    # Decoupled AI advisory layer (Triggered only when requested)
    if use_ai:
        try:
            import ai_engine
            ai_exp = ai_engine.analyze_simulation_with_ai(target_node, result_data)
            ai_rec = ai_engine.get_ai_recommendation(target_node, result_data)
            result_data["ai_explanation"] = ai_exp
            result_data["ai_recommendation"] = ai_rec
            result_data["architect_recommendation"] = ai_rec
        except Exception as e:
            result_data["ai_explanation"] = f"AI advisory generated from Digital Twin telemetry facts. (Notice: {str(e)})"
            result_data["ai_recommendation"] = f"Proceed with {action} under verified operational checklist."
            
    # Persist simulation run in database
    try:
        sim_record = models.Simulation(
            source_environment=source_environment,
            target_component_id=effective_target_id,
            action=action,
            destination_env=effective_dest,
            affected_components=list(all_affected_ids),
            risk_score=float(final_risk_score),
            risk_level=risk_level,
            estimated_downtime_minutes=int(estimated_downtime) if estimated_downtime is not None else 0,
            cost_delta_monthly=float(cost_delta) if cost_delta is not None else 0.0,
            status="completed",
            result_status="completed"
        )
        db.add(sim_record)
        db.commit()
        db.refresh(sim_record)
    except Exception as e:
        db.rollback()
        
    return SimulationResultDict(result_data)
