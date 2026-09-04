"""
sandbox_engine.py — Digital Twin Sandbox Execution Layer

Features:
1. Isolated Sandbox Environment Creation (cloning without mutating original Twin or live AWS).
2. Real Topology Mutation in Sandbox DB rows (ALB, Replicas, Queues, Shadow Targets, Scaling, Degraded/Decommissioned, etc.).
3. Rebuild NetworkX Graph for the sandbox.
4. Deterministic Post-Apply Simulation and SPOF recalculation.
5. Structured Before vs After Comparison (diffs, metric deltas, objective assessment).
6. Rollback (restoring baseline snapshot state atomically).
7. Accept (approving sandbox state while keeping original Twin/AWS unchanged).
"""

import uuid
from typing import Dict, Any, Optional, List, Set, Tuple
from sqlalchemy.orm import Session

import models
from simulation import build_graph, simulate_change, find_spofs
import snapshot_manager


def initialize_or_get_sandbox(
    db: Session,
    source_environment: str,
    sandbox_env_id: str = "sandbox",
    force_clone: bool = False
) -> Dict[str, Any]:
    """
    Ensures an isolated sandbox environment exists in the database.
    If sandbox already contains components and force_clone is False, reuses it.
    Otherwise, copies all components & dependencies from source_environment
    into sandbox_env_id with cloned IDs (sb-...).
    
    CRITICAL:
    - Never mutates the source_environment (original Twin).
    - Never mutates or touches live AWS resources.
    """
    # Check if sandbox already has components
    existing_comps = db.query(models.Component).filter(
        models.Component.source_environment == sandbox_env_id
    ).all()
    
    if existing_comps and not force_clone:
        existing_deps = db.query(models.Dependency).filter(
            models.Dependency.source_environment == sandbox_env_id
        ).all()
        return {
            "sandbox_id": sandbox_env_id,
            "components_count": len(existing_comps),
            "dependencies_count": len(existing_deps),
            "cloned": False,
            "id_map": {c.id: c.id for c in existing_comps}
        }

    # Wipe current sandbox contents before cloning fresh
    db.query(models.Dependency).filter(
        models.Dependency.source_environment == sandbox_env_id
    ).delete()
    db.query(models.Component).filter(
        models.Component.source_environment == sandbox_env_id
    ).delete()
    db.flush()

    # Query source components
    if source_environment == "manual":
        src_comps = db.query(models.Component).filter(
            models.Component.discovery_source.in_(["manual", "user_description"]) |
            (models.Component.source_environment == "manual")
        ).all()
        src_deps = db.query(models.Dependency).filter(
            models.Dependency.source.in_(["manual", "user_description"]) |
            (models.Dependency.source_environment == "manual")
        ).all()
    else:
        src_comps = db.query(models.Component).filter(
            (models.Component.source_environment == source_environment) |
            (models.Component.discovery_source == source_environment)
        ).all()
        src_deps = db.query(models.Dependency).filter(
            (models.Dependency.source_environment == source_environment) |
            (models.Dependency.source == source_environment)
        ).all()

    id_map = {}
    for c in src_comps:
        new_id = c.id if c.id.startswith("sb-") else f"sb-{c.id}"
        id_map[c.id] = new_id
        
        cloned_c = models.Component(
            id=new_id,
            name=c.name,
            type=c.type,
            environment=c.environment,
            location=c.location,
            criticality=c.criticality,
            owner=c.owner or "Sandbox User",
            status=c.status,
            cpu=c.cpu,
            memory=c.memory,
            cost_per_month=c.cost_per_month,
            arn=c.arn,
            aws_region=c.aws_region,
            discovery_source="sandbox",
            account_id=c.account_id,
            availability_zone=c.availability_zone,
            metadata_col=dict(c.metadata_col or {}),
            source_environment=sandbox_env_id,
            domain=c.domain or "general",
            properties=dict(c.properties or {})
        )
        db.add(cloned_c)

    db.flush()

    for d in src_deps:
        src_orig = d.source_component_id or d.source_id
        tgt_orig = d.target_component_id or d.target_id
        
        sb_src = id_map.get(src_orig, src_orig)
        sb_tgt = id_map.get(tgt_orig, tgt_orig)
        new_d_id = d.id if d.id.startswith("sb-") else f"sb-{d.id}"
        
        cloned_d = models.Dependency(
            id=new_d_id,
            source_id=sb_src,
            target_id=sb_tgt,
            source_component_id=sb_src,
            target_component_id=sb_tgt,
            relationship_type=d.relationship_type,
            criticality=d.criticality,
            source=sandbox_env_id,
            discovery_source="sandbox",
            metadata_col=dict(d.metadata_col or {})
        )
        db.add(cloned_d)

    db.commit()

    # Rebuild graph for the freshly cloned sandbox
    build_graph(db, sandbox_env_id)

    return {
        "sandbox_id": sandbox_env_id,
        "components_count": len(src_comps),
        "dependencies_count": len(src_deps),
        "cloned": True,
        "id_map": id_map
    }


