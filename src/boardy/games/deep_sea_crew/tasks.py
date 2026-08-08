"""Task cards as a small data-driven DSL.

PLACEHOLDER DATA (see docs/PLAN.md): the real game ships 96 illustrated
task cards with specific text and a difficulty rating. We don't have that
text, so tasks are expressed procedurally here and stored in
data/tasks.json. Replace that file with the real 96 tasks (same schema)
once available — no engine code should need to change.

Each task is assigned to a specific player and must be resolved (True/False)
by the time the mission ends. Most task kinds resolve immediately once
their condition is met or becomes impossible -- e.g. "never win a trick
with a blue card" fails the instant such a trick is won, and "win exactly
3 tricks" fails as soon as either a 4th trick is won or too few tricks
remain in the hand for 3 to still be reachable -- rather than waiting
until the last trick to find out.
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


_SUIT_KO = {
    Suit.YELLOW: "노랑",
    Suit.PINK: "분홍",
    Suit.GREEN: "초록",
    Suit.BLUE: "파랑",
    Suit.SUBMARINE: "잠수함",
}


@dataclass
class Task:
    id: str
    kind: TaskKind
    owner: int | None = None  # player index this task is assigned to; None until drafted
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
        hand_size: int,
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
        elif kind == TaskKind.WIN_LAST_TRICK:
            if is_final_trick:
                self._resolve(winner == self.owner)
        elif kind in (TaskKind.WIN_EXACT_COUNT, TaskKind.WIN_AT_LEAST):
            wins = wins_per_player.get(self.owner, 0)
            remaining = hand_size - trick_number
            n = self.params["n"]
            if kind == TaskKind.WIN_EXACT_COUNT:
                # fail as soon as N is exceeded, or as soon as too few
                # tricks remain in the hand for N to still be reachable
                if wins > n or wins + remaining < n:
                    self._resolve(False)
                elif is_final_trick:
                    self._resolve(wins == n)
            else:
                if wins + remaining < n:
                    self._resolve(False)
                elif is_final_trick:
                    self._resolve(wins >= n)

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
        """Task text without an owner prefix -- used for the draft pool,
        where a task doesn't belong to anyone yet."""
        p = self.params
        kind = self.kind
        # NOTE: deliberately if/elif, not a dict literal keyed by kind --
        # a dict literal evaluates every branch's f-string up front (to
        # build the dict) before picking one by key, so a branch that
        # only makes sense for a different kind (e.g. Suit(p['suit'])
        # when this task has no 'suit' param) would raise regardless of
        # which kind self.kind actually is.
        if kind == TaskKind.WIN_CARD:
            return f"{p.get('card')} 카드가 포함된 트릭을 획득해야 함"
        if kind == TaskKind.WIN_TRICK_NUMBER:
            return f"{p.get('n')}번째 트릭을 획득해야 함"
        if kind == TaskKind.WIN_EXACT_COUNT:
            return f"정확히 {p.get('n')}개의 트릭을 획득해야 함"
        if kind == TaskKind.WIN_AT_LEAST:
            return f"최소 {p.get('n')}개의 트릭을 획득해야 함"
        if kind == TaskKind.WIN_NO_TRICKS:
            return "트릭을 하나도 획득하면 안 됨"
        if kind == TaskKind.NEVER_WIN_COLOR:
            suit = Suit(p.get("suit"))
            return f"{_SUIT_KO.get(suit, suit.value)} 카드가 포함된 트릭을 획득하면 안 됨"
        if kind == TaskKind.WIN_FIRST_TRICK:
            return "첫 번째 트릭을 획득해야 함"
        if kind == TaskKind.WIN_LAST_TRICK:
            return "마지막 트릭을 획득해야 함"
        raise ValueError(f"Unknown task kind: {kind}")

    def describe_assigned(self) -> str:
        """Task text with the owning player prefixed -- used once claimed."""
        text = f"P{self.owner}: {self.describe()}"
        if self.order_index is not None:
            text += f" [순서 {self.order_index}]"
        return text


def missions_completed(tasks: list[Task]) -> bool | None:
    """True if all tasks succeeded, False if any failed, None if still pending."""
    if any(t.resolved and not t.success for t in tasks):
        return False
    if all(t.resolved for t in tasks):
        return True
    return None
