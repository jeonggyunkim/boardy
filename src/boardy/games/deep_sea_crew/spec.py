"""Adapts this game's engine to the generic boardy.core.GameSpec contract
so boardy.cli and boardy.web can host it without importing it directly.
"""

from __future__ import annotations

from ...core.game_spec import GameSpec
from ...core.registry import register
from .ai import get_shared_net
from .cards import Card
from .cli import main as _cli_main
from .engine import GameState, new_game
from .players import NetPlayer, Player, RandomPlayer
from .web_view import serialize_seat


class _StrPlayerAdapter:
    """Wraps a Player (choose_card -> Card) as the str-action Player the host layers expect."""

    def __init__(self, inner: Player) -> None:
        self._inner = inner
        self.name = inner.name

    def choose_action(self, state: GameState, seat: int) -> str:
        return str(self._inner.choose_card(state, seat))


def _make_random_player(name: str) -> _StrPlayerAdapter:
    return _StrPlayerAdapter(RandomPlayer(name=name))


def _make_smart_player(name: str) -> _StrPlayerAdapter:
    return _StrPlayerAdapter(
        NetPlayer(
            get_shared_net(),
            name=name,
            use_search=True,
            num_determinizations=5,
            sims_per_determinization=15,
        )
    )


def _legal_actions(state: GameState, seat: int) -> list[str]:
    return [str(c) for c in state.legal_cards_for(seat)]


def _play(state: GameState, seat: int, action: str) -> None:
    state.play_card(seat, Card.parse(action))


def _communicate(state: GameState, seat: int, action: str) -> None:
    state.communicate(seat, Card.parse(action))


def _post_move_delay(state: GameState) -> float:
    # trick_in_progress goes back to empty in the same instant a trick
    # completes, so this is the signal a trick just resolved: pause the
    # web AI-turn loop here for a moment so the just-finished trick is
    # actually visible before the next card starts landing on the table.
    if not state.trick_in_progress and state.history:
        return 1.4
    return 0.0


SPEC = GameSpec(
    slug="deep_sea_crew",
    name="Deep Sea Crew",
    description=(
        "The Crew: Mission Deep Sea 기반 협력 트릭테이킹 게임 "
        "(placeholder 룰 — docs/PLAN.md 참고)"
    ),
    min_players=2,
    max_players=5,
    new_game=new_game,
    legal_actions=_legal_actions,
    player_to_act=lambda state: state.player_to_act,
    play=_play,
    outcome=lambda state: state.outcome,
    serialize_seat=serialize_seat,
    make_random_player=_make_random_player,
    make_smart_player=_make_smart_player,
    communicate=_communicate,
    cli_main=_cli_main,
    post_move_delay=_post_move_delay,
)

register(SPEC)
