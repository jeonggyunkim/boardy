"""Minimal Elo rating helpers for tracking relative strength across
training checkpoints. Not calibrated to any external (e.g. human) Elo
pool -- these ratings are only meaningful relative to each other within
this project's own checkpoint history."""

from __future__ import annotations

DEFAULT_K = 32.0


def expected_score(rating_a: float, rating_b: float) -> float:
    """Probability `a` scores against `b` (win=1, draw=0.5, loss=0)."""
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))


def update_elo(
    rating_a: float,
    rating_b: float,
    score_a: float,
    k: float = DEFAULT_K,
) -> tuple[float, float]:
    """Update both ratings from a single match result. `score_a` is a's
    actual score in [0, 1] (e.g. wins_a/(wins_a+wins_b+draws) style, or
    just 1/0.5/0 for a single game)."""
    exp_a = expected_score(rating_a, rating_b)
    new_a = rating_a + k * (score_a - exp_a)
    new_b = rating_b + k * ((1.0 - score_a) - (1.0 - exp_a))
    return new_a, new_b


def match_score(wins_a: int, wins_b: int, draws: int) -> float:
    """Convert an N-game match tally into a single score in [0, 1] for `a`."""
    total = wins_a + wins_b + draws
    if total == 0:
        return 0.5
    return (wins_a + 0.5 * draws) / total
