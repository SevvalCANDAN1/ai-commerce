"""Train a global weekly demand model and export a JSON artifact for the API."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error
from sklearn.preprocessing import OrdinalEncoder

from ml.src.features_demand import save_weekly_demand
from ml.src.paths import MODELS_DIR

LAGS = (1, 2, 4)
ROLL_WINDOW = 4
HORIZON = 8
HISTORY_WEEKS = 12


def _add_calendar(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["week"] = pd.to_datetime(df["week"])
    iso = df["week"].dt.isocalendar()
    df["week_of_year"] = iso.week.astype(int)
    df["month"] = df["week"].dt.month
    df["week_sin"] = np.sin(2 * np.pi * df["week_of_year"] / 52)
    df["week_cos"] = np.cos(2 * np.pi * df["week_of_year"] / 52)
    return df


def _add_lags(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["category", "week"]).copy()
    grouped = df.groupby("category")["units"]
    for lag in LAGS:
        df[f"lag_{lag}"] = grouped.shift(lag)
    df["roll_4"] = grouped.shift(1).rolling(ROLL_WINDOW).mean()
    return df


def _feature_frame(weekly: pd.DataFrame) -> pd.DataFrame:
    complete = []
    weekly = weekly.copy()
    weekly["week"] = pd.to_datetime(weekly["week"])
    for category, part in weekly.groupby("category"):
        part = part.sort_values("week")
        idx = pd.date_range(part["week"].min(), part["week"].max(), freq="7D")
        filled = part.set_index("week").reindex(idx)
        filled["category"] = category
        filled["units"] = filled["units"].interpolate(limit=2).fillna(0)
        filled["gmv"] = filled["gmv"].interpolate(limit=2).fillna(0)
        filled = filled.reset_index().rename(columns={"index": "week"})
        complete.append(filled)
    panel = pd.concat(complete, ignore_index=True)
    panel = _add_calendar(panel)
    panel = _add_lags(panel)
    return panel.dropna(subset=[f"lag_{LAGS[-1]}", "roll_4"]).reset_index(drop=True)


FEATURE_COLS = ["week_sin", "week_cos", "month", "lag_1", "lag_2", "lag_4", "roll_4"]


def _time_split(df: pd.DataFrame, valid_weeks: int = 12) -> tuple[pd.DataFrame, pd.DataFrame]:
    cutoff = df["week"].max() - pd.Timedelta(weeks=valid_weeks)
    return df[df["week"] <= cutoff].copy(), df[df["week"] > cutoff].copy()


def _recursive_forecast(
    model: HistGradientBoostingRegressor,
    encoder: OrdinalEncoder,
    history: pd.DataFrame,
    category: str,
    horizon: int,
) -> list[dict]:
    series = history[history["category"] == category].sort_values("week").copy()
    units = series["units"].tolist()
    last_week = pd.Timestamp(series["week"].max())
    cat_code = encoder.transform(pd.DataFrame({"category": [category]}))[0][0]
    out: list[dict] = []
    for step in range(1, horizon + 1):
        week = last_week + pd.Timedelta(weeks=step)
        week_of_year = int(week.isocalendar().week)
        row = {
            "cat": cat_code,
            "week_sin": np.sin(2 * np.pi * week_of_year / 52),
            "week_cos": np.cos(2 * np.pi * week_of_year / 52),
            "month": int(week.month),
            "lag_1": units[-1],
            "lag_2": units[-2] if len(units) > 1 else units[-1],
            "lag_4": units[-4] if len(units) > 3 else units[-1],
            "roll_4": float(np.mean(units[-4:])),
        }
        pred = float(max(0.0, model.predict(pd.DataFrame([row]))[0]))
        units.append(pred)
        out.append({"week": week.strftime("%Y-%m-%d"), "predicted_units": round(pred, 2)})
    return out


def train(save: bool = True) -> dict:
    weekly, source = save_weekly_demand()

    panel = _feature_frame(weekly)
    train_df, valid_df = _time_split(panel)

    encoder = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)
    train_df = train_df.copy()
    valid_df = valid_df.copy()
    train_df["cat"] = encoder.fit_transform(train_df[["category"]]).ravel()
    valid_df["cat"] = encoder.transform(valid_df[["category"]]).ravel()

    x_cols = ["cat", *FEATURE_COLS]
    model = HistGradientBoostingRegressor(max_depth=6, learning_rate=0.08, random_state=42)
    model.fit(train_df[x_cols], train_df["units"])

    pred = model.predict(valid_df[x_cols])
    mae = float(mean_absolute_error(valid_df["units"], pred))
    mask = valid_df["units"].to_numpy() >= 10
    if mask.any():
        mape = float(
            mean_absolute_percentage_error(valid_df["units"].to_numpy()[mask], pred[mask])
        )
    else:
        mape = float("nan")

    categories = sorted(panel["category"].unique())
    forecasts = {}
    for category in categories:
        hist = (
            panel[panel["category"] == category]
            .sort_values("week")
            .tail(HISTORY_WEEKS)
        )
        forecasts[category] = {
            "history": [
                {"week": w.strftime("%Y-%m-%d"), "units": float(u)}
                for w, u in zip(hist["week"], hist["units"])
            ],
            "forecast": _recursive_forecast(model, encoder, panel, category, HORIZON),
        }

    metrics = {
        "source": source,
        "n_train": int(len(train_df)),
        "n_valid": int(len(valid_df)),
        "n_categories": len(categories),
        "mae": round(mae, 3),
        "mape": round(mape, 3),
        "horizon_weeks": HORIZON,
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }
    print("=== Demand forecast ===")
    print(f"Source: {source} | categories: {metrics['n_categories']}")
    print(f"Train/valid rows: {metrics['n_train']:,} / {metrics['n_valid']:,}")
    print(f"MAE: {metrics['mae']} | MAPE: {metrics['mape']}")

    if save:
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        joblib.dump({"model": model, "encoder": encoder, "features": x_cols}, MODELS_DIR / "demand_forecast.joblib")
        artifact = {"metrics": metrics, "categories": forecasts}
        (MODELS_DIR / "demand_forecast.json").write_text(
            json.dumps(artifact, indent=2),
            encoding="utf-8",
        )
        print(f"Saved -> {MODELS_DIR / 'demand_forecast.json'}")

    return metrics


if __name__ == "__main__":
    train()
