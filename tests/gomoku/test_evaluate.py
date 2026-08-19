import boardy.games.gomoku.evaluate as evaluate_module
from boardy.games.gomoku.evaluate import _play_two_net_games, _play_vs_random_games, arena
from boardy.games.gomoku.network import PolicyValueNet

# evaluate.py's game generation always uses engine.new_game(), which is
# hardcoded to the default 15x15 board -- so unlike mcts.py's tests, these
# nets can't use a smaller board_size for speed, just a smaller tower.
TINY = dict(channels=8, num_blocks=1)


def test_play_two_net_games_alternates_colors_across_chunk_boundaries():
    """Regression test: color alternation must be based on the game's
    position in the *overall* match, not reset to 0 for every chunk --
    see `_play_two_net_games`'s `start_idx` docstring. Simulates the
    arena_games=12/workers=12 case that silently gave the candidate
    black in all 12 games before the fix."""
    net_a = PolicyValueNet(**TINY)
    net_b = PolicyValueNet(**TINY)

    colors = []
    start_idx = 0
    for _ in range(8):
        winner, a_color = _play_two_net_games(net_a, net_b, 1, 5, 0.4, start_idx=start_idx)[0]
        colors.append(a_color)
        start_idx += 1

    assert colors == [1, -1, 1, -1, 1, -1, 1, -1]


def test_arena_passes_incrementing_start_idx_across_chunks(monkeypatch):
    """arena()'s non-pool branch must track a running start_idx across
    chunks (batch_size=1 forces one chunk per game, mirroring the
    arena_games=12/workers=12 production config that triggered the bug)."""
    seen_start_idx = []
    real_fn = evaluate_module._play_two_net_games

    def spy(net_a, net_b, num_games, num_simulations, temperature, start_idx=0):
        seen_start_idx.append(start_idx)
        return real_fn(net_a, net_b, num_games, num_simulations, temperature, start_idx=start_idx)

    monkeypatch.setattr(evaluate_module, "_play_two_net_games", spy)

    net_a = PolicyValueNet(**TINY)
    net_b = PolicyValueNet(**TINY)
    cand_wins, inc_wins, draws = arena(net_a, net_b, num_games=4, num_simulations=5, batch_size=1)

    assert seen_start_idx == [0, 1, 2, 3]
    assert cand_wins + inc_wins + draws == 4


def test_play_vs_random_games_alternates_across_chunk_boundaries():
    net = PolicyValueNet(**TINY)
    import random

    rng = random.Random(0)
    colors = []
    start_idx = 0
    for _ in range(6):
        winner, ai_color = _play_vs_random_games(net, 1, 5, rng, start_idx=start_idx)[0]
        colors.append(ai_color)
        start_idx += 1

    assert colors == [1, -1, 1, -1, 1, -1]
