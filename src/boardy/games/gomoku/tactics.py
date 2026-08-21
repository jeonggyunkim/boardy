"""Cheap, exact 1-ply tactical lookahead for Gomoku leaf positions.

Self-play diagnosis (docs/PLAN.md 2026-08-19/20) found the network's value
head can be badly miscalibrated exactly at forced continuations (e.g. not
recognizing an unstoppable open four as a loss). `tactical_result`
sidesteps that for the one case that's cheap and exact to compute
directly: whether `board.to_move` can win outright this turn, or is
already dead no matter what they play next. Runs on every non-terminal
MCTS leaf, so it's numba-jitted the same way renju.py's hot path is
(docs/PLAN.md 2026-08-21 has the perf history).

This alone won't catch a slower threat (e.g. an open three, a loss two
plies out) *at the position where it first appears* -- but MCTS explores
forward from there anyway, and the position two plies later (once the
three becomes an open four) is exactly the kind of node this does resolve
exactly, propagating back up through PUCT's backup step to the earlier
decision without this module needing to search any deeper itself.
"""

from __future__ import annotations

import numba
import numpy as np

from .board import BLACK, Board

_DIRECTIONS = np.array([(1, 0), (0, 1), (1, 1), (1, -1)], dtype=np.int64)


@numba.njit(cache=True)
def _completes_win(cells: np.ndarray, size: int, r: int, c: int, player: int, win_length: int, exact_only: bool) -> bool:
    for d in range(4):
        dr, dc = _DIRECTIONS[d, 0], _DIRECTIONS[d, 1]
        count = 1
        for sign in (1, -1):
            rr, cc = r + dr * sign, c + dc * sign
            while 0 <= rr < size and 0 <= cc < size and cells[rr * size + cc] == player:
                count += 1
                rr += dr * sign
                cc += dc * sign
        reached = count == win_length if exact_only else count >= win_length
        if reached:
            return True
    return False


@numba.njit(cache=True)
def _win_scan_jit(
    cells: np.ndarray, size: int, player: int, win_length: int, exact_only: bool, early_exit: bool
) -> tuple[np.ndarray, int]:
    """Flat indices of empty cells that complete a win for `player` (as
    `results[:count]`); stops at the first one if `early_exit`.

    Only checks empty cells within `win_length - 1` of an existing stone
    (either color) instead of the whole board: a `win_length` run through
    a candidate must have an existing same-color stone that close to it,
    so anchoring the scan on every occupied cell can't miss one, and stays
    proportional to stones-on-board rather than empty-cells (this function
    is called up to once per legal move from `tactical_result`'s loss
    check, so the whole-board version was O(n^2) -- see docs/PLAN.md
    2026-08-21).

    Doesn't place `player` at the candidate before calling `_completes_win`
    -- that function never reads `cells[r*size+c]` itself, only the
    neighbors outward from it, so the candidate's own array value doesn't
    matter and mutating it there was wasted writes."""
    n = cells.shape[0]
    seen = np.zeros(n, dtype=np.bool_)
    results = np.full(n, -1, dtype=np.int64)
    count = 0
    reach = win_length - 1
    for idx in range(n):
        if cells[idx] == 0:
            continue
        r0 = idx // size
        c0 = idx % size
        for d in range(4):
            dr, dc = _DIRECTIONS[d, 0], _DIRECTIONS[d, 1]
            for sign in (1, -1):
                for step in range(1, reach + 1):
                    rr = r0 + dr * sign * step
                    cc = c0 + dc * sign * step
                    if not (0 <= rr < size and 0 <= cc < size):
                        break
                    cidx = rr * size + cc
                    if cells[cidx] != 0 or seen[cidx]:
                        continue
                    seen[cidx] = True
                    if _completes_win(cells, size, rr, cc, player, win_length, exact_only):
                        results[count] = cidx
                        count += 1
                        if early_exit:
                            return results, count
    return results, count


def find_winning_move(board: Board) -> tuple[int, int] | None:
    """A legal move for `board.to_move` that would win immediately, if one
    exists (first one found -- for callers that only need to know one
    exists, e.g. `tactical_result`'s loss check).

    Skips `board.legal_moves()` -- that pays for a full Renju forbidden-move
    classification per empty cell, but a move completing an exact five is
    always legal regardless of double-three/double-four/overline (see
    board.py's module docstring), and `exact_only` below already keeps that
    correct for Black."""
    player = board.to_move
    exact_only = board.renju and player == BLACK
    results, count = _win_scan_jit(board.cells, board.size, player, board.win_length, exact_only, True)
    if count == 0:
        return None
    idx = int(results[0])
    return idx // board.size, idx % board.size


def find_all_winning_moves(board: Board) -> list[tuple[int, int]]:
    """Every legal move for `board.to_move` that would win immediately.
    Unlike `find_winning_move`, doesn't stop at the first one -- for a
    caller that wants to treat all of them as equally correct (a position
    can have more than one, e.g. an open four has two) rather than
    crediting whichever happens to be first in scan order."""
    player = board.to_move
    exact_only = board.renju and player == BLACK
    results, count = _win_scan_jit(board.cells, board.size, player, board.win_length, exact_only, False)
    size = board.size
    return [(int(results[i]) // size, int(results[i]) % size) for i in range(count)]


def tactical_result(
    board: Board, legal_moves: list[tuple[int, int]] | None = None
) -> tuple[float, list[tuple[int, int]] | None] | None:
    """Exact (value, winning_moves) from `board.to_move`'s perspective if
    the outcome is forced within the next ply, else None. `winning_moves`
    is every one of to_move's immediate wins when value is +1.0 (so a
    caller that also needs a policy prior can credit all of them, not just
    an arbitrary one -- and doesn't have to re-run the win search); None
    when value is -1.0, since which move is played no longer matters once
    all of them lose. `legal_moves` is reused if the caller already has it
    (mcts.py always does) -- unlike `find_winning_move`, this loop needs
    genuinely *legal* candidates, since an illegal move can't actually be
    played to escape the loss."""
    if board.move_count < board.win_length - 1:
        return None  # can't have win_length-1 stones down yet

    winning_moves = find_all_winning_moves(board)
    if winning_moves:
        return 1.0, winning_moves

    legal = legal_moves if legal_moves is not None else board.legal_moves()
    if not legal:
        return None  # board full -- a draw, not a loss

    player = board.to_move
    opponent = -player
    for r, c in legal:
        idx = board.index(r, c)
        board.cells[idx] = player
        board.to_move = opponent
        opponent_can_win = find_winning_move(board) is not None
        board.cells[idx] = 0
        board.to_move = player
        if not opponent_can_win:
            return None
    return -1.0, None
