from boardy.games.gomoku.board import BLACK, WHITE, Board


def set_stones(board: Board, color: int, coords: list[tuple[int, int]]) -> None:
    for r, c in coords:
        board.cells[board.index(r, c)] = color


def test_double_three_forbidden():
    board = Board(size=9, win_length=5, renju=True)
    # horizontal pair at (5,3),(5,4) and vertical pair at (3,5),(4,5);
    # playing (5,5) completes an open three in both directions at once.
    set_stones(board, BLACK, [(5, 3), (5, 4), (3, 5), (4, 5)])
    assert board.is_forbidden_for_black(5, 5) == "double_three"
    assert (5, 5) not in board.legal_moves()


def test_double_four_forbidden():
    board = Board(size=9, win_length=5, renju=True)
    # horizontal three at (5,2..4) and vertical three at (2..4,5);
    # playing (5,5) completes a four in both directions at once.
    set_stones(board, BLACK, [(5, 2), (5, 3), (5, 4), (2, 5), (3, 5), (4, 5)])
    assert board.is_forbidden_for_black(5, 5) == "double_four"
    assert (5, 5) not in board.legal_moves()


def test_overline_forbidden():
    board = Board(size=9, win_length=5, renju=True)
    # four in a row at cols 1-4 plus a lone stone at col 6; playing col 5
    # connects cols 1-6 -- six in a row, not a legal five for Black.
    set_stones(board, BLACK, [(5, 1), (5, 2), (5, 3), (5, 4), (5, 6)])
    assert board.is_forbidden_for_black(5, 5) == "overline"
    assert (5, 5) not in board.legal_moves()


def test_exact_five_overrides_would_be_double_three():
    board = Board(size=9, win_length=5, renju=True)
    # cols 1-4 in a row (exact five when col 5 is played) *and* a
    # would-be double-three set up through the same point -- the five
    # must win outright regardless.
    set_stones(
        board,
        BLACK,
        [(5, 1), (5, 2), (5, 3), (5, 4), (3, 5), (4, 5)],
    )
    assert board.is_forbidden_for_black(5, 5) is None
    assert (5, 5) in board.legal_moves()
    board.play(5, 5)
    assert board.winner == BLACK


def test_single_open_three_is_legal():
    board = Board(size=9, win_length=5, renju=True)
    set_stones(board, BLACK, [(5, 3), (5, 4)])
    assert board.is_forbidden_for_black(5, 5) is None
    assert (5, 5) in board.legal_moves()


def test_single_four_is_legal():
    board = Board(size=9, win_length=5, renju=True)
    set_stones(board, BLACK, [(5, 2), (5, 3), (5, 4)])
    assert board.is_forbidden_for_black(5, 5) is None
    assert (5, 5) in board.legal_moves()


def test_closed_three_is_not_open():
    # three in a row but blocked on the left by White -> can only ever
    # extend to a one-sided four, never an open (unstoppable) four, so it
    # must NOT count toward double-three.
    board = Board(size=9, win_length=5, renju=True)
    set_stones(board, WHITE, [(5, 2)])
    set_stones(board, BLACK, [(5, 3), (5, 4)])
    assert board.is_forbidden_for_black(5, 5) is None


def test_double_closed_three_is_legal():
    # two closed (one-side-blocked) threes crossing at the move -- since
    # neither is "open", this is NOT a forbidden double-three.
    board = Board(size=9, win_length=5, renju=True)
    set_stones(board, WHITE, [(5, 2), (2, 5)])
    set_stones(board, BLACK, [(5, 3), (5, 4), (3, 5), (4, 5)])
    assert board.is_forbidden_for_black(5, 5) is None
    assert (5, 5) in board.legal_moves()


def test_single_broken_three_is_legal():
    # BB_B (gap immediately before the candidate) with both outer flanks
    # empty is a genuine open three (filling the gap gives an open four),
    # but a single one is not forbidden by itself.
    board = Board(size=9, win_length=5, renju=True)
    set_stones(board, BLACK, [(5, 2), (5, 3)])  # gap at (5,4), candidate at (5,5)
    assert board.is_forbidden_for_black(5, 5) is None


def test_broken_three_counts_toward_double_three():
    # same BB_B broken three as above, crossed with an ordinary
    # contiguous pair in the other direction through the same point --
    # the broken three must count toward double-three just like a normal
    # open three would.
    board = Board(size=9, win_length=5, renju=True)
    set_stones(board, BLACK, [(5, 2), (5, 3)])  # gap at (5,4), candidate at (5,5)
    set_stones(board, BLACK, [(3, 5), (4, 5)])  # ordinary vertical pair through (5,5)
    assert board.is_forbidden_for_black(5, 5) == "double_three"


def test_three_blocked_both_ways_is_not_open_even_though_it_looks_like_one():
    # Horizontal three at cols 3-5 (after playing (5,5)) looks open --
    # both (5,2) and (5,6) are empty -- but neither side can actually
    # reach an open four: extending left through (5,2) would connect
    # into (5,0),(5,1) for six-in-a-row (overline, illegal for Black, so
    # not a real threat), and extending right through (5,6) runs into
    # White at (5,7) (a closed, not open, four). Crossed with a genuine
    # open vertical three, this must NOT be double-three.
    board = Board(size=9, win_length=5, renju=True)
    set_stones(board, BLACK, [(5, 0), (5, 1), (5, 3), (5, 4), (3, 5), (4, 5)])
    set_stones(board, WHITE, [(5, 7)])
    assert board.is_forbidden_for_black(5, 5) is None
    assert (5, 5) in board.legal_moves()


