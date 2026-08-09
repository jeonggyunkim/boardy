"""Core game engine: task draft, trick resolution, legal moves, mission progress.

ASSUMPTION (unverified, see docs/PLAN.md): standard trick-taking rules —
- Whoever holds submarine-4 leads the first trick (the "commander").
- Players must follow the suit led if they have a card of it; otherwise
  they may play anything, including a submarine (trump) card.
- A trick is won by the highest submarine card played, or if none was
  played, the highest card of the suit led.
- Winner of a trick leads the next one.

Before any trick play, the game is in a task-draft phase: a set of task
cards is drawn face-up, and starting from the commander, players take
turns (wrapping around the table as many times as needed) each claiming
one card they want. This is a deliberate choice, not a random deal —
tasks aren't assigned, they're drafted.

Between the draft and every trick (including the first), the game sits
in an explicit "trick_ready" phase: nobody may play a card yet, but
anyone still eligible may reveal a Sonar signal (see communicate()).
Every seat must individually mark itself ready (mark_ready) before the
trick actually opens for play; a seat can't communicate once it has done
so. This phase is a real, tracked part of the game state -- not a
side-effect of pacing the host UI -- so it's the same whether the game is
played in the CLI or the web GUI.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .cards import Card, Suit, deal
from .communication import CommunicationBoard, Signal
from .missions import draw_tasks
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
    available_tasks: list[Task]  # drawn, not yet claimed by anyone
    comms: CommunicationBoard
    current_leader: int  # this trick's leader -- changes every trick (winner leads next)
    commander: int  # fixed for the whole game: who led the draft order and trick 1
    hand_size: int
    phase: str = "task_draft"  # "task_draft" | "trick_ready" | "playing"
    tasks: list[Task] = field(default_factory=list)  # claimed tasks, in draft order
    picks_made: int = 0  # how many tasks have been claimed so far
    ready_seats: set[int] = field(default_factory=set)  # who has marked ready this "trick_ready" window
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
        if self.phase == "task_draft":
            if not self.available_tasks:
                return None
            # draft order starts at the commander and wraps around the
            # table as many times as needed to exhaust the drawn tasks
            return (self.current_leader + self.picks_made) % self.num_players
        if self.phase == "trick_ready":
            # not a single-actor turn -- every seat marks ready
            # independently, in any order (see mark_ready/communicate)
            return None
        for p in self._play_order:
            if p not in self.trick_in_progress:
                return p
        return None

    def draft_task(self, player: int, task_id: str) -> Task:
        if self.phase != "task_draft":
            raise ValueError("Not in the task-draft phase")
        if player != self.player_to_act:
            raise ValueError(f"It is not player {player}'s turn to draft a task")
        match = next((t for t in self.available_tasks if t.id == task_id), None)
        if match is None:
            raise ValueError(f"Task {task_id} is not available to draft")
        self.available_tasks.remove(match)
        match.owner = player
        self.tasks.append(match)
        self.picks_made += 1
        if not self.available_tasks:
            self.phase = "trick_ready"
            self.ready_seats = set()
        return match

    def mark_ready(self, seat: int) -> None:
        """Seat confirms it's done reviewing/signaling and the next trick
        may start once everyone has. Idempotent -- marking ready twice is a
        no-op, not an error, since a client resending it is harmless."""
        if self.phase != "trick_ready":
            raise ValueError("Not waiting for players to ready up right now")
        if not (0 <= seat < self.num_players):
            raise ValueError(f"Invalid seat {seat}")
        self.ready_seats.add(seat)
        if len(self.ready_seats) == self.num_players:
            self.phase = "playing"

    def auto_ready_up(self) -> None:
        """Mark every seat ready without any communication -- for
        non-interactive contexts (search rollouts, simulated/self-play
        games, the CLI) that don't model the ready-up window as a real
        decision point. No-op if not currently in that phase."""
        while self.phase == "trick_ready":
            for seat in range(self.num_players):
                if self.phase != "trick_ready":
                    break
                if seat not in self.ready_seats:
                    self.mark_ready(seat)

    def legal_cards_for(self, player: int) -> list[Card]:
        return legal_moves(self.hands[player], self.led_suit)

    def play_card(self, player: int, card: Card) -> TrickRecord | None:
        if self.phase != "playing":
            raise ValueError("Cannot play a card until everyone is ready")
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
        if self.outcome is None:
            self.phase = "trick_ready"
            self.ready_seats = set()
        return record

    def communicate(self, player: int, card: Card) -> Signal:
        if self.phase != "trick_ready":
            raise ValueError("Communication is only allowed while waiting for players to ready up")
        if player == self.current_leader:
            raise ValueError("The player leading this trick cannot communicate")
        if player in self.ready_seats:
            raise ValueError("Already marked ready -- can no longer communicate this window")
        return self.comms.communicate(player, card, self.hands[player])

    def communicable_seats(self) -> list[int]:
        """Seats currently allowed to attempt a Sonar signal: only during
        the "trick_ready" window, never the trick's leader, and not once a
        seat has already marked itself ready."""
        if self.phase != "trick_ready":
            return []
        return [
            seat
            for seat in range(self.num_players)
            if seat != self.current_leader and seat not in self.ready_seats and self.comms.can_communicate(seat)
        ]


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
    available_tasks = draw_tasks(num_players, hand_size, difficulty_budget, hands=hands, rng=rng)
    comms = CommunicationBoard(num_players)
    return GameState(
        num_players=num_players,
        hands=hands,
        available_tasks=available_tasks,
        comms=comms,
        current_leader=commander,
        commander=commander,
        hand_size=hand_size,
    )
