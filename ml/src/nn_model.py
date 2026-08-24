"""Tabular MLP with categorical embeddings."""

from __future__ import annotations

import torch
import torch.nn as nn


class TabularMLP(nn.Module):
    """
    Each categorical column -> Embedding
    Concat(embeddings, numerics) -> MLP -> logit (BCEWithLogitsLoss)
    """

    def __init__(
        self,
        n_numeric: int,
        cat_cardinalities: list[int],
        emb_dim: int = 8,
        hidden: list[int] | None = None,
        dropout: float = 0.2,
    ):
        super().__init__()
        hidden = hidden or [128, 64]

        self.embeddings = nn.ModuleList(
            [nn.Embedding(card, min(emb_dim, max(2, (card + 1) // 2))) for card in cat_cardinalities]
        )
        emb_out = sum(emb.embedding_dim for emb in self.embeddings)
        in_dim = n_numeric + emb_out

        layers: list[nn.Module] = []
        prev = in_dim
        for h in hidden:
            layers.extend(
                [
                    nn.Linear(prev, h),
                    nn.ReLU(),
                    nn.BatchNorm1d(h),
                    nn.Dropout(dropout),
                ]
            )
            prev = h
        layers.append(nn.Linear(prev, 1))
        self.mlp = nn.Sequential(*layers)

    def forward(self, x_num: torch.Tensor, x_cat: torch.Tensor) -> torch.Tensor:
        embs = [emb(x_cat[:, i]) for i, emb in enumerate(self.embeddings)]
        x = torch.cat([x_num] + embs, dim=1)
        return self.mlp(x).squeeze(1)
