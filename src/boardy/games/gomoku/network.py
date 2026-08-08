"""AlphaZero-style CNN policy/value network for Gomoku.

Small on purpose (CPU training, 9x9 board): 3 conv blocks shared trunk,
then separate policy (per-cell logits) and value (tanh, current-player
perspective — this is a real zero-sum game so value is win-probability-like
in [-1, 1], unlike Deep Sea Crew's cooperative [0, 1] success probability).
"""

from __future__ import annotations

import numpy as np
import torch
from torch import nn

from .board import Board
from .encoding import NUM_PLANES, encode_board, legal_action_mask


class ConvBlock(nn.Module):
    def __init__(self, in_ch: int, out_ch: int) -> None:
        super().__init__()
        self.conv = nn.Conv2d(in_ch, out_ch, 3, padding=1)
        self.bn = nn.BatchNorm2d(out_ch)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return torch.relu(self.bn(self.conv(x)))


class PolicyValueNet(nn.Module):
    def __init__(self, board_size: int = 9, channels: int = 64, in_planes: int = NUM_PLANES) -> None:
        super().__init__()
        self.board_size = board_size
        n_cells = board_size * board_size

        self.trunk = nn.Sequential(
            ConvBlock(in_planes, channels),
            ConvBlock(channels, channels),
            ConvBlock(channels, channels),
        )

        self.policy_conv = nn.Conv2d(channels, 2, 1)
        self.policy_bn = nn.BatchNorm2d(2)
        self.policy_fc = nn.Linear(2 * n_cells, n_cells)

        self.value_conv = nn.Conv2d(channels, 1, 1)
        self.value_bn = nn.BatchNorm2d(1)
        self.value_fc1 = nn.Linear(n_cells, 64)
        self.value_fc2 = nn.Linear(64, 1)

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        h = self.trunk(x)

        p = torch.relu(self.policy_bn(self.policy_conv(h)))
        p = p.flatten(1)
        logits = self.policy_fc(p)

        v = torch.relu(self.value_bn(self.value_conv(h)))
        v = v.flatten(1)
        v = torch.relu(self.value_fc1(v))
        value = torch.tanh(self.value_fc2(v)).squeeze(-1)

        return logits, value

    @torch.no_grad()
    def predict(self, board: Board) -> tuple[np.ndarray, float]:
        """Policy over all cells (masked to legal, current-player-relative)
        + scalar value in [-1, 1] from the current player-to-move's view."""
        self.eval()
        obs = encode_board(board)
        x = torch.from_numpy(obs).float().unsqueeze(0)
        logits, value = self.forward(x)
        logits = logits.squeeze(0).numpy()
        mask = legal_action_mask(board).astype(bool)
        logits = np.where(mask, logits, -1e9)
        probs = np.exp(logits - logits.max())
        probs *= mask
        total = probs.sum()
        probs = probs / total if total > 0 else mask.astype(np.float32) / max(mask.sum(), 1)
        return probs, float(value.item())
