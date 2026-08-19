"""Self-play game generation for AlphaZero training.

Each recorded example's value target is +1/-1/0 from the perspective of
whichever player was to move at that position -- i.e. the sign flips every
ply, unlike Deep Sea Crew where the whole game shares one value.

`play_self_play_games_batch` drives many games concurrently, in lockstep,
using a single `BatchedMCTS` instance per batch: each ply's search batches
its leaf evaluations across every still-unfinished game (letting a GPU
help), and after a move is played the tree is `advance()`d to the child
for that move instead of being rebuilt from scratch -- that child already
carries visit statistics from the previous search, so reaching the same
effective search depth next ply needs fewer new simulations.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .board import Board
from .encoding import action_to_index, encode_board
from .engine import new_game
from .mcts import BatchedMCTS, select_action
from .network import PolicyValueNet


@dataclass
class Example:
    obs: np.ndarray
    policy: np.ndarray  # length size*size
    value: float = 0.0  # filled in once the game ends


def play_self_play_games_batch(
    net: PolicyValueNet,
    num_games: int,
    num_simulations: int = 100,
    temperature_moves: int = 8,
    dirichlet_alpha: float = 0.3,
    dirichlet_eps: float = 0.25,
) -> list[tuple[list[Example], int | None]]:
    boards: list[Board] = [new_game() for _ in range(num_games)]
    size = boards[0].size
    examples: list[list[Example]] = [[] for _ in range(num_games)]
    ply = [0] * num_games
    winners: list[int | None] = [None] * num_games

    active = list(range(num_games))  # game indices currently held in `tree`, in tree order
    tree = BatchedMCTS([boards[i] for i in active], net)

    while active:
        visit_probs_list = tree.search(
            num_simulations, add_noise=True, dirichlet_alpha=dirichlet_alpha, dirichlet_eps=dirichlet_eps
        )

        actions: list[str] = []
        finished_positions: list[int] = []
        for pos, i in enumerate(active):
            board = boards[i]
            visit_probs = visit_probs_list[pos]

            policy_vec = np.zeros(size * size, dtype=np.float32)
            for action, p in visit_probs.items():
                policy_vec[action_to_index(action, size)] = p
            examples[i].append(Example(obs=encode_board(board), policy=policy_vec))

            temperature = 1.0 if ply[i] < temperature_moves else 0.0
            action = select_action(visit_probs, temperature=temperature)
            actions.append(action)
            r, c = (int(v) for v in action.split(","))
            board.play(r, c)
            ply[i] += 1

            if board.winner is not None:
                winners[i] = board.winner
                finished_positions.append(pos)

        tree.advance(actions)
        if finished_positions:
            tree.drop(finished_positions)
        finished_set = set(finished_positions)
        active = [i for pos, i in enumerate(active) if pos not in finished_set]

    results: list[tuple[list[Example], int | None]] = []
    for i in range(num_games):
        winner = winners[i]
        # examples[i][j] was recorded from the perspective of whoever was to
        # move at that ply, alternating starting with BLACK.
        for j, ex in enumerate(examples[i]):
            mover = 1 if j % 2 == 0 else -1
            ex.value = 0.0 if winner == 0 else (1.0 if winner == mover else -1.0)
        results.append((examples[i], winner))

    return results


def play_self_play_game(
    net: PolicyValueNet,
    num_simulations: int = 100,
    temperature_moves: int = 8,
) -> tuple[list[Example], int | None]:
    """Single-game convenience wrapper (e.g. for quick scripts/tests) --
    training should call `play_self_play_games_batch` directly so leaf
    evaluations across games can be batched onto the GPU."""
    return play_self_play_games_batch(net, num_games=1, num_simulations=num_simulations, temperature_moves=temperature_moves)[0]
