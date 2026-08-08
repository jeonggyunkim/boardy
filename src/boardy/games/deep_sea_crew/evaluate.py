"""Compare a trained network's mission success rate against RandomPlayer."""

from __future__ import annotations

import argparse
import io
import random
import sys
from pathlib import Path

import torch

from .engine import new_game
from .network import PolicyValueNet
from .players import NetPlayer, Player, RandomPlayer


def play_game(players: list[Player], num_players: int, difficulty: int, seed: int) -> bool:
    state = new_game(num_players, difficulty_budget=difficulty, seed=seed)
    while state.outcome is None:
        seat = state.player_to_act
        card = players[seat].choose_card(state, seat)
        state.play_card(seat, card)
    return bool(state.outcome)


def run_eval(
    checkpoint: Path | None,
    num_games: int,
    num_players: int,
    difficulty: int,
    use_search: bool,
    num_determinizations: int,
    sims_per_determinization: int,
    seed: int,
) -> None:
    net = PolicyValueNet()
    if checkpoint is not None:
        net.load_state_dict(torch.load(checkpoint, map_location="cpu"))
        print(f"Loaded checkpoint: {checkpoint}")
    else:
        print("No checkpoint given - evaluating an UNTRAINED network (sanity check only).")

    rng = random.Random(seed)

    def make_ai_team() -> list[Player]:
        return [
            NetPlayer(
                net,
                name=f"ai{i}",
                use_search=use_search,
                num_determinizations=num_determinizations,
                sims_per_determinization=sims_per_determinization,
                rng=random.Random(rng.randrange(1_000_000_000)),
            )
            for i in range(num_players)
        ]

    def make_random_team() -> list[Player]:
        return [RandomPlayer(name=f"rand{i}", rng=random.Random(rng.randrange(1_000_000_000))) for i in range(num_players)]

    ai_wins = 0
    random_wins = 0
    for g in range(num_games):
        seed_g = rng.randrange(1_000_000_000)
        ai_wins += int(play_game(make_ai_team(), num_players, difficulty, seed_g))
        random_wins += int(play_game(make_random_team(), num_players, difficulty, seed_g))

    print(f"\nGames: {num_games}, players={num_players}, difficulty={difficulty}")
    print(f"AI team success rate:     {ai_wins}/{num_games} = {ai_wins / num_games:.1%}")
    print(f"Random team success rate: {random_wins}/{num_games} = {random_wins / num_games:.1%}")


def main() -> None:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    parser = argparse.ArgumentParser(description="Evaluate a trained net vs random play.")
    parser.add_argument("--checkpoint", type=Path, default=None)
    parser.add_argument("--num-games", type=int, default=30)
    parser.add_argument("--players", type=int, default=3)
    parser.add_argument("--difficulty", type=int, default=8)
    parser.add_argument("--no-search", action="store_true", help="use raw network policy, skip ISMCTS")
    parser.add_argument("--num-determinizations", type=int, default=6)
    parser.add_argument("--sims-per-determinization", type=int, default=20)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    run_eval(
        checkpoint=args.checkpoint,
        num_games=args.num_games,
        num_players=args.players,
        difficulty=args.difficulty,
        use_search=not args.no_search,
        num_determinizations=args.num_determinizations,
        sims_per_determinization=args.sims_per_determinization,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
