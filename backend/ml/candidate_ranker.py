"""
backend/ml/candidate_ranker.py — ML-Based Candidate Ranking Layer

Architectural Principles:
- Digital Twin and deterministic simulation are the sole authority for infrastructure truth.
- ML must NOT:
    * discover dependencies
    * create dependencies
    * calculate graph relationships
    * invent infrastructure
    * invent cost
    * invent downtime
    * invent telemetry
    * replace deterministic simulation
- ML exists ONLY to rank/suggest among already-generated, independently-simulated candidates.
- Missing data is explicitly marked (null / _data_available=False), NEVER filled with arbitrary values.
- Prototype model is explicitly labeled 'Simulation-Trained ML Prototype'. No fake accuracy metrics.
- If ML is unavailable or inference fails, system falls back cleanly to 'unavailable' without fabricating scores.
"""

import os
import logging
from typing import List, Dict, Any, Optional, Tuple
import numpy as np

logger = logging.getLogger("infratwin.ml.candidate_ranker")

RANKING_METHOD_PROTOTYPE = "Simulation-Trained ML Prototype"
RANKING_METHOD_NONE = "none"


# ---------------------------------------------------------------------------
# Section 1: Feature Extraction Layer
# ---------------------------------------------------------------------------

def extract_candidate_features(
    candidate: Dict[str, Any],
    baseline: Dict[str, Any],
    component: Optional[Any] = None,
    component_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Extracts a clean, deterministic feature set for a single candidate solution.
    Features are strictly derived from actual Twin + graph + simulation data.

    Explicit missing-data handling:
    - If cost data does not exist in Twin/simulation: cost_delta=None, cost_data_available=False.
    - If downtime does not exist: estimated_downtime_minutes=None, downtime_data_available=False.
    - If risk score does not exist: risk_score=None, risk_score_available=False.
    - Never replaces missing data with arbitrary numbers.
    """
    sim_res = candidate.get("simulation_result", {}) or {}
    vs_base = sim_res.get("vs_baseline", {}) or {}
    affected_comps = candidate.get("affected_components", []) or []

    # 1. Component & telemetry facts from Twin (if available)
    comp_type = "unknown"
    comp_crit = "unknown"
    avail_health = []
    avail_resource = []
    target_has_cpu = False
    target_has_storage = False

    if component is not None:
        comp_type = getattr(component.type, "value", str(component.type)).lower() if hasattr(component, "type") else "unknown"
        comp_crit = getattr(component.criticality, "value", str(component.criticality)).lower() if hasattr(component, "criticality") else "unknown"
        meta = getattr(component, "metadata_col", {}) or {}
        if getattr(component, "cpu", None) is not None:
            avail_health.append("cpu_utilization")
            target_has_cpu = True
        if getattr(component, "memory", None) is not None:
            avail_health.append("memory_utilization")
        if meta.get("storage_gb") is not None or meta.get("db_size_gb") is not None:
            avail_resource.append("storage_gb")
            target_has_storage = True
    elif component_data:
        comp_type = str(component_data.get("type", "unknown")).lower()
        comp_crit = str(component_data.get("criticality", "unknown")).lower()
        if component_data.get("cpu") is not None:
            avail_health.append("cpu_utilization")
            target_has_cpu = True
        if component_data.get("memory") is not None:
            avail_health.append("memory_utilization")
        meta = component_data.get("metadata_col", {}) or {}
        if meta.get("storage_gb") is not None or meta.get("db_size_gb") is not None:
            avail_resource.append("storage_gb")
            target_has_storage = True

    # 2. Graph & topology features from deterministic simulation
    blast_radius = int(sim_res.get("blast_radius", 0))
    upstream_count = int(sim_res.get("upstream_impact_count", 0))
    downstream_count = int(sim_res.get("downstream_dependencies_count", 0))

    # Dependency depth: max hop distance among affected components
    hops = [c.get("hop_distance", 1) for c in affected_comps if isinstance(c, dict) and "hop_distance" in c]
    dependency_depth = max(hops) if hops else 0

    # Critical dependency count: affected components marked critical or high
    critical_deps = sum(
        1 for c in affected_comps
        if isinstance(c, dict) and str(c.get("criticality", "")).lower() in ("critical", "high")
    )

    # SPOF indicators
    baseline_is_spof = bool(baseline.get("is_single_point_of_failure", False))
    spof_eliminated = bool(sim_res.get("spof_eliminated", False))

    # Topology change size: number of nodes added/removed in candidate topology vs baseline
    resulting_topo = candidate.get("resulting_topology", {}) or {}
    baseline_topo = baseline.get("topology", {}) or {}
    cand_nodes = resulting_topo.get("node_count", 0)
    base_nodes = baseline_topo.get("node_count", 0)
    topology_change_size = abs(cand_nodes - base_nodes)

    # Dependency change count: edges added or modified in candidate topology vs baseline
    resulting_topo = candidate.get("resulting_topology", {}) or {}
    cand_edge_count = resulting_topo.get("edge_count")
    baseline_topo = baseline.get("topology", {}) or {}
    base_edge_count = baseline_topo.get("edge_count")
    if cand_edge_count is not None and base_edge_count is not None:
        dependency_change_count = abs(cand_edge_count - base_edge_count)
    else:
        dependency_change_count = topology_change_size

    # 3. Cost metrics with explicit missing-data handling
    has_twin_cost = False
    if component is not None:
        c_cost = getattr(component, "cost_per_month", None)
        if c_cost is not None and float(c_cost) > 0.0:
            has_twin_cost = True
    elif component_data:
        cd_cost = component_data.get("cost_per_month")
        if cd_cost is not None and float(cd_cost) > 0.0:
            has_twin_cost = True

    raw_cost_delta = sim_res.get("cost_delta_monthly")
    if has_twin_cost and raw_cost_delta is not None:
        cost_delta = float(raw_cost_delta)
        cost_data_available = True
    else:
        cost_delta = None
        cost_data_available = False


    # 4. Downtime metrics with explicit missing-data handling
    raw_downtime = sim_res.get("estimated_downtime_minutes")
    if raw_downtime is not None:
        estimated_downtime_minutes = int(raw_downtime)
        downtime_data_available = True
    else:
        estimated_downtime_minutes = None
        downtime_data_available = False

    # 5. Risk metrics
    raw_risk = sim_res.get("risk_score")
    if raw_risk is not None:
        risk_score = float(raw_risk)
        risk_score_available = True
    else:
        risk_score = None
        risk_score_available = False

    risk_score_delta = vs_base.get("risk_score_delta")
    blast_radius_delta = vs_base.get("blast_radius_delta")

    # 6. Candidate capability flags
    provides_redundancy = bool(candidate.get("provides_redundancy", False))
    zero_downtime_capable = bool(candidate.get("zero_downtime_capable", False))
    complexity = int(candidate.get("complexity", 1))
    feasibility = str(candidate.get("feasibility", "unknown"))

    # Missing data items specifically noted
    missing_data = list(candidate.get("missing_data", []))
    if not cost_data_available and "cost_per_month" not in missing_data:
        missing_data.append("cost_per_month")
    if not downtime_data_available and "estimated_downtime" not in missing_data:
        missing_data.append("estimated_downtime")
    if not target_has_cpu and "cpu_telemetry" not in missing_data:
        missing_data.append("cpu_telemetry")

    return {
        "candidate_id": candidate.get("candidate_id", ""),
        "strategy_type": candidate.get("strategy_type", "direct_lift_shift"),
        "component_type": comp_type,
        "criticality": comp_crit,
        "action": baseline.get("action", "fail"),
        "affected_component_count": blast_radius,
        "upstream_impact_count": upstream_count,
        "downstream_dependencies_count": downstream_count,
        "dependency_depth": dependency_depth,
        "critical_dependency_count": critical_deps,
        "spof_indicator": baseline_is_spof,
        "spof_eliminated": spof_eliminated,
        "topology_change_size": topology_change_size,
        "dependency_change_count": dependency_change_count,
        "available_health_metrics": avail_health,
        "available_resource_metrics": avail_resource,
        "cost_delta": cost_delta,
        "cost_data_available": cost_data_available,
        "estimated_downtime_minutes": estimated_downtime_minutes,
        "downtime_data_available": downtime_data_available,
        "risk_score": risk_score,
        "risk_score_available": risk_score_available,
        "risk_score_delta": risk_score_delta,
        "blast_radius_delta": blast_radius_delta,
        "provides_redundancy": provides_redundancy,
        "zero_downtime_capable": zero_downtime_capable,
        "complexity": complexity,
        "feasibility": feasibility,
        "missing_data": missing_data,
    }


def extract_all_candidate_features(
    candidates: List[Dict[str, Any]],
    baseline: Dict[str, Any],
    component: Optional[Any] = None,
    component_data: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Extracts features for all candidates in the candidate set."""
    return [
        extract_candidate_features(c, baseline, component=component, component_data=component_data)
        for c in candidates
    ]


# ---------------------------------------------------------------------------
# Section 2: ML Model Management & Prototype Abstraction
# ---------------------------------------------------------------------------

_MODEL_CACHE: Optional[Dict[str, Any]] = None

def get_prototype_model() -> Optional[Dict[str, Any]]:
    """
    Loads the prototype model artifact if present.
    Explicitly labeled: 'Simulation-Trained ML Prototype'.
    Returns None if the artifact cannot be loaded or is absent.
    """
    global _MODEL_CACHE
    if _MODEL_CACHE is not None:
        return _MODEL_CACHE

    model_path = os.path.join(
        os.path.dirname(__file__), "models", "solution_ranker.joblib"
    )
    if not os.path.exists(model_path):
        logger.warning(f"Prototype model not found at {model_path}")
        return None

    try:
        import joblib
        loaded = joblib.load(model_path)
        if isinstance(loaded, dict) and "regressor" in loaded and "feature_names" in loaded:
            _MODEL_CACHE = loaded
            return _MODEL_CACHE
        logger.warning("Loaded model object does not match expected prototype contract.")
        return None
    except Exception as e:
        logger.error(f"Failed to load prototype model: {e}")
        return None


def _build_model_feature_dict(
    feat: Dict[str, Any],
    candidate: Dict[str, Any],
    baseline: Dict[str, Any],
    component_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Adapts the clean candidate feature set into the format expected by the
    underlying prototype vectorizer, without mutating the clean feature set.
    """
    comp_dict = component_data or {}
    sim_dict = {
        "action": baseline.get("action", "fail"),
        "upstream_impact_count": feat.get("upstream_impact_count", 0),
        "downstream_dependencies_count": feat.get("downstream_dependencies_count", 0),
        "total_nodes_affected": feat.get("affected_component_count", 0),
        "risk_score": feat.get("risk_score") if feat.get("risk_score") is not None else 0.0,
        "estimated_downtime_minutes": feat.get("estimated_downtime_minutes"),
        "cost_delta_monthly": feat.get("cost_delta"),
        "risk_factors": {
            "is_single_point_of_failure": feat.get("spof_indicator", False),
            "critical_callers_affected": feat.get("critical_dependency_count", 0),
            "max_dependency_depth": feat.get("dependency_depth", 0),
        },
    }
    cand_dict = {
        "strategy_type": feat.get("strategy_type", "direct_lift_shift"),
        "complexity": feat.get("complexity", 1),
        "provides_redundancy": feat.get("provides_redundancy", False),
        "requires_data_sync": bool(candidate.get("requires_data_sync", False)),
        "zero_downtime_capable": feat.get("zero_downtime_capable", False),
    }

    from ml.feature_extractor import extract_features_dict
    return extract_features_dict(sim_dict, cand_dict, comp_dict)


# ---------------------------------------------------------------------------
# Section 3: Candidate Ranking Logic
# ---------------------------------------------------------------------------

def rank_candidates(
    candidates_with_features: List[Dict[str, Any]],
    candidates_raw: List[Dict[str, Any]],
    baseline: Dict[str, Any],
    component_data: Optional[Dict[str, Any]] = None,
    force_fallback: bool = False,
    simulate_inference_failure: bool = False,
) -> Dict[str, Any]:
    """
    Ranks candidate solutions based on extracted features and the prototype ML model.

    Returns:
    {
        "ranking_status": "ranked" | "insufficient_data" | "unavailable",
        "ranking_method": str,
        "ranked_candidates": List[Dict[str, Any]],
        "recommended_candidate_id": Optional[str],
        "evidence": List[str],
        "limitations": List[str],
        "missing_data": List[str]
    }

    Strict fallback guarantees:
    - If candidates list is empty: status = "insufficient_data".
    - If model is unavailable: status = "unavailable", no fake recommendations fabricated.
    - If model inference fails: status = "unavailable", catches exception safely.
    - Recommended candidate ID ALWAYS references an existing candidate in the list.
    """
    if not candidates_with_features or not candidates_raw:
        return {
            "ranking_status": "insufficient_data",
            "ranking_method": RANKING_METHOD_NONE,
            "ranked_candidates": [],
            "recommended_candidate_id": None,
            "evidence": ["No candidate solutions available to rank."],
            "limitations": ["Insufficient candidate data for ranking."],
            "missing_data": ["candidates"],
        }

    # Aggregate missing data across all candidate features
    all_missing: List[str] = []
    for f in candidates_with_features:
        for m in f.get("missing_data", []):
            if m not in all_missing:
                all_missing.append(m)

    # Check for forced fallback or simulated failure
    if force_fallback:
        return {
            "ranking_status": "unavailable",
            "ranking_method": RANKING_METHOD_NONE,
            "ranked_candidates": [],
            "recommended_candidate_id": None,
            "evidence": ["ML ranking was bypassed via fallback configuration."],
            "limitations": [
                "ML model is unavailable; returning independently simulated candidates without ML ranking."
            ],
            "missing_data": all_missing,
        }

    if simulate_inference_failure:
        return {
            "ranking_status": "unavailable",
            "ranking_method": RANKING_METHOD_NONE,
            "ranked_candidates": [],
            "recommended_candidate_id": None,
            "evidence": ["ML model inference encountered an error and fell back safely."],
            "limitations": [
                "ML model inference failed. Returning deterministic candidate simulation results without ML ranking."
            ],
            "missing_data": all_missing,
        }

    # Check if prototype model is available
    model_obj = get_prototype_model()
    if model_obj is None:
        return {
            "ranking_status": "unavailable",
            "ranking_method": RANKING_METHOD_NONE,
            "ranked_candidates": [],
            "recommended_candidate_id": None,
            "evidence": ["Prototype ML model artifact not found on disk."],
            "limitations": [
                "ML ranking model is unavailable. Returning deterministic candidate simulation results without ML ranking."
            ],
            "missing_data": all_missing,
        }

    # Run inference with safe exception handling
    try:
        from ml.feature_extractor import vectorize_features
        rf_reg = model_obj["regressor"]

        scored_candidates = []
        cand_map = {c["candidate_id"]: c for c in candidates_raw}

        for feat in candidates_with_features:
            cid = feat["candidate_id"]
            raw_cand = cand_map.get(cid, {})

            # Vectorize
            model_feat_dict = _build_model_feature_dict(feat, raw_cand, baseline, component_data)
            vec = vectorize_features(model_feat_dict).reshape(1, -1)

            # Predict continuous suitability score
            raw_score = float(rf_reg.predict(vec)[0])
            suitability = round(float(np.clip(raw_score, 0.0, 1.0)), 4)

            # Determine key driving features actually used
            features_used = []
            explanation_points = []

            if feat.get("spof_eliminated"):
                features_used.append("spof_eliminated")
                explanation_points.append("Eliminates single point of failure (SPOF)")

            if feat.get("provides_redundancy"):
                features_used.append("provides_redundancy")
                explanation_points.append("Introduces high-availability redundancy")

            if feat.get("zero_downtime_capable"):
                features_used.append("zero_downtime_capable")
                explanation_points.append("Supports zero-downtime cutover")

            br_delta = feat.get("blast_radius_delta")
            if br_delta is not None and br_delta < 0:
                features_used.append("blast_radius_delta")
                explanation_points.append(f"Reduces blast radius by {abs(br_delta)} nodes")

            risk_delta = feat.get("risk_score_delta")
            if risk_delta is not None and risk_delta < 0:
                features_used.append("risk_score_delta")
                explanation_points.append(f"Reduces risk score by {abs(risk_delta)}")

            feasibility = feat.get("feasibility", "unknown")
            features_used.append("feasibility")
            explanation_points.append(f"Simulation feasibility: {feasibility}")

            if not explanation_points:
                explanation_points.append(f"Strategy {feat.get('strategy_type')} baseline simulation profile")

            explanation = ". ".join(explanation_points) + "."

            scored_candidates.append({
                "candidate_id": cid,
                "strategy_type": feat.get("strategy_type"),
                "suitability_score": suitability,
                "features_used": features_used,
                "explanation": explanation,
                "feasibility": feasibility,
                "spof_eliminated": feat.get("spof_eliminated", False),
                "blast_radius_delta": br_delta if br_delta is not None else 0,
                "risk_score_delta": risk_delta if risk_delta is not None else 0.0,
            })

        # Sort candidates: primary by suitability_score desc, secondary by risk reduction
        scored_candidates.sort(
            key=lambda x: (
                x["suitability_score"],
                -x["risk_score_delta"],
                -x["blast_radius_delta"],
            ),
            reverse=True,
        )

        ranked_items = []
        for idx, item in enumerate(scored_candidates):
            is_recommended = (idx == 0)
            ranked_items.append({
                "candidate_id": item["candidate_id"],
                "rank": idx + 1,
                "recommendation": is_recommended,
                "ranking_method": RANKING_METHOD_PROTOTYPE,
                "features_used": item["features_used"],
                "explanation": item["explanation"],
            })

        recommended_id = ranked_items[0]["candidate_id"] if ranked_items else None

        # Build ranking evidence
        evidence = []
        if recommended_id:
            top_item = scored_candidates[0]
            evidence.append(
                f"Candidate '{top_item['candidate_id']}' ranked #1: {top_item['explanation']}"
            )
            if top_item.get("spof_eliminated"):
                evidence.append("Top candidate successfully eliminates the baseline single point of failure.")

        limitations = [
            "Ranking produced by Simulation-Trained ML Prototype; not calibrated for production SLA guarantees.",
            "Deterministic simulation results remain authoritative; ML does not alter blast radius or risk facts.",
        ]
        if all_missing:
            limitations.append(
                f"Missing telemetry/cost fields ({', '.join(all_missing)}) were treated as missing, not fabricated."
            )

        return {
            "ranking_status": "ranked",
            "ranking_method": RANKING_METHOD_PROTOTYPE,
            "ranked_candidates": ranked_items,
            "recommended_candidate_id": recommended_id,
            "evidence": evidence,
            "limitations": limitations,
            "missing_data": all_missing,
        }

    except Exception as exc:
        logger.error(f"Exception during ML candidate ranking: {exc}", exc_info=True)
        return {
            "ranking_status": "unavailable",
            "ranking_method": RANKING_METHOD_NONE,
            "ranked_candidates": [],
            "recommended_candidate_id": None,
            "evidence": [f"ML inference failure: {str(exc)}"],
            "limitations": [
                "ML model inference failed. Returning deterministic candidate simulation results without ML ranking."
            ],
            "missing_data": all_missing,
        }


# ---------------------------------------------------------------------------
# Section 4: Recommendation Response Builder
# ---------------------------------------------------------------------------

def build_structured_recommendation_object(
    scenario: Dict[str, Any],
    candidates: List[Dict[str, Any]],
    ranking_result: Dict[str, Any],
    extracted_features: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Constructs the final structured recommendation object strictly distinguishing:
    - DATA: Twin facts (scenario, baseline)
    - SIMULATION: Independent simulation results per candidate
    - ML: Ranking and suggestion
    - AI AGENT: Explanations and evidence
    """
    ranking_status = ranking_result.get("ranking_status", "unavailable")
    ranked_list = ranking_result.get("ranked_candidates", [])
    recommended_id = ranking_result.get("recommended_candidate_id")

    # Simulation results map keyed by candidate_id
    simulation_results = [
        {
            "candidate_id": c["candidate_id"],
            "name": c.get("name"),
            "strategy_type": c.get("strategy_type"),
            "simulation_result": c.get("simulation_result"),
            "feasibility": c.get("feasibility"),
        }
        for c in candidates
    ]

    # Recommendation summary object
    recommendation = None
    if recommended_id:
        top_cand = next((c for c in candidates if c["candidate_id"] == recommended_id), None)
        top_rank = next((r for r in ranked_list if r["candidate_id"] == recommended_id), None)
        if top_cand and top_rank:
            recommendation = {
                "recommended_candidate_id": recommended_id,
                "candidate_name": top_cand.get("name", recommended_id),
                "strategy_type": top_cand.get("strategy_type", ""),
                "reasoning": top_rank.get("explanation", ""),
                "ranking_method": top_rank.get("ranking_method", RANKING_METHOD_PROTOTYPE),
                "limitations": ranking_result.get("limitations", []),
            }

    return {
        "scenario": scenario,
        "candidates": candidates,
        "simulation_results": simulation_results,
        "extracted_features": extracted_features,
        "ranking": ranked_list,
        "ml_ranking": ranked_list,
        "recommended_candidate_id": recommended_id,
        "recommendation": recommendation,
        "ranking_status": ranking_status,
        "ranking_method": ranking_result.get("ranking_method", RANKING_METHOD_NONE),
        "evidence": ranking_result.get("evidence", []),
        "missing_data": ranking_result.get("missing_data", []),
        "limitations": ranking_result.get("limitations", []),
    }
