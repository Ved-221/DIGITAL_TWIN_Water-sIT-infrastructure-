import os
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Tuple
import joblib
import pandas as pd
import numpy as np

from sklearn.model_selection import train_test_split
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import OneHotEncoder
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix, f1_score, accuracy_score

from ml.dataset import generate_training_dataset, FEATURE_COLUMNS, RECOMMENDATION_CLASSES

logger = logging.getLogger("infratwin.ml.trainer")

ARTIFACTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "ml_artifacts"))
MODEL_FILE = os.path.join(ARTIFACTS_DIR, "recommendation_model.joblib")
METADATA_FILE = os.path.join(ARTIFACTS_DIR, "model_metadata.json")

CATEGORICAL_FEATURES = ["resource_type", "environment"]
NUMERICAL_FEATURES = [
    "criticality_score",
    "cost_monthly",
    "is_active",
    "resource_age_days",
    "dependency_count",
    "dependent_count",
    "cpu_utilization",
    "memory_utilization",
    "disk_utilization_pct",
    "disk_iops",
    "network_throughput_kb_s",
    "latency_ms",
    "error_rate_pct",
    "request_rate",
    "connection_count",
    "cpu_trend_1h",
    "traffic_trend_1h",
]

def build_model_pipeline() -> Pipeline:
    """
    Constructs an end-to-end scikit-learn Pipeline with proper categorical encoding,
    missing value imputation (with missingness indicators), and a Random Forest Classifier.
    """
    cat_transformer = Pipeline(steps=[
        ("imputer", SimpleImputer(strategy="constant", fill_value="missing")),
        ("encoder", OneHotEncoder(handle_unknown="ignore", sparse_output=False))
    ])

    num_transformer = Pipeline(steps=[
        ("imputer", SimpleImputer(strategy="constant", fill_value=-1.0, add_indicator=True))
    ])

    preprocessor = ColumnTransformer(
        transformers=[
            ("cat", cat_transformer, CATEGORICAL_FEATURES),
            ("num", num_transformer, NUMERICAL_FEATURES)
        ],
        remainder="drop"
    )

    classifier = RandomForestClassifier(
        n_estimators=120,
        max_depth=10,
        min_samples_split=4,
        min_samples_leaf=2,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1
    )

    pipeline = Pipeline(steps=[
        ("preprocessor", preprocessor),
        ("classifier", classifier)
    ])

    return pipeline


def train_and_evaluate(
    num_samples_per_class: int = 250,
    random_seed: int = 42
) -> Tuple[Pipeline, Dict[str, Any]]:
    """
    Generates training data, splits into Train/Val/Test, trains the Random Forest model,
    evaluates on the held-out test split, and persists artifacts.
    """
    os.makedirs(ARTIFACTS_DIR, exist_ok=True)

    # 1. Prepare data
    df = generate_training_dataset(num_samples_per_class=num_samples_per_class, random_seed=random_seed)
    X = df[FEATURE_COLUMNS]
    y = df["recommended_action"]

    # 2. 70% Train, 15% Validation, 15% Test
    X_train_val, X_test, y_train_val, y_test = train_test_split(
        X, y, test_size=0.15, stratify=y, random_state=random_seed
    )
    X_train, X_val, y_train, y_val = train_test_split(
        X_train_val, y_train_val, test_size=0.1765, stratify=y_train_val, random_state=random_seed
    ) # 0.1765 * 0.85 approx 0.15

    # 3. Fit pipeline on train set
    pipeline = build_model_pipeline()
    pipeline.fit(X_train, y_train)

    # 4. Evaluate on validation set
    y_val_pred = pipeline.predict(X_val)
    val_f1 = float(f1_score(y_val, y_val_pred, average="macro"))

    # 5. Evaluate on held-out test set
    y_test_pred = pipeline.predict(X_test)
    test_accuracy = float(accuracy_score(y_test, y_test_pred))
    test_macro_f1 = float(f1_score(y_test, y_test_pred, average="macro"))

    report = classification_report(y_test, y_test_pred, output_dict=True, zero_division=0)
    cm = confusion_matrix(y_test, y_test_pred, labels=RECOMMENDATION_CLASSES).tolist()

    # 6. Extract global feature importances
    rf = pipeline.named_steps["classifier"]
    preprocessor = pipeline.named_steps["preprocessor"]
    transformed_feature_names = []
    try:
        cat_encoder = preprocessor.named_transformers_["cat"].named_steps["encoder"]
        cat_cols = cat_encoder.get_feature_names_out(CATEGORICAL_FEATURES).tolist()
        num_imputer = preprocessor.named_transformers_["num"].named_steps["imputer"]
        num_cols = list(NUMERICAL_FEATURES)
        if hasattr(num_imputer, "indicator_") and num_imputer.indicator_ is not None:
            num_cols += [f"{NUMERICAL_FEATURES[idx]}_is_missing" for idx in num_imputer.indicator_.features_]
        transformed_feature_names = cat_cols + num_cols
    except Exception:
        transformed_feature_names = [f"f_{i}" for i in range(len(rf.feature_importances_))]

    importances = []
    if len(transformed_feature_names) == len(rf.feature_importances_):
        sorted_indices = np.argsort(rf.feature_importances_)[::-1]
        for idx in sorted_indices[:15]:
            importances.append({
                "feature": transformed_feature_names[idx],
                "importance": round(float(rf.feature_importances_[idx]), 4)
            })

    metadata = {
        "model_type": "RandomForestClassifier",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "n_samples_total": len(df),
        "n_samples_train": len(X_train),
        "n_samples_val": len(X_val),
        "n_samples_test": len(X_test),
        "validation_macro_f1": round(val_f1, 4),
        "test_accuracy": round(test_accuracy, 4),
        "test_macro_f1": round(test_macro_f1, 4),
        "classes": RECOMMENDATION_CLASSES,
        "classification_report": report,
        "confusion_matrix": cm,
        "top_feature_importances": importances,
        "model_file": MODEL_FILE
    }

    # 7. Persist model and metadata
    joblib.dump(pipeline, MODEL_FILE)
    with open(METADATA_FILE, "w") as f:
        json.dump(metadata, f, indent=2)

    logger.info("Trained and persisted RandomForest model with Test Macro F1: %.4f", test_macro_f1)
    return pipeline, metadata


def load_trained_model() -> Tuple[Pipeline, Dict[str, Any]]:
    """Loads the persisted model pipeline and metadata from disk."""
    if not os.path.exists(MODEL_FILE) or not os.path.exists(METADATA_FILE):
        # Auto-train if not yet built
        logger.info("No persisted model found. Training initial model...")
        return train_and_evaluate()

    pipeline = joblib.load(MODEL_FILE)
    with open(METADATA_FILE, "r") as f:
        metadata = json.load(f)
    return pipeline, metadata
