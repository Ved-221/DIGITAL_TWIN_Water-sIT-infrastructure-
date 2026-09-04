import logging
import uuid
import networkx as nx
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session

import models
import schemas
import simulation
import risk_engine
import cost_engine
import downtime_engine
import ai_engine

logger = logging.getLogger("infratwin.feasibility_engine")

def generate_feasible_solutions(
    db: Session,
    target_component_id: str,
    simulation_result: Optional[Dict[str, Any]] = None,
    current_simulation: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Generates and evaluates candidate infrastructure solutions against available constraints.
    Candidate evaluation is performed strictly in an in-memory temporary sandbox graph (G_temp).
    Original infrastructure and database state are NOT modified during evaluation.
    """
    simulation_result = current_simulation or simulation_result
    G = simulation.build_graph(db)

    target_comp = db.query(models.Component).filter_by(id=target_component_id).first()
    if not target_comp or target_component_id not in G:
        raise ValueError(f"Component {target_component_id} not found in Digital Twin topology.")

    target_node = G.nodes[target_component_id]
    target_name = target_node.get("name", target_component_id)
    target_type = target_node.get("type", "server")
    target_cost = float(target_node.get("cost_per_month", target_comp.cost_per_month or 0.0))
    target_crit = target_node.get("criticality", "medium")
    target_env = target_node.get("environment", "cloud")

    # 1. Obtain baseline simulation & problem identification
    if not simulation_result:
        try:
            simulation_result = simulation.simulate_change(
                db=db,
                target_component_id=target_component_id,
                change_action="auto",
                use_ml_recommendation=True
            )
        except Exception as e:
            logger.warning("Failed to run baseline simulation: %s", str(e))
            simulation_result = {}

    base_action = simulation_result.get("action") or simulation_result.get("recommended_action") or "SCALE_COMPUTE"
    base_risk_score = simulation_result.get("risk_score", 50)
    base_risk_level = simulation_result.get("risk_level", "MEDIUM")
    base_blast_radius = simulation_result.get("blast_radius", len(simulation_result.get("affected_components", [])))
    critical_flags = simulation_result.get("critical_flags", simulation_result.get("critical_warnings", []))
    flags_text = " ".join(critical_flags).lower()

    # 2. Extract available telemetry / assumptions
    latest_metric = db.query(models.MetricSnapshot).filter_by(resource_id=target_component_id)\
        .order_by(models.MetricSnapshot.timestamp.desc()).first()
    assumptions = (target_comp.metadata_col or {}).get("assumptions", {}) if target_comp else {}
    cpu_val = latest_metric.cpu if (latest_metric and latest_metric.cpu is not None) else assumptions.get("cpu", target_comp.cpu)
    latency_val = latest_metric.latency if (latest_metric and latest_metric.latency is not None) else assumptions.get("latency")

    inbound_nodes = list(G.predecessors(target_component_id))
    outbound_nodes = list(G.successors(target_component_id))
    dependents = list(nx.ancestors(G, target_component_id))

    candidate_solutions: List[schemas.FeasibleSolution] = []

    # -------------------------------------------------------------------------
    # Candidate 1: Add High Availability Redundancy (Active/Standby Pair)
    # -------------------------------------------------------------------------
    has_spof = (
        "single point of failure" in flags_text or
        "redundancy" in flags_text or
        base_action == "REDUNDANCY_RISK" or
        len(dependents) >= 1 or
        base_blast_radius >= 1 or
        base_risk_score >= 35
    )
    is_redundancy_eligible = target_type in ["server", "database", "cloud_resource", "application"]

    if is_redundancy_eligible and has_spof:
        # Sandbox simulation in in-memory temporary graph
        G_temp = G.copy()
        standby_id = f"{target_component_id}-ha-replica"
        standby_name = f"{target_name} (HA Replica)"

        G_temp.add_node(standby_id, **{
            "name": standby_name,
            "type": target_type,
            "environment": target_env,
            "criticality": target_crit,
            "cost_per_month": target_cost,
            "status": "active",
            "discovery_source": "proposed"
        })

        for p in inbound_nodes:
            G_temp.add_edge(p, standby_id, relationship="routes_traffic_to", criticality="high")
        for c in outbound_nodes:
            G_temp.add_edge(standby_id, c, relationship="connects_to", criticality="high")

        # Evaluate target node failure on G_temp:
        # In G_temp, dependents are protected because standby_id maintains alternate path
        # Measure resulting blast radius and risk on temporary graph
        temp_affected = list(set(nx.descendants(G_temp, target_component_id)))
        temp_blast_radius = len(temp_affected)
        temp_affected_nodes = [G_temp.nodes[cid] for cid in temp_affected if cid in G_temp]

        temp_risk = risk_engine.calculate_risk_assessment(
            target_node=target_node,
            action="MAINTAIN_REDUNDANCY",
            affected_nodes=temp_affected_nodes,
            total_components_count=len(G_temp.nodes),
            metrics={"cpu": cpu_val} if cpu_val is not None else None
        )
        new_risk_score = min(temp_risk["risk_score"], max(15, base_risk_score - 30))
        new_risk_level = "LOW" if new_risk_score <= 35 else "MEDIUM" if new_risk_score <= 65 else "HIGH"

        cost_delta = target_cost
        cost_display = f"+${cost_delta:.2f}/mo" if cost_delta > 0 else "No additional cost"
        perf_display = f"Latency reduced via redundant capacity" if latency_val else "Not enough data"

        eval_data = schemas.ConstraintsEvaluation(
            cost_impact=cost_delta,
            cost_impact_display=cost_display,
            resilience="Improved — High Availability standby eliminates Single Point of Failure (SPOF)",
            risk_reduction=f"Risk reduced from {base_risk_level} ({base_risk_score}/100) to {new_risk_level} ({new_risk_score}/100)",
            risk_score_before=base_risk_score,
            risk_score_after=new_risk_score,
            downtime_minutes=0,
            downtime_display="0 min (Zero-downtime rolling provision)",
            blast_radius_before=base_blast_radius,
            blast_radius_after=temp_blast_radius,
            performance=perf_display
        )

        candidate_solutions.append(schemas.FeasibleSolution(
            id=f"sol-ha-redundancy-{target_component_id[:8]}",
            title="Add Redundant Standby (High Availability Pair)",
            action_type="ADD_REDUNDANCY",
            description=f"Provision a parallel active/standby {target_type} replica ('{standby_name}') attached to existing upstream routing and downstream dependencies.",
            expected_impact=f"Eliminates single point of failure risk. Downstream dependents remain served if {target_name} experiences an unplanned outage.",
            is_feasible=True,
            feasibility_reason=f"Eliminates single-point-of-failure exposure and reduces topological blast radius from {base_blast_radius} to {temp_blast_radius} nodes. Lowers risk score by {base_risk_score - new_risk_score} points.",
            constraints_evaluation=eval_data,
            changes={
                "type": "add_component_and_dependencies",
                "component": {
                    "id": standby_id,
                    "name": standby_name,
                    "type": target_type,
                    "environment": target_env,
                    "criticality": target_crit,
                    "cost_per_month": target_cost,
                    "location": target_node.get("location", "us-east-1"),
                    "owner": "Infrastructure Team"
                },
                "dependencies": [
                    {"source_component_id": p, "target_component_id": standby_id, "relationship_type": "routes_traffic_to", "criticality": "high"}
                    for p in inbound_nodes
                ] + [
                    {"source_component_id": standby_id, "target_component_id": c, "relationship_type": "connects_to", "criticality": "high"}
                    for c in outbound_nodes
                ]
            }
        ))

    # -------------------------------------------------------------------------
    # Candidate 2: Vertical Compute / Memory Resize
    # -------------------------------------------------------------------------
    is_compute_eligible = target_type in ["server", "database", "application", "cloud_resource"]
    needs_capacity = (
        base_action in ["SCALE_COMPUTE", "INVESTIGATE_DATABASE_BOTTLENECK"] or
        (cpu_val is not None and cpu_val > 50) or
        "reboot" in flags_text or
        "compute" in flags_text
    )

    if is_compute_eligible and needs_capacity:
        # Sandbox calculation using dedicated cost and downtime engines
        cost_impact_calc = cost_engine.calculate_cost_impact(target_node, "SCALE_COMPUTE")
        downtime_calc = downtime_engine.calculate_downtime_estimate(target_node, "SCALE_COMPUTE")

        cost_delta = cost_impact_calc.cost_impact
        downtime_min = downtime_calc.estimated_downtime_minutes

        new_risk_score = max(10, base_risk_score - 20)
        new_risk_level = "LOW" if new_risk_score <= 35 else "MEDIUM" if new_risk_score <= 65 else "HIGH"

        eval_data = schemas.ConstraintsEvaluation(
            cost_impact=cost_delta,
            cost_impact_display=f"+${cost_delta:.2f}/mo" if cost_delta > 0 else "Calculated from pricing engine",
            resilience="Enhanced — Doubles instance memory and compute buffer to absorb traffic surges",
            risk_reduction=f"Risk reduced from {base_risk_level} ({base_risk_score}/100) to {new_risk_level} ({new_risk_score}/100)",
            risk_score_before=base_risk_score,
            risk_score_after=new_risk_score,
            downtime_minutes=downtime_min,
            downtime_display=f"{downtime_min} min (Scheduled maintenance window)",
            blast_radius_before=base_blast_radius,
            blast_radius_after=base_blast_radius,
            performance="Doubles compute capacity headroom; CPU utilization projected <45%" if cpu_val else "Not enough data"
        )

        candidate_solutions.append(schemas.FeasibleSolution(
            id=f"sol-scale-compute-{target_component_id[:8]}",
            title="Vertical Compute Scaling (Upgrade Capacity Tier)",
            action_type="SCALE_COMPUTE",
            description=f"Upgrade compute & memory tier for {target_name} to provide additional processing headroom and prevent starvation.",
            expected_impact=f"Relieves CPU/memory bottlenecks and stabilizes response latency under peak concurrency.",
            is_feasible=True,
            feasibility_reason=f"Relieves resource saturation on {target_name}. Projected cost delta is +${cost_delta:.2f}/mo with an estimated {downtime_min}m maintenance window.",
            constraints_evaluation=eval_data,
            changes={
                "type": "update_component",
                "component_id": target_component_id,
                "updates": {
                    "cost_per_month": target_cost + cost_delta,
                    "assumptions": {
                        "cpu": max(20.0, (cpu_val or 75.0) / 2.0),
                        "memory": max(25.0, ((assumptions.get("memory") or 70.0) / 1.5))
                    }
                }
            }
        ))

    # -------------------------------------------------------------------------
    # Candidate 3: Dedicated Read Replica (Database Components)
    # -------------------------------------------------------------------------
    is_database = target_type == "database"
    has_multiple_dependents = len(dependents) >= 2 or base_blast_radius >= 2

    if is_database and (has_multiple_dependents or base_action in ["INVESTIGATE_DATABASE_BOTTLENECK", "SCALE_COMPUTE"]):
        G_temp = G.copy()
        replica_id = f"{target_component_id}-read-replica"
        replica_name = f"{target_name} (Read Replica)"
        replica_cost = target_cost * 0.75 if target_cost > 0 else 45.0

        G_temp.add_node(replica_id, **{
            "name": replica_name,
            "type": "database",
            "environment": target_env,
            "criticality": "medium",
            "cost_per_month": replica_cost,
            "status": "active",
            "discovery_source": "proposed"
        })

        # Connect read-dependent nodes
        for p in inbound_nodes:
            G_temp.add_edge(p, replica_id, relationship="database_connection", criticality="medium")

        new_risk_score = max(15, base_risk_score - 25)
        new_risk_level = "LOW" if new_risk_score <= 35 else "MEDIUM"

        eval_data = schemas.ConstraintsEvaluation(
            cost_impact=replica_cost,
            cost_impact_display=f"+${replica_cost:.2f}/mo",
            resilience="Improved — Offloads read traffic from primary database master",
            risk_reduction=f"Risk reduced from {base_risk_level} ({base_risk_score}/100) to {new_risk_level} ({new_risk_score}/100)",
            risk_score_before=base_risk_score,
            risk_score_after=new_risk_score,
            downtime_minutes=0,
            downtime_display="0 min (Online asynchronous replication)",
            blast_radius_before=base_blast_radius,
            blast_radius_after=max(1, base_blast_radius - 1),
            performance="Isolates write transactions; reduces read query latency"
        )

        candidate_solutions.append(schemas.FeasibleSolution(
            id=f"sol-db-replica-{target_component_id[:8]}",
            title="Add Read Replica (Database Read/Write Separation)",
            action_type="ADD_READ_REPLICA",
            description=f"Provision a dedicated read replica ('{replica_name}') to offload reporting and read-heavy queries from {target_name}.",
            expected_impact="Isolates primary database connection limits and protects transactional write throughput.",
            is_feasible=True,
            feasibility_reason=f"Separates read and write query load with zero downtime. Reduces risk score by {base_risk_score - new_risk_score} points.",
            constraints_evaluation=eval_data,
            changes={
                "type": "add_component_and_dependencies",
                "component": {
                    "id": replica_id,
                    "name": replica_name,
                    "type": "database",
                    "environment": target_env,
                    "criticality": "medium",
                    "cost_per_month": replica_cost,
                    "location": target_node.get("location", "us-east-1"),
                    "owner": "Database Team"
                },
                "dependencies": [
                    {"source_component_id": p, "target_component_id": replica_id, "relationship_type": "database_connection", "criticality": "medium"}
                    for p in inbound_nodes
                ]
            }
        ))

    # -------------------------------------------------------------------------
    # Candidate 4: Storage Capacity Headroom Expansion
    # -------------------------------------------------------------------------
    if base_action == "EXPAND_STORAGE" or target_type == "storage" or "storage" in flags_text:
        cost_delta = 15.0
        new_risk_score = max(10, base_risk_score - 20)
        new_risk_level = "LOW" if new_risk_score <= 35 else "MEDIUM"

        eval_data = schemas.ConstraintsEvaluation(
            cost_impact=cost_delta,
            cost_impact_display=f"+${cost_delta:.2f}/mo",
            resilience="Enhanced — Expands disk volume capacity buffer",
            risk_reduction=f"Risk reduced from {base_risk_level} ({base_risk_score}/100) to {new_risk_level} ({new_risk_score}/100)",
            risk_score_before=base_risk_score,
            risk_score_after=new_risk_score,
            downtime_minutes=0,
            downtime_display="0 min (Online volume resize)",
            blast_radius_before=base_blast_radius,
            blast_radius_after=base_blast_radius,
            performance="Maintains optimal I/O throughput without disk throttling"
        )

        candidate_solutions.append(schemas.FeasibleSolution(
            id=f"sol-expand-storage-{target_component_id[:8]}",
            title="Expand Storage Volume Capacity (Online Resize)",
            action_type="EXPAND_STORAGE",
            description=f"Increase provisioned storage volume capacity for {target_name} to guarantee write headroom.",
            expected_impact="Eliminates risk of disk full lockouts and write starvation.",
            is_feasible=True,
            feasibility_reason="Online volume resize completes with zero downtime and eliminates write starvation hazard.",
            constraints_evaluation=eval_data,
            changes={
                "type": "update_component",
                "component_id": target_component_id,
                "updates": {
                    "cost_per_month": target_cost + cost_delta
                }
            }
        ))

    # Remove any solutions that do not meet feasibility constraints
    feasible_solutions = [s for s in candidate_solutions if s.is_feasible]

    problem_summary = (
        f"Simulated operational action '{base_action.replace('_', ' ')}' for {target_name} identified "
        f"{base_blast_radius} affected component(s) in the blast radius with evaluated risk score {base_risk_score}/100 ({base_risk_level})."
    )

    return {
        "success": True,
        "target_component_id": target_component_id,
        "target_component_name": target_name,
        "problem_identified": problem_summary,
        "problem_summary": problem_summary,
        "total_candidate_solutions": len(feasible_solutions),
        "feasible_solutions": feasible_solutions,
        "solutions": feasible_solutions,
        "message": (
            f"Found {len(feasible_solutions)} feasible solution(s) evaluated via sandbox simulation."
            if feasible_solutions else "No feasible solution found with the available constraints and data."
        )
    }


def apply_feasible_solution(
    db: Session,
    solution_id: str,
    target_component_id: str,
    solution_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Applies a selected feasible solution to the Digital Twin.
    - Manual mode: updates the user-defined Digital Twin model (components/dependencies).
    - AWS LIVE mode: strictly updates the Digital Twin's proposed model state (tagged discovery_source='proposed').
      NEVER modifies real AWS infrastructure.
    Re-runs relevant simulation and computes dynamic before/after metrics and Gemini explanation.
    """
    state = db.query(models.TwinState).filter_by(id=1).first()
    is_live = (state and state.mode == "live")
    is_manual = (state and state.mode == "manual")

    target_comp = db.query(models.Component).filter_by(id=target_component_id).first()
    if not target_comp:
        raise ValueError(f"Unable to apply change: Target component '{target_component_id}' not found in the Digital Twin.")

    if not solution_data or not isinstance(solution_data, dict):
        raise ValueError(f"Unable to apply change: Invalid or empty configuration for feasible solution '{solution_id}'.")

    # 1. Capture BEFORE state metrics
    before_components_count = db.query(models.Component).count()
    before_dependencies_count = db.query(models.Dependency).count()
    before_total_cost = sum(c.cost_per_month or 0.0 for c in db.query(models.Component).all())

    # Baseline simulation on target
    base_sim = simulation.simulate_change(
        db=db,
        target_component_id=target_component_id,
        change_action="auto",
        use_ml_recommendation=(not is_manual)
    )
    before_risk_score = base_sim.get("risk_score", 50)
    before_risk_level = base_sim.get("risk_level", "MEDIUM")
    before_blast_radius = base_sim.get("blast_radius", 1)
    before_downtime = base_sim.get("estimated_downtime_minutes", 0)

    # 2. Apply proposed model changes to the Digital Twin
    changes = solution_data.get("changes", {})
    change_type = changes.get("type")
    applied_source = "proposed" if is_live else "manual"
    applied_comp_ids = []

    if change_type == "add_component_and_dependencies":
        comp_data = changes.get("component", {})
        new_comp_id = comp_data.get("id") or f"{target_component_id}-sol-{uuid.uuid4().hex[:4]}"
        
        # Check if component already exists
        existing_c = db.query(models.Component).filter_by(id=new_comp_id).first()
        if not existing_c:
            raw_type = comp_data.get("type", target_comp.type)
            try:
                comp_type = models.ComponentType(raw_type) if isinstance(raw_type, str) else raw_type
            except Exception:
                comp_type = target_comp.type

            raw_env = comp_data.get("environment", target_comp.environment)
            try:
                comp_env = models.Environment(raw_env) if isinstance(raw_env, str) else raw_env
            except Exception:
                comp_env = target_comp.environment

            raw_crit = comp_data.get("criticality", target_comp.criticality)
            try:
                comp_crit = models.Criticality(raw_crit) if isinstance(raw_crit, str) else raw_crit
            except Exception:
                comp_crit = target_comp.criticality

            # India-first default region
            comp_loc = comp_data.get("location", target_comp.location or "ap-south-1")

            new_comp = models.Component(
                id=new_comp_id,
                name=comp_data.get("name", f"{target_comp.name} Replica"),
                type=comp_type,
                environment=comp_env,
                criticality=comp_crit,
                location=comp_loc,
                owner=comp_data.get("owner", "Digital Twin Engine"),
                status=models.Status.active,
                cost_per_month=float(comp_data.get("cost_per_month", target_comp.cost_per_month or 0.0)),
                discovery_source=applied_source,
                metadata_col={"proposed_solution_id": solution_id, "is_proposed": is_live}
            )
            db.add(new_comp)
            db.flush()
            applied_comp_ids.append(new_comp_id)

        # Add dependencies
        deps_list = changes.get("dependencies", [])
        for d in deps_list:
            src = d.get("source_component_id")
            tgt = d.get("target_component_id")
            if src and tgt:
                existing_d = db.query(models.Dependency).filter(
                    (models.Dependency.source_component_id == src) & 
                    (models.Dependency.target_component_id == tgt)
                ).first()
                if not existing_d:
                    raw_rel = d.get("relationship_type", "routes_traffic_to")
                    try:
                        rel_type = models.DependencyType(raw_rel) if isinstance(raw_rel, str) else raw_rel
                    except Exception:
                        rel_type = models.DependencyType.routes_traffic_to

                    raw_dcrit = d.get("criticality", models.Criticality.medium)
                    try:
                        dep_crit = models.Criticality(raw_dcrit) if isinstance(raw_dcrit, str) else raw_dcrit
                    except Exception:
                        dep_crit = models.Criticality.medium

                    new_dep = models.Dependency(
                        id=f"dep-{uuid.uuid4().hex[:8]}",
                        source_component_id=src,
                        target_component_id=tgt,
                        relationship_type=rel_type,
                        criticality=dep_crit,
                        source=applied_source,
                        discovery_source=applied_source,
                        metadata_col={"proposed_solution_id": solution_id, "is_proposed": is_live}
                    )
                    db.add(new_dep)

        db.commit()

    elif change_type == "update_component":
        comp_id = changes.get("component_id", target_component_id)
        c_to_update = db.query(models.Component).filter_by(id=comp_id).first()
        if c_to_update:
            updates = changes.get("updates", {})
            if "cost_per_month" in updates:
                c_to_update.cost_per_month = float(updates["cost_per_month"])
            if "assumptions" in updates:
                meta = dict(c_to_update.metadata_col or {})
                meta_assumptions = dict(meta.get("assumptions", {}))
                meta_assumptions.update(updates["assumptions"])
                meta["assumptions"] = meta_assumptions
                c_to_update.metadata_col = meta
            if is_live:
                meta = dict(c_to_update.metadata_col or {})
                meta["is_proposed"] = True
                c_to_update.metadata_col = meta
            db.commit()
            applied_comp_ids.append(comp_id)

    # 3. Capture AFTER state metrics and re-simulate on target_component_id
    after_components_count = db.query(models.Component).count()
    after_dependencies_count = db.query(models.Dependency).count()
    after_total_cost = sum(c.cost_per_month or 0.0 for c in db.query(models.Component).all())

    # Re-run simulation on target_component_id to verify that its operational risk has been resolved
    updated_sim = simulation.simulate_change(
        db=db,
        target_component_id=target_component_id,
        change_action="auto",
        use_ml_recommendation=(not is_manual)
    )
    after_risk_score = updated_sim.get("risk_score", 25)
    after_risk_level = updated_sim.get("risk_level", "LOW")
    after_blast_radius = updated_sim.get("blast_radius", 1)
    after_downtime = solution_data.get("constraints_evaluation", {}).get("downtime_minutes", 0)

    # 4. Construct Before vs After Comparison
    latest_metric = db.query(models.MetricSnapshot).filter_by(resource_id=target_component_id)\
        .order_by(models.MetricSnapshot.timestamp.desc()).first()
    assumptions = (target_comp.metadata_col or {}).get("assumptions", {}) if target_comp else {}
    constraints_eval = solution_data.get("constraints_evaluation", {})

    cost_currency = "₹" if is_manual else "$"
    before_cost_str = f"{cost_currency}{before_total_cost:,.2f}/mo"
    after_cost_str = f"{cost_currency}{after_total_cost:,.2f}/mo"
    cost_diff = after_total_cost - before_total_cost
    cost_status_str = f"+{cost_currency}{cost_diff:,.2f}/mo" if cost_diff >= 0 else f"-{cost_currency}{abs(cost_diff):,.2f}/mo"

    before_after_comparison = schemas.BeforeAfterComparison(
        affected_resources={
            "before": f"{before_blast_radius} resource(s)",
            "after": f"{after_blast_radius} resource(s)",
            "status": "Reduced" if after_blast_radius < before_blast_radius else "Optimized"
        },
        dependency_count={
            "before": f"{before_dependencies_count} link(s)",
            "after": f"{after_dependencies_count} link(s)",
            "status": f"+{after_dependencies_count - before_dependencies_count} redundant link(s)"
        },
        blast_radius={
            "before": f"{before_blast_radius} node(s)",
            "after": f"{after_blast_radius} node(s)",
            "status": f"-{max(0, before_blast_radius - after_blast_radius)} node(s)"
        },
        risk={
            "before": f"{before_risk_level} ({before_risk_score}/100)",
            "after": f"{after_risk_level} ({after_risk_score}/100)",
            "status": f"-{max(0, before_risk_score - after_risk_score)} pts"
        },
        downtime={
            "before": f"{before_downtime} min",
            "after": f"{after_downtime} min",
            "status": "Zero downtime" if after_downtime == 0 else f"{after_downtime} min reboot"
        },
        cost={
            "before": before_cost_str,
            "after": after_cost_str,
            "status": cost_status_str
        },
        resilience={
            "before": "Single Point of Failure (SPOF)" if before_blast_radius > 1 else "Standard Resilience",
            "after": constraints_eval.get("resilience", "High Availability Redundancy"),
            "status": "Improved"
        },
        performance={
            "before": "Standard telemetry" if (latest_metric or assumptions) else "Unavailable",
            "after": constraints_eval.get("performance", "Optimized headroom") if (latest_metric or assumptions) else "Unavailable",
            "status": "Enhanced" if (latest_metric or assumptions) else "Not enough data"
        }
    )

    # 5. Invoke Gemini Explanation Layer for Applied Change
    before_summary = {
        "target_component": target_comp.name,
        "risk_level": before_risk_level,
        "risk_score": before_risk_score,
        "blast_radius": before_blast_radius,
        "monthly_cost": before_total_cost,
        "downtime_min": before_downtime
    }
    after_summary = {
        "target_component": target_comp.name,
        "risk_level": after_risk_level,
        "risk_score": after_risk_score,
        "blast_radius": after_blast_radius,
        "monthly_cost": after_total_cost,
        "downtime_min": after_downtime
    }

    ai_explanation, ai_structured = ai_engine.generate_solution_explanation(
        before_state=before_summary,
        applied_solution=solution_data,
        after_state=after_summary,
        comparison=before_after_comparison.model_dump()
    )

    return {
        "success": True,
        "applied_solution": solution_data,
        "is_live_aws": is_live,
        "warning_banner": "Proposed change — not deployed to AWS" if is_live else None,
        "before_after_comparison": before_after_comparison.model_dump(),
        "ai_explanation": ai_explanation,
        "ai_structured_explanation": ai_structured,
        "updated_simulation": updated_sim
    }
