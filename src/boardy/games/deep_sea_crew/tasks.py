"""Task cards as a small data-driven DSL.

The 96 real Deep Sea Crew task cards live in data/deep_sea_crew/tasks.json.
Each task is assigned to a specific player and must be resolved (True/False)
by the time the mission ends. Most task kinds resolve immediately once
their condition is met or becomes impossible -- e.g. "never win a trick
with a blue card" fails the instant such a trick is won, and "win exactly
3 tricks" fails as soon as either a 4th trick is won or too few tricks
remain in the hand for 3 to still be reachable -- rather than waiting
until the last trick to find out.

Winning a trick captures *every* card played in it (not just the winner's
own card) -- this is what "카드 획득" / "따기" means throughout the real
card text (e.g. a "win 2 blue cards" task is satisfied by blue cards from
any trick the owner wins, played by anyone). "아무N" (any-rank) tasks only
match the four colour suits, never the submarine suit -- the cards
consistently treat "잠수함" as a separate category from "아무" rank text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .cards import COLOR_MAX_RANK, COLOR_SUITS, Card, Suit


class TaskKind(str, Enum):
    WIN_CARD = "win_card"  # win the trick containing `card`
    WIN_CARDS = "win_cards"  # win the tricks containing every card in `cards` (any order, any tricks)
    WIN_CARD_EXCLUDE_OTHERS = "win_card_exclude_others"  # win `card`'s trick; never win a trick containing any of `forbidden`
    WIN_TRICK_BY_RANK = "win_trick_by_rank"  # win a trick by playing (not just holding) a colour card of `rank`
    NEVER_WIN_RANK = "never_win_rank"  # never win a trick containing a colour card of `rank`
    NEVER_WIN_RANKS = "never_win_ranks"  # never win a trick containing a colour card whose rank is in `ranks`
    NEVER_WIN_COLOR = "never_win_color"  # never win a trick containing `suit`
    NEVER_WIN_COLORS = "never_win_colors"  # never win a trick containing any suit in `suits`
    WIN_TRICK_NUMBER = "win_trick_number"  # win the Nth trick played (1-indexed)
    WIN_EXACT_COUNT = "win_exact_count"  # win exactly N tricks total
    WIN_AT_LEAST = "win_at_least"  # win at least N tricks
    WIN_NO_TRICKS = "win_no_tricks"  # win zero tricks
    WIN_FIRST_TRICK = "win_first_trick"
    WIN_LAST_TRICK = "win_last_trick"
    WIN_TRICKS_ALL = "win_tricks_all"  # win every trick number listed in `numbers`
    NEVER_WIN_TRICKS = "never_win_tricks"  # win none of the trick numbers listed in `numbers`
    WIN_ONLY_TRICK = "win_only_trick"  # win trick `n` and no other trick
    WIN_EXACT_CARD_COUNT = "win_exact_card_count"  # for each {suit|rank, n} in `conditions`, capture exactly n matching cards
    WIN_AT_LEAST_CARD_COUNT = "win_at_least_card_count"  # same, but "at least n" for every condition
    WIN_TRICK_ALL_ABOVE = "win_trick_all_above"  # win a submarine-free trick where every card's rank > `threshold`
    WIN_TRICK_ALL_BELOW = "win_trick_all_below"  # win a submarine-free trick where every card's rank < `threshold`
    WIN_TRICK_SUM_BELOW = "win_trick_sum_below"  # win a submarine-free trick whose rank sum < `threshold`
    WIN_TRICK_SUM_IN = "win_trick_sum_in"  # win a submarine-free trick whose rank sum is in `values`
    WIN_TRICK_SUM_ABOVE = "win_trick_sum_above"  # win a submarine-free trick whose rank sum > `threshold`
    WIN_TRICK_EQUAL_COLOR_COUNTS = "win_trick_equal_color_counts"  # win a trick with an equal (>0) count of `suit_a`/`suit_b`
    WIN_TRICK_ALL_ODD = "win_trick_all_odd"  # win a trick where every card's rank is odd
    WIN_TRICK_ALL_EVEN = "win_trick_all_even"  # win a trick where every card's rank is even
    NEVER_LEAD_WITH_COLOR = "never_lead_with_color"  # never lead a trick with a card whose suit is in `suits`
    WIN_CARD_IN_LAST_TRICK = "win_card_in_last_trick"  # win the last trick, which must contain `card`
    PLAY_AND_WIN_WITH = "play_and_win_with"  # play a card matching `play`, win the trick, which must also contain a card matching `other`
    WIN_N_CONSECUTIVE = "win_n_consecutive"  # win `n` tricks in a row at some point
    NEVER_WIN_TWO_CONSECUTIVE = "never_win_two_consecutive"  # never win two tricks in a row
    WIN_EXACT_COUNT_CONSECUTIVE = "win_exact_count_consecutive"  # win exactly `n` tricks total, and they must be consecutive
    FEWER_THAN_EVERYONE = "fewer_than_everyone"  # strictly fewer tricks than every other player
    MORE_THAN_EVERYONE = "more_than_everyone"  # strictly more tricks than every other player
    MORE_THAN_SUM_OF_OTHERS = "more_than_sum_of_others"  # strictly more tricks than all other players combined
    PREDICT_EXACT_COUNT = "predict_exact_count"  # like WIN_EXACT_COUNT, but `n` is chosen by the owner at draft time
    FEWER_THAN_COMMANDER = "fewer_than_commander"  # fewer tricks than the commander (owner may not be the commander)
    MORE_THAN_COMMANDER = "more_than_commander"  # more tricks than the commander (owner may not be the commander)
    EQUAL_TO_COMMANDER = "equal_to_commander"  # same trick count as the commander (owner may not be the commander)
    COMPARE_COLOR_COUNTS = "compare_color_counts"  # captured `greater`-suit cards strictly outnumber captured `less`-suit cards
    EQUAL_COLOR_COUNTS_NONZERO = "equal_color_counts_nonzero"  # captured `color_a`/`color_b` counts equal and both > 0
    WIN_EACH_COLOR_AT_LEAST_ONE = "win_each_color_at_least_one"  # captured at least one card of all 4 colours
    WIN_FULL_COLOR_RUN = "win_full_color_run"  # captured all 9 cards of at least one colour


_SUIT_KO = {
    Suit.YELLOW: "노랑",
    Suit.PINK: "분홍",
    Suit.GREEN: "초록",
    Suit.BLUE: "파랑",
    Suit.SUBMARINE: "잠수함",
}


def _suits_ko(suits: list[str]) -> str:
    return "/".join(_SUIT_KO.get(Suit(s), s) for s in suits)


def _match_condition(card: Card, cond: dict[str, Any]) -> bool:
    if "suit" in cond:
        return card.suit.value == cond["suit"]
    return card.suit != Suit.SUBMARINE and card.rank == cond["rank"]


def _condition_ko(cond: dict[str, Any]) -> str:
    if "suit" in cond:
        return _SUIT_KO.get(Suit(cond["suit"]), cond["suit"])
    return f"아무{cond['rank']}"


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

    # internal bookkeeping, updated once per trick regardless of kind --
    # cheap to maintain, several kinds below read from them.
    _captured: set = field(default_factory=set, repr=False, compare=False)
    _owned_trick_numbers: list = field(default_factory=list, repr=False, compare=False)
    _streak: int = field(default=0, repr=False, compare=False)
    _last_won_trick: int | None = field(default=None, repr=False, compare=False)

    def check_after_trick(
        self,
        trick_number: int,
        trick_cards: dict[int, Card],
        winner: int,
        wins_per_player: dict[int, int],
        is_final_trick: bool,
        hand_size: int,
        *,
        leader: int | None = None,
        num_players: int | None = None,
        commander: int | None = None,
    ) -> None:
        """Update resolution state after a trick completes."""
        if self.resolved:
            return
        kind = self.kind
        p = self.params

        if winner == self.owner:
            self._captured.update(trick_cards.values())
            self._owned_trick_numbers.append(trick_number)
            if self._last_won_trick == trick_number - 1:
                self._streak += 1
            else:
                self._streak = 1
            self._last_won_trick = trick_number

        if kind == TaskKind.WIN_CARD:
            card = Card.parse(p["card"])
            if card in trick_cards.values():
                self._resolve(winner == self.owner)

        elif kind == TaskKind.WIN_CARDS:
            cards = {Card.parse(c) for c in p["cards"]}
            hit = cards & set(trick_cards.values())
            if hit:
                if winner != self.owner:
                    self._resolve(False)
                elif cards <= self._captured:
                    self._resolve(True)

        elif kind == TaskKind.WIN_CARD_EXCLUDE_OTHERS:
            target = Card.parse(p["card"])
            forbidden = {Card.parse(c) for c in p["forbidden"]}
            values = set(trick_cards.values())
            if winner == self.owner:
                if values & forbidden:
                    self._resolve(False)
                elif target in values:
                    self._resolve(True)
            elif target in values:
                self._resolve(False)

        elif kind == TaskKind.WIN_TRICK_BY_RANK:
            if winner == self.owner:
                mine = trick_cards[self.owner]
                if mine.suit != Suit.SUBMARINE and mine.rank == p["rank"]:
                    self._resolve(True)

        elif kind == TaskKind.NEVER_WIN_RANK:
            if winner == self.owner and any(
                c.suit != Suit.SUBMARINE and c.rank == p["rank"] for c in trick_cards.values()
            ):
                self._resolve(False)

        elif kind == TaskKind.NEVER_WIN_RANKS:
            ranks = set(p["ranks"])
            if winner == self.owner and any(
                c.suit != Suit.SUBMARINE and c.rank in ranks for c in trick_cards.values()
            ):
                self._resolve(False)

        elif kind == TaskKind.NEVER_WIN_COLOR:
            suit = Suit(p["suit"])
            if any(c.suit == suit for c in trick_cards.values()) and winner == self.owner:
                self._resolve(False)

        elif kind == TaskKind.NEVER_WIN_COLORS:
            suits = {Suit(s) for s in p["suits"]}
            if winner == self.owner and any(c.suit in suits for c in trick_cards.values()):
                self._resolve(False)

        elif kind == TaskKind.WIN_TRICK_NUMBER:
            if trick_number == p["n"]:
                self._resolve(winner == self.owner)

        elif kind == TaskKind.WIN_FIRST_TRICK:
            if trick_number == 1:
                self._resolve(winner == self.owner)

        elif kind == TaskKind.WIN_LAST_TRICK:
            if is_final_trick:
                self._resolve(winner == self.owner)

        elif kind == TaskKind.WIN_NO_TRICKS:
            if winner == self.owner:
                self._resolve(False)
            elif is_final_trick:
                self._resolve(True)

        elif kind in (TaskKind.WIN_EXACT_COUNT, TaskKind.PREDICT_EXACT_COUNT):
            wins = wins_per_player.get(self.owner, 0)
            remaining = hand_size - trick_number
            n = p["n"]
            if wins > n or wins + remaining < n:
                self._resolve(False)
            elif is_final_trick:
                self._resolve(wins == n)

        elif kind == TaskKind.WIN_AT_LEAST:
            wins = wins_per_player.get(self.owner, 0)
            remaining = hand_size - trick_number
            n = p["n"]
            if wins >= n:
                self._resolve(True)
            elif wins + remaining < n:
                self._resolve(False)
            elif is_final_trick:
                self._resolve(wins >= n)

        elif kind == TaskKind.WIN_TRICKS_ALL:
            numbers = p["numbers"]
            if trick_number in numbers:
                if winner != self.owner:
                    self._resolve(False)
                elif trick_number == max(numbers):
                    self._resolve(True)

        elif kind == TaskKind.NEVER_WIN_TRICKS:
            numbers = p["numbers"]
            if trick_number in numbers and winner == self.owner:
                self._resolve(False)
            elif trick_number == max(numbers):
                self._resolve(True)

        elif kind == TaskKind.WIN_ONLY_TRICK:
            n = p["n"]
            if trick_number == n:
                if winner != self.owner:
                    self._resolve(False)
            elif winner == self.owner:
                self._resolve(False)
            if not self.resolved and is_final_trick:
                self._resolve(True)

        elif kind in (TaskKind.WIN_EXACT_CARD_COUNT, TaskKind.WIN_AT_LEAST_CARD_COUNT):
            conditions = p["conditions"]
            counts = [sum(1 for c in self._captured if _match_condition(c, cond)) for cond in conditions]
            if kind == TaskKind.WIN_EXACT_CARD_COUNT:
                if any(cur > cond["n"] for cur, cond in zip(counts, conditions)):
                    self._resolve(False)
                elif is_final_trick:
                    self._resolve(all(cur == cond["n"] for cur, cond in zip(counts, conditions)))
            else:
                if all(cur >= cond["n"] for cur, cond in zip(counts, conditions)):
                    self._resolve(True)
                elif is_final_trick:
                    self._resolve(False)

        elif kind == TaskKind.WIN_TRICK_ALL_ABOVE:
            if winner == self.owner:
                values = list(trick_cards.values())
                if all(c.suit != Suit.SUBMARINE and c.rank > p["threshold"] for c in values):
                    self._resolve(True)

        elif kind == TaskKind.WIN_TRICK_ALL_BELOW:
            if winner == self.owner:
                values = list(trick_cards.values())
                if all(c.suit != Suit.SUBMARINE and c.rank < p["threshold"] for c in values):
                    self._resolve(True)

        elif kind in (TaskKind.WIN_TRICK_SUM_BELOW, TaskKind.WIN_TRICK_SUM_IN, TaskKind.WIN_TRICK_SUM_ABOVE):
            if winner == self.owner:
                values = list(trick_cards.values())
                if all(c.suit != Suit.SUBMARINE for c in values):
                    total = sum(c.rank for c in values)
                    if kind == TaskKind.WIN_TRICK_SUM_BELOW and total < p["threshold"]:
                        self._resolve(True)
                    elif kind == TaskKind.WIN_TRICK_SUM_IN and total in p["values"]:
                        self._resolve(True)
                    elif kind == TaskKind.WIN_TRICK_SUM_ABOVE and total > p["threshold"]:
                        self._resolve(True)

        elif kind == TaskKind.WIN_TRICK_EQUAL_COLOR_COUNTS:
            if winner == self.owner:
                a, b = Suit(p["suit_a"]), Suit(p["suit_b"])
                values = list(trick_cards.values())
                ca = sum(1 for c in values if c.suit == a)
                cb = sum(1 for c in values if c.suit == b)
                if ca == cb and ca > 0:
                    self._resolve(True)

        elif kind in (TaskKind.WIN_TRICK_ALL_ODD, TaskKind.WIN_TRICK_ALL_EVEN):
            if winner == self.owner:
                values = list(trick_cards.values())
                parity = 1 if kind == TaskKind.WIN_TRICK_ALL_ODD else 0
                if all(c.rank % 2 == parity for c in values):
                    self._resolve(True)

        elif kind == TaskKind.NEVER_LEAD_WITH_COLOR:
            if leader == self.owner:
                suits = {Suit(s) for s in p["suits"]}
                if trick_cards[self.owner].suit in suits:
                    self._resolve(False)

        elif kind == TaskKind.WIN_CARD_IN_LAST_TRICK:
            if is_final_trick and winner == self.owner and Card.parse(p["card"]) in trick_cards.values():
                self._resolve(True)

        elif kind == TaskKind.PLAY_AND_WIN_WITH:
            if winner == self.owner:
                mine = trick_cards[self.owner]
                play = p["play"]
                plays_ok = (
                    (play.get("submarine") and mine.suit == Suit.SUBMARINE)
                    or (play.get("rank") is not None and mine.suit != Suit.SUBMARINE and mine.rank == play["rank"])
                )
                if plays_ok:
                    other = p["other"]
                    others = [c for seat, c in trick_cards.items() if seat != self.owner]
                    if "card" in other:
                        other_ok = Card.parse(other["card"]) in others
                    else:
                        cands = [c for c in others if c.suit != Suit.SUBMARINE and c.rank == other["rank"]]
                        if other.get("differs_suit"):
                            cands = [c for c in cands if c.suit != mine.suit]
                        other_ok = bool(cands)
                    if other_ok:
                        self._resolve(True)

        elif kind == TaskKind.WIN_N_CONSECUTIVE:
            if self._streak >= p["n"]:
                self._resolve(True)
            elif is_final_trick:
                self._resolve(False)

        elif kind == TaskKind.NEVER_WIN_TWO_CONSECUTIVE:
            if self._streak >= 2:
                self._resolve(False)
            elif is_final_trick:
                self._resolve(True)

        elif kind == TaskKind.WIN_EXACT_COUNT_CONSECUTIVE:
            n = p["n"]
            wins = len(self._owned_trick_numbers)
            remaining = hand_size - trick_number
            if wins > n or wins + remaining < n:
                self._resolve(False)
            elif wins == n:
                nums = self._owned_trick_numbers
                contiguous = (max(nums) - min(nums) + 1) == n
                if not contiguous:
                    self._resolve(False)
                elif is_final_trick:
                    self._resolve(True)
            elif is_final_trick:
                self._resolve(False)

        elif kind in (
            TaskKind.FEWER_THAN_EVERYONE,
            TaskKind.MORE_THAN_EVERYONE,
            TaskKind.MORE_THAN_SUM_OF_OTHERS,
            TaskKind.FEWER_THAN_COMMANDER,
            TaskKind.MORE_THAN_COMMANDER,
            TaskKind.EQUAL_TO_COMMANDER,
        ):
            if is_final_trick:
                mine = wins_per_player.get(self.owner, 0)
                if kind == TaskKind.FEWER_THAN_EVERYONE:
                    others = [wins_per_player.get(i, 0) for i in range(num_players) if i != self.owner]
                    self._resolve(all(mine < w for w in others))
                elif kind == TaskKind.MORE_THAN_EVERYONE:
                    others = [wins_per_player.get(i, 0) for i in range(num_players) if i != self.owner]
                    self._resolve(all(mine > w for w in others))
                elif kind == TaskKind.MORE_THAN_SUM_OF_OTHERS:
                    total_others = sum(wins_per_player.get(i, 0) for i in range(num_players) if i != self.owner)
                    self._resolve(mine > total_others)
                else:
                    cmd = wins_per_player.get(commander, 0)
                    if kind == TaskKind.FEWER_THAN_COMMANDER:
                        self._resolve(mine < cmd)
                    elif kind == TaskKind.MORE_THAN_COMMANDER:
                        self._resolve(mine > cmd)
                    else:
                        self._resolve(mine == cmd)

        elif kind == TaskKind.COMPARE_COLOR_COUNTS:
            if is_final_trick:
                g = sum(1 for c in self._captured if c.suit.value == p["greater"])
                l = sum(1 for c in self._captured if c.suit.value == p["less"])
                self._resolve(g > l)

        elif kind == TaskKind.EQUAL_COLOR_COUNTS_NONZERO:
            if is_final_trick:
                a = sum(1 for c in self._captured if c.suit.value == p["color_a"])
                b = sum(1 for c in self._captured if c.suit.value == p["color_b"])
                self._resolve(a == b and a > 0)

        elif kind == TaskKind.WIN_EACH_COLOR_AT_LEAST_ONE:
            have = {c.suit for c in self._captured if c.suit != Suit.SUBMARINE}
            if len(have) == 4:
                self._resolve(True)
            elif is_final_trick:
                self._resolve(False)

        elif kind == TaskKind.WIN_FULL_COLOR_RUN:
            for suit in COLOR_SUITS:
                if all(Card(suit, r) in self._captured for r in range(1, COLOR_MAX_RANK + 1)):
                    self._resolve(True)
                    break
            else:
                if is_final_trick:
                    self._resolve(False)

    def force_resolve_if_unresolved_at_end(self, wins_per_player: dict[int, int]) -> None:
        if self.resolved:
            return
        if self.kind == TaskKind.WIN_NO_TRICKS:
            self._resolve(wins_per_player.get(self.owner, 0) == 0)
        elif self.kind in (TaskKind.NEVER_WIN_COLOR, TaskKind.NEVER_WIN_COLORS, TaskKind.NEVER_WIN_RANK,
                            TaskKind.NEVER_WIN_RANKS, TaskKind.NEVER_LEAD_WITH_COLOR, TaskKind.NEVER_WIN_TWO_CONSECUTIVE):
            # never triggered a failure across the whole hand -> success
            self._resolve(True)
        else:
            self._resolve(False)  # the trick(s) it depended on already passed without success

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
        if kind == TaskKind.WIN_CARDS:
            return f"{', '.join(p.get('cards', []))} 카드를 모두 획득해야 함"
        if kind == TaskKind.WIN_CARD_EXCLUDE_OTHERS:
            return f"{p.get('card')} 카드를 획득해야 하며, {', '.join(p.get('forbidden', []))} 중 어느 것도 포함된 트릭을 획득하면 안 됨"
        if kind == TaskKind.WIN_TRICK_BY_RANK:
            return f"아무{p.get('rank')}을(를) 내서 그 트릭을 획득해야 함"
        if kind == TaskKind.NEVER_WIN_RANK:
            return f"아무{p.get('rank')} 카드가 포함된 트릭을 획득하면 안 됨"
        if kind == TaskKind.NEVER_WIN_RANKS:
            ranks = ", ".join(f"아무{r}" for r in p.get("ranks", []))
            return f"{ranks} 카드가 포함된 트릭을 획득하면 안 됨"
        if kind == TaskKind.NEVER_WIN_COLOR:
            suit = Suit(p.get("suit"))
            return f"{_SUIT_KO.get(suit, suit.value)} 카드가 포함된 트릭을 획득하면 안 됨"
        if kind == TaskKind.NEVER_WIN_COLORS:
            return f"{_suits_ko(p.get('suits', []))} 카드가 포함된 트릭을 획득하면 안 됨"
        if kind == TaskKind.WIN_TRICK_NUMBER:
            return f"{p.get('n')}번째 트릭을 획득해야 함"
        if kind == TaskKind.WIN_EXACT_COUNT:
            return f"정확히 {p.get('n')}개의 트릭을 획득해야 함"
        if kind == TaskKind.WIN_AT_LEAST:
            return f"최소 {p.get('n')}개의 트릭을 획득해야 함"
        if kind == TaskKind.WIN_NO_TRICKS:
            return "트릭을 하나도 획득하면 안 됨"
        if kind == TaskKind.WIN_FIRST_TRICK:
            return "첫 번째 트릭을 획득해야 함"
        if kind == TaskKind.WIN_LAST_TRICK:
            return "마지막 트릭을 획득해야 함"
        if kind == TaskKind.WIN_TRICKS_ALL:
            nums = ", ".join(str(n) for n in p.get("numbers", []))
            return f"{nums}번째 트릭을 모두 획득해야 함"
        if kind == TaskKind.NEVER_WIN_TRICKS:
            nums = p.get("numbers", [])
            return f"{min(nums)}~{max(nums)}번째 트릭을 하나도 획득하면 안 됨"
        if kind == TaskKind.WIN_ONLY_TRICK:
            return f"오직 {p.get('n')}번째 트릭만 획득해야 함 (다른 트릭은 획득하면 안 됨)"
        if kind in (TaskKind.WIN_EXACT_CARD_COUNT, TaskKind.WIN_AT_LEAST_CARD_COUNT):
            verb = "정확히" if kind == TaskKind.WIN_EXACT_CARD_COUNT else "최소"
            parts = [f"{_condition_ko(c)} {c['n']}장 {verb}" for c in p.get("conditions", [])]
            return " / ".join(parts) + " 획득해야 함"
        if kind == TaskKind.WIN_TRICK_ALL_ABOVE:
            return f"모든 카드값이 {p.get('threshold')}보다 큰 트릭을 획득해야 함 (잠수함 포함 불가)"
        if kind == TaskKind.WIN_TRICK_ALL_BELOW:
            return f"모든 카드값이 {p.get('threshold')}보다 작은 트릭을 획득해야 함 (잠수함 포함 불가)"
        if kind == TaskKind.WIN_TRICK_SUM_BELOW:
            return f"카드값 총합이 {p.get('threshold')}보다 적은 트릭을 획득해야 함 (잠수함 포함 불가)"
        if kind == TaskKind.WIN_TRICK_SUM_IN:
            vals = " 또는 ".join(str(v) for v in p.get("values", []))
            return f"카드값 총합이 {vals}인 트릭을 획득해야 함 (잠수함 포함 불가)"
        if kind == TaskKind.WIN_TRICK_SUM_ABOVE:
            return f"카드값 총합이 {p.get('threshold')}보다 큰 트릭을 획득해야 함 (잠수함 포함 불가)"
        if kind == TaskKind.WIN_TRICK_EQUAL_COLOR_COUNTS:
            a = _SUIT_KO.get(Suit(p.get("suit_a")), p.get("suit_a"))
            b = _SUIT_KO.get(Suit(p.get("suit_b")), p.get("suit_b"))
            return f"{a}색과 {b}색 카드가 같은 장수만큼(0장 제외) 나온 트릭을 획득해야 함"
        if kind == TaskKind.WIN_TRICK_ALL_ODD:
            return "오직 홀수 카드로만 구성된 트릭을 획득해야 함"
        if kind == TaskKind.WIN_TRICK_ALL_EVEN:
            return "오직 짝수 카드로만 구성된 트릭을 획득해야 함"
        if kind == TaskKind.NEVER_LEAD_WITH_COLOR:
            return f"트릭을 {_suits_ko(p.get('suits', []))} 카드로 시작하면 안 됨"
        if kind == TaskKind.WIN_CARD_IN_LAST_TRICK:
            return f"이번 게임 마지막 트릭에서 {p.get('card')} 카드를 획득해야 함"
        if kind == TaskKind.PLAY_AND_WIN_WITH:
            play = p.get("play", {})
            play_text = "잠수함을" if play.get("submarine") else f"{play.get('rank')}을(를)"
            other = p.get("other", {})
            other_text = other.get("card") or (f"다른 {other['rank']}" if other.get("differs_suit") else str(other.get("rank")))
            return f"{play_text} 내서 {other_text} 따기"
        if kind == TaskKind.WIN_N_CONSECUTIVE:
            return f"{p.get('n')} 트릭 연속으로 획득해야 함"
        if kind == TaskKind.NEVER_WIN_TWO_CONSECUTIVE:
            return "절대 연속으로 두 트릭을 획득하면 안 됨"
        if kind == TaskKind.WIN_EXACT_COUNT_CONSECUTIVE:
            return f"정확히 {p.get('n')}개의 트릭을 (연속으로) 획득해야 함"
        if kind == TaskKind.FEWER_THAN_EVERYONE:
            return "그 누구보다도 트릭을 적게 획득해야 함"
        if kind == TaskKind.MORE_THAN_EVERYONE:
            return "그 누구보다도 트릭을 많이 획득해야 함"
        if kind == TaskKind.MORE_THAN_SUM_OF_OTHERS:
            return "다른 모든 사람들이 획득한 트릭 총 개수보다 더 많은 트릭을 획득해야 함"
        if kind == TaskKind.PREDICT_EXACT_COUNT:
            visibility = "공개" if p.get("public") else "비공개"
            n = p.get("n")
            n_text = f"{n}개" if n is not None else "?"
            return f"예측({visibility}): 정확히 트릭 {n_text}를 획득해야 함"
        if kind == TaskKind.FEWER_THAN_COMMANDER:
            return "사령관보다 적은 수의 트릭을 획득해야 함"
        if kind == TaskKind.MORE_THAN_COMMANDER:
            return "사령관보다 많은 수의 트릭을 획득해야 함"
        if kind == TaskKind.EQUAL_TO_COMMANDER:
            return "사령관과 같은 수의 트릭을 획득해야 함"
        if kind == TaskKind.COMPARE_COLOR_COUNTS:
            g = _SUIT_KO.get(Suit(p.get("greater")), p.get("greater"))
            l = _SUIT_KO.get(Suit(p.get("less")), p.get("less"))
            return f"{g}색 카드를 {l}색 카드보다 많이 획득해야 함"
        if kind == TaskKind.EQUAL_COLOR_COUNTS_NONZERO:
            a = _SUIT_KO.get(Suit(p.get("color_a")), p.get("color_a"))
            b = _SUIT_KO.get(Suit(p.get("color_b")), p.get("color_b"))
            return f"{a}색과 {b}색 카드를 같은 장수만큼(0장 제외) 획득해야 함"
        if kind == TaskKind.WIN_EACH_COLOR_AT_LEAST_ONE:
            return "4가지 색깔 카드를 적어도 1장씩 획득해야 함"
        if kind == TaskKind.WIN_FULL_COLOR_RUN:
            return "4가지 색깔 중 적어도 한 색깔의 모든 카드를 다 획득해야 함"
        raise ValueError(f"Unknown task kind: {kind}")

    def describe_assigned(self) -> str:
        """Task text with the owning player prefixed -- used once claimed."""
        text = f"P{self.owner}: {self.describe()}"
        if self.order_index is not None:
            text += f" [순서 {self.order_index}]"
        return text

    def is_hidden_from(self, viewer: int | None) -> bool:
        """True if this task's exact wording must stay hidden from `viewer`
        -- currently only the private 예측(비공개) prediction: the number
        is only ever known to its owner, not even the rest of the crew."""
        return (
            self.kind == TaskKind.PREDICT_EXACT_COUNT
            and not self.params.get("public")
            and viewer != self.owner
        )

    def describe_for(self, viewer: int | None) -> str:
        """Like describe(), but redacts the predicted number for anyone
        but the owner if the prediction was made 비공개 (private)."""
        if self.is_hidden_from(viewer):
            return "예측(비공개): 정확히 트릭 ?개를 획득해야 함 (본인만 확인 가능)"
        return self.describe()

    def describe_assigned_for(self, viewer: int | None) -> str:
        text = f"P{self.owner}: {self.describe_for(viewer)}"
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
