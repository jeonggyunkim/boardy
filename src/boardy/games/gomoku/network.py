"""AlphaZero-style CNN policy/value network for Gomoku.

Residual tower (default 10 blocks x 128 channels, ~5M params) sized to
exceed strong human Renju play when paired with a real MCTS search --
big enough to matter, small enough to batch cheaply on a single GPU.
Policy head emits per-cell logits; value head emits tanh in [-1, 1] from
the current player-to-move's perspective (this is a real zero-sum game,
unlike Deep Sea Crew's cooperative [0, 1] success probability).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import nn

from .board import DEFAULT_SIZE, Board
from .encoding import NUM_PLANES, encode_board, legal_action_mask, legal_action_mask_from_moves

DEFAULT_CHANNELS = 128
DEFAULT_NUM_BLOCKS = 10


class ConvBlock(nn.Module):
    def __init__(self, in_ch: int, out_ch: int) -> None:
        super().__init__()
        self.conv = nn.Conv2d(in_ch, out_ch, 3, padding=1)
        self.bn = nn.BatchNorm2d(out_ch)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return torch.relu(self.bn(self.conv(x)))


class ResidualBlock(nn.Module):
    def __init__(self, channels: int) -> None:
        super().__init__()
        self.conv1 = nn.Conv2d(channels, channels, 3, padding=1)
        self.bn1 = nn.BatchNorm2d(channels)
        self.conv2 = nn.Conv2d(channels, channels, 3, padding=1)
        self.bn2 = nn.BatchNorm2d(channels)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        h = torch.relu(self.bn1(self.conv1(x)))
        h = self.bn2(self.conv2(h))
        return torch.relu(x + h)


class PolicyValueNet(nn.Module):
    def __init__(
        self,
        board_size: int = DEFAULT_SIZE,
        channels: int = DEFAULT_CHANNELS,
        num_blocks: int = DEFAULT_NUM_BLOCKS,
        in_planes: int = NUM_PLANES,
    ) -> None:
        super().__init__()
        self.board_size = board_size
        self.channels = channels
        self.num_blocks = num_blocks
        self.in_planes = in_planes
        n_cells = board_size * board_size

        self.stem = ConvBlock(in_planes, channels)
        self.tower = nn.Sequential(*[ResidualBlock(channels) for _ in range(num_blocks)])

        self.policy_conv = nn.Conv2d(channels, 4, 1)
        self.policy_bn = nn.BatchNorm2d(4)
        self.policy_fc = nn.Linear(4 * n_cells, n_cells)

        self.value_conv = nn.Conv2d(channels, 2, 1)
        self.value_bn = nn.BatchNorm2d(2)
        self.value_fc1 = nn.Linear(2 * n_cells, 64)
        self.value_fc2 = nn.Linear(64, 1)

    @property
    def config(self) -> dict[str, int]:
        return {
            "board_size": self.board_size,
            "channels": self.channels,
            "num_blocks": self.num_blocks,
            "in_planes": self.in_planes,
        }

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        h = self.tower(self.stem(x))

        p = torch.relu(self.policy_bn(self.policy_conv(h)))
        p = p.flatten(1)
        logits = self.policy_fc(p)

        v = torch.relu(self.value_bn(self.value_conv(h)))
        v = v.flatten(1)
        v = torch.relu(self.value_fc1(v))
        value = torch.tanh(self.value_fc2(v)).squeeze(-1)

        return logits, value

    @torch.no_grad()
    def predict(self, board: Board, legal_moves: list[tuple[int, int]] | None = None) -> tuple[np.ndarray, float]:
        """Policy over all cells (masked to legal, current-player-relative)
        + scalar value in [-1, 1] from the current player-to-move's view.
        Pass `legal_moves` if the caller already computed it (e.g. MCTS
        expansion) -- Board.legal_moves() re-derives Black's Renju-forbidden
        cells from scratch every call, so recomputing it here too would
        silently double that cost for no reason."""
        self.eval()
        device = next(self.parameters()).device
        obs = encode_board(board)
        x = torch.from_numpy(obs).float().unsqueeze(0).to(device)
        logits, value = self.forward(x)
        logits = logits.squeeze(0).cpu().numpy()
        mask = (
            legal_action_mask(board) if legal_moves is None else legal_action_mask_from_moves(legal_moves, board.size)
        ).astype(bool)
        logits = np.where(mask, logits, -1e9)
        probs = np.exp(logits - logits.max())
        probs *= mask
        total = probs.sum()
        probs = probs / total if total > 0 else mask.astype(np.float32) / max(mask.sum(), 1)
        return probs, float(value.item())


def save_checkpoint(net: PolicyValueNet, path: Path) -> None:
    """Save weights alongside the architecture config that produced them,
    so `load_checkpoint` can reconstruct a matching network instead of
    relying on whatever `PolicyValueNet()`'s defaults happen to be at
    load time."""
    torch.save({"config": net.config, "state_dict": net.state_dict()}, path)


def load_checkpoint(path: Path, device: str | torch.device = "cpu") -> PolicyValueNet:
    payload: dict[str, Any] = torch.load(path, map_location="cpu")
    if "config" not in payload:
        raise ValueError(
            f"{path} is not a config-tagged checkpoint (old format). "
            "Re-train from scratch -- the network architecture has changed."
        )
    net = PolicyValueNet(**payload["config"])
    net.load_state_dict(payload["state_dict"])
    net.to(device)
    return net
