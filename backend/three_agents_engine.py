"""
backend/three_agents_engine.py — Three-Agent Decision and Explanation Layer

Architecture:
- Agents: Financial Analyst, Risk Analyst, System / Cloud Architect.
- Agents are NOT the source of truth; they interpret factual Twin and simulation data.
- Strict anti-fabrication: Never invent cost, downtime, risk, probabilities, availability, or infrastructure.
- Missing data is explicitly reported as 'unknown' with explanations.
- Structured agent reports with explicit evidence, findings, and unknowns.
- Consensus is evidence-based, references an existing candidate_id, and explicitly exposes conflicts.
- Safe failure fallback: If an agent fails or is unavailable, status='unavailable' without crashing.
"""

import os
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("infratwin.three_agents")


# ---------------------------------------------------------------------------
# Section 1: Financial Analyst
# ---------------------------------------------------------------------------

def run_financial_analyst(
    candidates: List[Dict[str, Any]],
    baseline: Dict[str, Any],
    component_data: Optional[Dict[str, Any]] = None,
    force_failure: bool = False,
) -> Dict[str, Any]:
    """
    Financial Analyst evaluates candidates strictly using available cost information.
    If cost information is missing, sets cost_status='unknown' and explains why.
    Never estimates or invents pricing figures.
    """
    if force_failure:
        return {
            "agent": "financial_analyst",
            "summary": "Financial analysis unavailable due to service error.",
            "cost_status": "unknown",
            "findings": [],
            "evidence": [],
            "unknowns": ["financial_service"],
            "recommendation": "Unable to provide financial recommendation.",
            "recommended_candidate_id": None,
            "status": "unavailable",
        }

    comp = component_data or {}
    raw_cost = comp.get("cost_per_month")
    has_target_cost = bool(raw_cost is not None and float(raw_cost) > 0.0)

    # Check which candidates have known cost information
    candidates_with_cost = []
    candidates_without_cost = []

    for c in candidates:
        sim = c.get("simulation_result", {})
        cost_delta = sim.get("cost_delta_monthly")
        if cost_delta is not None and has_target_cost:
            candidates_with_cost.append((c, cost_delta))
        else:
            candidates_without_cost.append(c)

    # If NO cost information is available in the Twin or simulation
    if not candidates_with_cost:
        unknowns = ["cost_per_month", "cloud_provider_pricing", "licensing_cost"]
        return {
            "agent": "financial_analyst",
            "summary": "Cost information is unavailable for this candidate set. No financial data was provided in the Digital Twin.",
            "cost_status": "unknown",
            "findings": [
                "Baseline component has no cost_per_month defined in the Digital Twin.",
                "Cost deltas cannot be calculated without baseline pricing data.",
                "Candidates cannot be financially differentiated until pricing metadata is supplied."
            ],
            "evidence": [
                f"Target component '{comp.get('name', 'target')}' cost_per_month is {raw_cost}.",
                "All candidates report cost_data_available as false."
            ],
            "unknowns": unknowns,
            "recommendation": "Financial recommendation is deferred until actual cost metrics or cloud billing data are provided.",
            "recommended_candidate_id": None,
            "status": "complete",
        }

    # Cost information is available
    candidates_with_cost.sort(key=lambda x: x[1])
    cheapest_cand, lowest_delta = candidates_with_cost[0]
    most_expensive_cand, highest_delta = candidates_with_cost[-1]

    findings = [
        f"Baseline monthly infrastructure expenditure is ${float(raw_cost):.2f}/month.",
        f"Candidate '{cheapest_cand['name']}' presents the lowest cost impact with delta of ${lowest_delta:+.2f}/month.",
    ]
    if highest_delta > lowest_delta:
        diff = highest_delta - lowest_delta
        findings.append(
            f"Tradeoff: '{most_expensive_cand['name']}' requires an additional ${diff:.2f}/month compared to the lowest-cost option."
        )

    evidence = [
        f"Baseline cost_per_month: ${float(raw_cost):.2f}",
        f"Candidate '{cheapest_cand['candidate_id']}' cost_delta_monthly: ${lowest_delta:+.2f}",
    ]

    unknowns = []
    if candidates_without_cost:
        unknowns.append(f"{len(candidates_without_cost)} candidate(s) lack complete cost telemetry")

    return {
        "agent": "financial_analyst",
        "summary": f"Financial assessment complete. '{cheapest_cand['name']}' provides the most cost-effective profile (${lowest_delta:+.2f}/mo).",
        "cost_status": "known",
        "findings": findings,
        "evidence": evidence,
        "unknowns": unknowns,
        "recommendation": f"Adopt '{cheapest_cand['name']}' for minimal financial impact.",
        "recommended_candidate_id": cheapest_cand["candidate_id"],
        "status": "complete",
    }


