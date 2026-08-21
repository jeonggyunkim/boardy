"""Renju forbidden-move rules for Black: double-three, double-four, overline.

White has no restrictions and wins with 5-or-more in a row. Black must win
with an EXACT five -- an "overline" of 6+ is not a win and is illegal for
Black to create -- and may not play a move that simultaneously creates two
open threes (double-three, 쌍삼) or two fours (double-four, 쌍사), UNLESS
that same move also completes an exact five somewhere else, which always
wins outright regardless of any forbidden pattern also formed elsewhere.

Rather than a hand-written table of line patterns (easy to get subtly
wrong), this works from the definitions directly:
  - a "four" is a line where some empty cell, if filled, completes an
    exact five;
  - an "open four" is a four with two such cells, each a *legal* exact-five
    completion for Black (a flank that would only reach an overline isn't
    a real threat -- see `_has_open_four_span`);
  - a "three" is "open" (활삼) if some empty cell e exists such that (a)
    playing Black there would itself be legal (not forbidden for Black in
    its own right -- an unplayable move can't be a real threat either, see
    docs/PLAN.md 2026-08-21) and (b) doing so creates an open four.
Every check below requires the pattern to actually pass through the move
just played (offset 0) -- not just exist somewhere nearby on the same
line -- so an unrelated pre-existing shape elsewhere can't produce a false
positive.

Performance note: this is the hot path of Gomoku MCTS (called once per
empty cell per node expansion, see Board.legal_moves) -- profiling a real
self-play run (2026-08-11, see docs/PLAN.md) found it responsible for
~65% of total wall time even after batching the neural net across many
games. The inner functions are Numba `@njit`-compiled: they already used
plain fixed-size arrays and unrolled loops (no dict, no any()/all()) from
an earlier optimization round, which is exactly the shape JIT compilation
wants, and `Board.cells` is a numpy array specifically so it crosses into
JIT'd code with zero copying. `classify_black_move` itself stays a thin
non-jitted wrapper: the jitted core returns an int code (Numba's nopython
mode doesn't mix `str` and `None` returns cleanly) which gets translated
to the original "overline"/"double_four"/"double_three"/None strings here
-- that public return contract is relied on by web_view.py (forbidden-move
reasons shown in the web UI) and tests/gomoku/test_renju.py, so it's kept
byte-for-byte the same even though the internals changed.
"""

from __future__ import annotations

import numba
import numpy as np

DIRECTIONS = [(1, 0), (0, 1), (1, 1), (1, -1)]
_DIRECTIONS_ARR = np.array(DIRECTIONS, dtype=np.int64)
_RADIUS = 5  # generous margin around the move; five/four/open-three checks all fit well within this
# _has_open_four_span reads up to one cell beyond _RADIUS on each side
# (the flank just outside a 4-window anchored at the radius edge), so the
# backing array needs to cover offset -(_RADIUS+1) .. (_RADIUS+1).
_PAD = _RADIUS + 1
_LEN = 2 * _PAD + 1

_LEGAL = 0
_OVERLINE = 1
_DOUBLE_FOUR = 2
_DOUBLE_THREE = 3
_REASON_BY_CODE = {_OVERLINE: "overline", _DOUBLE_FOUR: "double_four", _DOUBLE_THREE: "double_three"}


@numba.njit(cache=True)
def _line_values(cells: np.ndarray, size: int, r: int, c: int, dr: int, dc: int, mover: int) -> np.ndarray:
    """index (offset + _PAD) -> 1 (mover's stone), 0 (empty), -1 (blocked:
    opponent stone, off-board, or beyond the radius). Offset 0 (index
    _PAD) is (r, c) itself."""
    values = np.full(_LEN, -1, dtype=np.int8)
    for off in range(-_RADIUS, _RADIUS + 1):
        rr = r + dr * off
        cc = c + dc * off
        if 0 <= rr < size and 0 <= cc < size:
            v = cells[rr * size + cc]
            values[off + _PAD] = 1 if v == mover else (0 if v == 0 else -1)
    return values


@numba.njit(cache=True)
def _run_through_zero(values: np.ndarray) -> int:
    """Length of the contiguous run of the mover's stones through offset 0
    (offset 0 itself must be the mover's stone)."""
    run = 1
    i = _PAD - 1
    while values[i] == 1:
        run += 1
        i -= 1
    i = _PAD + 1
    while values[i] == 1:
        run += 1
        i += 1
    return run


