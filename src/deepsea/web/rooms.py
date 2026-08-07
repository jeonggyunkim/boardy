"""In-memory room/session management for realtime play.

A Room holds up to `num_players` seats. Each seat is either a connected
human (WebSocket) or an AI (RandomPlayer for now — swap in NetPlayer once
a checkpoint is trained, see docs/PLAN.md Phase 2). Single-process,
in-memory only: fine for a development skeleton, not for multi-instance
deployment.
"""

from __future__ import annotations

import asyncio
import random
import string
from dataclasses import dataclass, field

from fastapi import WebSocket

from ..cards import Card
from ..engine import GameState, new_game
from ..players import NetPlayer, Player, RandomPlayer
from .ai import get_shared_net
from .serialize import serialize_state


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
    num_players: int
    difficulty: int
    seats: list[SeatInfo | None] = field(default_factory=list)
    state: GameState | None = None

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
                tag = "smart" if mode == "smart" else "random"
                seat_name = name or f"AI-{i}({tag})"
                if mode == "smart":
                    player: Player = NetPlayer(
                        get_shared_net(),
                        name=seat_name,
                        use_search=True,
                        num_determinizations=5,
                        sims_per_determinization=15,
                    )
                else:
                    player = RandomPlayer(name=seat_name)
                self.seats[i] = SeatInfo(name=seat_name, kind="ai", ai_player=player)
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
        self.state = new_game(self.num_players, difficulty_budget=self.difficulty, seed=seed)

    async def broadcast_lobby(self) -> None:
        payload = {
            "type": "lobby",
            "code": self.code,
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
                    await s.ws.send_json(serialize_state(self.state, seat, meta))
                except Exception:
                    pass

    def _apply_move(self, seat: int, card: Card) -> None:
        assert self.state is not None
        self.state.play_card(seat, card)

    async def play_human_card(self, seat: int, card_text: str) -> None:
        assert self.state is not None
        if self.state.player_to_act != seat:
            return
        card = Card.parse(card_text)
        if card not in self.state.legal_cards_for(seat):
            return
        self._apply_move(seat, card)
        await self.broadcast()
        await self.run_ai_turns()

    async def communicate(self, seat: int, card_text: str) -> None:
        assert self.state is not None
        card = Card.parse(card_text)
        try:
            self.state.communicate(seat, card)
        except ValueError:
            return
        await self.broadcast()

    async def run_ai_turns(self) -> None:
        assert self.state is not None
        while self.state.outcome is None:
            seat = self.state.player_to_act
            if seat is None:
                break
            seat_info = self.seats[seat]
            if seat_info is None or seat_info.kind != "ai":
                break
            loop = asyncio.get_running_loop()
            card = await loop.run_in_executor(
                None, seat_info.ai_player.choose_card, self.state, seat
            )
            self._apply_move(seat, card)
            await self.broadcast()


class RoomRegistry:
    def __init__(self) -> None:
        self._rooms: dict[str, Room] = {}
        self._rng = random.Random()

    def create(self, num_players: int, difficulty: int) -> Room:
        code = make_room_code(self._rng)
        while code in self._rooms:
            code = make_room_code(self._rng)
        room = Room(code=code, num_players=num_players, difficulty=difficulty)
        self._rooms[code] = room
        return room

    def get(self, code: str) -> Room | None:
        return self._rooms.get(code.upper())


registry = RoomRegistry()
