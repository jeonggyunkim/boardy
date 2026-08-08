import random

from boardy.games.deep_sea_crew.engine import GameState, new_game
from boardy.games.deep_sea_crew.mcts import run_mcts, select_action
from boardy.games.deep_sea_crew.mcts_inference import run_ismcts, sample_determinization
from boardy.games.deep_sea_crew.network import PolicyValueNet


def _finish_draft(state: GameState, rng: random.Random) -> None:
    while state.phase == "task_draft":
        seat = state.player_to_act
        task = rng.choice(state.available_tasks)
        state.draft_task(seat, task.id)


def test_run_mcts_returns_distribution_over_legal_moves():
    net = PolicyValueNet()
    state = new_game(3, difficulty_budget=6, seed=1)
    _finish_draft(state, random.Random(1))
    legal = set(state.legal_cards_for(state.player_to_act))
    probs = run_mcts(state, net, num_simulations=10)
    assert set(probs.keys()) == legal
    assert abs(sum(probs.values()) - 1.0) < 1e-6


def test_select_action_greedy_picks_max_visit():
    probs = {"a": 0.1, "b": 0.7, "c": 0.2}
    assert select_action(probs, temperature=0.0) == "b"


def test_sample_determinization_preserves_own_hand_and_hand_sizes():
    net = PolicyValueNet()
    # difficulty=1 so the mission is easy enough that it's very unlikely to
    # fail after just one trick -- a harder mission occasionally does,
    # which would leave player_to_act as None before this test gets to
    # exercise what it's actually testing.
    state = new_game(4, difficulty_budget=1, seed=3)
    _finish_draft(state, random.Random(3))
    # advance one full trick so history-based void inference has something to chew on
    while state.outcome is None:
        seat = state.player_to_act
        card = state.legal_cards_for(seat)[0]
        rec = state.play_card(seat, card)
        if rec:
            break
    assert state.outcome is None, "mission failed after only one trick; pick a different seed/difficulty"
    seat = state.player_to_act
    det = sample_determinization(state, seat, random.Random(0))
    assert det.hands[seat] == state.hands[seat]
    assert [len(h) for h in det.hands] == [len(h) for h in state.hands]


def test_run_ismcts_returns_distribution_over_legal_moves():
    net = PolicyValueNet()
    state = new_game(3, difficulty_budget=6, seed=4)
    _finish_draft(state, random.Random(4))
    legal = set(state.legal_cards_for(state.player_to_act))
    probs = run_ismcts(state, net, num_determinizations=3, sims_per_determinization=5, seed=0)
    assert set(probs.keys()) <= legal
    assert abs(sum(probs.values()) - 1.0) < 1e-6
