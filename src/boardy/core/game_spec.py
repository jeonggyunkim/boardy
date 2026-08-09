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

    def choose_action(self, state: Any, seat: int) -> str: ...


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
    # state -> None while the game is ongoing, else any non-None terminal
    # marker. The host layers only ever check "is it None" (has the game
    # ended?) — what the marker actually contains is entirely up to the
    # game (e.g. Deep Sea Crew: True/False mission success; Gomoku: which
    # seat won, or a draw marker) and is interpreted by that game's own
    # serialize_seat, not by boardy.web or boardy.cli.
    outcome: Callable[[Any], Any]
    # state, seat, public players metadata -> JSON-able view for that seat.
    # There's no single universal schema here — the web frontend dispatches
    # its renderer by the "game" slug included in every message (see
    # boardy/web/rooms.py), so each game is free to shape this however its
    # own UI needs. Two shapes exist so far: a card-hand style (Deep Sea
    # Crew: hand/legal_moves/trick_in_progress/tasks/hand_sizes/signals/...,
    # see games/deep_sea_crew/web_view.py) and a board-grid style (Gomoku:
    # board/legal_moves/last_move/winner/..., see games/gomoku/web_view.py).
    # A new game either reuses one of those shapes or adds a new frontend
    # renderer for its own.
    serialize_seat: Callable[[Any, int, list[dict]], dict]

    make_random_player: Callable[[str], Player]
    # Optional stronger AI (e.g. search-based); None if the game has none yet.
    make_smart_player: Callable[[str], Player] | None = None
    # Optional secondary action channel beyond `play` (e.g. Deep Sea Crew's
    # Sonar communication). None if the game has no such mechanic.
    communicate: Callable[[Any, int, str], None] | None = None
    # Entry point for `python -m boardy.cli --game <slug> ...`
    cli_main: Callable[[], None] | None = None
    # Optional: state -> seconds to pause the web AI-turn loop after this
    # move before playing the next AI move. None/0 = no pause. Lets a game
    # give observers a moment to actually see a just-resolved intermediate
    # state (e.g. Deep Sea Crew pausing after a trick completes) instead of
    # AI turns firing back-to-back with no gap between broadcasts.
    post_move_delay: Callable[[Any], float] | None = None
    # Optional, only meaningful alongside `communicate`: state -> seat
    # indices currently allowed to use the secondary communicate channel
    # right now (e.g. Deep Sea Crew: everyone but the trick leader, only
    # before the trick's first card is played). Lets the web layer give
    # AI-controlled seats the same chance a human would get, instead of AI
    # seats silently never using the mechanic. None if the game has no
    # such mechanic.
    communicable_seats: Callable[[Any], list[int]] | None = None
    # Optional, only meaningful alongside `communicable_seats`: state, seat,
    # that seat's AI Player -> an action string to feed into `communicate`,
    # or None to skip. Only ever called for seats `communicable_seats`
    # returned.
    ai_communicate: Callable[[Any, int, Player], str | None] | None = None
    # Optional: state -> True while the game is in a phase where every
    # seat must individually confirm readiness before play continues (e.g.
    # Deep Sea Crew between tricks, so everyone gets a real chance to
    # communicate first -- see mark_ready/ready_seats below). While true,
    # `player_to_act` is expected to return None: nobody has an exclusive
    # turn, so the host drives `mark_ready` per seat instead (automatically
    # for AI seats, via an explicit UI action for humans). None if the
    # game has no such mechanic.
    awaiting_ready: Callable[[Any], bool] | None = None
    # Optional, alongside `awaiting_ready`: state, seat -> mutates state,
    # marking that seat ready.
    mark_ready: Callable[[Any, int], None] | None = None
    # Optional, alongside `awaiting_ready`: state -> seat indices that have
    # already marked ready this window, so the host/UI can tell who's
    # still being waited on.
    ready_seats: Callable[[Any], list[int]] | None = None
