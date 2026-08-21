"""In-memory room/session management for realtime play.

A Room holds up to `num_players` seats for one registered game (see
boardy.core.game_spec.GameSpec). Each seat is either a connected human
(WebSocket) or an AI (random or, if the game provides one, a stronger
search/learned player). All game logic is reached only through the
GameSpec — this module has no idea what a "card" or a "trick" is, so it
works unmodified for any future game that registers one. Single-process,
in-memory only: fine for a development skeleton, not for multi-instance
deployment.
"""

from __future__ import annotations

import asyncio
import json
import random
import string
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import WebSocket

from ..core.game_spec import GameSpec, Player

# One JSONL file per played game, for later debugging -- see Room._log_event.
# Gitignored (see .gitignore); not meant to be committed.
LOG_DIR = Path(__file__).resolve().parent.parent.parent.parent / "logs"


def make_room_code(rng: random.Random | None = None) -> str:
    rng = rng or random.Random()
    return "".join(rng.choices(string.ascii_uppercase + string.digits, k=5))


@dataclass
class SeatInfo:
    name: str
    kind: str  # "human" | "ai"
    ws: WebSocket | None = None
    ai_player: Player | None = None


@dataclass
class Room:
    code: str
    spec: GameSpec
    num_players: int
    difficulty: int
    seats: list[SeatInfo | None] = field(default_factory=list)
    state: Any | None = None
    # Set when a "pausable" moment (per spec.post_move_delay) happens with
    # at least one human seated: the AI-turn loop halts here until a human
    # explicitly acknowledges (see acknowledge_next), rather than either
    # blinking past it or wasting a fixed sleep on a room nobody's watching.
    awaiting_next: bool = False
    # Room-wide display preference set at creation (currently only Deep Sea
    # Crew's "카드 도우미" table uses it) -- lives here, not per-client, so
    # every seat sees the same thing regardless of who created the room.
    card_helper: bool = False
    # Path to this game's debug log (see _open_log/_log_event), set once
    # the room actually starts. None before that, or if the log couldn't
    # be opened -- logging is a debugging aid, never load-bearing.
    log_path: Path | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.seats:
            self.seats = [None] * self.num_players

    @property
    def is_full(self) -> bool:
        return all(s is not None for s in self.seats)

    @property
    def started(self) -> bool:
        return self.state is not None

    @property
    def has_human(self) -> bool:
        return any(s and s.kind == "human" for s in self.seats)

    def add_human(self, name: str, ws: WebSocket, seat: int | None = None) -> int | None:
        """Claim a specific seat (e.g. to pick Gomoku's Black/White), or
        the first empty one if `seat` isn't given. None if unavailable."""
        if seat is not None:
            if not (0 <= seat < len(self.seats)) or self.seats[seat] is not None:
                return None
            self.seats[seat] = SeatInfo(name=name, kind="human", ws=ws)
            return seat
        for i, s in enumerate(self.seats):
            if s is None:
                self.seats[i] = SeatInfo(name=name, kind="human", ws=ws)
                return i
        return None

    def add_ai(self, mode: str = "random", name: str | None = None) -> int | None:
        for i, s in enumerate(self.seats):
            if s is None:
                use_smart = mode == "smart" and self.spec.make_smart_player is not None
                tag = "smart" if use_smart else "random"
                seat_name = name or f"AI-{i}({tag})"
                factory = self.spec.make_smart_player if use_smart else self.spec.make_random_player
                self.seats[i] = SeatInfo(name=seat_name, kind="ai", ai_player=factory(seat_name))
                return i
        return None

    def remove_seat(self, seat: int) -> None:
        if 0 <= seat < len(self.seats):
            self.seats[seat] = None

    def players_meta(self) -> list[dict]:
        return [
            {"seat": i, "name": s.name if s else None, "kind": s.kind if s else None}
            for i, s in enumerate(self.seats)
        ]

    def start(self, seed: int | None = None) -> None:
        if self.started:
            raise ValueError("Room already started")
        if not self.is_full:
            raise ValueError("Room is not full yet")
        self.state = self.spec.new_game(self.num_players, self.difficulty, seed)
        self._open_log()

    def _open_log(self) -> None:
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            stamp = time.strftime("%Y%m%dT%H%M%S")
            self.log_path = LOG_DIR / f"{self.spec.slug}_{self.code}_{stamp}.jsonl"
            self._log_event(
                {
                    "type": "start",
                    "game": self.spec.slug,
                    "num_players": self.num_players,
                    "difficulty": self.difficulty,
                    "players": self.players_meta(),
                }
            )
        except OSError:
            self.log_path = None

    def _log_event(self, event: dict) -> None:
        """Append one JSON line for later debugging -- see docs/PLAN.md.
        Never allowed to break gameplay: any failure here is swallowed."""
        if self.log_path is None:
            return
        try:
            line = json.dumps({"ts": time.time(), **event}, ensure_ascii=False, default=str)
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass

    async def broadcast_lobby(self) -> None:
        payload = {
            "type": "lobby",
            "code": self.code,
            "game": self.spec.slug,
            "num_players": self.num_players,
            "difficulty": self.difficulty,
            "card_helper": self.card_helper,
            "players": self.players_meta(),
        }
        for s in self.seats:
            if s and s.kind == "human" and s.ws is not None:
                try:
                    await s.ws.send_json(payload)
                except Exception:
                    pass

    async def broadcast(self) -> None:
        assert self.state is not None
        meta = self.players_meta()
        # Full-information snapshot (every seat's view, including hidden
        # hands) so a later debugging request has the whole game to look
        # back through, not just whatever a human happened to see.
        self._log_event(
            {
                "type": "state",
                "views": {i: self.spec.serialize_seat(self.state, i, meta) for i in range(self.num_players)},
            }
        )
        for seat, s in enumerate(self.seats):
            if s and s.kind == "human" and s.ws is not None:
                try:
                    view = self.spec.serialize_seat(self.state, seat, meta)
                    await s.ws.send_json(
                        {
                            "type": "state",
                            "seat": seat,
                            "game": self.spec.slug,
                            "awaiting_next": self.awaiting_next,
                            "card_helper": self.card_helper,
                            **view,
                        }
                    )
                except Exception:
                    pass

    async def play_human_card(self, seat: int, action: str) -> None:
        assert self.state is not None
        if self.awaiting_next:
            return
        if self.spec.player_to_act(self.state) != seat:
            return
        # An action may carry extra payload after a colon (e.g. Deep Sea
        # Crew's prediction tasks send "task-3:5" -- the chosen number
        # tacked onto the drafted task's id, see games/deep_sea_crew/spec.py)
        # -- legality is checked against the bare id; the game's own `play`
        # is responsible for validating the payload itself.
        base_action = action.split(":", 1)[0]
        if base_action not in self.spec.legal_actions(self.state, seat):
            return
        try:
            self.spec.play(self.state, seat, action)
        except ValueError:
            # e.g. an out-of-range prediction payload -- reject the move,
            # not the connection.
            return
        await self.broadcast()
        if await self._maybe_pause():
            return
        await self.run_ai_turns()

    async def _maybe_pause(self) -> bool:
        """After a "pausable" move: halt (awaiting an explicit ack) if a
        human is seated to see it, else auto-continue after a brief sleep
        (so all-AI/spectator rooms still make progress). Returns True if
        the caller should stop advancing the game for now."""
        if self.spec.post_move_delay is None:
            return False
        delay = self.spec.post_move_delay(self.state)
        if delay <= 0:
            return False
        if self.has_human:
            self.awaiting_next = True
            await self.broadcast()
            return True
        await asyncio.sleep(delay)
        return False

    async def acknowledge_next(self) -> None:
        if not self.awaiting_next:
            return
        self.awaiting_next = False
        await self.broadcast()
        await self.run_ai_turns()

    async def communicate(self, seat: int, action: str) -> None:
        assert self.state is not None
        if self.spec.communicate is None:
            return
        try:
            self.spec.communicate(self.state, seat, action)
        except ValueError:
            return
        # Using the (one-time) signal is a final decision for this window
        # -- nothing legitimate left to do before the trick starts, so
        # auto-ready right away instead of requiring a separate "준비"
        # click. Matches what AI seats already do (see _advance_ready_phase).
        if self.spec.mark_ready is not None:
            try:
                self.spec.mark_ready(self.state, seat)
            except ValueError:
                pass
        await self.broadcast()
        await self.run_ai_turns()

    async def mark_ready(self, seat: int) -> None:
        """Human seat confirms it's done reviewing/signaling for this
        "everyone must ready up" window (see GameSpec.awaiting_ready)."""
        assert self.state is not None
        if self.spec.mark_ready is None:
            return
        try:
            self.spec.mark_ready(self.state, seat)
        except ValueError:
            return
        await self.broadcast()
        await self.run_ai_turns()

    async def _advance_ready_phase(self) -> None:
        """While the game is waiting for every seat to ready up: let each
        AI-controlled seat that hasn't readied yet optionally communicate
        first (same idea as the old _maybe_ai_communicate -- give AI seats
        the same shot at the secondary `communicate` channel a human
        would get), then mark itself ready. Any seat still un-ready
        afterward is human -- the caller stops and waits for their
        explicit "communicate"/"ready" WS messages."""
        assert self.state is not None
        if self.spec.mark_ready is None:
            return
        already_ready = set(self.spec.ready_seats(self.state)) if self.spec.ready_seats else set()
        changed = False
        for seat, seat_info in enumerate(self.seats):
            if seat_info is None or seat_info.kind != "ai" or seat in already_ready:
                continue
            if self.spec.communicable_seats is not None and self.spec.ai_communicate is not None:
                if seat in self.spec.communicable_seats(self.state):
                    action = self.spec.ai_communicate(self.state, seat, seat_info.ai_player)
                    if action is not None and self.spec.communicate is not None:
                        self.spec.communicate(self.state, seat, action)
                        changed = True
            self.spec.mark_ready(self.state, seat)
            changed = True
        if changed:
            await self.broadcast()

    async def run_ai_turns(self) -> None:
        assert self.state is not None
        while self.spec.outcome(self.state) is None:
            if self.awaiting_next:
                return
            if self.spec.awaiting_ready is not None and self.spec.awaiting_ready(self.state):
                await self._advance_ready_phase()
                if self.spec.awaiting_ready(self.state):
                    return  # still waiting on at least one human to ready up
                continue
            seat = self.spec.player_to_act(self.state)
            if seat is None:
                break
            seat_info = self.seats[seat]
            if seat_info is None or seat_info.kind != "ai":
                break
            loop = asyncio.get_running_loop()
            action = await loop.run_in_executor(
                None, seat_info.ai_player.choose_action, self.state, seat
            )
            self.spec.play(self.state, seat, action)
            await self.broadcast()
            if await self._maybe_pause():
                return


class RoomRegistry:
    def __init__(self) -> None:
        self._rooms: dict[str, Room] = {}
        self._rng = random.Random()

    def create(self, spec: GameSpec, num_players: int, difficulty: int, card_helper: bool = False) -> Room:
        code = make_room_code(self._rng)
        while code in self._rooms:
            code = make_room_code(self._rng)
        room = Room(code=code, spec=spec, num_players=num_players, difficulty=difficulty, card_helper=card_helper)
        self._rooms[code] = room
        return room

    def get(self, code: str) -> Room | None:
        return self._rooms.get(code.upper())


registry = RoomRegistry()
