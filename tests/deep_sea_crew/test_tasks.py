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


def test_win_at_least_succeeds_immediately_once_reached():
    t = Task(id="t1", owner=0, kind=TaskKind.WIN_AT_LEAST, params={"n": 2})
    # owner already has 2 -- unlike exact-count, winning more tricks later
    # can't un-succeed "at least 2", so this resolves right away rather
    # than waiting for the final trick
    t.check_after_trick(4, {0: Card(Suit.GREEN, 3), 1: Card(Suit.GREEN, 5)}, winner=0,
                         wins_per_player={0: 2}, is_final_trick=False, hand_size=10)
    assert t.resolved and t.success


def test_missions_completed_none_while_pending():
    t1 = Task(id="t1", owner=0, kind=TaskKind.WIN_NO_TRICKS, params={})
    assert missions_completed([t1]) is None


def test_missions_completed_false_on_any_failure():
    t1 = Task(id="t1", owner=0, kind=TaskKind.WIN_CARD, params={"card": "B7"})
    t1.resolved, t1.success = True, False
    t2 = Task(id="t2", owner=1, kind=TaskKind.WIN_NO_TRICKS, params={})
    assert missions_completed([t1, t2]) is False


def test_win_cards_needs_all_across_separate_tricks():
    t = Task(id="t1", owner=0, kind=TaskKind.WIN_CARDS, params={"cards": ["G3", "B5"]})
    t.check_after_trick(1, {0: Card(Suit.GREEN, 3), 1: Card(Suit.GREEN, 1)}, winner=0,
                         wins_per_player={0: 1}, is_final_trick=False, hand_size=3)
    assert not t.resolved
    t.check_after_trick(2, {0: Card(Suit.BLUE, 5), 1: Card(Suit.BLUE, 2)}, winner=0,
                         wins_per_player={0: 2}, is_final_trick=False, hand_size=3)
    assert t.resolved and t.success


def test_win_cards_fails_if_someone_else_wins_one_of_them():
    t = Task(id="t1", owner=0, kind=TaskKind.WIN_CARDS, params={"cards": ["G3", "B5"]})
    t.check_after_trick(1, {0: Card(Suit.GREEN, 1), 1: Card(Suit.GREEN, 3)}, winner=1,
                         wins_per_player={1: 1}, is_final_trick=False, hand_size=3)
    assert t.resolved and not t.success


def test_win_card_exclude_others_fails_on_forbidden_submarine():
    t = Task(id="t1", owner=0, kind=TaskKind.WIN_CARD_EXCLUDE_OTHERS,
              params={"card": "S1", "forbidden": ["S2", "S3", "S4"]})
    t.check_after_trick(1, {0: Card(Suit.SUBMARINE, 2), 1: Card(Suit.BLUE, 3)}, winner=0,
                         wins_per_player={0: 1}, is_final_trick=False, hand_size=3)
    assert t.resolved and not t.success


def test_win_card_exclude_others_succeeds_on_target_alone():
    t = Task(id="t1", owner=0, kind=TaskKind.WIN_CARD_EXCLUDE_OTHERS,
              params={"card": "S1", "forbidden": ["S2", "S3", "S4"]})
    t.check_after_trick(1, {0: Card(Suit.SUBMARINE, 1), 1: Card(Suit.BLUE, 3)}, winner=0,
                         wins_per_player={0: 1}, is_final_trick=False, hand_size=3)
    assert t.resolved and t.success


def test_win_trick_by_rank_requires_owner_to_have_played_that_rank():
    t = Task(id="t1", owner=0, kind=TaskKind.WIN_TRICK_BY_RANK, params={"rank": 6})
    t.check_after_trick(1, {0: Card(Suit.BLUE, 6), 1: Card(Suit.BLUE, 2)}, winner=0,
                         wins_per_player={0: 1}, is_final_trick=False, hand_size=2)
    assert t.resolved and t.success


def test_win_trick_by_rank_fails_if_won_with_different_rank():
    t = Task(id="t1", owner=0, kind=TaskKind.WIN_TRICK_BY_RANK, params={"rank": 6})
    t.check_after_trick(1, {0: Card(Suit.BLUE, 7), 1: Card(Suit.BLUE, 2)}, winner=0,
                         wins_per_player={0: 1}, is_final_trick=True, hand_size=1)
    t.force_resolve_if_unresolved_at_end({0: 1})
    assert t.resolved and not t.success


def test_never_win_rank_ignores_submarine_of_same_number():
    t = Task(id="t1", owner=0, kind=TaskKind.NEVER_WIN_RANK, params={"rank": 3})
    t.check_after_trick(1, {0: Card(Suit.SUBMARINE, 3), 1: Card(Suit.GREEN, 1)}, winner=0,
                         wins_per_player={0: 1}, is_final_trick=True, hand_size=1)
    assert not t.resolved
    t.force_resolve_if_unresolved_at_end({0: 1})
    assert t.success


