"""Policy/value network: MLP trunk, card-policy head, mission-success value head."""

from __future__ import annotations

import numpy as np
import torch
from torch import nn

from .encoding import NUM_CARDS, OBS_SIZE


class PolicyValueNet(nn.Module):
    def __init__(self, obs_size: int = OBS_SIZE, hidden: int = 256, num_cards: int = NUM_CARDS) -> None:
        super().__init__()
        self.trunk = nn.Sequential(
            nn.Linear(obs_size, hidden),
            nn.ReLU(),
            nn.Linear(hidden, hidden),
            nn.ReLU(),
            nn.Linear(hidden, hidden),
            nn.ReLU(),
        )
        self.policy_head = nn.Linear(hidden, num_cards)
        self.value_head = nn.Sequential(nn.Linear(hidden, 1), nn.Sigmoid())

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        h = self.trunk(x)
        return self.policy_head(h), self.value_head(h).squeeze(-1)

    @torch.no_grad()
    def predict(self, obs: np.ndarray, legal_mask: np.ndarray) -> tuple[np.ndarray, float]:
        """Single-observation inference: masked policy probs + scalar value."""
        self.eval()
        x = torch.from_numpy(obs).float().unsqueeze(0)
        logits, value = self.forward(x)
        logits = logits.squeeze(0).numpy()
        mask = legal_mask.astype(bool)
        logits = np.where(mask, logits, -1e9)
        probs = np.exp(logits - logits.max())
        probs *= mask
        total = probs.sum()
        probs = probs / total if total > 0 else mask.astype(np.float32) / max(mask.sum(), 1)
        return probs, float(value.item())
