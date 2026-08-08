"""The contract a game must implement to be hosted by the shared CLI/web layers.

A game's internal rules engine, AI, and state representation stay
completely custom — trick-taking and (eventually) other game shapes need
genuinely different state machines, so this module does not try to unify
that. What it *does* standardize is the narrow boundary the host layers
actually need: start a game, list legal actions for a seat, apply an
action, ask who moves next / whether it's over, and render a seat's view
as JSON for a browser client. Actions are plain strings (e.g. a card code)
so the boundary stays trivial regardless of what a game's internal action
type looks like.

See boardy/games/deep_sea_crew/spec.py for a concrete implementation, and
boardy/web/rooms.py for how the web layer drives a game purely through
this interface.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol


class Player(Protocol):
    name: str

    def choose_card(self, state: Any, seat: int) -> str: ...


@dataclass
class GameSpec:
    slug: str
    name: str
    description: str
    min_players: int
    max_players: int

    # (num_players, difficulty_budget, seed) -> new game state
    new_game: Callable[[int, int, int | None], Any]
    # state, seat -> legal action strings for that seat right now
    legal_actions: Callable[[Any, int], list[str]]
    # state -> seat index to act next, or None if the game has ended
    player_to_act: Callable[[Any], int | None]
    # state, seat, action -> mutates state in place
    play: Callable[[Any, int, str], None]
    # state -> None while ongoing, else True (success) / False (failure)
    outcome: Callable[[Any], bool | None]
    # state, seat, public players metadata -> JSON-able view for that seat.
    # Expected keys (the web frontend's generic contract): hand (list[str]),
    # legal_moves (list[str]), trick_in_progress (dict[str,str]), tasks
    # (list of {id,owner,describe,resolved,success}), hand_sizes (list[int]),
    # signals, can_communicate, outcome, player_to_act, current_leader,
    # trick_number, hand_size, num_players, history.
    serialize_seat: Callable[[Any, int, list[dict]], dict]

    make_random_player: Callable[[str], Player]
    # Optional stronger AI (e.g. search-based); None if the game has none yet.
    make_smart_player: Callable[[str], Player] | None = None
    # Optional secondary action channel beyond `play` (e.g. Deep Sea Crew's
    # Sonar communication). None if the game has no such mechanic.
    communicate: Callable[[Any, int, str], None] | None = None
    # Entry point for `python -m boardy.cli --game <slug> ...`
    cli_main: Callable[[], None] | None = None
