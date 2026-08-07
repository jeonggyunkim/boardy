"""Player interface — human/random now, AlphaZero-style policy later."""

from __future__ import annotations

import random
from abc import ABC, abstractmethod

from .cards import Card
from .engine import GameState


class Player(ABC):
    name: str

    @abstractmethod
    def choose_card(self, state: GameState, seat: int) -> Card: ...

    def choose_communication(self, state: GameState, seat: int) -> Card | None:
        """Return a card to signal this turn, or None to skip."""
        return None


class RandomPlayer(Player):
    def __init__(self, name: str = "bot", rng: random.Random | None = None) -> None:
        self.name = name
        self.rng = rng or random.Random()

    def choose_card(self, state: GameState, seat: int) -> Card:
        return self.rng.choice(state.legal_cards_for(seat))
