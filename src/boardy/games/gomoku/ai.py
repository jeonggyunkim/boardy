"""Shared PolicyValueNet singleton for web AI seats."""

from __future__ import annotations

from pathlib import Path

import torch

from .network import PolicyValueNet

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
# best.pt is the arena-gated network (see train.py); latest.pt is just
# whatever the in-progress candidate looked like most recently and may be
# temporarily behind best.pt, so prefer best.pt.
_CHECKPOINT_CANDIDATES = [
    _REPO_ROOT / "checkpoints_gomoku" / "best.pt",
    _REPO_ROOT / "checkpoints_gomoku" / "latest.pt",
]

_net: PolicyValueNet | None = None
_net_source: str = "untrained"


def get_shared_net() -> PolicyValueNet:
    global _net, _net_source
    if _net is None:
        _net = PolicyValueNet()
        for path in _CHECKPOINT_CANDIDATES:
            if path.exists():
                _net.load_state_dict(torch.load(path, map_location="cpu"))
                _net.eval()
                _net_source = str(path)
                break
    return _net


def net_source() -> str:
    get_shared_net()
    return _net_source
