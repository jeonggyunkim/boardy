"""Draws a mission's worth of task cards from data/tasks.json templates.

These come back *unassigned* (owner=None) -- see engine.py's task-draft
phase for how they get claimed by players.

Each of the 96 real task cards prints three difficulty numbers (3/4/5
players), stored as {"3": x, "4": y, "5": z} in the template. The physical
game has no printed number for 2 players, so we fall back to the 3-player
value; there's no way to verify this against the real rulebook, but it's
the closest available number.

A few kinds need a player-count-dependent value resolved once at draw
time rather than every check: WIN_TRICK_SUM_BELOW/ABOVE store their
threshold the same {"3":.., "4":.., "5":..} way. Trick-number params can
use the literal string "LAST", resolved here to `hand_size`.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from .tasks import Task, TaskKind

_DATA_PATH = Path(__file__).resolve().parent.parent.parent.parent.parent / "data" / "deep_sea_crew" / "tasks.json"


def load_templates() -> list[dict]:
    with open(_DATA_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data["templates"]


def _for_player_count(value: dict, num_players: int) -> int:
    key = str(min(max(num_players, 3), 5))
    return value[key]


def difficulty_for(template: dict, num_players: int) -> int:
    return _for_player_count(template["difficulty"], num_players)


def _resolve_trick_number(n, hand_size: int) -> int:
    return hand_size if n == "LAST" else n


def _resolve_params(kind: TaskKind, params: dict, num_players: int, hand_size: int) -> dict:
    params = dict(params)
    if kind == TaskKind.WIN_TRICK_NUMBER:
        params["n"] = _resolve_trick_number(params["n"], hand_size)
    elif kind in (TaskKind.WIN_TRICKS_ALL, TaskKind.NEVER_WIN_TRICKS):
        params["numbers"] = [_resolve_trick_number(n, hand_size) for n in params["numbers"]]
    elif kind == TaskKind.WIN_ONLY_TRICK:
        params["n"] = _resolve_trick_number(params["n"], hand_size)
    elif kind in (TaskKind.WIN_TRICK_SUM_BELOW, TaskKind.WIN_TRICK_SUM_ABOVE):
        params["threshold"] = _for_player_count(params["threshold"], num_players)
    return params


def draw_tasks(
    num_players: int,
    hand_size: int,
    difficulty_budget: int,
    hands: list[list] | None = None,
    rng: random.Random | None = None,
) -> list[Task]:
    """Pick templates whose difficulty (for this player count) sums close
    to difficulty_budget, resolve any player-count- or hand-size-dependent
    params, and return them unassigned (owner=None) -- players draft them
    one at a time (see GameState's task-draft phase), not a random
    assignment.
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
        total += difficulty_for(t, num_players)

    tasks: list[Task] = []
    for i, tmpl in enumerate(chosen):
        kind = TaskKind(tmpl["kind"])
        params = _resolve_params(kind, tmpl["params"], num_players, hand_size)
        tasks.append(Task(id=f"task-{i}", kind=kind, params=params, difficulty=difficulty_for(tmpl, num_players)))
    return tasks
