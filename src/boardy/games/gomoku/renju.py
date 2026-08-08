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
"""

from __future__ import annotations

DIRECTIONS = [(1, 0), (0, 1), (1, 1), (1, -1)]
_RADIUS = 5  # generous margin around the move; five/four/open-three checks all fit well within this


def _line_values(cells: list[int], size: int, r: int, c: int, dr: int, dc: int, mover: int) -> dict[int, int]:
    """offset -> 1 (mover's stone), 0 (empty), -1 (blocked: opponent stone or off-board).
    Offset 0 is (r, c) itself."""
    values: dict[int, int] = {}
    for off in range(-_RADIUS, _RADIUS + 1):
        rr, cc = r + dr * off, c + dc * off
        if 0 <= rr < size and 0 <= cc < size:
            v = cells[rr * size + cc]
            values[off] = 1 if v == mover else (0 if v == 0 else -1)
        else:
            values[off] = -1
    return values


def _run_through_zero(values: dict[int, int]) -> int:
    """Length of the contiguous run of the mover's stones through offset 0
    (offset 0 itself must be the mover's stone)."""
    run = 1
    i = -1
    while values.get(i) == 1:
        run += 1
        i -= 1
    i = 1
    while values.get(i) == 1:
        run += 1
        i += 1
    return run


def _is_four_through_zero(values: dict[int, int]) -> bool:
    """Some 5-window containing offset 0 has exactly 4 of the mover's
    stones and 1 empty cell (i.e. one move from an exact five)."""
    for i in range(-_RADIUS, _RADIUS - 3):
        if not (i <= 0 < i + 5):
            continue
        window = [values.get(i + k) for k in range(5)]
        if -1 in window:
            continue
        if window.count(1) == 4 and window.count(0) == 1:
            return True
    return False


def _has_open_four_span(values: dict[int, int], offsets_required: tuple[int, ...]) -> bool:
    """Some 4-window of the mover's stones, with both flanks empty, whose
    span includes every offset in `offsets_required`."""
    for i in range(-_RADIUS, _RADIUS - 2):
        if any(not (i <= off < i + 4) for off in offsets_required):
            continue
        if all(values.get(i + k) == 1 for k in range(4)) and values.get(i - 1) == 0 and values.get(i + 4) == 0:
            return True
    return False


def _is_open_three_through_zero(values: dict[int, int]) -> bool:
    """Some empty cell e exists such that playing there would create an
    open four spanning both offset 0 (this move) and e (the hypothetical
    follow-up) -- i.e. this three is one move from an unstoppable four."""
    for e in range(-_RADIUS + 1, _RADIUS):
        if values.get(e) != 0:
            continue
        hypothetical = dict(values)
        hypothetical[e] = 1
        if _has_open_four_span(hypothetical, (0, e)):
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
