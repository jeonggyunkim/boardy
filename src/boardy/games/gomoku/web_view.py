"""Maps Board -> the per-seat JSON view the Gomoku web frontend renders.

Board-grid shape (see boardy/core/game_spec.py for the two known shapes):
flat cell values (0 empty, 1 black, -1 white), legal moves as "r,c"
strings, last move, and a friendly winner marker.
"""

from __future__ import annotations

from .board import Board
from .engine import color_to_seat, player_to_act

_WINNER_NAME = {0: "draw", 1: "black", -1: "white"}


def serialize_seat(board: Board, seat: int, players_meta: list[dict]) -> dict:
    to_act = player_to_act(board)
    legal = [f"{r},{c}" for r, c in board.legal_moves()] if to_act == seat else []
    return {
        "players": players_meta,
        "size": board.size,
        "win_length": board.win_length,
        "board": list(board.cells),
        "my_color": "black" if seat == 0 else "white",
        "player_to_act": to_act,
        "legal_moves": legal,
        "last_move": list(board.last_move) if board.last_move is not None else None,
        "move_count": board.move_count,
        "winner": None if board.winner is None else _WINNER_NAME[board.winner],
        "winner_seat": color_to_seat(board.winner) if board.winner not in (None, 0) else None,
    }