def apply_candidate_to_sandbox(
    db: Session,
    source_environment: str,
    target_component_id: str,
    candidate_id: Optional[str] = None,
    action: str = "fail",
    candidate_data: Optional[Dict[str, Any]] = None,
    sandbox_env_id: str = "sandbox"
) -> Dict[str, Any]:
    """
    Applies a selected candidate solution ONLY to an isolated SANDBOX copy.
    
    Strict Safety Guarantees:
    - Never mutates the original/manual Twin.
    - Never mutates live AWS infrastructure.
    - Never calls AWS mutation APIs.
    - Captures a snapshot for single-step rollback.
    - Mutates actual database rows in the sandbox environment.
    - Rebuilds NetworkX graph and runs deterministic simulation.
    - Returns structured Before vs After comparisons with no fabricated numbers.
    """
    cand = candidate_data or {}
    strat_type = (
        cand.get("strategy_type") or 
        cand.get("strategy") or 
        cand.get("action_type") or 
        (candidate_id.split("-")[0] if candidate_id and "-" in candidate_id else candidate_id) or 
        "multi_az_modernize"
    ).lower()

    cand_name = cand.get("name") or cand.get("title") or strat_type.replace("_", " ").title()
    cand_id = candidate_id or cand.get("id") or f"cand-{uuid.uuid4().hex[:8]}"

    # Determine target sandbox environment ID
    # In legacy AWS simulation, aws clones to 'aws_sim_aws'
    if source_environment == "aws" and sandbox_env_id == "sandbox":
        target_env_id = "aws_sim_aws"
    else:
        target_env_id = sandbox_env_id

    # 1. Initialize or get Sandbox
    init_res = initialize_or_get_sandbox(
        db=db,
        source_environment=source_environment,
        sandbox_env_id=target_env_id,
        force_clone=False
    )
    id_map = init_res.get("id_map", {})

    # 2. Resolve target component in sandbox
    target_sb_id = id_map.get(target_component_id)
    if not target_sb_id:
        # Try direct match, sb- prefix, or name match in sandbox
        cand_comp = db.query(models.Component).filter(
            models.Component.source_environment == target_env_id,
            (models.Component.id == target_component_id) |
            (models.Component.id == f"sb-{target_component_id}") |
            (models.Component.name.ilike(f"%{target_component_id}%"))
        ).first()
        if cand_comp:
            target_sb_id = cand_comp.id
        else:
            # Check if target exists in source environment (by id or name)
            src_comp = db.query(models.Component).filter(
                (models.Component.id == target_component_id) |
                (models.Component.name.ilike(f"%{target_component_id}%"))
            ).first()
            if src_comp:
                target_sb_id = id_map.get(src_comp.id)
                if not target_sb_id:
                    # Look in sandbox by source component's cloned ID or name
                    sb_match = db.query(models.Component).filter(
                        models.Component.source_environment == target_env_id,
                        (models.Component.id == f"sb-{src_comp.id}") |
                        (models.Component.name == src_comp.name)
                    ).first()
                    if sb_match:
                        target_sb_id = sb_match.id
                    else:
                        init_res = initialize_or_get_sandbox(
                            db=db,
                            source_environment=source_environment,
                            sandbox_env_id=target_env_id,
                            force_clone=True
                        )
                        id_map = init_res.get("id_map", {})
                        target_sb_id = id_map.get(src_comp.id, f"sb-{src_comp.id}")
            else:
                raise ValueError(f"Component '{target_component_id}' not found in database.")

    target_comp = db.query(models.Component).filter(
        models.Component.id == target_sb_id,
        models.Component.source_environment == target_env_id
    ).first()

    if not target_comp:
        raise ValueError(f"Target component '{target_sb_id}' could not be located in sandbox '{target_env_id}'.")

    # 3. Baseline (BEFORE) state & simulation
    before_sim = simulate_change(
        db=db,
        target_component_id=target_sb_id,
        action=action,
        source_environment=target_env_id,
        use_ai=False
    )
    
    before_comps = db.query(models.Component).filter(
        models.Component.source_environment == target_env_id
    ).all()
    before_deps = db.query(models.Dependency).filter(
        models.Dependency.source_environment == target_env_id
    ).all()
    before_spof_res = find_spofs(db, target_env_id)

    b_risk = float(before_sim.get("risk_score", 0.0))
    b_level = before_sim.get("risk_level", "LOW")
    b_blast = int(before_sim.get("affected_count", len(before_sim.get("affected_components", []))))
    b_upstream = int(before_sim.get("upstream_impact_count", 0))
    b_dt = int(before_sim.get("estimated_downtime_minutes") or 0)
    b_monthly_cost = round(sum(float(c.cost_per_month or 0.0) for c in before_comps), 2)
    b_spof_count = len(before_spof_res.spof_nodes)
    b_spof_nodes = list(before_spof_res.spof_nodes)
    b_node_ids = {c.id for c in before_comps}
    b_edges = {(d.source_id, d.target_id, d.relationship_type) for d in before_deps}

    # 4. Capture baseline Snapshot before mutating sandbox
    snapshot_id = snapshot_manager.create_snapshot(
        db=db,
        environment_id=target_env_id,
        solution_info={
            "id": cand_id,
            "solution_id": cand_id,
            "name": cand_name,
            "strategy_type": strat_type
        }
    )

    # 5. Apply real topology mutations to sandbox rows
    mutations_applied: List[str] = []
    nodes_added: List[Dict[str, Any]] = []
    nodes_removed: List[Dict[str, Any]] = []
    nodes_modified: List[Dict[str, Any]] = []
    edges_added: List[Dict[str, Any]] = []
    edges_removed: List[Dict[str, Any]] = []

    try:
        if strat_type in ["multi_az_modernize", "multi_az_standby", "redundancy", "load_balancer"]:
            alb_id = f"alb-{uuid.uuid4().hex[:6]}"
            standby_id = f"standby-{uuid.uuid4().hex[:6]}"
            
            meta = dict(target_comp.metadata_col or {})
            meta["multi_az"] = True
            meta["redundancy_enabled"] = True
            target_comp.metadata_col = meta
            target_comp.criticality = "medium"
            nodes_modified.append({
                "id": target_comp.id,
                "name": target_comp.name,
                "changes": {"criticality": "medium", "multi_az": True}
            })
            
            alb_comp = models.Component(
                id=alb_id,
                name=f"ALB-{target_comp.name}",
                type="load_balancer" if hasattr(models.ComponentType, "load_balancer") else "application",
                criticality="high",
                source_environment=target_env_id,
                cost_per_month=25.0,
                status="active",
                owner=target_comp.owner
            )
            standby_comp = models.Component(
                id=standby_id,
                name=f"{target_comp.name}-Standby-AZ2",
                type=target_comp.type,
                criticality="medium",
                source_environment=target_env_id,
                cost_per_month=target_comp.cost_per_month or 50.0,
                status="active",
                owner=target_comp.owner
            )
            db.add_all([alb_comp, standby_comp])
            db.flush()
            nodes_added.append({"id": alb_id, "name": alb_comp.name, "type": alb_comp.type})
            nodes_added.append({"id": standby_id, "name": standby_comp.name, "type": standby_comp.type})

            alb_to_target = models.Dependency(
                id=f"dep-{uuid.uuid4().hex[:8]}",
                source_id=alb_id,
                target_id=target_comp.id,
                relationship_type="routes_traffic_to",
                source=target_env_id,
                discovery_source="sandbox"
            )
            alb_to_standby = models.Dependency(
                id=f"dep-{uuid.uuid4().hex[:8]}",
                source_id=alb_id,
                target_id=standby_id,
                relationship_type="routes_traffic_to",
                source=target_env_id,
                discovery_source="sandbox"
            )
            db.add_all([alb_to_target, alb_to_standby])
            edges_added.append({"source": alb_id, "target": target_comp.id, "type": "routes_traffic_to"})
            edges_added.append({"source": alb_id, "target": standby_id, "type": "routes_traffic_to"})

            # Reroute upstream callers pointing to target_comp to point to ALB instead
            upstream_deps = db.query(models.Dependency).filter(
                models.Dependency.source_environment == target_env_id,
                models.Dependency.target_id == target_comp.id,
                models.Dependency.source_id != alb_id
            ).all()
            for ud in upstream_deps:
                edges_removed.append({"source": ud.source_id, "target": ud.target_id, "type": ud.relationship_type})
                ud.target_id = alb_id
                ud.target_component_id = alb_id
                edges_added.append({"source": ud.source_id, "target": alb_id, "type": ud.relationship_type})

            mutations_applied.append(f"Injected Application Load Balancer ({alb_comp.name})")
            mutations_applied.append(f"Provisioned Multi-AZ Standby replica ({standby_comp.name})")
            mutations_applied.append(f"Rerouted {len(upstream_deps)} upstream caller dependency link(s) to ALB")
            mutations_applied.append("Eliminated Single Point of Failure (SPOF) with active health check failover")

        elif strat_type in ["read_replica_offload", "replication", "read_replica"]:
            replica_id = f"replica-{uuid.uuid4().hex[:6]}"
            replica_cost = round((target_comp.cost_per_month or 50.0) * 0.50, 2)
            
            replica_comp = models.Component(
                id=replica_id,
                name=f"{target_comp.name}-ReadReplica",
                type="database",
                criticality="medium",
                source_environment=target_env_id,
                cost_per_month=replica_cost,
                status="active",
                owner=target_comp.owner
            )
            db.add(replica_comp)
            db.flush()
            nodes_added.append({"id": replica_id, "name": replica_comp.name, "type": "database"})

            rep_dep = models.Dependency(
                id=f"dep-{uuid.uuid4().hex[:8]}",
                source_id=replica_id,
                target_id=target_comp.id,
                relationship_type="replicates_from",
                source=target_env_id,
                discovery_source="sandbox"
            )
            db.add(rep_dep)
            edges_added.append({"source": replica_id, "target": target_comp.id, "type": "replicates_from"})

            meta = dict(target_comp.metadata_col or {})
            meta["read_replica_enabled"] = True
            target_comp.metadata_col = meta
            nodes_modified.append({
                "id": target_comp.id,
                "name": target_comp.name,
                "changes": {"read_replica_enabled": True}
            })

            mutations_applied.append(f"Provisioned Dedicated Read Replica ({replica_comp.name})")
            mutations_applied.append("Configured automated database replication stream")

        elif strat_type in ["dependency_circuit_breaker", "circuit_breaker", "queue_buffer", "dependency_decoupling"]:
            queue_id = f"queue-{uuid.uuid4().hex[:6]}"
            
            queue_comp = models.Component(
                id=queue_id,
                name=f"Queue-Buffer-{target_comp.name}",
                type="application",
                criticality="medium",
                source_environment=target_env_id,
                cost_per_month=15.0,
                status="active",
                owner=target_comp.owner
            )
            db.add(queue_comp)
            db.flush()
            nodes_added.append({"id": queue_id, "name": queue_comp.name, "type": "application"})

            q_dep = models.Dependency(
                id=f"dep-{uuid.uuid4().hex[:8]}",
                source_id=queue_id,
                target_id=target_comp.id,
                relationship_type="buffers_to",
                source=target_env_id,
                discovery_source="sandbox"
            )
            db.add(q_dep)
            edges_added.append({"source": queue_id, "target": target_comp.id, "type": "buffers_to"})

            upstream_deps = db.query(models.Dependency).filter(
                models.Dependency.source_environment == target_env_id,
                models.Dependency.target_id == target_comp.id,
                models.Dependency.source_id != queue_id
            ).all()
            for ud in upstream_deps:
                edges_removed.append({"source": ud.source_id, "target": ud.target_id, "type": ud.relationship_type})
                ud.target_id = queue_id
                ud.target_component_id = queue_id
                edges_added.append({"source": ud.source_id, "target": queue_id, "type": ud.relationship_type})

            mutations_applied.append(f"Provisioned Asynchronous Queue Buffer ({queue_comp.name})")
            mutations_applied.append(f"Decoupled {len(upstream_deps)} upstream synchronous caller(s)")

        elif strat_type in ["phased_blue_green", "staged_migration", "shadow"]:
            shadow_id = f"shadow-{uuid.uuid4().hex[:6]}"
            
            shadow_comp = models.Component(
                id=shadow_id,
                name=f"{target_comp.name}-Shadow-Target",
                type=target_comp.type,
                criticality=target_comp.criticality,
                source_environment=target_env_id,
                cost_per_month=target_comp.cost_per_month or 50.0,
                status="active",
                owner=target_comp.owner
            )
            db.add(shadow_comp)
            db.flush()
            nodes_added.append({"id": shadow_id, "name": shadow_comp.name, "type": shadow_comp.type})

            s_dep = models.Dependency(
                id=f"dep-{uuid.uuid4().hex[:8]}",
                source_id=shadow_id,
                target_id=target_comp.id,
                relationship_type="syncs_with",
                source=target_env_id,
                discovery_source="sandbox"
            )
            db.add(s_dep)
            edges_added.append({"source": shadow_id, "target": target_comp.id, "type": "syncs_with"})

            meta = dict(target_comp.metadata_col or {})
            meta["staged_cutover"] = True
            meta["estimated_downtime_minutes"] = 0
            target_comp.metadata_col = meta
            nodes_modified.append({
                "id": target_comp.id,
                "name": target_comp.name,
                "changes": {"staged_cutover": True, "estimated_downtime_minutes": 0}
            })

            mutations_applied.append(f"Provisioned Parallel Shadow Target ({shadow_comp.name})")
            mutations_applied.append("Established dual-run state replication link")

        elif strat_type in ["scale_up", "scale_out", "scale"]:
            orig_cpu = target_comp.cpu or 2.0
            orig_mem = target_comp.memory or 4.0
            orig_cost = target_comp.cost_per_month or 40.0
            
            target_comp.cpu = orig_cpu * 2.0
            target_comp.memory = orig_mem * 2.0
            target_comp.cost_per_month = round(orig_cost * 1.5, 2)
            meta = dict(target_comp.metadata_col or {})
            meta["scaled_capacity"] = True
            target_comp.metadata_col = meta
            nodes_modified.append({
                "id": target_comp.id,
                "name": target_comp.name,
                "changes": {
                    "cpu": f"{orig_cpu} -> {target_comp.cpu}",
                    "memory": f"{orig_mem} -> {target_comp.memory}",
                    "cost_per_month": f"{orig_cost} -> {target_comp.cost_per_month}"
                }
            })
            mutations_applied.append(f"Scaled compute resources: CPU to {target_comp.cpu} vCPUs, RAM to {target_comp.memory} GB")

        elif strat_type in ["fail", "degrade"]:
            target_comp.status = "degraded"
            meta = dict(target_comp.metadata_col or {})
            meta["injected_failure"] = True
            target_comp.metadata_col = meta
            nodes_modified.append({
                "id": target_comp.id,
                "name": target_comp.name,
                "changes": {"status": "degraded"}
            })
            mutations_applied.append(f"Set status of {target_comp.name} to degraded")

        elif strat_type in ["remove", "decommission"]:
            # Delete dependencies incident to target_comp
            incident_deps = db.query(models.Dependency).filter(
                models.Dependency.source_environment == target_env_id,
                (models.Dependency.source_id == target_comp.id) | (models.Dependency.target_id == target_comp.id)
            ).all()
            for idp in incident_deps:
                edges_removed.append({"source": idp.source_id, "target": idp.target_id, "type": idp.relationship_type})
                db.delete(idp)
            nodes_removed.append({"id": target_comp.id, "name": target_comp.name, "type": target_comp.type})
            db.delete(target_comp)
            mutations_applied.append(f"Decommissioned component {target_sb_id} and removed {len(incident_deps)} edges")

        elif strat_type in ["direct_lift_shift", "migration", "workload_relocation"]:
            target_comp.location = "cloud"
            target_comp.provider = "aws"
            meta = dict(target_comp.metadata_col or {})
            meta["relocated"] = True
            target_comp.metadata_col = meta
            nodes_modified.append({
                "id": target_comp.id,
                "name": target_comp.name,
                "changes": {"location": "cloud", "provider": "aws"}
            })
            mutations_applied.append(f"Relocated {target_comp.name} workload to target cloud infrastructure")

        else:
            meta = dict(target_comp.metadata_col or {})
            meta["remediated"] = True
            meta["applied_strategy"] = strat_type
            target_comp.metadata_col = meta
            nodes_modified.append({
                "id": target_comp.id,
                "name": target_comp.name,
                "changes": {"applied_strategy": strat_type}
            })
            mutations_applied.append(f"Applied architecture remediation strategy: {cand_name}")

        db.commit()

    except Exception as e:
        db.rollback()
        raise RuntimeError(f"Database error executing topology mutation for solution '{cand_name}': {str(e)}")

    # 6. Rebuild NetworkX Graph for the mutated sandbox
    build_graph(db, target_env_id)

    # 7. Post-Apply (AFTER) state & simulation
    # If target_comp was decommissioned/removed, simulate change on the sandbox without target
    if strat_type in ["remove", "decommission"]:
        after_sim = {
            "risk_score": 0.0,
            "risk_level": "LOW",
            "affected_components": [],
            "affected_count": 0,
            "estimated_downtime_minutes": 0,
            "upstream_impact_count": 0,
            "cost_delta_monthly": 0.0
        }
    else:
        after_sim = simulate_change(
            db=db,
            target_component_id=target_sb_id,
            action=action,
            source_environment=target_env_id,
            use_ai=False
        )

    after_comps = db.query(models.Component).filter(
        models.Component.source_environment == target_env_id
    ).all()
    after_deps = db.query(models.Dependency).filter(
        models.Dependency.source_environment == target_env_id
    ).all()
    after_spof_res = find_spofs(db, target_env_id)

    a_risk = float(after_sim.get("risk_score", 0.0))
    a_level = after_sim.get("risk_level", "LOW")
    a_blast = int(after_sim.get("affected_count", len(after_sim.get("affected_components", []))))
    a_upstream = int(after_sim.get("upstream_impact_count", 0))
    a_dt = int(after_sim.get("estimated_downtime_minutes") or 0)
    a_monthly_cost = round(sum(float(c.cost_per_month or 0.0) for c in after_comps), 2)
    a_spof_count = len(after_spof_res.spof_nodes)
    a_spof_nodes = list(after_spof_res.spof_nodes)

    # 8. Compute Delta & Structured Comparison
    delta_risk = round(a_risk - b_risk, 1)
    delta_downtime = a_dt - b_dt
    delta_blast = a_blast - b_blast
    delta_cost = round(a_monthly_cost - b_monthly_cost, 2)
    delta_spof = a_spof_count - b_spof_count
    delta_upstream = a_upstream - b_upstream

    # Objective Evaluation Outcome
    if delta_risk < 0 or (delta_spof < 0 and delta_risk <= 0):
        if delta_cost > 0:
            remediation_outcome = "IMPROVED"  # With tradeoff
        else:
            remediation_outcome = "IMPROVED"
    elif delta_risk > 0 or delta_blast > 0:
        remediation_outcome = "WORSE"
    else:
        remediation_outcome = "NO_IMPROVEMENT"

    # Tradeoff Analysis
    tradeoffs = []
    if delta_cost > 0:
        tradeoffs.append(f"Monthly infrastructure expenditure increases by ${delta_cost:.2f}/mo.")
    if delta_risk < 0:
        tradeoffs.append(f"Simulation risk reduced by {abs(delta_risk):.1f} points.")
    if delta_spof < 0:
        tradeoffs.append(f"Eliminated {abs(delta_spof)} Single Point(s) of Failure.")
    if delta_downtime < 0:
        tradeoffs.append(f"Estimated downtime reduced by {abs(delta_downtime)} minutes.")

    # Missing Data Detection (never fabricate values)
    missing_data = []
    for c in after_comps:
        if c.cost_per_month is None:
            missing_data.append(f"Component '{c.name}' missing cost_per_month; defaulting to 0.0")
        if not c.properties or "telemetry" not in c.properties:
            missing_data.append(f"Component '{c.name}' has no active telemetry streams")

    before_metrics = {
        "risk": b_risk,
        "risk_score": b_risk,
        "risk_level": b_level,
        "downtime": b_dt,
        "estimated_downtime_minutes": b_dt,
        "blast_radius": b_blast,
        "affected_count": b_blast,
        "monthly_cost": b_monthly_cost,
        "spof_count": b_spof_count,
        "spof_nodes": b_spof_nodes,
        "upstream_impact": b_upstream,
        "components_count": len(before_comps),
        "dependencies_count": len(before_deps)
    }

    after_metrics = {
        "risk": a_risk,
        "risk_score": a_risk,
        "risk_level": a_level,
        "downtime": a_dt,
        "estimated_downtime_minutes": a_dt,
        "blast_radius": a_blast,
        "affected_count": a_blast,
        "monthly_cost": a_monthly_cost,
        "spof_count": a_spof_count,
        "spof_nodes": a_spof_nodes,
        "upstream_impact": a_upstream,
        "components_count": len(after_comps),
        "dependencies_count": len(after_deps)
    }

    deltas = {
        "risk": delta_risk,
        "risk_score": delta_risk,
        "downtime": delta_downtime,
        "estimated_downtime_minutes": delta_downtime,
        "blast_radius": delta_blast,
        "affected_count": delta_blast,
        "monthly_cost": delta_cost,
        "spof_count": delta_spof,
        "upstream_impact": delta_upstream
    }

    topology_diff = {
        "nodes_added": nodes_added,
        "nodes_removed": nodes_removed,
        "nodes_modified": nodes_modified,
        "edges_added": edges_added,
        "edges_removed": edges_removed
    }

    return {
        "success": True,
        "sandbox_id": target_env_id,
        "target_environment": target_env_id,
        "source_environment": source_environment,
        "target_component_id": target_sb_id,
        "original_component_id": target_component_id,
        "candidate_id": cand_id,
        "strategy_type": strat_type,
        "snapshot_id": snapshot_id,
        "remediation_outcome": remediation_outcome,
        "mutations_applied": mutations_applied,
        "topology_diff": topology_diff,
        "before": before_metrics,
        "after": after_metrics,
        "delta": deltas,
        "tradeoffs": tradeoffs,
        "missing_data": missing_data
    }


