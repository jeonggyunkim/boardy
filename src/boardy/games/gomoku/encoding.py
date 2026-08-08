"""Board -> CNN input planes, and the flat cell action space.

Actions are "r,c" strings (see spec.py) but the network works over a flat
index space 0..size*size-1 in row-major order.
"""

from __future__ import annotations

import numpy as np

from .board import Board

NUM_PLANES = 4  # current player's stones, opponent's stones, last move, color-to-move


def action_to_index(action: str, size: int) -> int:
    r, c = (int(v) for v in action.split(","))
    return r * size + c


def index_to_action(index: int, size: int) -> str:
    return f"{index // size},{index % size}"


def encode_board(board: Board) -> np.ndarray:
    n = board.size
    mine = np.zeros((n, n), dtype=np.float32)
    theirs = np.zeros((n, n), dtype=np.float32)
    last = np.zeros((n, n), dtype=np.float32)

    me = board.to_move
    for i, v in enumerate(board.cells):
        if v == 0:
            continue
        r, c = divmod(i, n)
        (mine if v == me else theirs)[r, c] = 1.0

    if board.last_move is not None:
        last[board.last_move] = 1.0

    color_plane = np.ones((n, n), dtype=np.float32) if me == 1 else np.zeros((n, n), dtype=np.float32)

    return np.stack([mine, theirs, last, color_plane], axis=0)


def legal_action_mask(board: Board) -> np.ndarray:
    n = board.size
    mask = np.zeros(n * n, dtype=np.float32)
    for r, c in board.legal_moves():
        mask[r * n + c] = 1.0
    return mask
