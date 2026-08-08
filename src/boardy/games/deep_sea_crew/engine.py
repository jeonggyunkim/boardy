"""Core game engine: trick resolution, legal moves, mission progress.

ASSUMPTION (unverified, see docs/PLAN.md): standard trick-taking rules —
- Whoever holds submarine-4 leads the first trick (the "commander").
- Players must follow the suit led if they have a card of it; otherwise
  they may play anything, including a submarine (trump) card.
- A trick is won by the highest submarine card played, or if none was
  played, the highest card of the suit led.
- Winner of a trick leads the next one.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .cards import Card, Suit, deal
from .communication import CommunicationBoard, Signal
from .missions import build_mission
from .tasks import Task, missions_completed


def find_commander(hands: list[list[Card]]) -> int:
    """Player holding submarine-4 leads first; if it was left in the unused
    remainder (deck doesn't divide evenly), fall back to whoever holds the
    highest submarine card, else player 0."""
    for i, hand in enumerate(hands):
        if Card(Suit.SUBMARINE, 4) in hand:
            return i
    best_player, best_rank = 0, -1
    for i, hand in enumerate(hands):
        for c in hand:
            if c.suit == Suit.SUBMARINE and c.rank > best_rank:
                best_player, best_rank = i, c.rank
    return best_player


def legal_moves(hand: list[Card], led_suit: Suit | None) -> list[Card]:
    if led_suit is None:
        return list(hand)
    following = [c for c in hand if c.suit == led_suit]
    return following if following else list(hand)


def resolve_trick(cards: dict[int, Card], led_suit: Suit) -> int:
    """Return the index of the player who wins the trick."""
    trumps = {p: c for p, c in cards.items() if c.suit == Suit.SUBMARINE}
    pool = trumps if trumps else {p: c for p, c in cards.items() if c.suit == led_suit}
    return max(pool, key=lambda p: pool[p].rank)


@dataclass
class TrickRecord:
    number: int
    leader: int
    cards: dict[int, Card]
    winner: int


@dataclass
class GameState:
    num_players: int
    hands: list[list[Card]]
    tasks: list[Task]
    comms: CommunicationBoard
    current_leader: int
    hand_size: int
    trick_in_progress: dict[int, Card] = field(default_factory=dict)
    trick_number: int = 1
    history: list[TrickRecord] = field(default_factory=list)
    wins_per_player: dict[int, int] = field(default_factory=dict)
    outcome: bool | None = None  # None = ongoing, True = success, False = failed

    @property
    def led_suit(self) -> Suit | None:
        if not self.trick_in_progress:
            return None
        first_player = min(self.trick_in_progress, key=lambda p: self._play_order.index(p))
        return self.trick_in_progress[first_player].suit

    @property
    def _play_order(self) -> list[int]:
        n = self.num_players
        return [(self.current_leader + i) % n for i in range(n)]

    @property
    def player_to_act(self) -> int | None:
        if self.outcome is not None:
            return None
        for p in self._play_order:
            if p not in self.trick_in_progress:
                return p
        return None

    def legal_cards_for(self, player: int) -> list[Card]:
        return legal_moves(self.hands[player], self.led_suit)

    def play_card(self, player: int, card: Card) -> TrickRecord | None:
        if self.outcome is not None:
            raise ValueError("Game already finished")
        if player != self.player_to_act:
            raise ValueError(f"It is not player {player}'s turn")
        if card not in self.hands[player]:
            raise ValueError(f"Player {player} does not hold {card}")
        if card not in self.legal_cards_for(player):
            raise ValueError(f"Player {player} must follow suit, cannot play {card}")

        self.hands[player].remove(card)
        self.trick_in_progress[player] = card
        self.comms.clear_played(player, card)

        if len(self.trick_in_progress) < self.num_players:
            return None
        return self._complete_trick()

    def _complete_trick(self) -> TrickRecord:
        led = self.led_suit
        assert led is not None
        winner = resolve_trick(self.trick_in_progress, led)
        self.wins_per_player[winner] = self.wins_per_player.get(winner, 0) + 1
        is_final = self.trick_number == self.hand_size

        for task in self.tasks:
            task.check_after_trick(
                self.trick_number, self.trick_in_progress, winner, self.wins_per_player, is_final, self.hand_size
            )

        record = TrickRecord(
            number=self.trick_number,
            leader=self.current_leader,
            cards=dict(self.trick_in_progress),
            winner=winner,
        )
        self.history.append(record)

        result = missions_completed(self.tasks)
        if result is False:
            self.outcome = False
        elif is_final:
            for task in self.tasks:
                task.force_resolve_if_unresolved_at_end(self.wins_per_player)
            self.outcome = missions_completed(self.tasks)

        self.trick_in_progress = {}
        self.current_leader = winner
        self.trick_number += 1
        return record

    def communicate(self, player: int, card: Card) -> Signal:
        if self.trick_in_progress:
            raise ValueError("Communication is only allowed before a trick starts")
        return self.comms.communicate(player, card, self.hands[player])


def new_game(
    num_players: int,
    difficulty_budget: int = 8,
    seed: int | None = None,
) -> GameState:
    import random

    rng = random.Random(seed)
    hands = deal(num_players, rng)
    hand_size = len(hands[0])
    commander = find_commander(hands)
    tasks = build_mission(num_players, hand_size, difficulty_budget, hands=hands, rng=rng)
    comms = CommunicationBoard(num_players)
    return GameState(
        num_players=num_players,
        hands=hands,
        tasks=tasks,
        comms=comms,
        current_leader=commander,
        hand_size=hand_size,
    )
