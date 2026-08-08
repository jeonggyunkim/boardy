"""Gomoku (five-in-a-row) board and rules.

Default board is 9x9 with Renju rules (see renju.py): Black may not play a
double-three, double-four, or overline (unless the same move also
completes an exact five, which always wins); White is unrestricted and
wins with five-or-more. Board size and win length are parameters, and
Renju enforcement can be turned off (`renju=False`) for a plain freestyle
variant if ever needed (e.g. quick tests). 9x9 instead of full
15x15/19x19 so self-play training actually finishes on CPU.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import renju

BLACK = 1
WHITE = -1

_DIRECTIONS = [(1, 0), (0, 1), (1, 1), (1, -1)]


@dataclass
class Board:
    size: int = 9
    win_length: int = 5
    renju: bool = True
    cells: list[int] = field(default_factory=list)  # size*size, row-major; 0=empty
    to_move: int = BLACK
    last_move: tuple[int, int] | None = None
    move_count: int = 0
    winner: int | None = None  # None=ongoing/unset, BLACK, WHITE, or 0 for draw

    def __post_init__(self) -> None:
        if not self.cells:
            self.cells = [0] * (self.size * self.size)

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
        if self.renju and self.to_move == BLACK:
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
            cells=list(self.cells),
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
