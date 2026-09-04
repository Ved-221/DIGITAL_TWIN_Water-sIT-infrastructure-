import os
import sys
import json
import joblib
import numpy as np
import pandas as pd

# Add backend root to sys.path for standalone script execution
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
from sklearn.metrics import mean_squared_error, r2_score, mean_absolute_error, accuracy_score, f1_score, classification_report
from ml.feature_extractor import vectorize_features, get_feature_names
from ml.dataset_generator import generate_simulation_dataset

def train_and_save_model(data_path: str = None, model_output_path: str = None):
    """
    Trains a supervised Random Forest pipeline on simulation-grounded infrastructure facts
    to rank candidate architecture/remediation strategies.
    """
    default_data_path = os.path.join(os.path.dirname(__file__), "data", "simulation_training_data.csv")
    csv_file = data_path or default_data_path
    
    if not os.path.exists(csv_file):
        print("Training dataset not found. Generating fresh simulation training dataset...")
        df = generate_simulation_dataset(num_scenarios=2400)
        os.makedirs(os.path.dirname(csv_file), exist_ok=True)
        df.to_csv(csv_file, index=False)
    else:
        df = pd.read_csv(csv_file)
        
    feature_names = get_feature_names()
    
    # Vectorize rows
    X_list = []
    y_reg_list = []
    y_clf_list = []
    
    for _, row in df.iterrows():
        feat_dict = row.to_dict()
        vec = vectorize_features(feat_dict)
        X_list.append(vec)
        y_reg_list.append(float(row["suitability_score"]))
        y_clf_list.append(int(row["is_suitable_label"]))
        
    X = np.array(X_list, dtype=np.float32)
    y_reg = np.array(y_reg_list, dtype=np.float32)
    y_clf = np.array(y_clf_list, dtype=np.int32)
    
    # Train / Test split (80% / 20%)
    X_train, X_test, y_reg_train, y_reg_test, y_clf_train, y_clf_test = train_test_split(
        X, y_reg, y_clf, test_size=0.2, random_state=42, stratify=y_clf
    )
    
    print(f"Training on {len(X_train)} samples, testing on {len(X_test)} samples across {X.shape[1]} features.")
    
    # 1. Train Regressor for continuous suitability ranking score
    rf_reg = RandomForestRegressor(
        n_estimators=120,
        max_depth=14,
        min_samples_split=4,
        min_samples_leaf=2,
        random_state=42,
        n_jobs=-1
    )
    rf_reg.fit(X_train, y_reg_train)
    
    # 2. Train Classifier for decision boundary & confidence calculation
    rf_clf = RandomForestClassifier(
        n_estimators=100,
        max_depth=12,
        min_samples_split=4,
        min_samples_leaf=2,
        random_state=42,
        n_jobs=-1
    )
    rf_clf.fit(X_train, y_clf_train)
    
    # Evaluation
    reg_preds = rf_reg.predict(X_test)
    clf_preds = rf_clf.predict(X_test)
    
    mse = float(mean_squared_error(y_reg_test, reg_preds))
    rmse = float(np.sqrt(mse))
    mae = float(mean_absolute_error(y_reg_test, reg_preds))
    r2 = float(r2_score(y_reg_test, reg_preds))
    acc = float(accuracy_score(y_clf_test, clf_preds))
    f1 = float(f1_score(y_clf_test, clf_preds))
    
    # Feature Importances
    importances = rf_reg.feature_importances_
    sorted_idx = np.argsort(importances)[::-1]
    top_features = [{"feature": feature_names[i], "importance": round(float(importances[i]), 4)} for i in sorted_idx[:10]]
    
    metrics = {
        "samples_count": len(X),
        "train_samples": len(X_train),
        "test_samples": len(X_test),
        "features_count": len(feature_names),
        "r2_score": round(r2, 4),
        "rmse": round(rmse, 4),
        "mae": round(mae, 4),
        "accuracy": round(acc, 4),
        "f1_score": round(f1, 4),
        "top_features": top_features
    }
    
    model_artifact = {
        "regressor": rf_reg,
        "classifier": rf_clf,
        "feature_names": feature_names,
        "metrics": metrics,
        "model_type": "RandomForestRegressor + RandomForestClassifier",
        "description": "Simulation-grounded architecture solution suitability ranking model."
    }
    
    default_model_path = os.path.join(os.path.dirname(__file__), "models", "solution_ranker.joblib")
    out_model = model_output_path or default_model_path
    os.makedirs(os.path.dirname(out_model), exist_ok=True)
    joblib.dump(model_artifact, out_model)
    
    # Also save metrics JSON
    metrics_path = os.path.join(os.path.dirname(out_model), "model_metrics.json")
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)
        
    print(f"Model saved successfully to: {out_model}")
    print(f"Evaluation Metrics: R^2={r2:.4f}, MAE={mae:.4f}, Accuracy={acc:.4f}, F1={f1:.4f}")
    print("Top 5 Driving Features:")
    for tf in top_features[:5]:
        print(f"  - {tf['feature']}: {tf['importance']:.4f}")
        
    return out_model, metrics

if __name__ == "__main__":
    train_and_save_model()