def test_win_exact_card_count_multi_condition():
    t = Task(id="t1", owner=0, kind=TaskKind.WIN_EXACT_CARD_COUNT,
              params={"conditions": [{"suit": "pink", "n": 1}, {"suit": "green", "n": 1}]})
    t.check_after_trick(1, {0: Card(Suit.PINK, 4), 1: Card(Suit.GREEN, 2)}, winner=0,
                         wins_per_player={0: 1}, is_final_trick=True, hand_size=1)
    assert t.resolved and t.success


def test_win_exact_card_count_fails_when_a_condition_exceeded():
    t = Task(id="t1", owner=0, kind=TaskKind.WIN_EXACT_CARD_COUNT,
              params={"conditions": [{"suit": "blue", "n": 1}]})
    t.check_after_trick(1, {0: Card(Suit.BLUE, 4), 1: Card(Suit.BLUE, 2)}, winner=0,
                         wins_per_player={0: 1}, is_final_trick=False, hand_size=2)
    assert t.resolved and not t.success


def test_win_trick_sum_below_excludes_submarine_tricks():
    t = Task(id="t1", owner=0, kind=TaskKind.WIN_TRICK_SUM_BELOW, params={"threshold": 8})
    t.check_after_trick(1, {0: Card(Suit.SUBMARINE, 1), 1: Card(Suit.GREEN, 2)}, winner=0,
                         wins_per_player={0: 1}, is_final_trick=False, hand_size=2)
    assert not t.resolved
    t.check_after_trick(2, {0: Card(Suit.GREEN, 2), 1: Card(Suit.GREEN, 3)}, winner=0,
                         wins_per_player={0: 2}, is_final_trick=True, hand_size=2)
    assert t.resolved and t.success


def test_win_only_trick_fails_if_another_trick_is_also_won():
    t = Task(id="t1", owner=0, kind=TaskKind.WIN_ONLY_TRICK, params={"n": 1})
    t.check_after_trick(1, {0: Card(Suit.GREEN, 5), 1: Card(Suit.GREEN, 2)}, winner=0,
                         wins_per_player={0: 1}, is_final_trick=False, hand_size=2)
    assert not t.resolved
    t.check_after_trick(2, {0: Card(Suit.GREEN, 5), 1: Card(Suit.GREEN, 2)}, winner=0,
                         wins_per_player={0: 2}, is_final_trick=True, hand_size=2)
    assert t.resolved and not t.success


def test_win_only_trick_succeeds_when_no_others_won():
    t = Task(id="t1", owner=0, kind=TaskKind.WIN_ONLY_TRICK, params={"n": 1})
    t.check_after_trick(1, {0: Card(Suit.GREEN, 5), 1: Card(Suit.GREEN, 2)}, winner=0,
                         wins_per_player={0: 1}, is_final_trick=False, hand_size=2)
    t.check_after_trick(2, {0: Card(Suit.GREEN, 1), 1: Card(Suit.GREEN, 2)}, winner=1,
                         wins_per_player={0: 1, 1: 1}, is_final_trick=True, hand_size=2)
    assert t.resolved and t.success


def test_win_n_consecutive_resolves_as_soon_as_streak_reached():
    t = Task(id="t1", owner=0, kind=TaskKind.WIN_N_CONSECUTIVE, params={"n": 2})
    t.check_after_trick(1, {0: Card(Suit.GREEN, 5)}, winner=0, wins_per_player={0: 1},
                         is_final_trick=False, hand_size=5)
    assert not t.resolved
    t.check_after_trick(2, {0: Card(Suit.GREEN, 5)}, winner=0, wins_per_player={0: 2},
                         is_final_trick=False, hand_size=5)
    assert t.resolved and t.success


def test_win_n_consecutive_streak_resets_after_a_loss():
    t = Task(id="t1", owner=0, kind=TaskKind.WIN_N_CONSECUTIVE, params={"n": 2})
    t.check_after_trick(1, {0: Card(Suit.GREEN, 5), 1: Card(Suit.GREEN, 9)}, winner=0,
                         wins_per_player={0: 1}, is_final_trick=False, hand_size=3)
    t.check_after_trick(2, {0: Card(Suit.GREEN, 1), 1: Card(Suit.GREEN, 9)}, winner=1,
                         wins_per_player={0: 1, 1: 1}, is_final_trick=False, hand_size=3)
    t.check_after_trick(3, {0: Card(Suit.GREEN, 5), 1: Card(Suit.GREEN, 2)}, winner=0,
                         wins_per_player={0: 2, 1: 1}, is_final_trick=True, hand_size=3)
    assert t.resolved and not t.success


