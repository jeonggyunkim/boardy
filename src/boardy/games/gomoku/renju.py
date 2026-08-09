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
  - an "open four" is a four with two such cells (unstoppable: the
    opponent can only block one);
  - a "three" is "open" (활삼) if some empty cell, if filled, would create
    an open four.
Every check below requires the pattern to actually pass through the move
just played (offset 0) -- not just exist somewhere nearby on the same
line -- so an unrelated pre-existing shape elsewhere can't produce a false
positive. This gets the standard textbook cases right, but it does not
attempt to reproduce every fine-print exemption in the official Renju
International Federation rulebook (e.g. a three/four that only "counts"
through a point that's itself already forbidden) -- flagged as a known
simplification, same spirit as the rest of this project's
placeholder/approximate rules.

Performance note: this is the hot path of Gomoku MCTS (called once per
empty cell per node expansion, see Board.legal_moves), so the line
representation is a plain list indexed by offset+_PAD (not a dict) and
the inner loops are unrolled rather than using any()/all() generators --
both cut pure Python-interpreter overhead substantially, verified via
cProfile. Semantics are unchanged from the original dict-based version;
see tests/gomoku/test_renju.py.
"""

from __future__ import annotations

DIRECTIONS = [(1, 0), (0, 1), (1, 1), (1, -1)]
_RADIUS = 5  # generous margin around the move; five/four/open-three checks all fit well within this
# _has_open_four_span reads up to one cell beyond _RADIUS on each side
# (the flank just outside a 4-window anchored at the radius edge), so the
# backing list needs to cover offset -(_RADIUS+1) .. (_RADIUS+1).
_PAD = _RADIUS + 1
_LEN = 2 * _PAD + 1


def _line_values(cells: list[int], size: int, r: int, c: int, dr: int, dc: int, mover: int) -> list[int]:
    """index (offset + _PAD) -> 1 (mover's stone), 0 (empty), -1 (blocked:
    opponent stone, off-board, or beyond the radius). Offset 0 (index
    _PAD) is (r, c) itself."""
    values = [-1] * _LEN
    for off in range(-_RADIUS, _RADIUS + 1):
        rr, cc = r + dr * off, c + dc * off
        if 0 <= rr < size and 0 <= cc < size:
            v = cells[rr * size + cc]
            values[off + _PAD] = 1 if v == mover else (0 if v == 0 else -1)
    return values


def _run_through_zero(values: list[int]) -> int:
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


def _is_four_through_zero(values: list[int]) -> bool:
    """Some 5-window containing offset 0 has exactly 4 of the mover's
    stones and 1 empty cell (i.e. one move from an exact five)."""
    for i in range(-_RADIUS, _RADIUS - 3):
        if not (i <= 0 < i + 5):
            continue
        base = i + _PAD
        ones = zeros = 0
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


def _has_open_four_span(values: list[int], a: int, b: int) -> bool:
    """Some 4-window of the mover's stones, with both flanks empty, whose
    span includes both offsets `a` and `b`."""
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
        ):
            return True
    return False


def _is_open_three_through_zero(values: list[int]) -> bool:
    """Some empty cell e exists such that playing there would create an
    open four spanning both offset 0 (this move) and e (the hypothetical
    follow-up) -- i.e. this three is one move from an unstoppable four."""
    for e in range(-_RADIUS + 1, _RADIUS):
        idx = e + _PAD
        if values[idx] != 0:
            continue
        values[idx] = 1
        found = _has_open_four_span(values, 0, e)
        values[idx] = 0
        if found:
            return True
    return False


def classify_black_move(cells: list[int], size: int, r: int, c: int, mover: int) -> str | None:
    """`cells` must already have `mover`'s stone placed at (r, c). Returns
    None if the move is fine, else "overline", "double_four", or
    "double_three"."""
    any_five = False
    any_overline = False
    four_count = 0
    open_three_count = 0
    for dr, dc in DIRECTIONS:
        values = _line_values(cells, size, r, c, dr, dc, mover)
        run = _run_through_zero(values)
        if run == 5:
            any_five = True
        elif run >= 6:
            any_overline = True
        if _is_four_through_zero(values):
            four_count += 1
        if _is_open_three_through_zero(values):
            open_three_count += 1

    if any_five:
        return None  # an exact five always wins, overriding any forbidden pattern
    if any_overline:
        return "overline"
    if four_count >= 2:
        return "double_four"
    if open_three_count >= 2:
        return "double_three"
    return None
