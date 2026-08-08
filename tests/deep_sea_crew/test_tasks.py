from boardy.games.deep_sea_crew.cards import Card, Suit
from boardy.games.deep_sea_crew.tasks import Task, TaskKind, missions_completed


def test_describe_does_not_choke_on_params_missing_from_other_kinds():
    # describe() must not eagerly evaluate every kind's formatting (e.g.
    # Suit(params['suit']) for a WIN_CARD task, which has no 'suit' param)
    for kind, params in [
        (TaskKind.WIN_CARD, {"card": "B7"}),
        (TaskKind.WIN_TRICK_NUMBER, {"n": 3}),
        (TaskKind.WIN_EXACT_COUNT, {"n": 2}),
        (TaskKind.WIN_AT_LEAST, {"n": 2}),
        (TaskKind.WIN_NO_TRICKS, {}),
        (TaskKind.NEVER_WIN_COLOR, {"suit": "blue"}),
        (TaskKind.WIN_FIRST_TRICK, {}),
        (TaskKind.WIN_LAST_TRICK, {}),
    ]:
        t = Task(id="t1", kind=kind, params=params)
        assert isinstance(t.describe(), str) and t.describe()
        t.owner = 0
        assert isinstance(t.describe_assigned(), str) and t.describe_assigned()


def test_win_card_success():
    t = Task(id="t1", owner=0, kind=TaskKind.WIN_CARD, params={"card": "B7"})
    t.check_after_trick(1, {0: Card(Suit.BLUE, 7), 1: Card(Suit.BLUE, 3)}, winner=0,
                         wins_per_player={0: 1}, is_final_trick=False, hand_size=2)
    assert t.resolved and t.success


def test_win_card_wrong_winner_fails():
    t = Task(id="t1", owner=1, kind=TaskKind.WIN_CARD, params={"card": "B7"})
    t.check_after_trick(1, {0: Card(Suit.BLUE, 7), 1: Card(Suit.BLUE, 3)}, winner=0,
                         wins_per_player={0: 1}, is_final_trick=False, hand_size=2)
    assert t.resolved and not t.success


def test_never_win_color_fails_immediately():
    t = Task(id="t1", owner=0, kind=TaskKind.NEVER_WIN_COLOR, params={"suit": "blue"})
    t.check_after_trick(1, {0: Card(Suit.BLUE, 7), 1: Card(Suit.GREEN, 3)}, winner=0,
                         wins_per_player={0: 1}, is_final_trick=False, hand_size=2)
    assert t.resolved and not t.success


def test_never_win_color_succeeds_if_never_violated():
    t = Task(id="t1", owner=0, kind=TaskKind.NEVER_WIN_COLOR, params={"suit": "blue"})
    # a full hand where the owner never wins a trick containing blue
    t.check_after_trick(1, {0: Card(Suit.GREEN, 3), 1: Card(Suit.GREEN, 5)}, winner=1,
                         wins_per_player={1: 1}, is_final_trick=True, hand_size=1)
    t.force_resolve_if_unresolved_at_end({1: 1})
    assert t.resolved and t.success


def test_win_no_tricks_succeeds_if_never_violated():
    t = Task(id="t1", owner=0, kind=TaskKind.WIN_NO_TRICKS, params={})
    t.check_after_trick(1, {0: Card(Suit.GREEN, 3), 1: Card(Suit.GREEN, 5)}, winner=1,
                         wins_per_player={1: 1}, is_final_trick=True, hand_size=1)
    assert t.resolved and t.success  # already resolved by check_after_trick's own final-trick branch


def test_win_exact_count_fails_early_once_exceeded():
    t = Task(id="t1", owner=0, kind=TaskKind.WIN_EXACT_COUNT, params={"n": 2})
    # owner already has 3 tricks after this one -- exceeds n=2, well before the hand ends
    t.check_after_trick(3, {0: Card(Suit.GREEN, 3), 1: Card(Suit.GREEN, 5)}, winner=0,
                         wins_per_player={0: 3}, is_final_trick=False, hand_size=10)
    assert t.resolved and not t.success


def test_win_exact_count_fails_early_when_unreachable():
    t = Task(id="t1", owner=0, kind=TaskKind.WIN_EXACT_COUNT, params={"n": 5})
    # owner has 1 trick with only 3 tricks left in the hand (1+3=4 < 5) -- can never reach 5
    t.check_after_trick(7, {0: Card(Suit.GREEN, 3), 1: Card(Suit.GREEN, 5)}, winner=1,
                         wins_per_player={0: 1, 1: 6}, is_final_trick=False, hand_size=10)
    assert t.resolved and not t.success


def test_win_exact_count_stays_pending_while_still_reachable():
    t = Task(id="t1", owner=0, kind=TaskKind.WIN_EXACT_COUNT, params={"n": 5})
    # owner has 2 tricks with 6 remaining (2+6=8 >= 5) and hasn't exceeded 5 -- still possible
    t.check_after_trick(4, {0: Card(Suit.GREEN, 3), 1: Card(Suit.GREEN, 5)}, winner=1,
                         wins_per_player={0: 2, 1: 2}, is_final_trick=False, hand_size=10)
    assert not t.resolved


def test_win_exact_count_succeeds_at_final_trick():
    t = Task(id="t1", owner=0, kind=TaskKind.WIN_EXACT_COUNT, params={"n": 2})
    t.check_after_trick(10, {0: Card(Suit.GREEN, 3), 1: Card(Suit.GREEN, 5)}, winner=1,
                         wins_per_player={0: 2, 1: 8}, is_final_trick=True, hand_size=10)
    assert t.resolved and t.success


def test_win_at_least_fails_early_when_unreachable():
    t = Task(id="t1", owner=0, kind=TaskKind.WIN_AT_LEAST, params={"n": 5})
    # owner has 1 trick with only 3 tricks left (1+3=4 < 5) -- can never reach at least 5
    t.check_after_trick(7, {0: Card(Suit.GREEN, 3), 1: Card(Suit.GREEN, 5)}, winner=1,
                         wins_per_player={0: 1, 1: 6}, is_final_trick=False, hand_size=10)
    assert t.resolved and not t.success


def test_win_at_least_succeeds_once_guaranteed_reachable_but_only_resolves_at_end():
    t = Task(id="t1", owner=0, kind=TaskKind.WIN_AT_LEAST, params={"n": 2})
    # owner already has 2, still not the final trick -- stays pending (only fails early,
    # success is still only confirmed at the final trick, same as other count-based tasks)
    t.check_after_trick(4, {0: Card(Suit.GREEN, 3), 1: Card(Suit.GREEN, 5)}, winner=0,
                         wins_per_player={0: 2}, is_final_trick=False, hand_size=10)
    assert not t.resolved


def test_missions_completed_none_while_pending():
    t1 = Task(id="t1", owner=0, kind=TaskKind.WIN_NO_TRICKS, params={})
    assert missions_completed([t1]) is None


def test_missions_completed_false_on_any_failure():
    t1 = Task(id="t1", owner=0, kind=TaskKind.WIN_CARD, params={"card": "B7"})
    t1.resolved, t1.success = True, False
    t2 = Task(id="t2", owner=1, kind=TaskKind.WIN_NO_TRICKS, params={})
    assert missions_completed([t1, t2]) is False
