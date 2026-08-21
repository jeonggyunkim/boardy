"""Gomoku (five-in-a-row) board and rules.

Standard 15x15 board with Renju rules (see renju.py): Black may not play a
double-three, double-four, or overline (unless the same move also
completes an exact five, which always wins); White is unrestricted and
wins with five-or-more. Board size and win length are parameters, and
Renju enforcement can be turned off (`renju=False`) for a plain freestyle
variant if ever needed (e.g. quick tests).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import renju

BLACK = 1
WHITE = -1

DEFAULT_SIZE = 15
DEFAULT_WIN_LENGTH = 5

_DIRECTIONS = [(1, 0), (0, 1), (1, 1), (1, -1)]


# eq=False: `cells` is a numpy array (see below -- passing it straight into
# renju.py's numba-jitted hot path is what makes that fast, no per-call
# list<->array conversion), and dataclass's auto-generated __eq__ compares
# fields with `==`, which for two arrays returns an array, not a bool --
# `Board() == Board()` would raise "truth value of an array is ambiguous"
# instead of comparing. Nothing in this codebase compares Boards with `==`
# (grepped), so this only forecloses a footgun, not an existing use case.
@dataclass(eq=False)
class Board:
    size: int = DEFAULT_SIZE
    win_length: int = DEFAULT_WIN_LENGTH
    renju: bool = True
    cells: np.ndarray = field(default_factory=lambda: np.empty(0, dtype=np.int8))  # size*size, row-major; 0=empty
    to_move: int = BLACK
    last_move: tuple[int, int] | None = None
    move_count: int = 0
    winner: int | None = None  # None=ongoing/unset, BLACK, WHITE, or 0 for draw

    def __post_init__(self) -> None:
        if self.cells.size == 0:
            self.cells = np.zeros(self.size * self.size, dtype=np.int8)

    def index(self, r: int, c: int) -> int:
        return r * self.size + c

    def get(self, r: int, c: int) -> int:
        return self.cells[self.index(r, c)]

    def in_bounds(self, r: int, c: int) -> bool:
        return 0 <= r < self.size and 0 <= c < self.size

    def is_forbidden_for_black(self, r: int, c: int) -> str | None:
        """Whether placing BLACK at empty cell (r, c) would be a forbidden
        Renju move. None if the cell isn't empty or Black wouldn't be
        forbidden there."""
        idx = self.index(r, c)
        if self.cells[idx] != 0:
            return None
        self.cells[idx] = BLACK
        try:
            return renju.classify_black_move(self.cells, self.size, r, c, BLACK)
        finally:
            self.cells[idx] = 0

    def legal_moves(self) -> list[tuple[int, int]]:
        if self.winner is not None:
            return []
        empties = [(i // self.size, i % self.size) for i, v in enumerate(self.cells) if v == 0]
        # Every forbidden pattern needs at least 2 of Black's own stones
        # already down per line direction it spans (a "three" -- even a
        # broken one -- is 2 existing stones + this move; double-three
        # needs that in 2 distinct directions, and a stone can't count
        # towards both since each occupies one specific relative
        # position), so double-three's 4 is the lowest bar of the three
        # patterns (double-four needs 6, overline needs 5) -- below 4
        # Black stones on the board, no empty cell can possibly be
        # forbidden, so skip the per-cell classification entirely (this
        # file's hot path, see renju.py's docstring) instead of paying
        # for it 225 times over on an empty-ish board just to always get
        # None back. Counts actual stones on `cells` rather than trusting
        # `move_count` -- callers that build a position by writing
        # `cells` directly (tests, position-analysis tools) don't always
        # keep `move_count` in sync, and getting this wrong would mean
        # silently skipping real forbidden-move checks.
        if self.renju and self.to_move == BLACK and int(np.count_nonzero(self.cells == BLACK)) >= 4:
            return [(r, c) for r, c in empties if self.is_forbidden_for_black(r, c) is None]
        return empties

    def play(self, r: int, c: int) -> None:
        if self.winner is not None:
            raise ValueError("Game already finished")
        if not self.in_bounds(r, c):
            raise ValueError(f"Move out of bounds: {(r, c)}")
        idx = self.index(r, c)
        if self.cells[idx] != 0:
            raise ValueError(f"Cell already occupied: {(r, c)}")

        if self.renju and self.to_move == BLACK:
            forbidden = self.is_forbidden_for_black(r, c)
            if forbidden is not None:
                raise ValueError(f"Forbidden Renju move for Black at {(r, c)}: {forbidden}")

        self.cells[idx] = self.to_move
        self.last_move = (r, c)
        self.move_count += 1

        if self._check_win(r, c, self.to_move):
            self.winner = self.to_move
        elif self.move_count == self.size * self.size:
            self.winner = 0  # draw

        self.to_move = WHITE if self.to_move == BLACK else BLACK

    def _check_win(self, r: int, c: int, player: int) -> bool:
        exact_only = self.renju and player == BLACK
        for dr, dc in _DIRECTIONS:
            count = 1
            for sign in (1, -1):
                rr, cc = r + dr * sign, c + dc * sign
                while self.in_bounds(rr, cc) and self.get(rr, cc) == player:
                    count += 1
                    rr += dr * sign
                    cc += dc * sign
            reached = count == self.win_length if exact_only else count >= self.win_length
            if reached:
                return True
        return False

    def clone(self) -> "Board":
        return Board(
            size=self.size,
            win_length=self.win_length,
            renju=self.renju,
            cells=self.cells.copy(),
            to_move=self.to_move,
            last_move=self.last_move,
            move_count=self.move_count,
            winner=self.winner,
        )

    def render(self) -> str:
        symbols = {0: ".", BLACK: "X", WHITE: "O"}
        header = "   " + " ".join(f"{c:>2}" for c in range(self.size))
        lines = [header]
        for r in range(self.size):
            row = " ".join(f"{symbols[self.get(r, c)]:>2}" for c in range(self.size))
            lines.append(f"{r:>2} {row}")
        return "\n".join(lines)