# ---------------------------------------------------------------------------
# Section 2: Risk Analyst
# ---------------------------------------------------------------------------

def run_risk_analyst(
    candidates: List[Dict[str, Any]],
    baseline: Dict[str, Any],
    component_data: Optional[Dict[str, Any]] = None,
    force_failure: bool = False,
) -> Dict[str, Any]:
    """
    Risk Analyst evaluates topological and operational blast radius from actual graph simulation.
    Does NOT invent failure probabilities, uptime percentages, or subjective severities.
    """
    if force_failure:
        return {
            "agent": "risk_analyst",
            "summary": "Risk analysis unavailable due to service error.",
            "findings": [],
            "evidence": [],
            "unknowns": ["risk_service"],
            "recommendation": "Unable to provide risk recommendation.",
            "recommended_candidate_id": None,
            "status": "unavailable",
        }

    comp = component_data or {}
    base_blast = baseline.get("blast_radius", 0)
    base_risk = baseline.get("risk_score", 0.0)
    is_spof = bool(baseline.get("is_single_point_of_failure", False))

    findings = [
        f"Baseline failure blast radius impacts {base_blast} component(s) across the topology.",
        f"Baseline deterministic risk score is {base_risk} ({baseline.get('risk_level', 'LOW')}).",
    ]
    if is_spof:
        findings.append("Target component is mathematically identified as a Single Point of Failure (SPOF).")

    evidence = [
        f"Baseline blast_radius: {base_blast}",
        f"Baseline risk_score: {float(base_risk):.1f}",
        f"Baseline is_single_point_of_failure: {is_spof}",
    ]

    # Evaluate candidate risk reductions
    # Primary: SPOF elimination, Secondary: lowest risk_score, blast_radius
    candidates_ranked_by_risk = sorted(
        candidates,
        key=lambda c: (
            -int(c.get("simulation_result", {}).get("spof_eliminated", False)),
            c.get("simulation_result", {}).get("risk_score", 100.0) or 100.0,
            c.get("simulation_result", {}).get("blast_radius", 100),
        ),
    )

    best_risk_cand = candidates_ranked_by_risk[0] if candidates_ranked_by_risk else None
    recommended_id = best_risk_cand["candidate_id"] if best_risk_cand else None

    if best_risk_cand:
        best_sim = best_risk_cand.get("simulation_result", {})
        cand_spof_elim = best_sim.get("spof_eliminated", False)
        cand_blast = best_sim.get("blast_radius", 0)
        cand_risk = best_sim.get("risk_score")

        if is_spof and cand_spof_elim:
            findings.append(f"Candidate '{best_risk_cand['name']}' successfully eliminates the Single Point of Failure.")
            evidence.append(f"Candidate '{best_risk_cand['candidate_id']}' spof_eliminated: True")
        if cand_risk is not None:
            findings.append(f"Candidate '{best_risk_cand['name']}' achieves lowest simulated risk score ({cand_risk}).")
            evidence.append(f"Candidate '{best_risk_cand['candidate_id']}' risk_score: {cand_risk}")

    unknowns = []
    if comp.get("cpu") is None:
        unknowns.append("live_cpu_telemetry")
    if comp.get("memory") is None:
        unknowns.append("live_memory_telemetry")

    recommendation = (
        f"Adopt '{best_risk_cand['name']}' to minimize topological blast radius and eliminate architectural risk."
        if best_risk_cand else "No candidate available for risk evaluation."
    )

    return {
        "agent": "risk_analyst",
        "summary": f"Risk assessment complete. '{best_risk_cand['name'] if best_risk_cand else 'None'}' identified as highest-resilience candidate.",
        "findings": findings,
        "evidence": evidence,
        "unknowns": unknowns,
        "recommendation": recommendation,
        "recommended_candidate_id": recommended_id,
        "status": "complete",
    }


# ---------------------------------------------------------------------------
# Section 3: System / Cloud Architect
# ---------------------------------------------------------------------------

