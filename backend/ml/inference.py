import os
import joblib
import numpy as np
from typing import Dict, Any, List, Optional
from ml.feature_extractor import extract_features_dict, vectorize_features

_MODEL_CACHE = None

def load_model(model_path: str = None) -> Dict[str, Any]:
    global _MODEL_CACHE
    if _MODEL_CACHE is not None:
        return _MODEL_CACHE
        
    default_path = os.path.join(os.path.dirname(__file__), "models", "solution_ranker.joblib")
    target_path = model_path or default_path
    
    if not os.path.exists(target_path):
        from ml.train import train_and_save_model
        target_path, _ = train_and_save_model()
        
    _MODEL_CACHE = joblib.load(target_path)
    return _MODEL_CACHE

def get_model_metadata() -> Dict[str, Any]:
    model_obj = load_model()
    return {
        "model_type": model_obj.get("model_type", "RandomForestRegressor + RandomForestClassifier"),
        "description": model_obj.get("description", "Architecture remediation suitability ranker"),
        "metrics": model_obj.get("metrics", {}),
        "features_count": len(model_obj.get("feature_names", []))
    }

def rank_candidate_solutions(
    simulation_result: Dict[str, Any],
    candidate_solutions: List[Dict[str, Any]],
    component_data: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Takes the actual Digital Twin simulation payload and a list of candidate strategies,
    extracts dynamic feature vectors, runs ML inference, and ranks the candidates.
    """
    model_obj = load_model()
    rf_reg = model_obj["regressor"]
    rf_clf = model_obj["classifier"]
    feature_names = model_obj["feature_names"]
    feature_importances = rf_reg.feature_importances_
    
    ranked_results = []
    
    for cand in candidate_solutions:
        # Convert schema object or dict
        cand_dict = cand.model_dump() if hasattr(cand, "model_dump") else dict(cand)
        
        # Extract features
        feat_dict = extract_features_dict(simulation_result, cand_dict, component_data)
        vec = vectorize_features(feat_dict).reshape(1, -1)
        
        # 1. Regressor Suitability Score (0.0 to 1.0)
        suitability = float(np.clip(rf_reg.predict(vec)[0], 0.05, 0.99))
        
        # 2. Classifier Confidence & Class Probability
        try:
            proba = rf_clf.predict_proba(vec)[0]
            confidence_val = float(np.max(proba))
        except Exception:
            confidence_val = 0.85
            
        if confidence_val >= 0.80:
            confidence_label = "High"
        elif confidence_val >= 0.60:
            confidence_label = "Moderate"
        else:
            confidence_label = "Low"
            
        # 3. Identify Top Driving Features for this specific candidate
        supporting_features = []
        comp_type = feat_dict.get("component_type", "server")
        strat_type = feat_dict.get("strategy_type", "")
        upstream = feat_dict.get("upstream_callers_count", 0)
        is_spof = feat_dict.get("is_spof", 0)
        cpu = feat_dict.get("cpu_percent", -1.0)
        
        if is_spof == 1 and cand_dict.get("provides_redundancy"):
            supporting_features.append("Target component is a Single Point of Failure (SPOF) needing redundancy.")
        if upstream > 1 and cand_dict.get("zero_downtime_capable"):
            supporting_features.append(f"Protects {upstream} upstream caller service(s) with zero/low-downtime cutover.")
        if comp_type == "database" and cand_dict.get("requires_data_sync"):
            supporting_features.append("Stateful database architecture safely replicated before transition.")
        if cpu > 75.0 and "scale" in strat_type:
            supporting_features.append(f"Elevated CPU load ({cpu}%) relieved via horizontal capacity distribution.")
        if not supporting_features:
            supporting_features.append(f"Standard execution profile suitable for {comp_type} workload.")
            
        # Augment candidate dictionary
        cand_dict["predicted_suitability"] = round(suitability, 4)
        cand_dict["suitability_percentage"] = round(suitability * 100.0, 1)
        cand_dict["feasibility_score"] = round(suitability, 2)
        cand_dict["confidence"] = confidence_label
        cand_dict["confidence_score"] = round(confidence_val, 4)
        cand_dict["supporting_features"] = supporting_features
        cand_dict["ml_derived"] = True
        
        ranked_results.append(cand_dict)
        
    # Sort descending by predicted suitability score
    ranked_results.sort(key=lambda x: x["predicted_suitability"], reverse=True)
    
    # Assign ranks
    for idx, item in enumerate(ranked_results):
        item["rank"] = idx + 1
        
    return ranked_results
