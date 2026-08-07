"""Cards and deck for Deep Sea Crew.

ASSUMPTION (unverified against the physical rulebook, see docs/PLAN.md):
four colour suits ranked 1-9, plus a trump "submarine" suit ranked 1-4.
Trump cards always beat colour cards regardless of the suit led.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import random


class Suit(str, Enum):
    YELLOW = "yellow"
    PINK = "pink"
    GREEN = "green"
    BLUE = "blue"
    SUBMARINE = "submarine"  # trump suit


COLOR_SUITS: tuple[Suit, ...] = (Suit.YELLOW, Suit.PINK, Suit.GREEN, Suit.BLUE)
COLOR_MAX_RANK = 9
SUBMARINE_MAX_RANK = 4


@dataclass(frozen=True, order=True)
class Card:
    suit: Suit
    rank: int

    def __post_init__(self) -> None:
        max_rank = SUBMARINE_MAX_RANK if self.suit == Suit.SUBMARINE else COLOR_MAX_RANK
        if not (1 <= self.rank <= max_rank):
            raise ValueError(f"Invalid rank {self.rank} for suit {self.suit}")

    @property
    def is_trump(self) -> bool:
        return self.suit == Suit.SUBMARINE

    def __str__(self) -> str:
        symbol = {
            Suit.YELLOW: "Y",
            Suit.PINK: "P",
            Suit.GREEN: "G",
            Suit.BLUE: "B",
            Suit.SUBMARINE: "S",
        }[self.suit]
        return f"{symbol}{self.rank}"

    @classmethod
    def parse(cls, text: str) -> "Card":
        """Parse a short code like 'Y7' or 'S3' back into a Card."""
        text = text.strip().upper()
        letter_to_suit = {
            "Y": Suit.YELLOW,
            "P": Suit.PINK,
            "G": Suit.GREEN,
            "B": Suit.BLUE,
            "S": Suit.SUBMARINE,
        }
        if len(text) < 2 or text[0] not in letter_to_suit:
            raise ValueError(f"Cannot parse card code: {text!r}")
        return cls(letter_to_suit[text[0]], int(text[1:]))


def full_deck() -> list[Card]:
    deck = [Card(suit, rank) for suit in COLOR_SUITS for rank in range(1, COLOR_MAX_RANK + 1)]
    deck += [Card(Suit.SUBMARINE, rank) for rank in range(1, SUBMARINE_MAX_RANK + 1)]
    return deck


def deal(num_players: int, rng: random.Random | None = None) -> list[list[Card]]:
    """Deal the full deck as evenly as possible among num_players hands.

    The player holding submarine 4 (the highest trump) leads the first trick
    and is the game's "commander" — callers should locate that player after
    dealing (see engine.find_commander).
    """
    if num_players < 2:
        raise ValueError("Need at least 2 players")
    rng = rng or random.Random()
    deck = full_deck()
    rng.shuffle(deck)
    # Keep hand sizes equal (required for trick-taking to stay in sync);
    # any remainder cards that don't divide evenly are set aside unused.
    usable = (len(deck) // num_players) * num_players
    deck = deck[:usable]
    hands: list[list[Card]] = [[] for _ in range(num_players)]
    for i, card in enumerate(deck):
        hands[i % num_players].append(card)
    for hand in hands:
        hand.sort(key=lambda c: (c.suit.value, c.rank))
    return hands
