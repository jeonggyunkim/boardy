from boardy.games.gomoku.board import BLACK, Board
from boardy.games.gomoku.mcts import run_mcts, select_action
from boardy.games.gomoku.network import PolicyValueNet


def test_run_mcts_returns_distribution_over_legal_moves():
    net = PolicyValueNet(board_size=9)
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
    net = PolicyValueNet(board_size=6)
    probs = run_mcts(board, net, num_simulations=200)
    best = max(probs, key=probs.get)
    assert best == "0,4"  # only cell that completes five in a row
