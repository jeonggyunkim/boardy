"""Task cards as a small data-driven DSL.

PLACEHOLDER DATA (see docs/PLAN.md): the real game ships 96 illustrated
task cards with specific text and a difficulty rating. We don't have that
text, so tasks are expressed procedurally here and stored in
data/tasks.json. Replace that file with the real 96 tasks (same schema)
once available — no engine code should need to change.

Each task is assigned to a specific player and must be resolved (True/False)
by the time the mission ends. Some task kinds resolve immediately when their
condition becomes impossible (e.g. "never win a trick with a blue card" fails
the instant such a trick is won), others only resolve at the end of the hand
(e.g. "win exactly 3 tricks").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .cards import Card, Suit


class TaskKind(str, Enum):
    WIN_CARD = "win_card"  # this player must win the trick containing `card`
    WIN_TRICK_NUMBER = "win_trick_number"  # must win the Nth trick played (1-indexed)
    WIN_EXACT_COUNT = "win_exact_count"  # must win exactly N tricks total
    WIN_AT_LEAST = "win_at_least"  # must win at least N tricks
    WIN_NO_TRICKS = "win_no_tricks"  # must win zero tricks
    NEVER_WIN_COLOR = "never_win_color"  # must never win a trick containing `suit`
    WIN_FIRST_TRICK = "win_first_trick"
    WIN_LAST_TRICK = "win_last_trick"


@dataclass
class Task:
    id: str
    owner: int  # player index this task is assigned to
    kind: TaskKind
    params: dict[str, Any] = field(default_factory=dict)
    order_index: int | None = None  # for tasks that must complete in a stated sequence
    difficulty: int = 1
    resolved: bool = False
    success: bool | None = None  # None while unresolved

    def check_after_trick(
        self,
        trick_number: int,
        trick_cards: dict[int, Card],
        winner: int,
        wins_per_player: dict[int, int],
        is_final_trick: bool,
    ) -> None:
        """Update resolution state after a trick completes."""
        if self.resolved:
            return
        kind = self.kind
        if kind == TaskKind.WIN_CARD:
            card = Card.parse(self.params["card"])
            if card in trick_cards.values():
                self._resolve(winner == self.owner)
        elif kind == TaskKind.WIN_TRICK_NUMBER:
            if trick_number == self.params["n"]:
                self._resolve(winner == self.owner)
        elif kind == TaskKind.NEVER_WIN_COLOR:
            suit = Suit(self.params["suit"])
            if any(c.suit == suit for c in trick_cards.values()) and winner == self.owner:
                self._resolve(False)
        elif kind == TaskKind.WIN_FIRST_TRICK:
            if trick_number == 1:
                self._resolve(winner == self.owner)
        elif kind == TaskKind.WIN_NO_TRICKS:
            if winner == self.owner:
                self._resolve(False)
            elif is_final_trick:
                self._resolve(True)
        elif kind in (TaskKind.WIN_EXACT_COUNT, TaskKind.WIN_AT_LEAST, TaskKind.WIN_LAST_TRICK):
            if is_final_trick:
                self._finalize(wins_per_player, winner, trick_number)

    def _finalize(self, wins_per_player: dict[int, int], winner: int, trick_number: int) -> None:
        if self.kind == TaskKind.WIN_EXACT_COUNT:
            self._resolve(wins_per_player.get(self.owner, 0) == self.params["n"])
        elif self.kind == TaskKind.WIN_AT_LEAST:
            self._resolve(wins_per_player.get(self.owner, 0) >= self.params["n"])
        elif self.kind == TaskKind.WIN_LAST_TRICK:
            self._resolve(winner == self.owner)

    def force_resolve_if_unresolved_at_end(self, wins_per_player: dict[int, int]) -> None:
        if self.resolved:
            return
        if self.kind == TaskKind.WIN_NO_TRICKS:
            self._resolve(wins_per_player.get(self.owner, 0) == 0)
        elif self.kind == TaskKind.NEVER_WIN_COLOR:
            # never triggered a failure across the whole hand -> success
            self._resolve(True)
        elif self.kind in (TaskKind.WIN_CARD, TaskKind.WIN_TRICK_NUMBER, TaskKind.WIN_FIRST_TRICK):
            self._resolve(False)  # the trick it depended on already passed without success
        else:
            self._resolve(False)

    def _resolve(self, success: bool) -> None:
        self.resolved = True
        self.success = success

    def describe(self) -> str:
        p = self.params
        text = {
            TaskKind.WIN_CARD: f"Player {self.owner} must win the trick containing {p.get('card')}",
            TaskKind.WIN_TRICK_NUMBER: f"Player {self.owner} must win trick #{p.get('n')}",
            TaskKind.WIN_EXACT_COUNT: f"Player {self.owner} must win exactly {p.get('n')} tricks",
            TaskKind.WIN_AT_LEAST: f"Player {self.owner} must win at least {p.get('n')} tricks",
            TaskKind.WIN_NO_TRICKS: f"Player {self.owner} must win no tricks",
            TaskKind.NEVER_WIN_COLOR: f"Player {self.owner} must never win a trick containing {p.get('suit')}",
            TaskKind.WIN_FIRST_TRICK: f"Player {self.owner} must win the first trick",
            TaskKind.WIN_LAST_TRICK: f"Player {self.owner} must win the last trick",
        }[self.kind]
        if self.order_index is not None:
            text += f" [order {self.order_index}]"
        return text


def missions_completed(tasks: list[Task]) -> bool | None:
    """True if all tasks succeeded, False if any failed, None if still pending."""
    if any(t.resolved and not t.success for t in tasks):
        return False
    if all(t.resolved for t in tasks):
        return True
    return None
