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
        if state.phase == "task_draft":
            return self._inner.choose_task(state, seat)
        return str(self._inner.choose_card(state, seat))

    def choose_communication(self, state: GameState, seat: int) -> str | None:
        card = self._inner.choose_communication(state, seat)
        return str(card) if card is not None else None


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
    if state.player_to_act != seat:
        return []
    if state.phase == "task_draft":
        return [t.id for t in state.draftable_tasks(seat)]
    return [str(c) for c in state.legal_cards_for(seat)]


def _play(state: GameState, seat: int, action: str) -> None:
    if state.phase == "task_draft":
        # A prediction task's action carries its chosen number as
        # "task-id:n" (see static/app.js's inline prediction input) --
        # every other task just drafts by bare id, same as before.
        task_id, _, raw_n = action.partition(":")
        prediction = int(raw_n) if raw_n else None
        state.draft_task(seat, task_id, prediction=prediction)
    else:
        state.play_card(seat, Card.parse(action))


def _communicate(state: GameState, seat: int, action: str) -> None:
    state.communicate(seat, Card.parse(action))


def _ai_communicate(state: GameState, seat: int, player: _StrPlayerAdapter) -> str | None:
    return player.choose_communication(state, seat)


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
    communicable_seats=lambda state: state.communicable_seats(),
    ai_communicate=_ai_communicate,
    awaiting_ready=lambda state: state.phase == "trick_ready",
    mark_ready=lambda state, seat: state.mark_ready(seat),
    ready_seats=lambda state: sorted(state.ready_seats),
)

register(SPEC)
