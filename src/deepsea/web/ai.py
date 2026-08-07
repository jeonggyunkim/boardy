"""Shared PolicyValueNet singleton for AI seats.

Loads the first checkpoint it finds (see docs/PLAN.md Phase 2 for training
status — as of writing, training this small hasn't clearly beaten a plain
ISMCTS search using an untrained network, but search itself is a real
strength boost over RandomPlayer either way, see the Phase 2 log). Falls
back to an untrained network if no checkpoint exists, which still benefits
from search.
"""

from __future__ import annotations

from pathlib import Path

import torch

from ..network import PolicyValueNet

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_CHECKPOINT_CANDIDATES = [
    _REPO_ROOT / "checkpoints_easy" / "latest.pt",
    _REPO_ROOT / "checkpoints" / "latest.pt",
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
