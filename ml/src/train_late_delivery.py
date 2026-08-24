"""Train a late-delivery classifier with a time-based split.

Default model: HistGradientBoosting (stronger tabular baseline).
Decision threshold is tuned on validation for best late-class F1
(0.5 + class_weight='balanced' often destroys precision).
"""

from __future__ import annotations

import json

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler

from ml.src.columns import CATEGORICAL, NUMERIC
from ml.src.features_late_delivery import save_late_delivery_dataset
from ml.src.paths import MODELS_DIR, PROCESSED_DIR


def time_split(df: pd.DataFrame, valid_ratio: float = 0.2):
    df = df.sort_values("order_purchase_timestamp")
    cut = int(len(df) * (1 - valid_ratio))
    train = df.iloc[:cut].copy()
    valid = df.iloc[cut:].copy()
    return train, valid


def build_pipeline(model: str = "hgb") -> Pipeline:
    if model == "logreg":
        pre = ColumnTransformer(
            transformers=[
                (
                    "num",
                    Pipeline(
                        [
                            ("imputer", SimpleImputer(strategy="median")),
                            ("scaler", StandardScaler()),
                        ]
                    ),
                    NUMERIC,
                ),
                (
                    "cat",
                    Pipeline(
                        [
                            ("imputer", SimpleImputer(strategy="most_frequent")),
                            (
                                "onehot",
                                OneHotEncoder(handle_unknown="ignore", min_frequency=50),
                            ),
                        ]
                    ),
                    CATEGORICAL,
                ),
            ]
        )
        clf = LogisticRegression(
            max_iter=1000,
            class_weight="balanced",
            random_state=42,
        )
        return Pipeline([("pre", pre), ("clf", clf)])

    # HistGradientBoosting: ordinal cats + native missing handling on numerics
    pre = ColumnTransformer(
        transformers=[
            (
                "num",
                SimpleImputer(strategy="median"),
                NUMERIC,
            ),
            (
                "cat",
                Pipeline(
                    [
                        ("imputer", SimpleImputer(strategy="most_frequent")),
                        (
                            "ord",
                            OrdinalEncoder(
                                handle_unknown="use_encoded_value",
                                unknown_value=-1,
                            ),
                        ),
                    ]
                ),
                CATEGORICAL,
            ),
        ]
    )
    clf = HistGradientBoostingClassifier(
        max_depth=6,
        learning_rate=0.08,
        max_iter=300,
        l2_regularization=0.1,
        early_stopping=True,
        validation_fraction=0.1,
        random_state=42,
        # No class_weight: probabilities stay better calibrated;
        # imbalance handled by threshold tuning on F1 / business cost.
    )
    return Pipeline([("pre", pre), ("clf", clf)])


def best_f1_threshold(y_true, proba: np.ndarray) -> tuple[float, float]:
    prec, rec, thr = precision_recall_curve(y_true, proba)
    if len(thr) == 0:
        return 0.5, 0.0
    denom = prec[:-1] + rec[:-1]
    f1 = np.divide(2 * prec[:-1] * rec[:-1], denom, out=np.zeros_like(denom), where=denom > 0)
    i = int(np.argmax(f1))
    return float(thr[i]), float(f1[i])


def evaluate(model: Pipeline, X, y, threshold: float | None = None) -> dict:
    proba = model.predict_proba(X)[:, 1]
    tuned_thr, tuned_f1 = best_f1_threshold(y, proba)
    thr = tuned_thr if threshold is None else threshold
    pred = (proba >= thr).astype(int)
    report = classification_report(y, pred, digits=3, output_dict=True)
    pred_05 = (proba >= 0.5).astype(int)
    return {
        "threshold": float(thr),
        "best_f1_threshold": float(tuned_thr),
        "best_f1_at_tuned_threshold": float(tuned_f1),
        "f1_at_0_5": float(f1_score(y, pred_05, pos_label=1)),
        "roc_auc": float(roc_auc_score(y, proba)),
        "pr_auc": float(average_precision_score(y, proba)),
        "pr_auc_baseline": float(y.mean()),
        "accuracy": float(report["accuracy"]),
        "late_precision": float(report["1"]["precision"]),
        "late_recall": float(report["1"]["recall"]),
        "late_f1": float(report["1"]["f1-score"]),
        "majority_baseline_accuracy": float(1 - y.mean()),
        "confusion_matrix": confusion_matrix(y, pred).tolist(),
        "classification_report": classification_report(y, pred, digits=3),
    }


def train(save: bool = True, model: str = "hgb") -> dict:
    processed = PROCESSED_DIR / "late_delivery_orders.csv"
    if processed.exists():
        df = pd.read_csv(processed, parse_dates=["order_purchase_timestamp"])
    else:
        df = save_late_delivery_dataset()

    train_df, valid_df = time_split(df)
    X_train, y_train = train_df[NUMERIC + CATEGORICAL], train_df["late"]
    X_valid, y_valid = valid_df[NUMERIC + CATEGORICAL], valid_df["late"]

    pipe = build_pipeline(model=model)
    pipe.fit(X_train, y_train)

    metrics = evaluate(pipe, X_valid, y_valid)
    metrics["model"] = model
    metrics["n_train"] = int(len(train_df))
    metrics["n_valid"] = int(len(valid_df))
    metrics["train_late_rate"] = float(y_train.mean())
    metrics["valid_late_rate"] = float(y_valid.mean())

    print(f"=== Validation ({model}) ===")
    print(f"Train: {metrics['n_train']:,} | Valid: {metrics['n_valid']:,}")
    print(f"Late rate train/valid: {metrics['train_late_rate']:.2%} / {metrics['valid_late_rate']:.2%}")
    print(f"PR-AUC baseline (late rate): {metrics['pr_auc_baseline']:.3f}")
    print(f"ROC-AUC: {metrics['roc_auc']:.3f} | PR-AUC: {metrics['pr_auc']:.3f}")
    print(f"F1@0.5: {metrics['f1_at_0_5']:.3f} | best thr={metrics['threshold']:.3f} -> F1={metrics['late_f1']:.3f}")
    print(
        f"Late P/R/F1 @tuned: {metrics['late_precision']:.3f} / "
        f"{metrics['late_recall']:.3f} / {metrics['late_f1']:.3f}"
    )
    print(metrics["classification_report"])
    print("Confusion matrix [[TN FP] [FN TP]]:")
    print(metrics["confusion_matrix"])

    if save:
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        model_path = MODELS_DIR / f"late_delivery_{model}.joblib"
        meta_path = MODELS_DIR / f"late_delivery_{model}_meta.json"
        joblib.dump({"model": pipe, "threshold": metrics["threshold"], "features": NUMERIC + CATEGORICAL}, model_path)
        serializable = {k: v for k, v in metrics.items() if k != "classification_report"}
        meta_path.write_text(json.dumps(serializable, indent=2), encoding="utf-8")
        print(f"Saved model -> {model_path}")
        print(f"Saved metrics -> {meta_path}")

    return metrics


if __name__ == "__main__":
    train(model="hgb")