def test_three_overline_flank_two_cells_away_is_not_open():
    # X . . X X ? . O -- same idea as above, but the overline-causing
    # stone is *two* cells past the extension point (5,2), not adjacent
    # to it, so (5,2)'s immediate flank at (5,1) is empty on its own.
    # Naively that makes cols 2-5 look like a genuine open four (both
    # (5,1) and (5,6) empty), but playing (5,1) to finish it would still
    # connect with the existing stone at (5,0) for six-in-a-row -- so
    # that end is a fake threat, and this must NOT be double-three.
    board = Board(size=9, win_length=5, renju=True)
    set_stones(board, BLACK, [(5, 0), (5, 3), (5, 4), (3, 5), (4, 5)])
    set_stones(board, WHITE, [(5, 7)])
    assert board.is_forbidden_for_black(5, 5) is None
    assert (5, 5) in board.legal_moves()


def test_three_whose_completion_point_is_itself_forbidden_is_not_open():
    # Real position reported by a user (docs/PLAN.md 2026-08-21, move 37 of
    # a game record): a broken diagonal three only reaches an open four by
    # playing a specific point, but that point is itself a double-four for
    # Black -- unplayable -- so the diagonal three isn't a real threat.
    # Crossed with a genuine open three elsewhere, this must NOT be
    # double-three even though the naive (non-recursive) check says it is.
    def coord(letter: str, num: int) -> tuple[int, int]:
        return 15 - num, ord(letter) - ord("a")

    board = Board(size=15, win_length=5, renju=True)
    moves = [
        ("h", 8, BLACK), ("i", 7, WHITE), ("f", 8, BLACK), ("g", 8, WHITE), ("g", 7, BLACK),
        ("f", 6, WHITE), ("h", 6, BLACK), ("e", 9, WHITE), ("h", 5, BLACK), ("h", 7, WHITE),
        ("i", 5, BLACK), ("j", 4, WHITE), ("j", 5, BLACK), ("k", 5, WHITE), ("i", 4, BLACK),
        ("i", 3, WHITE), ("l", 6, BLACK), ("k", 6, WHITE), ("i", 9, BLACK), ("k", 4, WHITE),
        ("k", 7, BLACK), ("j", 8, WHITE), ("j", 10, BLACK), ("k", 11, WHITE), ("l", 8, BLACK),
        ("h", 4, WHITE), ("g", 5, BLACK), ("f", 5, WHITE), ("k", 9, BLACK), ("m", 7, WHITE),
        ("i", 11, BLACK), ("h", 12, WHITE), ("j", 9, BLACK), ("l", 9, WHITE), ("i", 10, BLACK),
        ("i", 12, WHITE),
    ]
    for letter, num, color in moves:
        set_stones(board, color, [coord(letter, num)])

    r, c = coord("h", 10)
    assert board.is_forbidden_for_black(r, c) is None
    assert (r, c) in board.legal_moves()

    rg9, cg9 = coord("g", 9)
    board.cells[board.index(r, c)] = BLACK
    assert board.is_forbidden_for_black(rg9, cg9) == "double_four"


def test_three_blocked_one_way_still_counts_if_the_other_way_is_open():
    # Same as above but without the (5,0),(5,1) overline setup -- the
    # left extension is now genuinely open, so this three still counts
    # even though its right extension is closed by White.
    board = Board(size=9, win_length=5, renju=True)
    set_stones(board, BLACK, [(5, 3), (5, 4), (3, 5), (4, 5)])
    set_stones(board, WHITE, [(5, 7)])
    assert board.is_forbidden_for_black(5, 5) == "double_three"


def test_white_has_no_forbidden_moves():
    board = Board(size=9, win_length=5, renju=True)
    board.to_move = WHITE
    # the same double-three shape that's forbidden for Black is fine for White
    set_stones(board, WHITE, [(5, 3), (5, 4), (3, 5), (4, 5)])
    assert (5, 5) in board.legal_moves()
    board.play(5, 5)
    assert board.winner is None  # just a double three, not a win, but a legal move


def test_white_wins_with_overline():
    board = Board(size=9, win_length=5, renju=True)
    board.to_move = WHITE
    set_stones(board, WHITE, [(5, 1), (5, 2), (5, 3), (5, 4), (5, 6)])
    board.play(5, 5)  # connects cols 1-6 for White: six in a row
    assert board.winner == WHITE


def test_play_raises_on_forbidden_black_move():
    board = Board(size=9, win_length=5, renju=True)
    set_stones(board, BLACK, [(5, 3), (5, 4), (3, 5), (4, 5)])
    try:
        board.play(5, 5)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_renju_disabled_allows_double_three_and_overline():
    board = Board(size=9, win_length=5, renju=False)
    set_stones(board, BLACK, [(5, 3), (5, 4), (3, 5), (4, 5)])
    assert (5, 5) in board.legal_moves()
    board2 = Board(size=9, win_length=5, renju=False)
    set_stones(board2, BLACK, [(5, 1), (5, 2), (5, 3), (5, 4), (5, 6)])
    board2.play(5, 5)  # six in a row
    assert board2.winner == BLACK  # freestyle: 5-or-more always wins, no overline rule
