"""Thin engine layer: Board + the seat<->color mapping used by the rest
of the package (seat 0 = BLACK, moves first; seat 1 = WHITE).
"""

from __future__ import annotations

from .board import BLACK, WHITE, Board

DEFAULT_SIZE = 9
DEFAULT_WIN_LENGTH = 5


def new_game(num_players: int = 2, difficulty: int = 0, seed: int | None = None) -> Board:
    """difficulty/seed are unused (gomoku is deterministic and always fair —
    black moves first with no randomness); kept for GameSpec signature
    compatibility with games that do use them."""
    if num_players != 2:
        raise ValueError("Gomoku is a 2-player game")
    return Board(size=DEFAULT_SIZE, win_length=DEFAULT_WIN_LENGTH)


def seat_to_color(seat: int) -> int:
    return BLACK if seat == 0 else WHITE


def color_to_seat(color: int) -> int:
    return 0 if color == BLACK else 1


def player_to_act(board: Board) -> int | None:
    if board.winner is not None:
        return None
    return color_to_seat(board.to_move)


def winner_seat(board: Board) -> int | None:
    """None if drawn or ongoing, else the winning seat."""
    if board.winner in (None, 0):
        return None
    return color_to_seat(board.winner)
