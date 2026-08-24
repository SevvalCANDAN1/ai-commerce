"""Train a PyTorch tabular MLP for late-delivery prediction."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import (
    average_precision_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    roc_auc_score,
)
from torch.utils.data import DataLoader

from ml.src.columns import CATEGORICAL, NUMERIC
from ml.src.features_late_delivery import save_late_delivery_dataset
from ml.src.nn_data import LateDeliveryDataset, TabularCodec
from ml.src.nn_model import TabularMLP
from ml.src.paths import MODELS_DIR, PROCESSED_DIR
from ml.src.train_late_delivery import time_split


def best_f1_threshold(y_true: np.ndarray, proba: np.ndarray) -> float:
    prec, rec, thr = precision_recall_curve(y_true, proba)
    if len(thr) == 0:
        return 0.5
    denom = prec[:-1] + rec[:-1]
    f1 = np.divide(2 * prec[:-1] * rec[:-1], denom, out=np.zeros_like(denom), where=denom > 0)
    return float(thr[int(np.argmax(f1))])


@torch.no_grad()
def predict_proba(model: TabularMLP, loader: DataLoader, device: torch.device) -> tuple[np.ndarray, np.ndarray]:
    model.eval()
    probs, labels = [], []
    for x_num, x_cat, y in loader:
        x_num = x_num.to(device)
        x_cat = x_cat.to(device)
        logits = model(x_num, x_cat)
        probs.append(torch.sigmoid(logits).cpu().numpy())
        labels.append(y.numpy().astype(np.int64))
    return np.concatenate(probs), np.concatenate(labels)


def evaluate(y_true: np.ndarray, proba: np.ndarray, threshold: float | None = None) -> dict:
    y_true = y_true.astype(np.int64)
    thr = best_f1_threshold(y_true, proba) if threshold is None else threshold
    pred = (proba >= thr).astype(int)
    report = classification_report(y_true, pred, digits=3, output_dict=True, zero_division=0)
    late = report.get("1") or report.get("1.0") or {"precision": 0.0, "recall": 0.0, "f1-score": 0.0}
    return {
        "threshold": float(thr),
        "roc_auc": float(roc_auc_score(y_true, proba)),
        "pr_auc": float(average_precision_score(y_true, proba)),
        "pr_auc_baseline": float(y_true.mean()),
        "f1_at_0_5": float(f1_score(y_true, (proba >= 0.5).astype(int), pos_label=1, zero_division=0)),
        "late_precision": float(late["precision"]),
        "late_recall": float(late["recall"]),
        "late_f1": float(late["f1-score"]),
        "accuracy": float(report["accuracy"]),
        "confusion_matrix": confusion_matrix(y_true, pred).tolist(),
        "classification_report": classification_report(y_true, pred, digits=3, zero_division=0),
    }


def train(
    epochs: int = 20,
    batch_size: int = 512,
    lr: float = 1e-3,
    hidden: list[int] | None = None,
    device: str | None = None,
) -> dict:
    hidden = hidden or [128, 64]
    device_t = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))

    processed = PROCESSED_DIR / "late_delivery_orders.csv"
    if processed.exists():
        df = pd.read_csv(processed, parse_dates=["order_purchase_timestamp"])
    else:
        df = save_late_delivery_dataset()

    train_df, valid_df = time_split(df)
    codec = TabularCodec.fit(train_df)

    x_num_tr, x_cat_tr = codec.transform(train_df)
    x_num_va, x_cat_va = codec.transform(valid_df)
    y_tr = train_df["late"].to_numpy()
    y_va = valid_df["late"].to_numpy()

    train_loader = DataLoader(
        LateDeliveryDataset(x_num_tr, x_cat_tr, y_tr),
        batch_size=batch_size,
        shuffle=True,
    )
    valid_loader = DataLoader(
        LateDeliveryDataset(x_num_va, x_cat_va, y_va),
        batch_size=batch_size,
        shuffle=False,
    )

    model = TabularMLP(
        n_numeric=len(NUMERIC),
        cat_cardinalities=[codec.cat_cardinalities[c] for c in CATEGORICAL],
        hidden=hidden,
    ).to(device_t)

    # pos_weight = n_neg / n_pos  -> minority (late=1) gets higher loss weight
    n_pos = max(int(y_tr.sum()), 1)
    n_neg = len(y_tr) - n_pos
    pos_weight = torch.tensor([n_neg / n_pos], device=device_t)
    criterion = torch.nn.BCEWithLogitsLoss(pos_weight=pos_weight)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-4)

    best_pr = -1.0
    best_state = None
    history = []

    for epoch in range(1, epochs + 1):
        model.train()
        total_loss = 0.0
        n_batches = 0
        for x_num, x_cat, y in train_loader:
            x_num = x_num.to(device_t)
            x_cat = x_cat.to(device_t)
            y = y.to(device_t)

            optimizer.zero_grad()
            logits = model(x_num, x_cat)
            loss = criterion(logits, y)
            loss.backward()
            optimizer.step()

            total_loss += float(loss.item())
            n_batches += 1

        proba, labels = predict_proba(model, valid_loader, device_t)
        metrics = evaluate(labels, proba)
        avg_loss = total_loss / max(n_batches, 1)
        history.append(
            {
                "epoch": epoch,
                "train_loss": avg_loss,
                "roc_auc": metrics["roc_auc"],
                "pr_auc": metrics["pr_auc"],
                "late_f1": metrics["late_f1"],
            }
        )
        print(
            f"epoch {epoch:02d}/{epochs}  loss={avg_loss:.4f}  "
            f"ROC={metrics['roc_auc']:.3f}  PR={metrics['pr_auc']:.3f}  "
            f"F1@tuned={metrics['late_f1']:.3f}"
        )

        if metrics["pr_auc"] > best_pr:
            best_pr = metrics["pr_auc"]
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}

    assert best_state is not None
    model.load_state_dict(best_state)
    proba, labels = predict_proba(model, valid_loader, device_t)
    final = evaluate(labels, proba)
    final["model"] = "tabular_mlp"
    final["device"] = str(device_t)
    final["n_train"] = int(len(train_df))
    final["n_valid"] = int(len(valid_df))
    final["train_late_rate"] = float(y_tr.mean())
    final["valid_late_rate"] = float(y_va.mean())
    final["pos_weight"] = float(n_neg / n_pos)
    final["history"] = history

    print("\n=== Best validation (by PR-AUC) ===")
    print(f"ROC-AUC: {final['roc_auc']:.3f} | PR-AUC: {final['pr_auc']:.3f} (baseline {final['pr_auc_baseline']:.3f})")
    print(f"threshold={final['threshold']:.3f}")
    print(
        f"Late P/R/F1: {final['late_precision']:.3f} / "
        f"{final['late_recall']:.3f} / {final['late_f1']:.3f}"
    )
    print(final["classification_report"])
    print("Confusion matrix [[TN FP] [FN TP]]:")
    print(final["confusion_matrix"])

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    ckpt_path = MODELS_DIR / "late_delivery_mlp.pt"
    meta_path = MODELS_DIR / "late_delivery_mlp_meta.json"
    torch.save(
        {
            "state_dict": best_state,
            "codec": codec,
            "threshold": final["threshold"],
            "numeric": NUMERIC,
            "categorical": CATEGORICAL,
            "hidden": hidden,
            "cat_cardinalities": [codec.cat_cardinalities[c] for c in CATEGORICAL],
        },
        ckpt_path,
    )
    serializable = {k: v for k, v in final.items() if k != "classification_report"}
    meta_path.write_text(json.dumps(serializable, indent=2), encoding="utf-8")
    print(f"Saved -> {ckpt_path}")
    print(f"Saved -> {meta_path}")
    return final


if __name__ == "__main__":
    train()
