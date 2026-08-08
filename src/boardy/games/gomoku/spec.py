"""Adapts this game's engine to the generic boardy.core.GameSpec contract."""

from __future__ import annotations

from ...core.game_spec import GameSpec
from ...core.registry import register
from .ai import get_shared_net
from .board import Board
from .cli import main as _cli_main
from .engine import new_game, player_to_act
from .players import NetPlayer, Player, RandomPlayer
from .web_view import serialize_seat


class _ActionAdapter:
    """Wraps a Player (choose_move(board) -> 'r,c') as the (state, seat)
    -> action Player the host layers expect."""

    def __init__(self, inner: Player) -> None:
        self._inner = inner
        self.name = inner.name

    def choose_action(self, state: Board, seat: int) -> str:
        return self._inner.choose_move(state)


def _make_random_player(name: str) -> _ActionAdapter:
    return _ActionAdapter(RandomPlayer(name=name))


def _make_smart_player(name: str) -> _ActionAdapter:
    return _ActionAdapter(
        NetPlayer(get_shared_net(), name=name, num_simulations=200, temperature=0.1)
    )


def _legal_actions(board: Board, seat: int) -> list[str]:
    if player_to_act(board) != seat:
        return []
    return [f"{r},{c}" for r, c in board.legal_moves()]


def _play(board: Board, seat: int, action: str) -> None:
    r, c = (int(v) for v in action.split(","))
    board.play(r, c)


SPEC = GameSpec(
    slug="gomoku",
    name="Gomoku",
    description="오목 (5목) — 9x9 보드, 5개 연속이면 승리. 진짜 2인 제로섬 완전정보 게임이라 표준 AlphaZero 학습이 그대로 적용됨.",
    min_players=2,
    max_players=2,
    new_game=new_game,
    legal_actions=_legal_actions,
    player_to_act=player_to_act,
    play=_play,
    outcome=lambda board: board.winner,
    serialize_seat=serialize_seat,
    make_random_player=_make_random_player,
    make_smart_player=_make_smart_player,
    communicate=None,
    cli_main=_cli_main,
)

register(SPEC)
