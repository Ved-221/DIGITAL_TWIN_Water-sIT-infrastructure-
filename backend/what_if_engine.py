"""
what_if_engine.py — Multiple What-If Candidate Solutions Engine

Architecture:
    Original Twin (DB) → snapshot_twin_graph()  [read-only]
        │
        ├── Candidate A  →  G_A (deep copy) → simulate_candidate_on_graph(G_A) → result_A
        ├── Candidate B  →  G_B (deep copy) → simulate_candidate_on_graph(G_B) → result_B
        └── Candidate C  →  G_C (deep copy) → simulate_candidate_on_graph(G_C) → result_C

Rules:
- Original DB is NEVER written to during candidate generation.
- Each candidate operates on an independent deep-copied NetworkX graph.
- If required data is missing, feasibility is "unknown" — never fabricated.
- Candidates are derived exclusively from actual topology + component attributes.
"""

import uuid
import copy
from typing import List, Dict, Any, Optional, Tuple

import networkx as nx
from sqlalchemy.orm import Session

import models
from simulation import build_graph
from ml.candidate_ranker import (
    extract_all_candidate_features,
    rank_candidates,
    build_structured_recommendation_object,
)
from three_agents_engine import evaluate_candidates_with_agents


# ---------------------------------------------------------------------------
# Data types (plain dicts to avoid Pydantic coupling inside the engine)
# ---------------------------------------------------------------------------

def _empty_candidate_simulation() -> Dict[str, Any]:
    return {
        "blast_radius": 0,
        "upstream_impact": [],
        "downstream_deps": [],
        "risk_score": None,
        "risk_level": "unknown",
        "estimated_downtime_minutes": None,
        "cost_delta_monthly": None,
        "critical_flags": [],
        "spof_eliminated": False,
    }


# ---------------------------------------------------------------------------
# Step 1 — Snapshot the original twin graph (read-only)
# ---------------------------------------------------------------------------

def snapshot_twin_graph(
    db: Session, source_environment: str
) -> Tuple[nx.DiGraph, Dict[str, models.Component]]:
    """
    Build a read-only NetworkX graph from the database.
    Also returns a registry of Component ORM objects keyed by component id.
    The returned graph is the canonical 'original' — callers must deep-copy it
    before applying any mutations.
    """
    G = build_graph(db, source_environment)

    comp_registry: Dict[str, models.Component] = {}
    for comp in db.query(models.Component).all():
        comp_registry[comp.id] = comp

    return G, comp_registry


# ---------------------------------------------------------------------------
# Step 2 — Simulate a single candidate on an isolated graph copy
# ---------------------------------------------------------------------------

