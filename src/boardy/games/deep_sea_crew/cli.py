"""Interactive CLI: human plays seat 0 against RandomPlayer bots."""

from __future__ import annotations

import argparse
import io
import random
import sys

from .cards import Card
from .engine import GameState, new_game
from .players import Player, RandomPlayer


def render_hand(hand: list[Card]) -> str:
    return " ".join(str(c) for c in hand)


def render_trick(state: GameState) -> str:
    if not state.trick_in_progress:
        return "(no cards played yet this trick)"
    order = state._play_order  # noqa: SLF001 (CLI is allowed to peek for display)
    parts = [f"P{p}:{state.trick_in_progress[p]}" for p in order if p in state.trick_in_progress]
    return " ".join(parts)


class HumanPlayer(Player):
    def __init__(self, name: str = "you") -> None:
        self.name = name

    def choose_card(self, state: GameState, seat: int) -> Card:
        hand = state.hands[seat]
        legal = state.legal_cards_for(seat)
        print(f"\nYour hand: {render_hand(hand)}")
        print(f"Trick so far: {render_trick(state)}")
        print(f"Legal moves: {render_hand(legal)}")
        while True:
            raw = input("Play a card (e.g. Y7): ").strip()
            try:
                card = Card.parse(raw)
            except ValueError:
                print("Could not parse that card code, try again.")
                continue
            if card not in legal:
                print("That card isn't a legal move right now.")
                continue
            return card

    def choose_task(self, state: GameState, seat: int) -> str:
        print("\nAvailable tasks:")
        for t in state.available_tasks:
            print(f"  [{t.id}] (difficulty {t.difficulty}) {t.describe()}")
        valid_ids = {t.id for t in state.available_tasks}
        while True:
            raw = input("Draft which task (enter its id, e.g. task-0): ").strip()
            if raw not in valid_ids:
                print("Not an available task id, try again.")
                continue
            return raw


def print_tasks(state: GameState) -> None:
    print("\nMission tasks:")
    for t in state.tasks:
        status = "PENDING" if not t.resolved else ("OK" if t.success else "FAILED")
        print(f"  [{status}] {t.describe_assigned()}")


def run(num_players: int, difficulty: int, seed: int | None) -> None:
    state = new_game(num_players, difficulty_budget=difficulty, seed=seed)
    players: list[Player] = [HumanPlayer()] + [
        RandomPlayer(name=f"bot{i}", rng=random.Random((seed or 0) + i))
        for i in range(1, num_players)
    ]

    print("=== Deep Sea Crew (placeholder ruleset - see docs/PLAN.md) ===")

    print(f"\n--- Task draft (starting with the commander, P{state.current_leader}) ---")
    while state.phase == "task_draft":
        seat = state.player_to_act
        player = players[seat]
        task_id = player.choose_task(state, seat)
        task = state.draft_task(seat, task_id)
        print(f"P{seat} ({player.name}) drafts [{task.id}]: {task.describe()}")

    print_tasks(state)

    while state.outcome is None:
        # The CLI doesn't have interactive comm/ready-up UI (communication
        # was never supported here even before this phase existed) --
        # auto-confirm everyone ready so play proceeds the same as before.
        state.auto_ready_up()
        seat = state.player_to_act
        if seat is None:
            break
        player = players[seat]
        card = player.choose_card(state, seat)
        record = state.play_card(seat, card)
        if not isinstance(player, HumanPlayer):
            print(f"P{seat} ({player.name}) plays {card}")
        if record is not None:
            print(f"\n--- Trick {record.number} complete: {render_trick_record(record)} ---")
            print(f"Winner: P{record.winner}")
            print_tasks(state)

    print("\n=== GAME OVER ===")
    print("SUCCESS! The crew completed the mission." if state.outcome else "FAILED.")


def render_trick_record(record) -> str:
    order = sorted(record.cards, key=lambda p: (p - record.leader) % 100)
    return " ".join(f"P{p}:{record.cards[p]}" for p in order)


def main() -> None:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    parser = argparse.ArgumentParser(description="Play Deep Sea Crew in the terminal.")
    parser.add_argument("--players", type=int, default=3)
    parser.add_argument("--difficulty", type=int, default=8)
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()
    run(args.players, args.difficulty, args.seed)


if __name__ == "__main__":
    main()