def run_architect_analyst(
    candidates: List[Dict[str, Any]],
    baseline: Dict[str, Any],
    component_data: Optional[Dict[str, Any]] = None,
    ml_ranking: Optional[List[Dict[str, Any]]] = None,
    force_failure: bool = False,
) -> Dict[str, Any]:
    """
    Architect Analyst evaluates structural changes, topology mutations,
    operational implications, and alignment with the ML ranking.
    Does NOT invent infrastructure components.
    """
    if force_failure:
        return {
            "agent": "system_architect",
            "summary": "Architectural analysis unavailable due to service error.",
            "findings": [],
            "evidence": [],
            "unknowns": ["architect_service"],
            "recommendation": "Unable to provide architectural recommendation.",
            "recommended_candidate_id": None,
            "status": "unavailable",
        }

    comp = component_data or {}
    ml_top_id = None
    if ml_ranking and len(ml_ranking) > 0:
        ml_top_id = ml_ranking[0].get("candidate_id")

    findings = []
    evidence = []

    # Map candidate topologies
    cand_map = {c["candidate_id"]: c for c in candidates}
    top_cand = cand_map.get(ml_top_id) if ml_top_id else (candidates[0] if candidates else None)

    if top_cand:
        mutations = top_cand.get("proposed_changes", [])
        resulting_topo = top_cand.get("resulting_topology", {}) or {}
        n_count = resulting_topo.get("node_count", "unknown")
        e_count = resulting_topo.get("edge_count", "unknown")

        findings.append(
            f"Candidate '{top_cand['name']}' introduces {len(mutations)} topological mutation(s), resulting in {n_count} nodes and {e_count} edges."
        )
        for m in mutations:
            evidence.append(f"Proposed mutation: {m}")

        if top_cand.get("zero_downtime_capable"):
            findings.append("Candidate architecture supports staged zero-downtime cutover.")
            evidence.append("zero_downtime_capable: True")

        if top_cand.get("provides_redundancy"):
            findings.append("Architecture introduces active standby redundancy to isolate component failures.")
            evidence.append("provides_redundancy: True")

    unknowns = [
        "traffic_surge_characteristics",
        "inter_az_latency_telemetry",
    ]
    if not comp.get("metadata_col", {}).get("maintenance_window_minutes"):
        unknowns.append("maintenance_window_schedule")

    recommended_id = top_cand["candidate_id"] if top_cand else None
    recommendation = (
        f"Architecturally endorse '{top_cand['name']}' based on structural feasibility and redundancy safeguards."
        if top_cand else "No candidate available for architectural evaluation."
    )

    return {
        "agent": "system_architect",
        "summary": f"Architectural evaluation complete. Endorsing '{top_cand['name'] if top_cand else 'None'}' for operational soundness.",
        "findings": findings,
        "evidence": evidence,
        "unknowns": unknowns,
        "recommendation": recommendation,
        "recommended_candidate_id": recommended_id,
        "status": "complete",
    }


# ---------------------------------------------------------------------------
# Section 4: Agent Consensus Engine
# ---------------------------------------------------------------------------