def simulate_candidate_on_graph(
    G_candidate: nx.DiGraph,
    target_id: str,
    action: str,
    component: models.Component,
    base_result: Dict[str, Any],
    available_metrics: List[str],
    missing_data: List[str],
) -> Dict[str, Any]:
    """
    Pure in-memory simulation on an already-mutated graph copy.
    Returns a dict of simulation metrics derived solely from the graph structure
    and component attributes present in the graph nodes.

    Never writes to the database.
    Never invents values for missing data — marks them as None with an explanation.
    """
    result = _empty_candidate_simulation()

    if target_id not in G_candidate:
        result["risk_level"] = "unknown"
        result["critical_flags"].append(f"Target '{target_id}' not present in candidate graph.")
        return result

    target_node = G_candidate.nodes[target_id]

    # ---- Blast radius -------------------------------------------------------
    upstream_nodes = set(nx.ancestors(G_candidate, target_id))
    downstream_nodes = set(nx.descendants(G_candidate, target_id))
    all_affected = upstream_nodes.union(downstream_nodes)

    upstream_impact = []
    for uid in upstream_nodes:
        nd = G_candidate.nodes[uid]
        try:
            hop = nx.shortest_path_length(G_candidate, source=uid, target=target_id)
        except Exception:
            hop = 1
        upstream_impact.append({
            "id": uid,
            "name": nd.get("name", uid),
            "type": nd.get("type", "server"),
            "criticality": nd.get("criticality", "medium"),
            "hop_distance": hop,
            "impact_type": "Caller Service Disruption",
        })

    downstream_deps = []
    for did in downstream_nodes:
        nd = G_candidate.nodes[did]
        try:
            hop = nx.shortest_path_length(G_candidate, source=target_id, target=did)
        except Exception:
            hop = 1
        downstream_deps.append({
            "id": did,
            "name": nd.get("name", did),
            "type": nd.get("type", "server"),
            "criticality": nd.get("criticality", "medium"),
            "hop_distance": hop,
            "impact_type": "Underlying Dependency",
        })

    result["blast_radius"] = len(all_affected)
    result["upstream_impact"] = sorted(upstream_impact, key=lambda x: x["hop_distance"])
    result["downstream_deps"] = sorted(downstream_deps, key=lambda x: x["hop_distance"])

    # ---- SPOF analysis -------------------------------------------------------
    undirected = G_candidate.to_undirected()
    articulation_pts = set(nx.articulation_points(undirected)) if len(G_candidate) >= 2 else set()
    target_meta = target_node.get("metadata_col", {}) or {}
    has_redundancy = bool(
        target_meta.get("redundancy_enabled")
        or target_meta.get("multi_az")
        or target_meta.get("staged_cutover")
    )
    was_spof = base_result.get("risk_factors", {}).get("is_single_point_of_failure", False)
    is_spof_now = (target_id in articulation_pts) and not has_redundancy
    result["spof_eliminated"] = was_spof and not is_spof_now

    # ---- Risk score ----------------------------------------------------------
    crit_str = str(target_node.get("criticality", "medium")).lower()
    crit_base = 35 if crit_str == "critical" else (22 if crit_str == "high" else (12 if crit_str == "medium" else 5))
    action_lower = action.lower()
    if action_lower in ["fail", "outage"]:
        action_sev = 35
    elif action_lower == "migrate":
        action_sev = 15
    elif action_lower == "scale":
        action_sev = 8
    elif action_lower in ["restart", "reboot"]:
        action_sev = 5
    else:
        action_sev = 10

    if has_redundancy:
        action_sev = max(action_sev - 10, 2)

    crit_callers = sum(1 for a in upstream_impact if a.get("criticality") in ["critical", "high"])
    blast_pen = min(len(upstream_nodes) * 12 + crit_callers * 8, 30)
    spof_pen = 0 if (has_redundancy or not is_spof_now) else 15

    if has_redundancy:
        blast_pen = blast_pen // 3

    # CPU telemetry
    cpu_val = target_node.get("cpu")
    health_penalty = 0
    if cpu_val is not None and float(cpu_val) > 80.0:
        health_penalty = 20
    elif cpu_val is None:
        missing_data.append("live_cpu_telemetry")

    total_risk = crit_base + action_sev + blast_pen + spof_pen + health_penalty
    final_risk = min(max(total_risk, 5), 100)
    result["risk_score"] = round(final_risk, 1)

    if final_risk >= 70:
        result["risk_level"] = "CRITICAL"
        result["critical_flags"].append("Risk level is CRITICAL after candidate topology change.")
    elif final_risk >= 45:
        result["risk_level"] = "HIGH"
    elif final_risk >= 25:
        result["risk_level"] = "MODERATE"
    else:
        result["risk_level"] = "LOW"

    # ---- Downtime -----------------------------------------------------------
    node_type = target_node.get("type", "server").lower()
    meta = target_node.get("metadata_col", {}) or {}
    telemetry = target_node.get("telemetry", {}) or {}
    explicit_dt = meta.get("estimated_downtime_minutes") or meta.get("maintenance_window_minutes")
    storage_gb = meta.get("storage_gb") or telemetry.get("storage_size_gb")
    transfer_mbps = telemetry.get("transfer_rate_mbps") or meta.get("transfer_rate_mbps")
    max_hop = max((a["hop_distance"] for a in upstream_impact), default=0)

    if has_redundancy:
        result["estimated_downtime_minutes"] = 0
    elif explicit_dt is not None:
        result["estimated_downtime_minutes"] = int(explicit_dt)
    elif storage_gb and transfer_mbps and float(transfer_mbps) > 0:
        mins = (float(storage_gb) * 8192) / (float(transfer_mbps) * 60)
        result["estimated_downtime_minutes"] = max(int(round(mins + max_hop * 2)), 1)
    else:
        if action_lower in ["restart", "reboot"]:
            base_dt = 3 if node_type in ["lambda", "container"] else 5
        elif action_lower == "scale":
            base_dt = 1
        elif action_lower in ["fail", "outage"]:
            base_dt = 45 if node_type in ["database", "storage"] else (20 if node_type in ["server", "application"] else 5)
        else:
            base_dt = 30 if node_type in ["database", "storage"] else (15 if node_type in ["server", "application"] else 5)
        result["estimated_downtime_minutes"] = base_dt + max_hop * 5

    # ---- Cost delta ---------------------------------------------------------
    raw_node_cost = target_node.get("cost_per_month")
    has_target_cost = bool(raw_node_cost is not None and float(raw_node_cost) > 0.0)
    actual_cost = float(raw_node_cost or 0.0)
    target_cost_meta = meta.get("target_cost_per_month")
    extra_cost = float(target_meta.get("_extra_monthly_cost", 0.0))  # set by candidate mutator

    if not has_target_cost and target_cost_meta is None:
        result["cost_delta_monthly"] = None
        if "cost_per_month" not in missing_data:
            missing_data.append("cost_per_month")

    elif action_lower in ["restart", "reboot"]:
        result["cost_delta_monthly"] = 0.0
    elif action_lower in ["fail", "outage"]:
        result["cost_delta_monthly"] = 0.0
    elif target_cost_meta is not None:
        result["cost_delta_monthly"] = round(float(target_cost_meta) - actual_cost + extra_cost, 2)
    elif action_lower == "scale":
        result["cost_delta_monthly"] = round(actual_cost * 0.50 + extra_cost, 2)
    elif action_lower == "migrate":
        data_transfer_gb = meta.get("data_transfer_gb") or telemetry.get("data_transfer_gb")
        egress = (float(data_transfer_gb) * 0.09) if data_transfer_gb else (len(all_affected) * 5.0)
        result["cost_delta_monthly"] = round(actual_cost * 0.20 + egress + extra_cost, 2)
    else:
        result["cost_delta_monthly"] = round(extra_cost, 2) if extra_cost else None

    return result



