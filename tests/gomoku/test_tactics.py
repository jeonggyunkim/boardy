from boardy.games.gomoku.board import BLACK, WHITE, Board
from boardy.games.gomoku.tactics import find_all_winning_moves, find_winning_move, tactical_result


def _place(board: Board, player: int, cells: list[tuple[int, int]]) -> None:
    for r, c in cells:
        board.cells[board.index(r, c)] = player
    board.move_count = len(cells)


def test_find_winning_move_finds_the_completing_cell() -> None:
    board = Board(renju=False)
    _place(board, WHITE, [(5, 3), (5, 4), (5, 5), (5, 6)])
    board.to_move = WHITE
    move = find_winning_move(board)
    assert move in {(5, 2), (5, 7)}


def test_find_winning_move_returns_none_without_a_win() -> None:
    board = Board(renju=False)
    _place(board, WHITE, [(5, 3), (5, 4), (5, 5)])
    board.to_move = WHITE
    assert find_winning_move(board) is None


def test_find_all_winning_moves_returns_every_completion_not_just_one() -> None:
    # Open four (5,3)-(5,6): both (5,2) and (5,7) independently complete
    # five -- neither should be dropped in favor of the other.
    board = Board(renju=False)
    _place(board, WHITE, [(5, 3), (5, 4), (5, 5), (5, 6)])
    board.to_move = WHITE
    assert set(find_all_winning_moves(board)) == {(5, 2), (5, 7)}


def test_tactical_result_credits_every_winning_move_when_to_move_can_win_now() -> None:
    board = Board(renju=False)
    _place(board, BLACK, [(5, 3), (5, 4), (5, 5), (5, 6)])
    board.to_move = BLACK
    value, winning_moves = tactical_result(board)
    assert value == 1.0
    assert set(winning_moves) == {(5, 2), (5, 7)}


def test_tactical_result_is_minus_one_when_every_move_hands_opponent_a_win() -> None:
    # Black has an open four (5,3)-(5,6): whichever empty cell White fills,
    # Black completes five at the other open end next move.
    board = Board(renju=False)
    _place(board, BLACK, [(5, 3), (5, 4), (5, 5), (5, 6)])
    board.to_move = WHITE
    assert tactical_result(board) == (-1.0, None)


def test_tactical_result_is_none_for_an_ordinary_position() -> None:
    board = Board(renju=False)
    _place(board, BLACK, [(5, 3), (5, 4), (5, 5)])
    board.to_move = WHITE
    assert tactical_result(board) is None


def test_tactical_result_none_before_any_win_is_possible() -> None:
    board = Board(renju=False)
    _place(board, BLACK, [(5, 3)])
    board.to_move = WHITE
    assert tactical_result(board) is None


def test_tactical_value_respects_renju_exact_five_for_black() -> None:
    # Filling (5,1) makes an exact five (5,1)-(5,5): a real win. Filling
    # (5,6) instead would connect into a run of six ((5,2)-(5,7)): an
    # overline, forbidden and NOT a win for Black under Renju rules.
    board = Board(renju=True)
    _place(board, BLACK, [(5, 2), (5, 3), (5, 4), (5, 5), (5, 7)])
    board.to_move = BLACK
    move = find_winning_move(board)
    assert move == (5, 1)


def test_overline_completion_alone_is_not_a_win_for_black() -> None:
    board = Board(renju=True)
    _place(board, BLACK, [(5, 2), (5, 3), (5, 4), (5, 5), (5, 7)])
    board.cells[board.index(5, 1)] = WHITE  # block the real winning cell
    board.move_count += 1
    board.to_move = BLACK
    assert find_winning_move(board) is None
