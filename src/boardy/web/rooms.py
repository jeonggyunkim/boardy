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
import random
import string
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket

from ..core.game_spec import GameSpec, Player


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

    def __post_init__(self) -> None:
        if not self.seats:
            self.seats = [None] * self.num_players

    @property
    def is_full(self) -> bool:
        return all(s is not None for s in self.seats)

    @property
    def started(self) -> bool:
        return self.state is not None

    def add_human(self, name: str, ws: WebSocket) -> int | None:
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

    async def broadcast_lobby(self) -> None:
        payload = {
            "type": "lobby",
            "code": self.code,
            "game": self.spec.slug,
            "num_players": self.num_players,
            "difficulty": self.difficulty,
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
        for seat, s in enumerate(self.seats):
            if s and s.kind == "human" and s.ws is not None:
                try:
                    view = self.spec.serialize_seat(self.state, seat, meta)
                    await s.ws.send_json({"type": "state", "seat": seat, **view})
                except Exception:
                    pass

    async def play_human_card(self, seat: int, action: str) -> None:
        assert self.state is not None
        if self.spec.player_to_act(self.state) != seat:
            return
        if action not in self.spec.legal_actions(self.state, seat):
            return
        self.spec.play(self.state, seat, action)
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
        await self.broadcast()

    async def run_ai_turns(self) -> None:
        assert self.state is not None
        while self.spec.outcome(self.state) is None:
            seat = self.spec.player_to_act(self.state)
            if seat is None:
                break
            seat_info = self.seats[seat]
            if seat_info is None or seat_info.kind != "ai":
                break
            loop = asyncio.get_running_loop()
            action = await loop.run_in_executor(
                None, seat_info.ai_player.choose_card, self.state, seat
            )
            self.spec.play(self.state, seat, action)
            await self.broadcast()


class RoomRegistry:
    def __init__(self) -> None:
        self._rooms: dict[str, Room] = {}
        self._rng = random.Random()

    def create(self, spec: GameSpec, num_players: int, difficulty: int) -> Room:
        code = make_room_code(self._rng)
        while code in self._rooms:
            code = make_room_code(self._rng)
        room = Room(code=code, spec=spec, num_players=num_players, difficulty=difficulty)
        self._rooms[code] = room
        return room

    def get(self, code: str) -> Room | None:
        return self._rooms.get(code.upper())


registry = RoomRegistry()