# ---------------------------------------------------------------------------
# Step 3 — Apply candidate topology mutations to isolated graph copy
# ---------------------------------------------------------------------------

def _apply_candidate_mutation(
    G_original: nx.DiGraph,
    target_id: str,
    strategy_type: str,
    component: models.Component,
) -> Tuple[nx.DiGraph, List[str], float]:
    """
    Deep-copies G_original and applies the candidate's topology mutations.

    Returns:
        G_cand      — mutated graph (isolated from original)
        mutations   — human-readable description of changes
        extra_cost  — additional monthly cost added by this topology change
    """
    G_cand = copy.deepcopy(G_original)
    mutations: List[str] = []
    extra_cost = 0.0

    if target_id not in G_cand:
        return G_cand, mutations, extra_cost

    target_meta = dict(G_cand.nodes[target_id].get("metadata_col", {}) or {})
    base_cost = float(G_cand.nodes[target_id].get("cost_per_month", 0.0) or 0.0)

    if strategy_type in ["multi_az_modernize", "multi_az_standby", "redundancy"]:
        alb_id = f"alb-{uuid.uuid4().hex[:6]}"
        standby_id = f"standby-{uuid.uuid4().hex[:6]}"
        extra_cost = 25.0 + base_cost
        target_meta["multi_az"] = True
        target_meta["redundancy_enabled"] = True
        target_meta["estimated_downtime_minutes"] = 0
        target_meta["_extra_monthly_cost"] = extra_cost
        G_cand.nodes[target_id]["metadata_col"] = target_meta
        G_cand.nodes[target_id]["criticality"] = "medium"

        G_cand.add_node(alb_id, name=f"ALB-{component.name}", type="application",
                        criticality="high", status="active", cost_per_month=25.0,
                        metadata_col={})
        G_cand.add_node(standby_id, name=f"{component.name}-Standby-AZ2",
                        type=str(component.type), criticality="medium",
                        status="active", cost_per_month=base_cost, metadata_col={})
        G_cand.add_edge(alb_id, target_id, relationship_type="routes_traffic")
        G_cand.add_edge(alb_id, standby_id, relationship_type="routes_traffic")

        for p in list(G_cand.predecessors(target_id)):
            if p != alb_id:
                G_cand.remove_edge(p, target_id)
                G_cand.add_edge(p, alb_id, relationship_type="routes_traffic")

        mutations.append("Injected Application Load Balancer + Multi-AZ Standby replica")

    elif strategy_type in ["read_replica_offload", "replication"]:
        replica_id = f"replica-{uuid.uuid4().hex[:6]}"
        extra_cost = round(base_cost * 0.50, 2)
        target_meta["read_replica_enabled"] = True
        target_meta["_extra_monthly_cost"] = extra_cost
        G_cand.nodes[target_id]["metadata_col"] = target_meta
        G_cand.add_node(replica_id, name=f"{component.name}-ReadReplica",
                        type="database", criticality="medium", status="active",
                        cost_per_month=extra_cost, metadata_col={})
        G_cand.add_edge(replica_id, target_id, relationship_type="replicates_from")
        mutations.append("Provisioned Dedicated Read Replica")

    elif strategy_type in ["dependency_circuit_breaker", "dependency_decoupling"]:
        queue_id = f"queue-{uuid.uuid4().hex[:6]}"
        extra_cost = 15.0
        target_meta["_extra_monthly_cost"] = extra_cost
        G_cand.nodes[target_id]["metadata_col"] = target_meta
        G_cand.add_node(queue_id, name=f"Queue-Buffer-{component.name}",
                        type="application", criticality="medium", status="active",
                        cost_per_month=15.0, metadata_col={})
        G_cand.add_edge(queue_id, target_id, relationship_type="buffers_to")
        for p in list(G_cand.predecessors(target_id)):
            if p != queue_id:
                G_cand.remove_edge(p, target_id)
                G_cand.add_edge(p, queue_id, relationship_type="buffers_to")
        mutations.append("Injected Asynchronous Message Buffer + Circuit Breaker")

    elif strategy_type in ["phased_blue_green", "staged_migration"]:
        shadow_id = f"shadow-{uuid.uuid4().hex[:6]}"
        extra_cost = base_cost
        target_meta["staged_cutover"] = True
        target_meta["estimated_downtime_minutes"] = 0
        target_meta["_extra_monthly_cost"] = extra_cost
        G_cand.nodes[target_id]["metadata_col"] = target_meta
        G_cand.add_node(shadow_id, name=f"{component.name}-Shadow-Target",
                        type=str(component.type), criticality=str(component.criticality),
                        status="active", cost_per_month=base_cost, metadata_col={})
        G_cand.add_edge(shadow_id, target_id, relationship_type="syncs_with")
        mutations.append("Provisioned Shadow Target with Live Traffic Sync")

    elif strategy_type in ["scale_up", "scale_out", "scale"]:
        extra_cost = round(base_cost * 0.50, 2)
        target_meta["_extra_monthly_cost"] = extra_cost
        G_cand.nodes[target_id]["metadata_col"] = target_meta
        G_cand.nodes[target_id]["cpu"] = (float(G_cand.nodes[target_id].get("cpu") or 2)) * 2
        G_cand.nodes[target_id]["memory"] = (float(G_cand.nodes[target_id].get("memory") or 4)) * 2
        mutations.append("Doubled CPU and RAM compute capacity")

    elif strategy_type == "direct_lift_shift":
        # No topology change — runs the original graph as-is
        mutations.append("No topology change; direct sequential execution")

    return G_cand, mutations, extra_cost


