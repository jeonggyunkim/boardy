"""Interactive CLI: human vs AI (random or trained-net+MCTS) Gomoku."""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

import torch

from .board import BLACK, WHITE, Board
from .engine import new_game
from .network import PolicyValueNet
from .players import NetPlayer, Player, RandomPlayer

COLOR_NAME = {BLACK: "Black(X)", WHITE: "White(O)"}


def parse_move(raw: str, board: Board) -> tuple[int, int]:
    raw = raw.strip().replace(" ", ",")
    parts = [p for p in raw.split(",") if p != ""]
    if len(parts) != 2:
        raise ValueError("Enter a move as 'row,col', e.g. 4,4")
    r, c = int(parts[0]), int(parts[1])
    if not board.in_bounds(r, c):
        raise ValueError(f"Out of bounds (board is {board.size}x{board.size})")
    if board.get(r, c) != 0:
        raise ValueError("That cell is already occupied")
    return r, c


class HumanPlayer(Player):
    def __init__(self, name: str = "you") -> None:
        self.name = name

    def choose_move(self, board: Board) -> str:
        print(f"\n{board.render()}\n")
        while True:
            raw = input(f"Your move as 'row,col' (0-{board.size - 1}): ")
            try:
                r, c = parse_move(raw, board)
            except ValueError as e:
                print(f"  {e}")
                continue
            return f"{r},{c}"


def run(human_color: int, checkpoint: Path | None, num_simulations: int) -> None:
    board = new_game()

    net = None
    if checkpoint is not None:
        net = PolicyValueNet()
        net.load_state_dict(torch.load(checkpoint, map_location="cpu"))
        ai: Player = NetPlayer(net, name="ai", num_simulations=num_simulations, temperature=0.0)
        print(f"AI: trained net + MCTS ({num_simulations} sims/move), checkpoint={checkpoint}")
    else:
        ai = RandomPlayer(name="ai")
        print("AI: random (pass --checkpoint to play a trained net instead)")

    human = HumanPlayer()
    players: dict[int, Player] = {human_color: human, -human_color: ai}
    print(f"You are {COLOR_NAME[human_color]}. Black always moves first.")

    while board.winner is None:
        mover = players[board.to_move]
        action = mover.choose_move(board)
        r, c = (int(v) for v in action.split(","))
        board.play(r, c)
        if mover is not human:
            print(f"\n{board.render()}\n")
            print(f"AI plays {r},{c}")

    print(f"\n{board.render()}\n")
    if board.winner == 0:
        print("=== DRAW ===")
    elif board.winner == human_color:
        print("=== YOU WIN ===")
    else:
        print("=== AI WINS ===")


def main() -> None:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    parser = argparse.ArgumentParser(description="Play Gomoku in the terminal.")
    parser.add_argument("--color", choices=["black", "white"], default="black")
    parser.add_argument("--checkpoint", type=Path, default=None)
    parser.add_argument("--simulations", type=int, default=200)
    args = parser.parse_args()
    run(BLACK if args.color == "black" else WHITE, args.checkpoint, args.simulations)


if __name__ == "__main__":
    main()
