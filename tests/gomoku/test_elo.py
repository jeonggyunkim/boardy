from boardy.games.gomoku.elo import expected_score, match_score, update_elo


def test_expected_score_equal_ratings_is_half():
    assert abs(expected_score(1000, 1000) - 0.5) < 1e-9


def test_expected_score_higher_rating_favored():
    assert expected_score(1200, 1000) > 0.5
    assert expected_score(1000, 1200) < 0.5


def test_update_elo_winner_gains_loser_loses():
    new_a, new_b = update_elo(1000, 1000, score_a=1.0)
    assert new_a > 1000
    assert new_b < 1000
    assert abs((new_a - 1000) - (1000 - new_b)) < 1e-9  # zero-sum for equal ratings


def test_update_elo_draw_leaves_equal_ratings_unchanged():
    new_a, new_b = update_elo(1000, 1000, score_a=0.5)
    assert abs(new_a - 1000) < 1e-9
    assert abs(new_b - 1000) < 1e-9


def test_match_score():
    assert match_score(wins_a=8, wins_b=2, draws=0) == 0.8
    assert match_score(wins_a=0, wins_b=0, draws=0) == 0.5
    assert match_score(wins_a=1, wins_b=1, draws=2) == 0.5