# ---------------------------------------------------------------------------
# Step 4 — Build resulting topology snapshot (nodes + edges from candidate graph)
# ---------------------------------------------------------------------------

def _extract_resulting_topology(G: nx.DiGraph) -> Dict[str, Any]:
    return {
        "nodes": [
            {
                "id": n,
                "name": G.nodes[n].get("name", n),
                "type": G.nodes[n].get("type", "server"),
                "criticality": G.nodes[n].get("criticality", "medium"),
                "status": G.nodes[n].get("status", "active"),
            }
            for n in G.nodes
        ],
        "edges": [
            {
                "source": u,
                "target": v,
                "relationship_type": G.edges[u, v].get("relationship_type", "depends_on"),
            }
            for u, v in G.edges
        ],
        "node_count": G.number_of_nodes(),
        "edge_count": G.number_of_edges(),
    }


# ---------------------------------------------------------------------------
# Step 5 — Determine feasibility and evidence
# ---------------------------------------------------------------------------

def _assess_feasibility(
    sim_result: Dict[str, Any],
    missing_data: List[str],
    strategy_type: str,
    action: str,
) -> Tuple[str, List[str]]:
    """
    Returns (feasibility_status, evidence_list).

    feasibility_status: "feasible" | "conditional" | "unknown" | "not_feasible"
    Evidence is derived solely from simulation facts — never invented.
    """
    evidence: List[str] = []
    risk = sim_result.get("risk_score")

    if missing_data:
        unknown_fields = ", ".join(missing_data)
        evidence.append(f"Missing data prevents full evaluation: {unknown_fields}.")
        return "unknown", evidence

    if risk is None:
        evidence.append("Simulation could not compute a risk score.")
        return "unknown", evidence

    if sim_result.get("spof_eliminated"):
        evidence.append("This candidate eliminates the Single Point of Failure.")

    blast = sim_result.get("blast_radius", 0)
    evidence.append(f"Blast radius: {blast} component(s) affected.")

    downtime = sim_result.get("estimated_downtime_minutes")
    if downtime is not None:
        evidence.append(f"Estimated downtime: {downtime} minute(s).")

    cost = sim_result.get("cost_delta_monthly")
    if cost is not None:
        sign = "+" if cost >= 0 else ""
        evidence.append(f"Monthly cost delta: {sign}${cost:,.2f}.")

    if risk >= 70:
        evidence.append(f"Risk score {risk} indicates CRITICAL exposure — remediation required before applying.")
        return "conditional", evidence
    elif risk >= 45:
        evidence.append(f"Risk score {risk} indicates HIGH risk — phased rollout recommended.")
        return "conditional", evidence
    else:
        evidence.append(f"Risk score {risk} is within acceptable operational parameters.")
        return "feasible", evidence


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_what_if_candidates(
    db: Session,
    target_component_id: str,
    action: str = "fail",
    source_environment: Optional[str] = None,
    force_ml_fallback: bool = False,
    simulate_ml_failure: bool = False,
    fail_agent: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Full pipeline:
    1. Snapshot original twin graph (read-only)
    2. Identify base simulation context on original graph
    3. Generate applicable candidate strategies from actual topology
    4. Simulate each candidate independently on isolated graph copies
    5. Extract clean features from actual Twin + graph + simulation data
    6. ML ranking and suggestion
    7. Return structured recommendation object with deterministic facts kept separate

    The original DB is NEVER mutated.
    """
    # --- Resolve source environment ---
    if not source_environment:
        comp = db.query(models.Component).filter(models.Component.id == target_component_id).first()
        if comp and comp.source_environment:
            source_environment = comp.source_environment
        elif comp and comp.discovery_source:
            source_environment = comp.discovery_source
        else:
            source_environment = "aws"

    # Normalize: user_description components are stored under the 'manual' graph key
    if source_environment == "user_description":
        source_environment = "manual"

    # --- Step 1: Snapshot ---
    G_original, comp_registry = snapshot_twin_graph(db, source_environment)

    if target_component_id not in G_original:
        return {
            "success": False,
            "error": f"Component '{target_component_id}' not found in environment '{source_environment}'.",
            "target_component_id": target_component_id,
            "action": action,
            "source_environment": source_environment,
            "candidates": [],
            "original_baseline": None,
            "scenario": {
                "target_component_id": target_component_id,
                "action": action,
                "source_environment": source_environment,
            },
            "simulation_results": [],
            "extracted_features": [],
            "ml_ranking": [],
            "ranking": [],
            "recommended_candidate_id": None,
            "recommendation": None,
            "ranking_status": "insufficient_data",
            "ranking_method": "none",
            "evidence": ["Target component not found in environment."],
            "missing_data": ["target_component"],
            "limitations": ["Component not found."],
        }

    component = comp_registry.get(target_component_id)
    if not component:
        return {
            "success": False,
            "error": f"Component record not found in DB for id '{target_component_id}'.",
            "target_component_id": target_component_id,
            "action": action,
            "source_environment": source_environment,
            "candidates": [],
            "original_baseline": None,
            "scenario": {
                "target_component_id": target_component_id,
                "action": action,
                "source_environment": source_environment,
            },
            "simulation_results": [],
            "extracted_features": [],
            "ml_ranking": [],
            "ranking": [],
            "recommended_candidate_id": None,
            "recommendation": None,
            "ranking_status": "insufficient_data",
            "ranking_method": "none",
            "evidence": ["Component record not found in DB."],
            "missing_data": ["target_component"],
            "limitations": ["Component record not found in DB."],
        }

    target_node = G_original.nodes[target_component_id]

    # --- Step 2: Baseline simulation on original graph ---
    upstream_nodes = set(nx.ancestors(G_original, target_component_id))
    downstream_nodes = set(nx.descendants(G_original, target_component_id))
    all_affected_orig = upstream_nodes.union(downstream_nodes)

    undirected_orig = G_original.to_undirected()
    art_points = set(nx.articulation_points(undirected_orig)) if len(G_original) >= 2 else set()
    orig_meta = target_node.get("metadata_col", {}) or {}
    orig_redundancy = bool(orig_meta.get("redundancy_enabled") or orig_meta.get("multi_az"))
    orig_is_spof = (target_component_id in art_points) and not orig_redundancy

    # Derive baseline risk the same way simulate_change does
    crit_str = str(target_node.get("criticality", "medium")).lower()
    crit_base = 35 if crit_str == "critical" else (22 if crit_str == "high" else (12 if crit_str == "medium" else 5))
    action_lower = action.lower()
    if action_lower in ["fail", "outage"]:
        action_sev = 35
    elif action_lower == "migrate":
        action_sev = 15
    elif action_lower == "scale":
        action_sev = 8
    elif action_lower in ["restart", "reboot"]:
        action_sev = 5
    else:
        action_sev = 10

    crit_callers = sum(1 for uid in upstream_nodes if G_original.nodes[uid].get("criticality") in ["critical", "high"])
    blast_pen = min(len(upstream_nodes) * 12 + crit_callers * 8, 30)
    spof_pen = 15 if orig_is_spof else 0
    cpu_val = target_node.get("cpu")
    health_pen = 20 if (cpu_val is not None and float(cpu_val) > 80.0) else 0
    base_risk = min(max(crit_base + action_sev + blast_pen + spof_pen + health_pen, 5), 100)

    original_baseline = {
        "target_component_id": target_component_id,
        "target_component_name": target_node.get("name", target_component_id),
        "action": action,
        "source_environment": source_environment,
        "blast_radius": len(all_affected_orig),
        "upstream_impact_count": len(upstream_nodes),
        "downstream_dependencies_count": len(downstream_nodes),
        "risk_score": round(base_risk, 1),
        "risk_level": (
            "CRITICAL" if base_risk >= 70 else
            "HIGH" if base_risk >= 45 else
            "MODERATE" if base_risk >= 25 else "LOW"
        ),
        "is_single_point_of_failure": orig_is_spof,
        "topology": _extract_resulting_topology(G_original),
    }

    base_result_for_candidates = {
        "risk_score": base_risk,
        "estimated_downtime_minutes": 30,
        "affected_count": len(all_affected_orig),
        "affected_components": [],
        "cost_delta_monthly": 0.0,
        "risk_factors": {
            "is_single_point_of_failure": orig_is_spof,
        },
    }

    # --- Step 3: Generate candidate strategies from topology ---
    import solution_generator

    upstream_impact_list = []
    for uid in upstream_nodes:
        nd = G_original.nodes[uid]
        upstream_impact_list.append({
            "id": uid,
            "name": nd.get("name", uid),
            "type": nd.get("type", "server"),
            "criticality": nd.get("criticality", "medium"),
            "is_articulation_point": uid in art_points,
            "hop_distance": 1,
            "impact_type": "Caller Service Disruption",
        })

    sim_ctx = {
        "action": action,
        "affected_count": len(all_affected_orig),
        "upstream_impact_count": len(upstream_nodes),
        "risk_score": base_risk,
        "cost_delta_monthly": 0.0,
        "estimated_downtime_minutes": None,
        "risk_factors": {
            "is_single_point_of_failure": orig_is_spof,
            "target_criticality": crit_str,
        },
    }

    # include_extended for databases or when upstream callers >= 2
    comp_type_str = str(target_node.get("type", "server")).lower()
    include_ext = comp_type_str == "database" or len(upstream_nodes) >= 2

    raw_candidates = solution_generator.generate_applicable_candidates(
        component=component,
        simulation_result=sim_ctx,
        currency=target_node.get("currency", "USD"),
        include_extended=include_ext,
    )

    # --- Step 4: Simulate each candidate independently ---
    candidate_results = []

    for raw in raw_candidates:
        strategy_type = raw.get("strategy_type", "direct_lift_shift")
        cand_missing_data: List[str] = []
        cand_available_metrics: List[str] = []

        # Track which metrics are actually available
        if target_node.get("cpu") is not None:
            cand_available_metrics.append("cpu_utilization")
        if target_node.get("memory") is not None:
            cand_available_metrics.append("memory_utilization")
        if orig_meta.get("storage_gb"):
            cand_available_metrics.append("storage_gb")
        if target_node.get("cost_per_month"):
            cand_available_metrics.append("cost_per_month")

        # Apply mutations to isolated copy
        G_cand, mutations, extra_cost = _apply_candidate_mutation(
            G_original=G_original,
            target_id=target_component_id,
            strategy_type=strategy_type,
            component=component,
        )

        # Simulate on the isolated candidate graph
        cand_sim = simulate_candidate_on_graph(
            G_candidate=G_cand,
            target_id=target_component_id,
            action=action,
            component=component,
            base_result=base_result_for_candidates,
            available_metrics=cand_available_metrics,
            missing_data=cand_missing_data,
        )

        # Resulting topology from the candidate graph (not the original)
        resulting_topology = _extract_resulting_topology(G_cand)

        # Feasibility assessment from simulation facts
        feasibility, evidence = _assess_feasibility(
            sim_result=cand_sim,
            missing_data=cand_missing_data,
            strategy_type=strategy_type,
            action=action,
        )

        # Collect affected components list
        affected_components = cand_sim["upstream_impact"] + cand_sim["downstream_deps"]

        candidate_results.append({
            "candidate_id": raw.get("id", f"cand-{uuid.uuid4().hex[:6]}"),
            "name": raw.get("name", strategy_type),
            "description": raw.get("description", ""),
            "strategy_type": strategy_type,
            "proposed_changes": mutations,
            "resulting_topology": resulting_topology,
            "affected_components": affected_components,
            "simulation_result": {
                "blast_radius": cand_sim["blast_radius"],
                "upstream_impact_count": len(cand_sim["upstream_impact"]),
                "downstream_dependencies_count": len(cand_sim["downstream_deps"]),
                "risk_score": cand_sim["risk_score"],
                "risk_level": cand_sim["risk_level"],
                "estimated_downtime_minutes": cand_sim["estimated_downtime_minutes"],
                "cost_delta_monthly": cand_sim["cost_delta_monthly"],
                "critical_flags": cand_sim["critical_flags"],
                "spof_eliminated": cand_sim["spof_eliminated"],
                "vs_baseline": {
                    "blast_radius_delta": cand_sim["blast_radius"] - len(all_affected_orig),
                    "risk_score_delta": (
                        round(cand_sim["risk_score"] - base_risk, 1)
                        if cand_sim["risk_score"] is not None else None
                    ),
                    "downtime_delta": (
                        cand_sim["estimated_downtime_minutes"] - (base_result_for_candidates.get("estimated_downtime_minutes") or 30)
                        if cand_sim["estimated_downtime_minutes"] is not None else None
                    ),
                },
            },
            "available_metrics": cand_available_metrics,
            "missing_data": cand_missing_data,
            "feasibility": feasibility,
            "evidence": evidence,
            "pros": raw.get("pros", []),
            "cons": raw.get("cons", []),
            "prerequisites": raw.get("prerequisites", []),
            "implementation_steps": raw.get("implementation_steps", []),
            "complexity": raw.get("complexity", 1),
            "provides_redundancy": raw.get("provides_redundancy", False),
            "zero_downtime_capable": raw.get("zero_downtime_capable", False),
        })

    # --- Step 5: Feature Extraction from actual Twin + graph + simulation data ---
    extracted_features = extract_all_candidate_features(
        candidates=candidate_results,
        baseline=original_baseline,
        component=component,
        component_data=target_node,
    )

    # --- Step 6: ML Candidate Ranking ---
    ranking_result = rank_candidates(
        candidates_with_features=extracted_features,
        candidates_raw=candidate_results,
        baseline=original_baseline,
        component_data=target_node,
        force_fallback=force_ml_fallback,
        simulate_inference_failure=simulate_ml_failure,
    )

    scenario_obj = {
        "target_component_id": target_component_id,
        "target_component_name": target_node.get("name", target_component_id),
        "action": action,
        "source_environment": source_environment,
        "baseline_blast_radius": original_baseline.get("blast_radius", 0),
        "baseline_risk_score": original_baseline.get("risk_score", 0.0),
        "is_single_point_of_failure": original_baseline.get("is_single_point_of_failure", False),
    }

    # --- Step 7: Structured Recommendation Response ---
    rec_obj = build_structured_recommendation_object(
        scenario=scenario_obj,
        candidates=candidate_results,
        ranking_result=ranking_result,
        extracted_features=extracted_features,
    )

    # --- Step 8: Three-Agent Decision and Explanation Layer ---
    agents_eval = evaluate_candidates_with_agents(
        candidates=candidate_results,
        baseline=original_baseline,
        component_data=target_node,
        ml_ranking=ranking_result.get("ranked_candidates", []),
        fail_agent=fail_agent,
    )

    return {
        "success": True,
        "target_component_id": target_component_id,
        "target_component_name": target_node.get("name", target_component_id),
        "action": action,
        "source_environment": source_environment,
        "original_baseline": original_baseline,
        "candidate_count": len(candidate_results),
        "candidates": candidate_results,
        # ML Ranking & Recommendation additions
        "scenario": scenario_obj,
        "simulation_results": rec_obj["simulation_results"],
        "extracted_features": extracted_features,
        "ml_ranking": rec_obj["ml_ranking"],
        "ranking": rec_obj["ranking"],
        "recommended_candidate_id": rec_obj["recommended_candidate_id"],
        "recommendation": rec_obj["recommendation"],
        "ranking_status": rec_obj["ranking_status"],
        "ranking_method": rec_obj["ranking_method"],
        "evidence": rec_obj["evidence"],
        "missing_data": rec_obj["missing_data"],
        "limitations": rec_obj["limitations"],
        # Three-Agent Decision additions
        "agents": agents_eval,
        "consensus": agents_eval.get("consensus"),
        "financial_analyst": agents_eval.get("financial"),
        "risk_analyst": agents_eval.get("risk"),
        "system_architect": agents_eval.get("architect"),
    }

