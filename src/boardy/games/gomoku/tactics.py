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

_DIRECTIONS = np.array([(0, 1), (1, 0), (1, 1), (1, -1)], dtype=np.int64)


@numba.njit(cache=True)
def _slide_line(
    cells: np.ndarray,
    size: int,
    start_r: int,
    start_c: int,
    dr: int,
    dc: int,
    line_len: int,
    player: int,
    win_length: int,
    exact_only: bool,
    seen: np.ndarray,
    results: np.ndarray,
    count: int,
    early_exit: bool,
) -> tuple[int, bool]:
    """Slide a length-`win_length` window along one line of the board
    (`line_len` cells starting at (start_r, start_c), stepping by
    (dr, dc)), maintaining running player/empty counts incrementally
    instead of rescanning the window from scratch at each step -- O(1)
    per step instead of O(win_length), and the whole scan across all
    lines/directions in `_win_scan_jit` costs O(size^2) regardless of how
    many stones are on the board (the earlier per-stone-anchored version
    grew with stone count -- worse late-game, see docs/PLAN.md 2026-08-21).

    A window with exactly `win_length - 1` player stones and 1 empty cell
    means that empty cell wins. For Black (`exact_only`), also checks the
    single cell just outside each end of the window isn't `player` --
    otherwise filling the empty cell would run past `win_length` (an
    overline, not a win)."""
    if line_len < win_length:
        return count, False

    player_count = 0
    empty_count = 0
    for i in range(win_length):
        v = cells[(start_r + dr * i) * size + (start_c + dc * i)]
        if v == player:
            player_count += 1
        elif v == 0:
            empty_count += 1

    for start in range(0, line_len - win_length + 1):
        if start > 0:
            leaving = cells[(start_r + dr * (start - 1)) * size + (start_c + dc * (start - 1))]
            if leaving == player:
                player_count -= 1
            elif leaving == 0:
                empty_count -= 1
            entering = cells[(start_r + dr * (start + win_length - 1)) * size + (start_c + dc * (start + win_length - 1))]
            if entering == player:
                player_count += 1
            elif entering == 0:
                empty_count += 1

        if player_count != win_length - 1 or empty_count != 1:
            continue

        cand_r, cand_c = -1, -1
        for i in range(win_length):
            rr, cc = start_r + dr * (start + i), start_c + dc * (start + i)
            if cells[rr * size + cc] == 0:
                cand_r, cand_c = rr, cc
                break

        if exact_only:
            overline = False
            if start - 1 >= 0:
                br, bc = start_r + dr * (start - 1), start_c + dc * (start - 1)
                if cells[br * size + bc] == player:
                    overline = True
            if not overline and start + win_length < line_len:
                ar, ac = start_r + dr * (start + win_length), start_c + dc * (start + win_length)
                if cells[ar * size + ac] == player:
                    overline = True
            if overline:
                continue

        cidx = cand_r * size + cand_c
        if not seen[cidx]:
            seen[cidx] = True
            results[count] = cidx
            count += 1
            if early_exit:
                return count, True
    return count, False


@numba.njit(cache=True)
def _win_scan_jit(
    cells: np.ndarray, size: int, player: int, win_length: int, exact_only: bool, early_exit: bool
) -> tuple[np.ndarray, int]:
    """Flat indices of empty cells that complete a win for `player` (as
    `results[:count]`); stops at the first one if `early_exit`. Sweeps
    every line of the board once per direction (horizontal, vertical, the
    2 diagonals) via `_slide_line` -- see that function's docstring."""
    n = cells.shape[0]
    seen = np.zeros(n, dtype=np.bool_)
    results = np.full(n, -1, dtype=np.int64)
    count = 0

    for r in range(size):  # horizontal: one line per row
        count, done = _slide_line(cells, size, r, 0, 0, 1, size, player, win_length, exact_only, seen, results, count, early_exit)
        if done:
            return results, count
    for c in range(size):  # vertical: one line per column
        count, done = _slide_line(cells, size, 0, c, 1, 0, size, player, win_length, exact_only, seen, results, count, early_exit)
        if done:
            return results, count
    for r in range(size):  # diagonal \: lines starting down the left column...
        count, done = _slide_line(cells, size, r, 0, 1, 1, size - r, player, win_length, exact_only, seen, results, count, early_exit)
        if done:
            return results, count
    for c in range(1, size):  # ...plus the rest starting along the top row
        count, done = _slide_line(cells, size, 0, c, 1, 1, size - c, player, win_length, exact_only, seen, results, count, early_exit)
        if done:
            return results, count
    for r in range(size):  # diagonal /: lines starting down the right column...
        count, done = _slide_line(
            cells, size, r, size - 1, 1, -1, size - r, player, win_length, exact_only, seen, results, count, early_exit
        )
        if done:
            return results, count
    for c in range(size - 1):  # ...plus the rest starting along the top row
        count, done = _slide_line(cells, size, 0, c, 1, -1, c + 1, player, win_length, exact_only, seen, results, count, early_exit)
        if done:
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