def test_win_exact_count_consecutive_fails_when_wins_not_contiguous():
    t = Task(id="t1", owner=0, kind=TaskKind.WIN_EXACT_COUNT_CONSECUTIVE, params={"n": 2})
    t.check_after_trick(1, {0: Card(Suit.GREEN, 5), 1: Card(Suit.GREEN, 9)}, winner=0,
                         wins_per_player={0: 1}, is_final_trick=False, hand_size=3)
    t.check_after_trick(2, {0: Card(Suit.GREEN, 1), 1: Card(Suit.GREEN, 9)}, winner=1,
                         wins_per_player={0: 1, 1: 1}, is_final_trick=False, hand_size=3)
    t.check_after_trick(3, {0: Card(Suit.GREEN, 5), 1: Card(Suit.GREEN, 2)}, winner=0,
                         wins_per_player={0: 2, 1: 1}, is_final_trick=True, hand_size=3)
    assert t.resolved and not t.success


def test_win_exact_count_consecutive_succeeds_when_contiguous():
    t = Task(id="t1", owner=0, kind=TaskKind.WIN_EXACT_COUNT_CONSECUTIVE, params={"n": 2})
    t.check_after_trick(1, {0: Card(Suit.GREEN, 5)}, winner=0, wins_per_player={0: 1},
                         is_final_trick=False, hand_size=3)
    t.check_after_trick(2, {0: Card(Suit.GREEN, 5)}, winner=0, wins_per_player={0: 2},
                         is_final_trick=False, hand_size=3)
    t.check_after_trick(3, {0: Card(Suit.GREEN, 1), 1: Card(Suit.GREEN, 9)}, winner=1,
                         wins_per_player={0: 2, 1: 1}, is_final_trick=True, hand_size=3)
    assert t.resolved and t.success


def test_fewer_than_commander_only_resolves_at_final_trick():
    t = Task(id="t1", owner=1, kind=TaskKind.FEWER_THAN_COMMANDER, params={})
    t.check_after_trick(1, {0: Card(Suit.GREEN, 5), 1: Card(Suit.GREEN, 2)}, winner=0,
                         wins_per_player={0: 1}, is_final_trick=True, hand_size=1,
                         num_players=2, commander=0)
    assert t.resolved and t.success


def test_win_full_color_run_needs_every_rank_of_one_color():
    t = Task(id="t1", owner=0, kind=TaskKind.WIN_FULL_COLOR_RUN, params={})
    from boardy.games.deep_sea_crew.cards import COLOR_MAX_RANK
    for r in range(1, COLOR_MAX_RANK + 1):
        final = r == COLOR_MAX_RANK
        t.check_after_trick(r, {0: Card(Suit.YELLOW, r), 1: Card(Suit.GREEN, 1)}, winner=0,
                             wins_per_player={0: r}, is_final_trick=final, hand_size=COLOR_MAX_RANK)
    assert t.resolved and t.success


def test_win_trick_all_below_succeeds_when_every_card_under_threshold():
    t = Task(id="t1", owner=0, kind=TaskKind.WIN_TRICK_ALL_BELOW, params={"threshold": 7})
    t.check_after_trick(1, {0: Card(Suit.GREEN, 6), 1: Card(Suit.GREEN, 2)}, winner=0,
                         wins_per_player={0: 1}, is_final_trick=False, hand_size=2)
    assert t.resolved and t.success


def test_win_trick_all_below_fails_to_trigger_on_a_card_at_or_above_threshold():
    t = Task(id="t1", owner=0, kind=TaskKind.WIN_TRICK_ALL_BELOW, params={"threshold": 7})
    t.check_after_trick(1, {0: Card(Suit.GREEN, 7), 1: Card(Suit.GREEN, 2)}, winner=0,
                         wins_per_player={0: 1}, is_final_trick=True, hand_size=1)
    t.force_resolve_if_unresolved_at_end({0: 1})
    assert t.resolved and not t.success


def test_win_trick_all_below_excludes_submarine_tricks():
    t = Task(id="t1", owner=0, kind=TaskKind.WIN_TRICK_ALL_BELOW, params={"threshold": 7})
    t.check_after_trick(1, {0: Card(Suit.SUBMARINE, 1), 1: Card(Suit.GREEN, 2)}, winner=0,
                         wins_per_player={0: 1}, is_final_trick=True, hand_size=1)
    t.force_resolve_if_unresolved_at_end({0: 1})
    assert t.resolved and not t.success


def test_play_and_win_with_requires_own_card_and_other_card_together():
    t = Task(id="t1", owner=0, kind=TaskKind.PLAY_AND_WIN_WITH,
              params={"play": {"rank": 6}, "other": {"rank": 6, "differs_suit": True}})
    t.check_after_trick(1, {0: Card(Suit.BLUE, 6), 1: Card(Suit.GREEN, 6)}, winner=0,
                         wins_per_player={0: 1}, is_final_trick=False, hand_size=2)
    assert t.resolved and t.success
