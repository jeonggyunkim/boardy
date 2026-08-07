"""Self-play game generation for training data.

Each played game yields one training example per decision point: the
acting seat's partial-info encoding, the MCTS visit-count policy target,
and (once the game ends) the shared mission-outcome value target — the
same value for every example in the game, since success/failure is a
team result, not per-player.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .encoding import NUM_CARDS, CARD_TO_INDEX, encode_observation
from .engine import new_game
from .mcts import run_mcts, select_action
from .network import PolicyValueNet


@dataclass
class Example:
    obs: np.ndarray
    policy: np.ndarray  # length NUM_CARDS, zeros on illegal actions
    value: float = 0.0  # filled in after the game ends


def play_self_play_game(
    net: PolicyValueNet,
    num_players: int = 3,
    difficulty_budget: int = 8,
    num_simulations: int = 40,
    temperature_moves: int = 4,
    seed: int | None = None,
) -> tuple[list[Example], bool]:
    state = new_game(num_players, difficulty_budget=difficulty_budget, seed=seed)
    examples: list[Example] = []
    ply = 0

    while state.outcome is None:
        seat = state.player_to_act
        visit_probs = run_mcts(state, net, num_simulations=num_simulations, add_noise=True)

        policy_vec = np.zeros(NUM_CARDS, dtype=np.float32)
        for card, p in visit_probs.items():
            policy_vec[CARD_TO_INDEX[card]] = p

        examples.append(Example(obs=encode_observation(state, seat), policy=policy_vec))

        temperature = 1.0 if ply < temperature_moves else 0.0
        card = select_action(visit_probs, temperature=temperature)
        state.play_card(seat, card)
        ply += 1

    outcome = bool(state.outcome)
    value = 1.0 if outcome else 0.0
    for ex in examples:
        ex.value = value
    return examples, outcome
