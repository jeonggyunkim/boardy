"""Sonar-token communication mechanic.

ASSUMPTION (unverified, see docs/PLAN.md): once per game, a player may
reveal one COLORED card (not a submarine -- there's only one trump suit,
so "highest/lowest/only of its suit" isn't a meaningful signal for it)
from their hand face-up and mark it with a Sonar token indicating it is
the HIGHEST, LOWEST, or ONLY card of that suit in their hand. Only
allowed before a trick starts, and never by the player leading that
trick (see GameState.communicate) -- once the first card of a trick has
been played, no one may communicate until that trick resolves and the
next one begins. The card stays visible
(but still in hand, still playable) until it is played. Some missions may
disable or grant extra communications (Currents / Rapture of the Deep) —
not yet modelled, tracked as a TODO for when real task text is available.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .cards import Card, Suit


class SonarMarker(str, Enum):
    HIGHEST = "highest"
    LOWEST = "lowest"
    ONLY = "only"


@dataclass(frozen=True)
class Signal:
    player: int
    card: Card
    marker: SonarMarker


def valid_marker(card: Card, hand: list[Card]) -> set[SonarMarker]:
    """Which markers are truthfully applicable to `card` within `hand`.
    Submarine (trump) cards can never be signaled -- the highest/lowest/
    only comparison is a same-color-suit concept, and submarines aren't
    one of the four colors."""
    if card.suit == Suit.SUBMARINE:
        return set()
    same_suit = [c for c in hand if c.suit == card.suit]
    if len(same_suit) == 1:
        return {SonarMarker.ONLY}
    ranks = [c.rank for c in same_suit]
    markers = set()
    if card.rank == max(ranks):
        markers.add(SonarMarker.HIGHEST)
    if card.rank == min(ranks):
        markers.add(SonarMarker.LOWEST)
    return markers


class CommunicationBoard:
    """Tracks who has used their (single) communication and active signals."""

    def __init__(self, num_players: int, allowance_per_player: int = 1) -> None:
        self._remaining = [allowance_per_player] * num_players
        self.signals: dict[int, Signal] = {}

    def can_communicate(self, player: int) -> bool:
        return self._remaining[player] > 0

    def communicate(self, player: int, card: Card, hand: list[Card]) -> Signal:
        if not self.can_communicate(player):
            raise ValueError(f"Player {player} has no communication left")
        markers = valid_marker(card, hand)
        if not markers:
            raise ValueError(f"{card} is not a valid signal card for this hand")
        marker = SonarMarker.ONLY if SonarMarker.ONLY in markers else next(iter(markers))
        signal = Signal(player=player, card=card, marker=marker)
        self._remaining[player] -= 1
        self.signals[player] = signal
        return signal

    def clear_played(self, player: int, card: Card) -> None:
        """Remove a signal once its card has actually been played."""
        signal = self.signals.get(player)
        if signal is not None and signal.card == card:
            del self.signals[player]
