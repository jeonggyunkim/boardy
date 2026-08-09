"""Compare a trained network's win rate against RandomPlayer."""

from __future__ import annotations

import argparse
import io
import random
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import torch

from .board import Board
from .engine import new_game
from .network import PolicyValueNet
from .players import NetPlayer, Player, RandomPlayer


def play_game(black: Player, white: Player) -> int:
    board: Board = new_game()
    players = {1: black, -1: white}
    while board.winner is None:
        mover = players[board.to_move]
        action = mover.choose_move(board)
        r, c = (int(v) for v in action.split(","))
        board.play(r, c)
    return board.winner  # 1=black won, -1=white won, 0=draw


def _arena_game_worker(payload: tuple[dict, dict, int, float, bool, int]) -> tuple[int, int]:
    """Runs in a worker process (see train.py's _self_play_worker for why
    plain state_dicts, not nn.Module instances, cross the process
    boundary, and why num_threads is pinned to 1 here)."""
    cand_state, inc_state, num_simulations, temperature, cand_is_black, seed = payload
    torch.set_num_threads(1)
    random.seed(seed)
    np.random.seed(seed)
    candidate = PolicyValueNet()
    candidate.load_state_dict(cand_state)
    incumbent = PolicyValueNet()
    incumbent.load_state_dict(inc_state)
    cand_player = NetPlayer(candidate, name="candidate", num_simulations=num_simulations, temperature=temperature)
    inc_player = NetPlayer(incumbent, name="incumbent", num_simulations=num_simulations, temperature=temperature)
    winner = play_game(cand_player, inc_player) if cand_is_black else play_game(inc_player, cand_player)
    cand_color = 1 if cand_is_black else -1
    return winner, cand_color


def arena(
    candidate: PolicyValueNet,
    incumbent: PolicyValueNet,
    num_games: int,
    num_simulations: int,
    temperature: float = 0.4,
    pool: ProcessPoolExecutor | None = None,
    rng: random.Random | None = None,
) -> tuple[int, int, int]:
    """Play candidate vs incumbent, alternating colors. Returns (candidate_wins,
    incumbent_wins, draws). temperature > 0 so games are actually independent
    (not the same deterministic game replayed with colors swapped). Pass a
    `pool` to run the (independent) games across worker processes instead
    of sequentially in this one."""
    cand_wins = inc_wins = draws = 0
    if pool is not None:
        rng = rng or random.Random()
        cand_state = {k: v.cpu() for k, v in candidate.state_dict().items()}
        inc_state = {k: v.cpu() for k, v in incumbent.state_dict().items()}
        payloads = [
            (cand_state, inc_state, num_simulations, temperature, g % 2 == 0, rng.randrange(1_000_000_000))
            for g in range(num_games)
        ]
        results = list(pool.map(_arena_game_worker, payloads))
    else:
        results = []
        for g in range(num_games):
            cand_is_black = g % 2 == 0
            cand_player = NetPlayer(
                candidate, name="candidate", num_simulations=num_simulations, temperature=temperature
            )
            inc_player = NetPlayer(
                incumbent, name="incumbent", num_simulations=num_simulations, temperature=temperature
            )
            winner = play_game(cand_player, inc_player) if cand_is_black else play_game(inc_player, cand_player)
            results.append((winner, 1 if cand_is_black else -1))

    for winner, cand_color in results:
        if winner == 0:
            draws += 1
        elif winner == cand_color:
            cand_wins += 1
        else:
            inc_wins += 1
    return cand_wins, inc_wins, draws


def run_eval(checkpoint: Path | None, num_games: int, num_simulations: int, seed: int) -> None:
    net = PolicyValueNet()
    if checkpoint is not None:
        net.load_state_dict(torch.load(checkpoint, map_location="cpu"))
        print(f"Loaded checkpoint: {checkpoint}")
    else:
        print("No checkpoint given - evaluating an UNTRAINED network (sanity check only).")

    rng = random.Random(seed)
    ai_wins = ai_losses = draws = 0
    for g in range(num_games):
        ai_is_black = g % 2 == 0  # alternate colors to cancel first-move advantage
        ai = NetPlayer(net, name="ai", num_simulations=num_simulations, temperature=0.0)
        rnd = RandomPlayer(name="rand", rng=random.Random(rng.randrange(1_000_000_000)))
        winner = play_game(ai, rnd) if ai_is_black else play_game(rnd, ai)
        ai_color = 1 if ai_is_black else -1
        if winner == 0:
            draws += 1
        elif winner == ai_color:
            ai_wins += 1
        else:
            ai_losses += 1

    print(f"\nGames: {num_games}, sims/move={num_simulations}")
    print(f"AI wins:   {ai_wins}/{num_games} = {ai_wins / num_games:.1%}")
    print(f"AI losses: {ai_losses}/{num_games} = {ai_losses / num_games:.1%}")
    print(f"Draws:     {draws}/{num_games} = {draws / num_games:.1%}")


def main() -> None:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    parser = argparse.ArgumentParser(description="Evaluate a trained Gomoku net vs random play.")
    parser.add_argument("--checkpoint", type=Path, default=None)
    parser.add_argument("--num-games", type=int, default=30)
    parser.add_argument("--num-simulations", type=int, default=200)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    run_eval(
        checkpoint=args.checkpoint,
        num_games=args.num_games,
        num_simulations=args.num_simulations,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