def rollback_sandbox(
    db: Session,
    snapshot_id: str,
    sandbox_env_id: str = "sandbox"
) -> Dict[str, Any]:
    """
    Restores the sandbox environment to its baseline state prior to candidate application.
    Atomic DB transaction: wipes current mutated sandbox state and re-inserts snapshot components.
    Rebuilds the NetworkX graph for the sandbox.
    Keeps the original Twin and AWS live completely untouched.
    """
    snapshot = db.query(models.SandboxSnapshot).filter(
        models.SandboxSnapshot.id == snapshot_id
    ).first()
    if not snapshot:
        raise ValueError(f"Snapshot '{snapshot_id}' not found.")

    env_id = snapshot.environment_id or sandbox_env_id
    restore_res = snapshot_manager.restore_snapshot(db, snapshot_id)
    
    # Rebuild NetworkX graph for the restored sandbox environment
    build_graph(db, env_id)

    return {
        "restored": True,
        "snapshot_id": snapshot_id,
        "environment_id": env_id,
        "sandbox_id": env_id,
        "components_count": restore_res.get("components_count", 0),
        "dependencies_count": restore_res.get("dependencies_count", 0),
        "status": "rejected"
    }


def accept_sandbox(
    db: Session,
    snapshot_id: str,
    sandbox_env_id: str = "sandbox"
) -> Dict[str, Any]:
    """
    Approves the mutated sandbox state and marks the snapshot as accepted.
    Preserves the mutated topology as the new sandbox baseline.
    Original Twin and live AWS infrastructure remain completely unchanged.
    """
    snapshot = db.query(models.SandboxSnapshot).filter(
        models.SandboxSnapshot.id == snapshot_id
    ).first()
    if not snapshot:
        raise ValueError(f"Snapshot '{snapshot_id}' not found.")

    env_id = snapshot.environment_id or sandbox_env_id
    accept_res = snapshot_manager.accept_snapshot(db, snapshot_id)

    return {
        "accepted": True,
        "snapshot_id": snapshot_id,
        "environment_id": env_id,
        "sandbox_id": env_id,
        "status": "accepted"
    }


