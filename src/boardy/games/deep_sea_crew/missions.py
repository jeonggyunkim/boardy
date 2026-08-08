"""Draws a mission's worth of task cards from data/tasks.json templates.

These come back *unassigned* (owner=None) -- see engine.py's task-draft
phase for how they get claimed by players. See docs/PLAN.md — the
templates are placeholders, not the real 96 cards.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from .cards import Card, Suit
from .tasks import Task, TaskKind

_DATA_PATH = Path(__file__).resolve().parent.parent.parent.parent.parent / "data" / "deep_sea_crew" / "tasks.json"


def load_templates() -> list[dict]:
    with open(_DATA_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data["templates"]


def _resolve_card_param(token: str, taken: set[Card], rng: random.Random) -> Card:
    color_suits = [Suit.YELLOW, Suit.PINK, Suit.GREEN, Suit.BLUE]
    if token == "SUBMARINE_4":
        return Card(Suit.SUBMARINE, 4)
    band = {"RANDOM_LOW": (1, 3), "RANDOM_MID": (4, 6), "RANDOM_HIGH": (7, 9)}[token]
    for _ in range(200):
        suit = rng.choice(color_suits)
        rank = rng.randint(*band)
        card = Card(suit, rank)
        if card not in taken:
            taken.add(card)
            return card
    raise RuntimeError(f"Could not find unused card for token {token}")


def draw_tasks(
    num_players: int,
    hand_size: int,
    difficulty_budget: int,
    hands: list[list[Card]] | None = None,
    rng: random.Random | None = None,
) -> list[Task]:
    """Pick templates whose difficulty sums close to difficulty_budget,
    instantiate any random params, and return them unassigned (owner=None)
    -- players draft them one at a time (see GameState's task-draft phase),
    not a random assignment.

    If `hands` is given, win_card tasks are only assigned cards that were
    actually dealt to someone (so the task is achievable).
    """
    rng = rng or random.Random()
    templates = load_templates()
    rng.shuffle(templates)

    chosen: list[dict] = []
    total = 0
    for t in templates:
        if total >= difficulty_budget:
            break
        chosen.append(t)
        total += t["difficulty"]

    taken_cards: set[Card] = set()
    dealt_cards = [c for h in (hands or []) for c in h]
    tasks: list[Task] = []
    for i, tmpl in enumerate(chosen):
        params = dict(tmpl["params"])
        kind = TaskKind(tmpl["kind"])
        if kind == TaskKind.WIN_CARD:
            token = params["card"]
            if dealt_cards:
                candidates = [c for c in dealt_cards if c not in taken_cards]
                card = rng.choice(candidates) if candidates else _resolve_card_param(
                    token, taken_cards, rng
                )
                taken_cards.add(card)
            else:
                card = _resolve_card_param(token, taken_cards, rng)
            params["card"] = str(card)
        elif kind == TaskKind.WIN_TRICK_NUMBER and params.get("n") == "LAST":
            params["n"] = hand_size
        tasks.append(Task(id=f"task-{i}", kind=kind, params=params, difficulty=tmpl["difficulty"]))
    return tasks