@numba.njit(cache=True)
def _is_four_through_zero(values: np.ndarray) -> bool:
    """Some 5-window containing offset 0 has exactly 4 of the mover's
    stones and 1 empty cell (i.e. one move from an exact five)."""
    for i in range(-_RADIUS, _RADIUS - 3):
        if not (i <= 0 < i + 5):
            continue
        base = i + _PAD
        ones = 0
        zeros = 0
        blocked = False
        for k in range(5):
            v = values[base + k]
            if v == -1:
                blocked = True
                break
            elif v == 1:
                ones += 1
            else:
                zeros += 1
        if not blocked and ones == 4 and zeros == 1:
            return True
    return False


@numba.njit(cache=True)
def _has_open_four_span(values: np.ndarray, a: int, b: int) -> bool:
    """Some 4-window of the mover's stones, with both flanks empty *and*
    each flank a genuine winning completion, whose span includes both
    offsets `a` and `b`.

    A flank being merely empty isn't enough: this is only ever evaluated
    for Black (see this module's docstring -- White has no forbidden
    moves), who wins with an *exact* five, so if the cell just beyond a
    flank is already the mover's own stone, filling that flank would run
    six-plus in a row (an illegal overline) rather than winning -- that
    end can't actually be used, so it doesn't make the four "open" (the
    opponent only needs to watch the other end, same as an ordinary
    closed four)."""
    lo = a if a < b else b
    hi = a if a > b else b
    for i in range(-_RADIUS, _RADIUS - 2):
        if i > lo or i + 3 < hi:
            continue
        base = i + _PAD
        if (
            values[base] == 1
            and values[base + 1] == 1
            and values[base + 2] == 1
            and values[base + 3] == 1
            and values[base - 1] == 0
            and values[base + 4] == 0
            and values[base - 2] != 1
            and values[base + 5] != 1
        ):
            return True
    return False


@numba.njit(cache=False)  # cache=True + this function's self-recursion segfaulted, see docstring
def _classify_black_move_code(cells: np.ndarray, size: int, r: int, c: int, mover: int, check_completion_legal: bool) -> int:
    """The open-three check below (`is_open`) inlines what used to be a
    separate `_is_open_three_through_zero` function, so that its
    recursive call back into `_classify_black_move_code` (to check
    whether a three's completion point is itself legal -- see the module
    docstring) is *self*-recursion rather than mutual recursion between
    two @njit functions -- mutual recursion between two separate @njit
    functions crashed the interpreter outright (segfault) on some real
    positions. Self-recursion doesn't have that problem, but `cache=True`
    combined with recursion into the *same* function did (also a
    segfault, reproduced on this file's exact code -- a numba disk-cache
    bug with recursive jitted functions, not a logic bug: a pure-Python
    port of this same algorithm ran correctly and terminated in 3 calls /
    depth 1 on the position that crashed it, see docs/PLAN.md 2026-08-21).
    `cache=False` costs a one-time recompile per process (self-play
    workers each start a fresh process anyway) in exchange for not
    segfaulting.

    The recursive call always passes `check_completion_legal=False`,
    which skips this whole block on the way back in, capping the
    recursion at one level -- matches how real Renju rule references
    handle it, and keeps this from growing unbounded."""
    any_five = False
    any_overline = False
    four_count = 0
    open_three_count = 0
    for k in range(4):
        dr = _DIRECTIONS_ARR[k, 0]
        dc = _DIRECTIONS_ARR[k, 1]
        values = _line_values(cells, size, r, c, dr, dc, mover)
        run = _run_through_zero(values)
        if run == 5:
            any_five = True
        elif run >= 6:
            any_overline = True
        if _is_four_through_zero(values):
            four_count += 1

        is_open = False
        for e in range(-_RADIUS + 1, _RADIUS):
            idx = e + _PAD
            if values[idx] != 0:
                continue
            values[idx] = 1
            found = _has_open_four_span(values, 0, e)
            values[idx] = 0
            if not found:
                continue
            if check_completion_legal:
                er = r + dr * e
                ec = c + dc * e
                eidx = er * size + ec
                cells[eidx] = mover
                legal = _classify_black_move_code(cells, size, er, ec, mover, False) == _LEGAL
                cells[eidx] = 0
                if not legal:
                    continue
            is_open = True
            break
        if is_open:
            open_three_count += 1

    if any_five:
        return _LEGAL  # an exact five always wins, overriding any forbidden pattern
    if any_overline:
        return _OVERLINE
    if four_count >= 2:
        return _DOUBLE_FOUR
    if open_three_count >= 2:
        return _DOUBLE_THREE
    return _LEGAL


def classify_black_move(cells: np.ndarray, size: int, r: int, c: int, mover: int) -> str | None:
    """`cells` must already have `mover`'s stone placed at (r, c). Returns
    None if the move is fine, else "overline", "double_four", or
    "double_three"."""
    return _REASON_BY_CODE.get(_classify_black_move_code(cells, size, r, c, mover, True))
