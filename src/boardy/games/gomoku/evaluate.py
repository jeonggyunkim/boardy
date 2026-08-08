"""Compare a trained network's win rate against RandomPlayer."""

from __future__ import annotations

import argparse
import io
import random
import sys
from pathlib import Path

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
