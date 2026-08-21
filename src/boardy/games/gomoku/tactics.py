"""Cheap, exact 1-ply tactical lookahead for Gomoku leaf positions.

The network's value head has to *infer* who's winning from board features
alone, and self-play's own diagnosis (docs/PLAN.md 2026-08-19/20) found this
inference can be badly miscalibrated exactly at forced continuations (e.g.
failing to recognize an unstoppable open four as a loss). `tactical_value`
sidesteps that inference for the one case where the true value is cheap and
exact to compute directly: whether `board.to_move` can win outright this
turn, or is already dead no matter what they play next.

This alone won't catch a slower threat (e.g. an open three, which is a
loss two plies out rather than one) *at the position where it first
appears* -- but MCTS explores forward from there anyway, and the position
two plies later (after the three becomes an open four) is exactly the kind
of node this function does resolve exactly. Plugging the correct value in
there is enough for it to propagate back up through PUCT's backup step to
the earlier decision, without this module needing to search any deeper
itself.

Performance note: `tactical_value` runs on every non-terminal leaf of
every MCTS simulation -- the same hot path renju.py's docstring already
flags as ~65% of self-play wall time even before this. A first version
here scanned with `Board._check_win` (a plain Python loop) and cost 2.6x
self-play wall time; numba-jitting the win scan the same way renju.py
does brought that down to a small single-digit-percent overhead (see
docs/PLAN.md 2026-08-21).
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
def _find_winning_move_jit(cells: np.ndarray, size: int, player: int, win_length: int, exact_only: bool) -> tuple[int, int]:
    """Returns (r, c) of the first empty cell that completes a win for
    `player`, or (-1, -1) if none does.

    Only checks empty cells within `win_length - 1` of an existing stone
    (either color -- an anchor just needs to be *a* stone, not necessarily
    one of `player`'s own) instead of scanning the whole board: any cell
    that completes a `win_length` run must have an existing same-color
    stone within `win_length - 1` of it somewhere along that run, so
    anchoring the scan on every occupied cell can't miss a real candidate.
    This matters because this function is called up to once per legal
    move from `tactical_value`'s loss check -- an O(n^2) full-board scan
    there was measured to cost 2.6x self-play wall time (docs/PLAN.md
    2026-08-21); this keeps the per-call cost close to the number of
    stones already on the board, not the number of empty cells.

    Doesn't place `player` at the candidate before calling `_completes_win`
    (unlike `Board.is_forbidden_for_black`'s temp-place-then-revert
    pattern) -- `_completes_win` never reads `cells[r*size+c]` itself, only
    the neighbors outward from it, so the candidate cell's actual array
    value is irrelevant and mutating it there was pure wasted writes."""
    n = cells.shape[0]
    seen = np.zeros(n, dtype=np.bool_)
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
                        return rr, cc
    return -1, -1


def find_winning_move(board: Board) -> tuple[int, int] | None:
    """A legal move for `board.to_move` that would win immediately, if one
    exists (first one found; self-play only needs to know one exists).

    Deliberately does *not* go through `board.legal_moves()` -- that pays
    for a full Renju forbidden-move classification per empty cell, which is
    the right cost when enumerating genuine candidate moves but wasteful
    here: a move that completes an exact five is always legal regardless of
    double-three/double-four/overline (see board.py's module docstring),
    and the `exact_only` handling below already keeps this correct for
    Black (an overline doesn't count as reaching exactly `win_length`)."""
    player = board.to_move
    exact_only = board.renju and player == BLACK
    r, c = _find_winning_move_jit(board.cells, board.size, player, board.win_length, exact_only)
    return (int(r), int(c)) if r >= 0 else None


def tactical_result(
    board: Board, legal_moves: list[tuple[int, int]] | None = None
) -> tuple[float, tuple[int, int] | None] | None:
    """Exact (value, winning_move) from `board.to_move`'s perspective if the
    outcome is forced within the next ply, else None (not forced -- fall
    back to the network for both value and policy). `winning_move` is the
    move to move's immediate win when value is +1.0 (so a caller that also
    needs a policy prior for this node doesn't have to re-run the win
    search); it's None when value is -1.0, since which particular move is
    played no longer matters once every move loses. `legal_moves`, if the
    caller already computed it (mcts.py always has), is reused instead of
    recomputed -- unlike `find_winning_move`, this loss-check loop needs
    genuinely *legal* candidates (a Renju-forbidden move isn't one the
    current player could actually play to escape the loss)."""
    # A win needs win_length-1 stones of one color already down; cheaper
    # than scanning the board just to find out nothing is possible yet.
    if board.move_count < board.win_length - 1:
        return None

    winning_move = find_winning_move(board)
    if winning_move is not None:
        return 1.0, winning_move

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


def tactical_value(board: Board, legal_moves: list[tuple[int, int]] | None = None) -> float | None:
    """Exact value from `board.to_move`'s perspective if it's forced within
    the next ply -- see `tactical_result`. Convenience wrapper for callers
    that don't need the winning move."""
    result = tactical_result(board, legal_moves)
    return result[0] if result is not None else None
