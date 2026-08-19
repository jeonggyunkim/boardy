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
    me = board.to_move

    cells = np.asarray(board.cells, dtype=np.int8).reshape(n, n)
    mine = (cells == me).astype(np.float32)
    theirs = ((cells != 0) & (cells != me)).astype(np.float32)

    last = np.zeros((n, n), dtype=np.float32)
    if board.last_move is not None:
        last[board.last_move] = 1.0

    color_plane = np.full((n, n), 1.0 if me == 1 else 0.0, dtype=np.float32)

    return np.stack([mine, theirs, last, color_plane], axis=0)


def legal_action_mask(board: Board) -> np.ndarray:
    return legal_action_mask_from_moves(board.legal_moves(), board.size)


def legal_action_mask_from_moves(moves: list[tuple[int, int]], size: int) -> np.ndarray:
    """Same as legal_action_mask, but takes an already-computed move list --
    Board.legal_moves() re-derives Black's Renju-forbidden cells from
    scratch every call (see renju.py), which isn't cheap, so callers that
    already have the list (e.g. MCTS expansion) should pass it through
    instead of paying for a second full scan."""
    mask = np.zeros(size * size, dtype=np.float32)
    for r, c in moves:
        mask[r * size + c] = 1.0
    return mask
