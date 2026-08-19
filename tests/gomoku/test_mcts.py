from boardy.games.gomoku.board import BLACK, Board
from boardy.games.gomoku.mcts import BatchedMCTS, run_mcts, run_mcts_batch, select_action
from boardy.games.gomoku.network import PolicyValueNet

# Tiny architecture for fast tests -- the default (10 blocks x 128ch) is
# sized for real training, not for running hundreds of times in CI.
TINY = dict(channels=8, num_blocks=1)


def test_run_mcts_returns_distribution_over_legal_moves():
    net = PolicyValueNet(board_size=9, **TINY)
    board = Board(size=9, win_length=5)
    board.play(2, 2)
    legal = {f"{r},{c}" for r, c in board.legal_moves()}
    probs = run_mcts(board, net, num_simulations=10)
    assert set(probs.keys()) == legal
    assert abs(sum(probs.values()) - 1.0) < 1e-6


def test_select_action_greedy_picks_max_visit():
    probs = {"a": 0.1, "b": 0.7, "c": 0.2}
    assert select_action(probs, temperature=0.0) == "b"


def test_mcts_finds_immediate_winning_move():
    # Black has four in a row (open at column 4), white's stones are
    # elsewhere and don't block -> it's black's turn again (strict
    # alternation means white must move once per black move), and any
    # decent search should find the move that completes five. Uses a small
    # board (few legal moves) and enough simulations to comfortably visit
    # every root child at least once even with an untrained (near-uniform
    # prior) network -- otherwise the winning child may simply never get
    # sampled within the simulation budget.
    board = Board(size=6, win_length=5)
    for i in range(4):
        board.play(0, i)  # black
        board.play(5, i)  # white, elsewhere
    assert board.to_move == BLACK
    net = PolicyValueNet(board_size=6, **TINY)
    probs = run_mcts(board, net, num_simulations=200)
    best = max(probs, key=probs.get)
    assert best == "0,4"  # only cell that completes five in a row


def test_run_mcts_batch_matches_single_game_wrapper():
    boards = [Board(size=6, win_length=5) for _ in range(3)]
    boards[1].play(2, 2)
    net = PolicyValueNet(board_size=6, **TINY)

    batch_probs = run_mcts_batch(boards, net, num_simulations=20)
    assert len(batch_probs) == 3
    for board, probs in zip(boards, batch_probs):
        legal = {f"{r},{c}" for r, c in board.legal_moves()}
        assert set(probs.keys()) == legal
        assert abs(sum(probs.values()) - 1.0) < 1e-6


def test_run_mcts_wrapper_equals_batch_of_one():
    board = Board(size=6, win_length=5)
    board.play(2, 2)
    net = PolicyValueNet(board_size=6, **TINY)

    single = run_mcts(board.clone(), net, num_simulations=20, add_noise=False)
    batch = run_mcts_batch([board.clone()], net, num_simulations=20, add_noise=False)[0]
    assert set(single.keys()) == set(batch.keys())


# --- BatchedMCTS tree reuse (advance/drop) -- this logic went through three
# rounds of self-caught bugs during development (running full num_simulations
# unconditionally every call; counting grandchildren instead of the new
# root's own visit_count as carryover; a single shared per-batch round count
# dragging every game down to the worst-carryover game's budget -- see
# docs/PLAN.md 2026-08-11), so it's worth locking down directly rather than
# only through self_play.py's end-to-end behavior.


def test_advance_carries_over_visit_count_from_previous_search():
    board = Board(size=6, win_length=5)
    net = PolicyValueNet(board_size=6, **TINY)
    tree = BatchedMCTS([board], net)

    tree.search(30, add_noise=False)
    root = tree.roots[0]
    action = max(root.children.items(), key=lambda kv: kv[1].visit_count)[0]
    carried = root.children[action].visit_count
    assert carried >= 1  # the chosen action must have been visited at least once

    tree.advance([action])
    # advance() re-roots to that exact child -- its visit_count must survive
    # the re-rooting unchanged, since that's the whole quantity search()
    # uses to decide how many *new* simulations are still owed.
    assert tree.roots[0].visit_count == carried


def test_search_does_not_exceed_target_when_called_twice_without_advancing():
    """Regression for the first tree-reuse bug: search() must treat
    num_simulations as a target total, not "always run this many more" --
    calling search() again on the same (non-advanced) root should be a
    no-op once the target is already met."""
    board = Board(size=6, win_length=5)
    net = PolicyValueNet(board_size=6, **TINY)
    tree = BatchedMCTS([board], net)

    tree.search(25, add_noise=False)
    assert tree.roots[0].visit_count == 25
    tree.search(25, add_noise=False)
    assert tree.roots[0].visit_count == 25  # no new simulations added


def test_search_after_advance_only_runs_the_shortfall():
    """Regression for the second/third tree-reuse bugs: after advance(), the
    new root's target is max(carryover, num_simulations), and it should end
    up exactly at that target -- not short of it (bug #1's opposite: reuse
    silently starving a line of its full budget) and not double-counting."""
    board = Board(size=6, win_length=5)
    net = PolicyValueNet(board_size=6, **TINY)
    tree = BatchedMCTS([board], net)

    tree.search(40, add_noise=False)
    root = tree.roots[0]
    action = max(root.children.items(), key=lambda kv: kv[1].visit_count)[0]
    carried = root.children[action].visit_count

    tree.advance([action])
    tree.search(40, add_noise=False)
    assert tree.roots[0].visit_count == max(carried, 40)


def test_drop_removes_finished_games_by_position_only():
    boards = [Board(size=6, win_length=5) for _ in range(3)]
    net = PolicyValueNet(board_size=6, **TINY)
    tree = BatchedMCTS(boards, net)
    tree.search(5, add_noise=False)

    kept = [tree.roots[0], tree.roots[2]]
    tree.drop([1])  # drop the middle game only
    assert tree.roots == kept
