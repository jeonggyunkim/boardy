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
    # Renju-forbidden intersections for Black are just excluded from
    # legal_moves with no explanation -- expose *why* each one is
    # forbidden (double-three/double-four/overline) so the GUI can tell
    # Black clicking one what actually happened, instead of it silently
    # doing nothing. Only meaningful (and only computed) on Black's own
    # turn -- White has no restrictions, and it's irrelevant on anyone
    # else's turn.
    forbidden_reasons: dict[str, str] = {}
    if to_act == seat and board.renju and board.to_move == 1:  # BLACK
        for i, v in enumerate(board.cells):
            if v != 0:
                continue
            r, c = divmod(i, board.size)
            reason = board.is_forbidden_for_black(r, c)
            if reason is not None:
                forbidden_reasons[f"{r},{c}"] = reason
    return {
        "players": players_meta,
        "size": board.size,
        "win_length": board.win_length,
        "board": list(board.cells),
        "my_color": "black" if seat == 0 else "white",
        "player_to_act": to_act,
        "legal_moves": legal,
        "forbidden_reasons": forbidden_reasons,
        "last_move": list(board.last_move) if board.last_move is not None else None,
        "move_count": board.move_count,
        "winner": None if board.winner is None else _WINNER_NAME[board.winner],
        "winner_seat": color_to_seat(board.winner) if board.winner not in (None, 0) else None,
    }