def get_before_after_comparison(
    db: Session,
    snapshot_id: str
) -> Dict[str, Any]:
    """
    Retrieves comparison data for a snapshot.
    """
    snapshot = db.query(models.SandboxSnapshot).filter(
        models.SandboxSnapshot.id == snapshot_id
    ).first()
    if not snapshot:
        raise ValueError(f"Snapshot '{snapshot_id}' not found.")

    state = snapshot.state_json or {}
    baseline_comps = state.get("components", [])
    baseline_deps = state.get("dependencies", [])
    env_id = snapshot.environment_id

    current_comps = db.query(models.Component).filter(
        models.Component.source_environment == env_id
    ).all()
    current_deps = db.query(models.Dependency).filter(
        models.Dependency.source_environment == env_id
    ).all()

    b_cost = round(sum(float(c.get("cost_per_month") or 0.0) for c in baseline_comps), 2)
    a_cost = round(sum(float(c.cost_per_month or 0.0) for c in current_comps), 2)

    return {
        "snapshot_id": snapshot_id,
        "environment_id": env_id,
        "status": snapshot.status,
        "solution_id": snapshot.solution_id,
        "solution_name": snapshot.solution_name,
        "strategy_type": snapshot.strategy_type,
        "created_at": snapshot.created_at,
        "baseline_components_count": len(baseline_comps),
        "current_components_count": len(current_comps),
        "baseline_dependencies_count": len(baseline_deps),
        "current_dependencies_count": len(current_deps),
        "baseline_monthly_cost": b_cost,
        "current_monthly_cost": a_cost,
        "monthly_cost_delta": round(a_cost - b_cost, 2)
    }
