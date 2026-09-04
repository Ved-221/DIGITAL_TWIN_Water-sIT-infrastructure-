import uuid
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
import models
from simulation import simulate_change, find_spofs
import snapshot_manager

def apply_solution_to_sandbox(
    db: Session,
    source_environment: str,
    target_component_id: str,
    solution: Optional[Dict[str, Any]] = None,
    solution_id: Optional[str] = None,
    solution_name: Optional[str] = None,
    strategy_type: Optional[str] = None,
    action: str = "migrate"
) -> Dict[str, Any]:
    """
    Applies a selected feasible solution to the appropriate Digital Twin environment.
    
    Environment Isolation Rules:
    - MANUAL ENVIRONMENT: Mutates the selected manual project directly.
    - AWS LIVE: NEVER mutates live AWS. Clones to 'aws_sim_aws' and mutates the sandbox copy.
    - AWS SIMULATION SANDBOX: Mutates the sandbox environment directly.
    
    Creates a baseline snapshot, executes topology mutations, re-simulates,
    and returns full Before vs After deltas with objective evaluation.
    """
    solution_dict = solution or {}
    
    # 1. Resolve strategy type & identifiers
    strat_type = (
        strategy_type or 
        solution_dict.get("strategy_type") or 
        "multi_az_modernize"
    ).lower()
    
    sol_name = (
        solution_name or 
        solution_dict.get("name") or 
        strat_type.replace("_", " ").title()
    )
    
    sol_id = (
        solution_id or 
        solution_dict.get("id") or 
        f"sol-{uuid.uuid4().hex[:8]}"
    )
    
    # 2. Validate source component
    source_comp = db.query(models.Component).filter(models.Component.id == target_component_id).first()
    if not source_comp:
        raise ValueError(f"Component '{target_component_id}' not found in database.")
        
    actual_source_env = source_comp.source_environment or source_environment
    
    # 3. Determine target environment based on isolation rules
    if actual_source_env == "aws":
        target_env_id = "aws_sim_aws"
        is_cloning_required = True
    elif actual_source_env.startswith("aws_sim_"):
        target_env_id = actual_source_env
        is_cloning_required = False
    else:
        target_env_id = actual_source_env
        is_cloning_required = False

    # 4. Run BEFORE simulation on baseline environment
    before_sim = simulate_change(
        db=db,
        target_component_id=target_component_id,
        action=action,
        source_environment=actual_source_env,
        use_ai=False
    )
    
    before_comps = db.query(models.Component).filter(models.Component.source_environment == actual_source_env).all()
    before_deps = db.query(models.Dependency).filter(models.Dependency.source_environment == actual_source_env).all()
    before_spof_res = find_spofs(db, actual_source_env)
    
    b_score = float(before_sim.get("risk_score", 0.0))
    b_level = before_sim.get("risk_level", "LOW")
    b_blast = int(before_sim.get("affected_count", len(before_sim.get("affected_components", []))))
    b_upstream = int(before_sim.get("upstream_impact_count", 0))
    b_spof = bool(before_sim.get("risk_factors", {}).get("is_single_point_of_failure", False))
    b_dt = before_sim.get("estimated_downtime_minutes")
    b_cost_delta = before_sim.get("cost_delta_monthly") or 0.0
    
    # Calculate environment-wide total monthly cost consistently
    b_env_monthly_cost = round(sum(float(c.cost_per_month or 0.0) for c in before_comps), 2)
    b_spof_count = len(before_spof_res.spof_nodes)
    b_comp_count = len(before_comps)
    b_dep_count = len(before_deps)

    # 5. Capture Snapshot before applying mutations
    snapshot_id = snapshot_manager.create_snapshot(
        db=db,
        environment_id=target_env_id if not is_cloning_required else actual_source_env,
        solution_info={
            "id": sol_id,
            "solution_id": sol_id,
            "name": sol_name,
            "strategy_type": strat_type
        }
    )

    # 6. Apply topological mutations in a transaction
    mutations_applied: List[str] = []
    
    try:
        sim_target_id = target_component_id
        
        if is_cloning_required:
            db.query(models.Dependency).filter(models.Dependency.source_environment == target_env_id).delete()
            db.query(models.Component).filter(models.Component.source_environment == target_env_id).delete()
            db.flush()
            
            id_map = {}
            for c in before_comps:
                new_id = f"sim-{c.id}"
                id_map[c.id] = new_id
                db_c = models.Component(
                    id=new_id,
                    name=c.name,
                    type=c.type,
                    environment=c.environment,
                    environment_id=target_env_id,
                    provider=c.provider,
                    region=c.region,
                    location=c.location,
                    criticality=c.criticality,
                    owner="Simulated Deployment",
                    status=c.status,
                    cpu=c.cpu,
                    memory=c.memory,
                    cost_per_month=c.cost_per_month,
                    currency=c.currency,
                    position_x=c.position_x,
                    position_y=c.position_y,
                    metadata_col=dict(c.metadata_col or {}),
                    telemetry=dict(c.telemetry or {}),
                    source_environment=target_env_id
                )
                db.add(db_c)
                
            for d in before_deps:
                src = id_map.get(d.source_id, d.source_id)
                tgt = id_map.get(d.target_id, d.target_id)
                db_d = models.Dependency(
                    id=f"sim-{d.id}",
                    environment_id=target_env_id,
                    source_id=src,
                    target_id=tgt,
                    relationship_type=d.relationship_type,
                    criticality=d.criticality,
                    source_environment=target_env_id
                )
                db.add(db_d)
                
            db.flush()
            sim_target_id = id_map.get(target_component_id, target_component_id)
            mutations_applied.append(f"Cloned live AWS topology ({len(before_comps)} components) to isolated sandbox '{target_env_id}'")

        target_comp = db.query(models.Component).filter(
            models.Component.id == sim_target_id,
            models.Component.source_environment == target_env_id
        ).first()
        
        if not target_comp:
            raise ValueError(f"Target component '{sim_target_id}' could not be located in environment '{target_env_id}'.")

        # Architectural strategy mutations
        if strat_type in ["multi_az_modernize", "multi_az_standby", "redundancy"]:
            alb_id = f"alb-{uuid.uuid4().hex[:6]}"
            standby_id = f"standby-{uuid.uuid4().hex[:6]}"
            
            meta = dict(target_comp.metadata_col or {})
            meta["multi_az"] = True
            meta["redundancy_enabled"] = True
            meta["estimated_downtime_minutes"] = 0
            target_comp.metadata_col = meta
            target_comp.criticality = "medium"
            
            alb_comp = models.Component(
                id=alb_id,
                name=f"ALB-{target_comp.name}",
                type="application",
                criticality="high",
                source_environment=target_env_id,
                environment_id=target_env_id,
                cost_per_month=25.0,
                status="active",
                owner=target_comp.owner,
                position_x=(target_comp.position_x or 100) - 150,
                position_y=target_comp.position_y or 100
            )
            standby_comp = models.Component(
                id=standby_id,
                name=f"{target_comp.name}-Standby-AZ2",
                type=target_comp.type,
                criticality="medium",
                source_environment=target_env_id,
                environment_id=target_env_id,
                cost_per_month=target_comp.cost_per_month,
                status="active",
                owner=target_comp.owner,
                position_x=(target_comp.position_x or 100) + 150,
                position_y=(target_comp.position_y or 100) + 100
            )
            db.add_all([alb_comp, standby_comp])
            db.flush()
            
            db.add(models.Dependency(
                id=str(uuid.uuid4()),
                source_id=alb_id,
                target_id=target_comp.id,
                relationship_type="routes_traffic",
                source_environment=target_env_id,
                environment_id=target_env_id
            ))
            db.add(models.Dependency(
                id=str(uuid.uuid4()),
                source_id=alb_id,
                target_id=standby_id,
                relationship_type="routes_traffic",
                source_environment=target_env_id,
                environment_id=target_env_id
            ))
            
            upstream_deps = db.query(models.Dependency).filter(
                models.Dependency.source_environment == target_env_id,
                models.Dependency.target_id == target_comp.id,
                models.Dependency.source_id != alb_id
            ).all()
            for ud in upstream_deps:
                ud.target_id = alb_id
                
            mutations_applied.append(f"Injected Application Load Balancer ({alb_comp.name})")
            mutations_applied.append(f"Provisioned Multi-AZ Standby replica ({standby_comp.name})")
            mutations_applied.append(f"Rerouted {len(upstream_deps)} upstream caller dependency link(s) to ALB")
            mutations_applied.append("Eliminated Single Point of Failure (SPOF) with active health check failover")

        elif strat_type in ["read_replica_offload", "replication"]:
            replica_id = f"replica-{uuid.uuid4().hex[:6]}"
            replica_cost = round((target_comp.cost_per_month or 50.0) * 0.50, 2)
            
            replica_comp = models.Component(
                id=replica_id,
                name=f"{target_comp.name}-ReadReplica",
                type="database",
                criticality="medium",
                source_environment=target_env_id,
                environment_id=target_env_id,
                cost_per_month=replica_cost,
                status="active",
                owner=target_comp.owner,
                position_x=(target_comp.position_x or 100) + 150,
                position_y=(target_comp.position_y or 100) + 80
            )
            db.add(replica_comp)
            db.flush()
            
            db.add(models.Dependency(
                id=str(uuid.uuid4()),
                source_id=replica_id,
                target_id=target_comp.id,
                relationship_type="replicates_from",
                source_environment=target_env_id,
                environment_id=target_env_id
            ))
            
            meta = dict(target_comp.metadata_col or {})
            meta["read_replica_enabled"] = True
            target_comp.metadata_col = meta
            
            mutations_applied.append(f"Provisioned Dedicated Read Replica ({replica_comp.name})")
            mutations_applied.append("Configured automated database replication stream")

        elif strat_type in ["dependency_circuit_breaker", "dependency_decoupling"]:
            queue_id = f"queue-{uuid.uuid4().hex[:6]}"
            
            queue_comp = models.Component(
                id=queue_id,
                name=f"Queue-Buffer-{target_comp.name}",
                type="application",
                criticality="medium",
                source_environment=target_env_id,
                environment_id=target_env_id,
                cost_per_month=15.0,
                status="active",
                owner=target_comp.owner,
                position_x=(target_comp.position_x or 100) - 120,
                position_y=target_comp.position_y or 100
            )
            db.add(queue_comp)
            db.flush()
            
            db.add(models.Dependency(
                id=str(uuid.uuid4()),
                source_id=queue_id,
                target_id=target_comp.id,
                relationship_type="buffers_to",
                source_environment=target_env_id,
                environment_id=target_env_id
            ))
            
            upstream_deps = db.query(models.Dependency).filter(
                models.Dependency.source_environment == target_env_id,
                models.Dependency.target_id == target_comp.id,
                models.Dependency.source_id != queue_id
            ).all()
            for ud in upstream_deps:
                ud.target_id = queue_id
                
            mutations_applied.append(f"Provisioned Asynchronous Queue Buffer ({queue_comp.name})")
            mutations_applied.append(f"Decoupled {len(upstream_deps)} upstream synchronous caller(s)")

        elif strat_type in ["phased_blue_green", "staged_migration"]:
            shadow_id = f"shadow-{uuid.uuid4().hex[:6]}"
            
            shadow_comp = models.Component(
                id=shadow_id,
                name=f"{target_comp.name}-Shadow-Target",
                type=target_comp.type,
                criticality=target_comp.criticality,
                source_environment=target_env_id,
                environment_id=target_env_id,
                cost_per_month=target_comp.cost_per_month,
                status="active",
                owner=target_comp.owner,
                position_x=(target_comp.position_x or 100) + 120,
                position_y=(target_comp.position_y or 100) + 80
            )
            db.add(shadow_comp)
            db.flush()
            
            db.add(models.Dependency(
                id=str(uuid.uuid4()),
                source_id=shadow_id,
                target_id=target_comp.id,
                relationship_type="syncs_with",
                source_environment=target_env_id,
                environment_id=target_env_id
            ))
            
            meta = dict(target_comp.metadata_col or {})
            meta["staged_cutover"] = True
            meta["estimated_downtime_minutes"] = 0
            target_comp.metadata_col = meta
            
            mutations_applied.append(f"Provisioned Parallel Shadow Target ({shadow_comp.name})")
            mutations_applied.append("Established dual-run state replication link")

        elif strat_type in ["scale_up", "scale_out", "scale"]:
            target_comp.cpu = (target_comp.cpu or 2) * 2
            target_comp.memory = (target_comp.memory or 4) * 2
            target_comp.cost_per_month = round((target_comp.cost_per_month or 40.0) * 1.5, 2)
            meta = dict(target_comp.metadata_col or {})
            meta["scaled_capacity"] = True
            target_comp.metadata_col = meta
            
            mutations_applied.append(f"Scaled compute resources: CPU to {target_comp.cpu} vCPUs, RAM to {target_comp.memory} GB")

        elif strat_type in ["direct_lift_shift", "migration", "workload_relocation"]:
            target_comp.location = "cloud"
            target_comp.provider = "aws"
            meta = dict(target_comp.metadata_col or {})
            meta["relocated"] = True
            target_comp.metadata_col = meta
            
            mutations_applied.append(f"Relocated {target_comp.name} workload to target cloud infrastructure")

        else:
            meta = dict(target_comp.metadata_col or {})
            meta["remediated"] = True
            meta["applied_strategy"] = strat_type
            target_comp.metadata_col = meta
            mutations_applied.append(f"Applied architecture remediation strategy: {sol_name}")

        db.commit()
        
    except Exception as e:
        db.rollback()
        raise RuntimeError(f"Database error executing topology mutation for solution '{sol_name}': {str(e)}")

    # 7. Re-run AFTER simulation on mutated environment
    after_sim = simulate_change(
        db=db,
        target_component_id=sim_target_id,
        action=action,
        source_environment=target_env_id,
        use_ai=False
    )
    
    after_comps = db.query(models.Component).filter(models.Component.source_environment == target_env_id).all()
    after_deps = db.query(models.Dependency).filter(models.Dependency.source_environment == target_env_id).all()
    after_spof_res = find_spofs(db, target_env_id)
    
    a_score = float(after_sim.get("risk_score", 0.0))
    a_level = after_sim.get("risk_level", "LOW")
    a_blast = int(after_sim.get("affected_count", len(after_sim.get("affected_components", []))))
    a_upstream = int(after_sim.get("upstream_impact_count", 0))
    a_spof = bool(after_sim.get("risk_factors", {}).get("is_single_point_of_failure", False))
    a_dt = after_sim.get("estimated_downtime_minutes")
    a_cost_delta = after_sim.get("cost_delta_monthly") or 0.0
    
    a_env_monthly_cost = round(sum(float(c.cost_per_month or 0.0) for c in after_comps), 2)
    a_spof_count = len(after_spof_res.spof_nodes)
    a_comp_count = len(after_comps)
    a_dep_count = len(after_deps)

    # 8. Compute dynamic Before vs After diffs
    risk_diff = round(b_score - a_score, 1)
    risk_pct = round((risk_diff / b_score * 100.0), 1) if b_score > 0 else 0.0
    spof_eliminated = bool(b_spof and not a_spof)
    
    dt_saved = max((b_dt or 0) - (a_dt or 0), 0) if b_dt is not None else 0
    blast_radius_delta = a_blast - b_blast
    monthly_cost_delta = round(float(a_env_monthly_cost - b_env_monthly_cost), 2)
    
    # 9. Evaluate Remediation Outcome & Primary Objective
    primary_obj = "remove_spof" if b_spof else ("reduce_risk" if b_score >= 60 else "improve_resilience")
    
    if a_score < b_score and (not a_spof if b_spof else True) and blast_radius_delta <= 0:
        remediation_outcome = "IMPROVED"
        obj_result = "Primary objective achieved: Risk reduced and architecture resilient"
    elif a_score < b_score or spof_eliminated:
        remediation_outcome = "PARTIALLY_IMPROVED"
        obj_result = f"Partial improvement: Risk reduced by {risk_diff} pts with minor trade-offs"
    elif a_score == b_score:
        remediation_outcome = "NO_IMPROVEMENT"
        obj_result = "No measurable change in risk profile"
    else:
        remediation_outcome = "WORSE"
        obj_result = "Architecture risk increased under selected configuration"

    tradeoffs = []
    if monthly_cost_delta > 0:
        tradeoffs.append(f"Added infrastructure increases monthly run-rate by +${monthly_cost_delta:,.2f}/mo")
    if (a_dt or 0) > (b_dt or 0):
        tradeoffs.append(f"Execution maintenance window increased by {(a_dt or 0) - (b_dt or 0)} minutes")

    before_data = {
        "risk": b_score,
        "risk_score": b_score,
        "risk_level": b_level,
        "downtime": b_dt if b_dt is not None else 0,
        "estimated_downtime_minutes": b_dt if b_dt is not None else 0,
        "blast_radius": b_blast,
        "blast_radius_nodes_count": b_blast,
        "affected_count": b_blast,
        "upstream_impact_count": b_upstream,
        "monthly_cost": b_env_monthly_cost,
        "cost_delta_monthly": b_cost_delta,
        "spof_count": b_spof_count,
        "is_spof": b_spof,
        "is_single_point_of_failure": b_spof,
        "component_count": b_comp_count,
        "dependency_count": b_dep_count
    }

    after_data = {
        "risk": a_score,
        "risk_score": a_score,
        "risk_level": a_level,
        "downtime": a_dt if a_dt is not None else 0,
        "estimated_downtime_minutes": a_dt if a_dt is not None else 0,
        "blast_radius": a_blast,
        "blast_radius_nodes_count": a_blast,
        "affected_count": a_blast,
        "upstream_impact_count": a_upstream,
        "monthly_cost": a_env_monthly_cost,
        "cost_delta_monthly": a_cost_delta,
        "spof_count": a_spof_count,
        "is_spof": a_spof,
        "is_single_point_of_failure": a_spof,
        "component_count": a_comp_count,
        "dependency_count": a_dep_count
    }

    delta_data = {
        "risk": round(a_score - b_score, 1),
        "risk_delta_points": round(a_score - b_score, 1),
        "risk_reduction_points": risk_diff,
        "risk_reduction_percent": risk_pct,
        "downtime": (a_dt or 0) - (b_dt or 0),
        "downtime_saved_minutes": dt_saved,
        "blast_radius": blast_radius_delta,
        "blast_radius_delta": blast_radius_delta,
        "monthly_cost": monthly_cost_delta,
        "monthly_cost_delta": monthly_cost_delta,
        "spof_count": a_spof_count - b_spof_count,
        "spof_eliminated": spof_eliminated,
        "component_count": a_comp_count - b_comp_count,
        "dependency_count": a_dep_count - b_dep_count
    }

    return {
        "success": True,
        "solution_id": sol_id,
        "solution_name": sol_name,
        "solution_applied": sol_name,
        "strategy_type": strat_type,
        "target_component_id": target_component_id,
        "source_environment": actual_source_env,
        "target_environment": target_env_id,
        "sandbox_environment_id": target_env_id,
        "snapshot_id": snapshot_id,
        "implementation_status": "SUCCESS",
        "remediation_outcome": remediation_outcome,
        "primary_objective": primary_obj,
        "objective_result": obj_result,
        "tradeoffs": tradeoffs,
        "mutations": mutations_applied,
        "mutations_applied": mutations_applied,
        "before": before_data,
        "before_metrics": before_data,
        "after": after_data,
        "after_metrics": after_data,
        "delta": delta_data,
        "comparison": delta_data,
        "improvements": delta_data,
        "changes": mutations_applied,
        "missing_data": before_sim.get("missing_data", []),
        "after_simulation_result": after_sim
    }
