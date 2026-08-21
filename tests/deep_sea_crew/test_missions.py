import random

from boardy.games.deep_sea_crew.missions import difficulty_for, draw_tasks
from boardy.games.deep_sea_crew.tasks import TaskKind


def test_difficulty_for_picks_column_by_player_count():
    tmpl = {"difficulty": {"3": 1, "4": 2, "5": 3}}
    assert difficulty_for(tmpl, 3) == 1
    assert difficulty_for(tmpl, 4) == 2
    assert difficulty_for(tmpl, 5) == 3


def test_difficulty_for_falls_back_to_3p_below_and_5p_above():
    tmpl = {"difficulty": {"3": 1, "4": 2, "5": 3}}
    assert difficulty_for(tmpl, 2) == 1
    assert difficulty_for(tmpl, 6) == 3


def test_draw_tasks_resolves_last_token_to_hand_size():
    rng = random.Random(0)
    tasks = draw_tasks(num_players=4, hand_size=9, difficulty_budget=200, rng=rng)
    assert tasks  # a large budget should pull in essentially every template
    for t in tasks:
        if t.kind == TaskKind.WIN_ONLY_TRICK:
            assert t.params["n"] != "LAST"
        if t.kind in (TaskKind.WIN_TRICKS_ALL, TaskKind.NEVER_WIN_TRICKS):
            assert "LAST" not in t.params["numbers"]


def test_draw_tasks_resolves_sum_threshold_by_player_count():
    rng = random.Random(0)
    tasks = draw_tasks(num_players=3, hand_size=13, difficulty_budget=300, rng=rng)
    below = [t for t in tasks if t.kind == TaskKind.WIN_TRICK_SUM_BELOW]
    assert below and all(t.params["threshold"] == 8 for t in below)

    rng = random.Random(0)
    tasks5 = draw_tasks(num_players=5, hand_size=8, difficulty_budget=300, rng=rng)
    below5 = [t for t in tasks5 if t.kind == TaskKind.WIN_TRICK_SUM_BELOW]
    assert below5 and all(t.params["threshold"] == 16 for t in below5)


def test_draw_tasks_stops_near_budget():
    rng = random.Random(1)
    tasks = draw_tasks(num_players=4, hand_size=10, difficulty_budget=8, rng=rng)
    total = sum(t.difficulty for t in tasks)
    # the loop only stops once total >= budget, so it may overshoot by the
    # last template's difficulty but should never stop far short of it
    assert total >= 8
