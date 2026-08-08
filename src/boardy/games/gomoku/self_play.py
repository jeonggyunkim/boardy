"""Self-play game generation for AlphaZero training.

Each recorded example's value target is +1/-1/0 from the perspective of
whichever player was to move at that position — i.e. the sign flips every
ply, unlike Deep Sea Crew where the whole game shares one value.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .board import Board
from .encoding import action_to_index, encode_board
from .engine import new_game
from .mcts import run_mcts, select_action
from .network import PolicyValueNet


@dataclass
class Example:
    obs: np.ndarray
    policy: np.ndarray  # length size*size
    value: float = 0.0  # filled in once the game ends


def play_self_play_game(
    net: PolicyValueNet,
    num_simulations: int = 100,
    temperature_moves: int = 8,
) -> tuple[list[Example], int | None]:
    board: Board = new_game()
    size = board.size
    examples: list[Example] = []
    ply = 0

    while board.winner is None:
        visit_probs = run_mcts(board, net, num_simulations=num_simulations, add_noise=True)

        policy_vec = np.zeros(size * size, dtype=np.float32)
        for action, p in visit_probs.items():
            policy_vec[action_to_index(action, size)] = p

        examples.append(Example(obs=encode_board(board), policy=policy_vec))

        temperature = 1.0 if ply < temperature_moves else 0.0
        action = select_action(visit_probs, temperature=temperature)
        r, c = (int(v) for v in action.split(","))
        board.play(r, c)
        ply += 1

    winner = board.winner  # BLACK(1), WHITE(-1), or 0 for draw
    # examples[i] was recorded from the perspective of whoever was to move
    # at that ply, alternating starting with BLACK.
    for i, ex in enumerate(examples):
        mover = 1 if i % 2 == 0 else -1
        ex.value = 0.0 if winner == 0 else (1.0 if winner == mover else -1.0)

    return examples, winner