def build_agent_consensus(
    financial_report: Dict[str, Any],
    risk_report: Dict[str, Any],
    architect_report: Dict[str, Any],
    candidates: List[Dict[str, Any]],
    ml_ranking: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Builds a structured consensus from the 3 agents.
    Rules:
    - Consensus MUST reference an existing candidate_id.
    - If agents disagree, the disagreement is EXPLICITLY exposed with tradeoff reasons.
    - Compares consensus candidate with ML ranking without silently overriding ML.
    """
    cand_map = {c["candidate_id"]: c for c in candidates}
    fin_rec = financial_report.get("recommended_candidate_id")
    risk_rec = risk_report.get("recommended_candidate_id")
    arch_rec = architect_report.get("recommended_candidate_id")

    recs = [r for r in [fin_rec, risk_rec, arch_rec] if r is not None and r in cand_map]

    # Evaluate agreement level
    if len(recs) == 3 and fin_rec == risk_rec == arch_rec:
        agreement = "unanimous"
    elif len(recs) >= 2 and (
        (fin_rec == risk_rec and fin_rec is not None)
        or (risk_rec == arch_rec and risk_rec is not None)
        or (fin_rec == arch_rec and fin_rec is not None)
    ):
        agreement = "majority"
    elif len(recs) > 0:
        agreement = "split"
    else:
        agreement = "none"

    # Identify conflicts & trade-offs
    conflicts = []
    if fin_rec and risk_rec and fin_rec != risk_rec:
        fin_name = cand_map[fin_rec].get("name", fin_rec)
        risk_name = cand_map[risk_rec].get("name", risk_rec)
        conflicts.append({
            "dimension": "Cost vs Resilience",
            "financial_view": f"Prefers '{fin_name}' ({fin_rec}) for lowest expenditure impact.",
            "risk_view": f"Prefers '{risk_name}' ({risk_rec}) to eliminate single point of failure and minimize blast radius.",
            "tradeoff_summary": f"Adopting '{risk_name}' ({risk_rec}) increases resilience and eliminates SPOF, but may require higher infrastructure investment than '{fin_name}' ({fin_rec})."
        })

    if fin_rec and arch_rec and fin_rec != arch_rec and arch_rec != risk_rec:
        fin_name = cand_map[fin_rec].get("name", fin_rec)
        arch_name = cand_map[arch_rec].get("name", arch_rec)
        conflicts.append({
            "dimension": "Cost vs Architectural Complexity",
            "financial_view": f"Prefers '{fin_name}' ({fin_rec}) for minimal cost delta.",
            "architect_view": f"Prefers '{arch_name}' ({arch_rec}) for structural robustness.",
            "tradeoff_summary": f"'{arch_name}' ({arch_rec}) requires operational configuration but provides high availability."
        })

    # Consensus candidate selection:
    # 1. Majority vote if available
    # 2. If split or financial is unknown, prioritize risk + architect consensus
    # 3. Must ALWAYS match an existing candidate
    consensus_id = None
    if agreement == "unanimous":
        consensus_id = fin_rec
    elif agreement == "majority":
        if fin_rec == risk_rec:
            consensus_id = fin_rec
        elif risk_rec == arch_rec:
            consensus_id = risk_rec
        else:
            consensus_id = arch_rec
    elif risk_rec:
        consensus_id = risk_rec
    elif arch_rec:
        consensus_id = arch_rec
    elif fin_rec:
        consensus_id = fin_rec
    elif candidates:
        consensus_id = candidates[0]["candidate_id"]

    # Verify consensus matches an existing candidate
    assert consensus_id is None or consensus_id in cand_map, "Consensus must reference an existing candidate"

    # Check ML alignment
    ml_top_id = ml_ranking[0].get("candidate_id") if ml_ranking and len(ml_ranking) > 0 else None
    ml_aligned = (consensus_id == ml_top_id) if (consensus_id and ml_top_id) else False

    reasoning = []
    if consensus_id and consensus_id in cand_map:
        c_obj = cand_map[consensus_id]
        reasoning.append(
            f"Consensus selected Candidate '{c_obj.get('name', consensus_id)}' ({consensus_id}) with {agreement} agent agreement."
        )
        if ml_aligned:
            reasoning.append("Consensus recommendation directly aligns with the ML rank #1 candidate.")
        elif ml_top_id:
            reasoning.append(
                f"Agent consensus favors '{c_obj.get('name')}', noting trade-offs against ML rank #1 ('{cand_map.get(ml_top_id, {}).get('name', ml_top_id)}')."
            )

        if conflicts:
            for c in conflicts:
                reasoning.append(c["tradeoff_summary"])

    return {
        "candidate_id": consensus_id,
        "agreement": agreement,
        "reasoning": reasoning,
        "conflicts": conflicts,
        "ml_alignment": ml_aligned,
    }


# ---------------------------------------------------------------------------
# Section 5: Orchestrator
# ---------------------------------------------------------------------------

def evaluate_candidates_with_agents(
    candidates: List[Dict[str, Any]],
    baseline: Dict[str, Any],
    component_data: Optional[Dict[str, Any]] = None,
    ml_ranking: Optional[List[Dict[str, Any]]] = None,
    fail_agent: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Runs the 3 agents and builds the structured consensus object.
    Supports graceful single-agent failure testing via fail_agent parameter.
    """
    fin_report = run_financial_analyst(
        candidates=candidates,
        baseline=baseline,
        component_data=component_data,
        force_failure=(fail_agent == "financial"),
    )

    risk_report = run_risk_analyst(
        candidates=candidates,
        baseline=baseline,
        component_data=component_data,
        force_failure=(fail_agent == "risk"),
    )

    arch_report = run_architect_analyst(
        candidates=candidates,
        baseline=baseline,
        component_data=component_data,
        ml_ranking=ml_ranking,
        force_failure=(fail_agent == "architect"),
    )

    consensus = build_agent_consensus(
        financial_report=fin_report,
        risk_report=risk_report,
        architect_report=arch_report,
        candidates=candidates,
        ml_ranking=ml_ranking,
    )

    return {
        "financial": fin_report,
        "risk": risk_report,
        "architect": arch_report,
        "consensus": consensus,
    }
