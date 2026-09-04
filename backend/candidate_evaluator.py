import uuid
from typing import List, Dict, Any, Optional
import networkx as nx
from sqlalchemy.orm import Session
import models
from simulation import build_graph, find_spofs
from ml.inference import rank_candidate_solutions

def evaluate_and_rank_candidates(
    db: Session,
    component: models.Component,
    simulation_result: Dict[str, Any],
    candidates: List[Dict[str, Any]],
    source_environment: str,
    primary_objective: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Pre-simulates EVERY candidate solution on an isolated in-memory graph clone.
    Calculates actual risk, downtime, cost, blast radius, SPOF count, and objective feasibility.
    Then feeds features into the trained Random Forest ML ranker.
    """
    b_score = float(simulation_result.get("risk_score", 0.0))
    b_dt = simulation_result.get("estimated_downtime_minutes") or 0
    b_blast = int(simulation_result.get("affected_count", len(simulation_result.get("affected_components", []))))
    b_spof = bool(simulation_result.get("risk_factors", {}).get("is_single_point_of_failure", False))
    b_cost_delta = float(simulation_result.get("cost_delta_monthly") or 0.0)
    
    # 1. Determine Primary Objective dynamically
    if not primary_objective:
        if b_spof:
            primary_objective = "remove_spof"
        elif b_score >= 60:
            primary_objective = "reduce_risk"
        elif b_dt >= 15:
            primary_objective = "reduce_downtime"
        elif b_blast >= 3:
            primary_objective = "reduce_blast_radius"
        else:
            primary_objective = "improve_resilience"

    evaluated_candidates = []
    
    for cand in candidates:
        strat_type = cand.get("strategy_type", "direct_lift_shift")
        
        # 2. Build in-memory graph clone
        G_cand = build_graph(db, source_environment)
        target_id = component.id
        
        if target_id not in G_cand:
            evaluated_candidates.append(cand)
            continue
            
        target_data = dict(G_cand.nodes[target_id])
        target_meta = dict(target_data.get("metadata_col", {}) or {})
        
        # 3. Apply candidate topological mutations in memory to G_cand
        cand_mutations = []
        extra_monthly_cost = 0.0
        
        if strat_type in ["multi_az_modernize", "multi_az_standby", "redundancy"]:
            alb_id = f"alb-{uuid.uuid4().hex[:6]}"
            standby_id = f"standby-{uuid.uuid4().hex[:6]}"
            extra_monthly_cost = 25.0 + float(component.cost_per_month or 0.0)
            
            target_meta["multi_az"] = True
            target_meta["redundancy_enabled"] = True
            target_meta["estimated_downtime_minutes"] = 0
            G_cand.nodes[target_id]["metadata_col"] = target_meta
            G_cand.nodes[target_id]["criticality"] = "medium"
            
            G_cand.add_node(alb_id, name=f"ALB-{component.name}", type="application", criticality="high", status="active", cost_per_month=25.0)
            G_cand.add_node(standby_id, name=f"{component.name}-Standby-AZ2", type=component.type, criticality="medium", status="active", cost_per_month=component.cost_per_month)
            
            G_cand.add_edge(alb_id, target_id, relationship_type="routes_traffic")
            G_cand.add_edge(alb_id, standby_id, relationship_type="routes_traffic")
            
            # Reroute callers in G_cand
            predecessors = list(G_cand.predecessors(target_id))
            for p in predecessors:
                if p != alb_id:
                    G_cand.remove_edge(p, target_id)
                    G_cand.add_edge(p, alb_id, relationship_type="routes_traffic")
                    
            cand_mutations.append("Injected Application Load Balancer and Multi-AZ Standby")

        elif strat_type in ["read_replica_offload", "replication"]:
            replica_id = f"replica-{uuid.uuid4().hex[:6]}"
            extra_monthly_cost = round(float(component.cost_per_month or 50.0) * 0.50, 2)
            
            target_meta["read_replica_enabled"] = True
            G_cand.nodes[target_id]["metadata_col"] = target_meta
            
            G_cand.add_node(replica_id, name=f"{component.name}-ReadReplica", type="database", criticality="medium", status="active", cost_per_month=extra_monthly_cost)
            G_cand.add_edge(replica_id, target_id, relationship_type="replicates_from")
            cand_mutations.append("Provisioned Dedicated Read Replica")

        elif strat_type in ["dependency_circuit_breaker", "dependency_decoupling"]:
            queue_id = f"queue-{uuid.uuid4().hex[:6]}"
            extra_monthly_cost = 15.0
            
            G_cand.add_node(queue_id, name=f"Queue-Buffer-{component.name}", type="application", criticality="medium", status="active", cost_per_month=15.0)
            G_cand.add_edge(queue_id, target_id, relationship_type="buffers_to")
            
            predecessors = list(G_cand.predecessors(target_id))
            for p in predecessors:
                if p != queue_id:
                    G_cand.remove_edge(p, target_id)
                    G_cand.add_edge(p, queue_id, relationship_type="buffers_to")
            cand_mutations.append("Injected Asynchronous Message Buffer")

        elif strat_type in ["phased_blue_green", "staged_migration"]:
            shadow_id = f"shadow-{uuid.uuid4().hex[:6]}"
            extra_monthly_cost = float(component.cost_per_month or 0.0)
            
            target_meta["staged_cutover"] = True
            target_meta["estimated_downtime_minutes"] = 0
            G_cand.nodes[target_id]["metadata_col"] = target_meta
            
            G_cand.add_node(shadow_id, name=f"{component.name}-Shadow-Target", type=component.type, criticality=component.criticality, status="active", cost_per_month=component.cost_per_month)
            G_cand.add_edge(shadow_id, target_id, relationship_type="syncs_with")
            cand_mutations.append("Provisioned Shadow Target with Live Sync")

        elif strat_type in ["scale_up", "scale_out", "scale"]:
            extra_monthly_cost = round(float(component.cost_per_month or 40.0) * 0.50, 2)
            G_cand.nodes[target_id]["cpu"] = (component.cpu or 2) * 2
            G_cand.nodes[target_id]["memory"] = (component.memory or 4) * 2
            cand_mutations.append("Doubled Compute and RAM capacity")

        # 4. Deterministically simulate change impact on in-memory G_cand
        try:
            upstream_nodes = list(nx.ancestors(G_cand, target_id))
        except Exception:
            upstream_nodes = []
        try:
            downstream_nodes = list(nx.descendants(G_cand, target_id))
        except Exception:
            downstream_nodes = []
            
        cand_blast = len(set(upstream_nodes).union(downstream_nodes))
        
        # Articulation / SPOF in candidate graph
        undirected = G_cand.to_undirected()
        cand_articulation = list(nx.articulation_points(undirected)) if len(G_cand) >= 2 else []
        cand_is_spof = target_id in cand_articulation and not (target_meta.get("redundancy_enabled") or target_meta.get("multi_az"))
        
        # Risk derivation
        crit_str = str(G_cand.nodes[target_id].get("criticality", "medium")).lower()
        crit_base = 35 if crit_str == "critical" else (22 if crit_str == "high" else (12 if crit_str == "medium" else 5))
        
        has_redundancy = bool(target_meta.get("redundancy_enabled") or target_meta.get("multi_az") or target_meta.get("staged_cutover"))
        if has_redundancy:
            action_sev = 2
            blast_pen = min(len(upstream_nodes) * 4, 10)
            spof_pen = 0
        else:
            action_sev = 15
            blast_pen = min(len(upstream_nodes) * 12, 30)
            spof_pen = 15 if cand_is_spof else 0
            
        cand_risk = min(max(crit_base + action_sev + blast_pen + spof_pen, 5), 100)
        cand_dt = 0 if has_redundancy else (cand.get("estimated_downtime_minutes") or b_dt)
        cand_cost = b_cost_delta + extra_monthly_cost
        
        # 5. Objective evaluation & Tradeoffs
        if primary_objective == "remove_spof":
            obj_met = not cand_is_spof
            obj_result = "SPOF successfully eliminated via redundancy" if obj_met else "SPOF condition remains"
        elif primary_objective == "reduce_risk":
            obj_met = cand_risk < b_score
            obj_result = f"Risk reduced by {round(b_score - cand_risk, 1)} pts" if obj_met else "No risk reduction"
        elif primary_objective == "reduce_downtime":
            obj_met = cand_dt < b_dt
            obj_result = f"Downtime reduced by {b_dt - cand_dt}m" if obj_met else "Downtime unchanged"
        elif primary_objective == "reduce_blast_radius":
            obj_met = cand_blast <= b_blast
            obj_result = f"Blast radius contained to {cand_blast} nodes" if obj_met else "Blast radius expanded"
        else:
            obj_met = cand_risk <= b_score
            obj_result = "Resilience enhanced" if obj_met else "Baseline preserved"

        tradeoffs = []
        if extra_monthly_cost > 0:
            tradeoffs.append(f"Increases monthly cost by +${extra_monthly_cost:,.2f}/mo")
        if cand_dt > 0 and cand_dt >= b_dt:
            tradeoffs.append(f"Requires a {cand_dt}-minute maintenance window")
        if cand.get("complexity", 1) >= 2:
            tradeoffs.append("Requires multi-node replication synchronization")

        cand_evaluated = {
            **cand,
            "pre_simulated": True,
            "candidate_risk_score": float(cand_risk),
            "candidate_downtime_minutes": int(cand_dt),
            "candidate_cost_delta": float(cand_cost),
            "candidate_blast_radius": int(cand_blast),
            "candidate_is_spof": bool(cand_is_spof),
            "primary_objective": primary_objective,
            "objective_met": obj_met,
            "objective_result": obj_result,
            "tradeoffs": tradeoffs,
            "mutations": cand_mutations
        }
        evaluated_candidates.append(cand_evaluated)

    # 6. Rank all candidates with the real trained Random Forest ML model
    comp_dict = {
        "id": component.id,
        "name": component.name,
        "type": component.type,
        "criticality": component.criticality,
        "cost_per_month": component.cost_per_month,
        "cpu": component.cpu,
        "memory": component.memory,
        "status": component.status,
        "metadata_col": component.metadata_col
    }
    
    ranked = rank_candidate_solutions(
        simulation_result=simulation_result,
        candidate_solutions=evaluated_candidates,
        component_data=comp_dict
    )
    return ranked
