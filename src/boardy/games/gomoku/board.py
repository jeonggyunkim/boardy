"""Gomoku (five-in-a-row) board and rules.

Default board is 9x9 with a plain five-or-more-in-a-row win condition (no
Renju-style forbidden moves for black) — a common simplified variant that
trains much faster than full 15x15/19x19 on CPU. Board size and win
length are parameters so this can scale up later.
"""

from __future__ import annotations

from dataclasses import dataclass, field

BLACK = 1
WHITE = -1

_DIRECTIONS = [(1, 0), (0, 1), (1, 1), (1, -1)]


@dataclass
class Board:
    size: int = 9
    win_length: int = 5
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

    def legal_moves(self) -> list[tuple[int, int]]:
        if self.winner is not None:
            return []
        return [
            (i // self.size, i % self.size) for i, v in enumerate(self.cells) if v == 0
        ]

    def play(self, r: int, c: int) -> None:
        if self.winner is not None:
            raise ValueError("Game already finished")
        if not self.in_bounds(r, c):
            raise ValueError(f"Move out of bounds: {(r, c)}")
        idx = self.index(r, c)
        if self.cells[idx] != 0:
            raise ValueError(f"Cell already occupied: {(r, c)}")
        self.cells[idx] = self.to_move
        self.last_move = (r, c)
        self.move_count += 1

        if self._check_win(r, c, self.to_move):
            self.winner = self.to_move
        elif self.move_count == self.size * self.size:
            self.winner = 0  # draw

        self.to_move = WHITE if self.to_move == BLACK else BLACK

    def _check_win(self, r: int, c: int, player: int) -> bool:
        for dr, dc in _DIRECTIONS:
            count = 1
            for sign in (1, -1):
                rr, cc = r + dr * sign, c + dc * sign
                while self.in_bounds(rr, cc) and self.get(rr, cc) == player:
                    count += 1
                    rr += dr * sign
                    cc += dc * sign
            if count >= self.win_length:
                return True
        return False

    def clone(self) -> "Board":
        return Board(
            size=self.size,
            win_length=self.win_length,
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
