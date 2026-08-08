from boardy.games.deep_sea_crew.cards import Card, Suit
from boardy.games.deep_sea_crew.tasks import Task, TaskKind, missions_completed


def test_win_card_success():
    t = Task(id="t1", owner=0, kind=TaskKind.WIN_CARD, params={"card": "B7"})
    t.check_after_trick(1, {0: Card(Suit.BLUE, 7), 1: Card(Suit.BLUE, 3)}, winner=0,
                         wins_per_player={0: 1}, is_final_trick=False)
    assert t.resolved and t.success


def test_win_card_wrong_winner_fails():
    t = Task(id="t1", owner=1, kind=TaskKind.WIN_CARD, params={"card": "B7"})
    t.check_after_trick(1, {0: Card(Suit.BLUE, 7), 1: Card(Suit.BLUE, 3)}, winner=0,
                         wins_per_player={0: 1}, is_final_trick=False)
    assert t.resolved and not t.success


def test_never_win_color_fails_immediately():
    t = Task(id="t1", owner=0, kind=TaskKind.NEVER_WIN_COLOR, params={"suit": "blue"})
    t.check_after_trick(1, {0: Card(Suit.BLUE, 7), 1: Card(Suit.GREEN, 3)}, winner=0,
                         wins_per_player={0: 1}, is_final_trick=False)
    assert t.resolved and not t.success


def test_never_win_color_succeeds_if_never_violated():
    t = Task(id="t1", owner=0, kind=TaskKind.NEVER_WIN_COLOR, params={"suit": "blue"})
    # a full hand where the owner never wins a trick containing blue
    t.check_after_trick(1, {0: Card(Suit.GREEN, 3), 1: Card(Suit.GREEN, 5)}, winner=1,
                         wins_per_player={1: 1}, is_final_trick=True)
    t.force_resolve_if_unresolved_at_end({1: 1})
    assert t.resolved and t.success


def test_win_no_tricks_succeeds_if_never_violated():
    t = Task(id="t1", owner=0, kind=TaskKind.WIN_NO_TRICKS, params={})
    t.check_after_trick(1, {0: Card(Suit.GREEN, 3), 1: Card(Suit.GREEN, 5)}, winner=1,
                         wins_per_player={1: 1}, is_final_trick=True)
    assert t.resolved and t.success  # already resolved by check_after_trick's own final-trick branch


def test_missions_completed_none_while_pending():
    t1 = Task(id="t1", owner=0, kind=TaskKind.WIN_NO_TRICKS, params={})
    assert missions_completed([t1]) is None


def test_missions_completed_false_on_any_failure():
    t1 = Task(id="t1", owner=0, kind=TaskKind.WIN_CARD, params={"card": "B7"})
    t1.resolved, t1.success = True, False
    t2 = Task(id="t2", owner=1, kind=TaskKind.WIN_NO_TRICKS, params={})
    assert missions_completed([t1, t2]) is False
