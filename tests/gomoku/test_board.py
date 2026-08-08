import pytest

from boardy.games.gomoku.board import BLACK, WHITE, Board


def test_horizontal_win():
    b = Board(size=9, win_length=5)
    for c in range(5):
        b.play(0, c)  # black
        if c < 4:
            b.play(1, c)  # white
    assert b.winner == BLACK


def test_vertical_win():
    b = Board(size=9, win_length=5)
    for r in range(5):
        b.play(r, 0)
        if r < 4:
            b.play(r, 1)
    assert b.winner == BLACK


def test_diagonal_win():
    b = Board(size=9, win_length=5)
    for i in range(5):
        b.play(i, i)
        if i < 4:
            b.play(i, i + 1)
    assert b.winner == BLACK


def test_anti_diagonal_win():
    b = Board(size=9, win_length=5)
    for i in range(5):
        b.play(i, 4 - i)
        if i < 4:
            b.play(i, 5 - i)
    assert b.winner == BLACK


def test_no_win_with_four():
    b = Board(size=9, win_length=5)
    for c in range(4):
        b.play(0, c)
        b.play(1, c)
    assert b.winner is None


def test_draw_detection():
    b = Board(size=2, win_length=5)  # too small to ever get 5 in a row
    b.play(0, 0)
    b.play(0, 1)
    b.play(1, 0)
    b.play(1, 1)
    assert b.winner == 0


def test_cannot_play_occupied_cell():
    b = Board(size=9, win_length=5)
    b.play(0, 0)
    with pytest.raises(ValueError):
        b.play(0, 0)


def test_cannot_play_after_win():
    b = Board(size=9, win_length=5)
    for c in range(5):
        b.play(0, c)
        if c < 4:
            b.play(1, c)
    with pytest.raises(ValueError):
        b.play(2, 0)


def test_legal_moves_shrinks():
    b = Board(size=3, win_length=5)
    assert len(b.legal_moves()) == 9
    b.play(0, 0)
    assert len(b.legal_moves()) == 8


def test_to_move_alternates():
    b = Board()
    assert b.to_move == BLACK
    b.play(0, 0)
    assert b.to_move == WHITE
    b.play(0, 1)
    assert b.to_move == BLACK
