"""PyTorch tabular dataset with categorical integer codes + scaled numerics."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import torch
from sklearn.preprocessing import StandardScaler
from torch.utils.data import Dataset

from ml.src.columns import CATEGORICAL, NUMERIC


@dataclass
class TabularCodec:
    numeric: list[str]
    categorical: list[str]
    scaler: StandardScaler
    cat_maps: dict[str, dict[str, int]]
    cat_cardinalities: dict[str, int]

    def transform(self, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        x_num = self.scaler.transform(df[self.numeric].astype(float).fillna(0.0))
        cat_cols = []
        for col in self.categorical:
            mapping = self.cat_maps[col]
            # 0 = unknown / unseen
            codes = df[col].fillna("__NA__").astype(str).map(mapping).fillna(0).astype(int)
            cat_cols.append(codes.to_numpy())
        x_cat = np.stack(cat_cols, axis=1)
        return x_num.astype(np.float32), x_cat.astype(np.int64)

    @classmethod
    def fit(cls, df: pd.DataFrame, numeric: list[str] | None = None, categorical: list[str] | None = None) -> "TabularCodec":
        numeric = numeric or NUMERIC
        categorical = categorical or CATEGORICAL
        scaler = StandardScaler()
        scaler.fit(df[numeric].astype(float).fillna(0.0))

        cat_maps: dict[str, dict[str, int]] = {}
        cat_cardinalities: dict[str, int] = {}
        for col in categorical:
            values = sorted(df[col].fillna("__NA__").astype(str).unique().tolist())
            # reserve 0 for unknown
            mapping = {v: i + 1 for i, v in enumerate(values)}
            cat_maps[col] = mapping
            cat_cardinalities[col] = len(mapping) + 1
        return cls(numeric, categorical, scaler, cat_maps, cat_cardinalities)


class LateDeliveryDataset(Dataset):
    def __init__(self, x_num: np.ndarray, x_cat: np.ndarray, y: np.ndarray):
        self.x_num = torch.from_numpy(x_num)
        self.x_cat = torch.from_numpy(x_cat)
        self.y = torch.from_numpy(y.astype(np.float32))

    def __len__(self) -> int:
        return len(self.y)

    def __getitem__(self, idx: int):
        return self.x_num[idx], self.x_cat[idx], self.y[idx]
