"""Self-play training loop: generate games with MCTS, fit the network, repeat.

Usage:
    python -m deepsea.train --iterations 20 --games-per-iter 20
"""

from __future__ import annotations

import argparse
import io
import random
import sys
import time
from collections import deque
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from .network import PolicyValueNet
from .self_play import Example, play_self_play_game

DEFAULT_CHECKPOINT_DIR = Path(__file__).resolve().parent.parent.parent / "checkpoints"


def train_on_batch(net: PolicyValueNet, optimizer: torch.optim.Optimizer, batch: list[Example]) -> tuple[float, float]:
    net.train()
    obs = torch.from_numpy(np.stack([e.obs for e in batch])).float()
    target_policy = torch.from_numpy(np.stack([e.policy for e in batch])).float()
    target_value = torch.tensor([e.value for e in batch], dtype=torch.float32)

    logits, value = net(obs)
    legal_mask = target_policy > 0
    masked_logits = logits.masked_fill(~legal_mask, -1e9)
    log_probs = F.log_softmax(masked_logits, dim=-1)
    policy_loss = -(target_policy * log_probs).sum(dim=-1).mean()
    value_loss = F.binary_cross_entropy(value, target_value)
    loss = policy_loss + value_loss

    optimizer.zero_grad()
    loss.backward()
    optimizer.step()
    return float(policy_loss.item()), float(value_loss.item())


def run_training(
    iterations: int,
    games_per_iter: int,
    num_simulations: int,
    epochs_per_iter: int,
    batch_size: int,
    lr: float,
    buffer_size: int,
    checkpoint_dir: Path,
    players_range: tuple[int, int],
    difficulty_range: tuple[int, int],
    seed: int | None,
) -> None:
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)

    net = PolicyValueNet()
    latest = checkpoint_dir / "latest.pt"
    if latest.exists():
        net.load_state_dict(torch.load(latest, map_location="cpu"))
        print(f"Resumed from {latest}")

    optimizer = torch.optim.Adam(net.parameters(), lr=lr)
    buffer: deque[Example] = deque(maxlen=buffer_size)

    for it in range(1, iterations + 1):
        t0 = time.time()
        successes = 0
        for g in range(games_per_iter):
            num_players = rng.randint(*players_range)
            difficulty = rng.randint(*difficulty_range)
            examples, outcome = play_self_play_game(
                net,
                num_players=num_players,
                difficulty_budget=difficulty,
                num_simulations=num_simulations,
                seed=rng.randrange(1_000_000_000),
            )
            buffer.extend(examples)
            successes += int(outcome)
        gen_time = time.time() - t0

        policy_losses, value_losses = [], []
        if len(buffer) >= batch_size:
            for _ in range(epochs_per_iter):
                batch = rng.sample(list(buffer), batch_size)
                pl, vl = train_on_batch(net, optimizer, batch)
                policy_losses.append(pl)
                value_losses.append(vl)

        torch.save(net.state_dict(), latest)
        torch.save(net.state_dict(), checkpoint_dir / f"iter_{it:04d}.pt")

        win_rate = successes / games_per_iter
        pl_mean = np.mean(policy_losses) if policy_losses else float("nan")
        vl_mean = np.mean(value_losses) if value_losses else float("nan")
        print(
            f"iter {it}/{iterations}  self-play win-rate={win_rate:.2f}  "
            f"buffer={len(buffer)}  policy_loss={pl_mean:.3f}  value_loss={vl_mean:.3f}  "
            f"gen_time={gen_time:.1f}s"
        )


def main() -> None:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    parser = argparse.ArgumentParser(description="Train the Deep Sea Crew policy/value net via self-play.")
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--games-per-iter", type=int, default=20)
    parser.add_argument("--num-simulations", type=int, default=30)
    parser.add_argument("--epochs-per-iter", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--buffer-size", type=int, default=20000)
    parser.add_argument("--checkpoint-dir", type=Path, default=DEFAULT_CHECKPOINT_DIR)
    parser.add_argument("--min-players", type=int, default=3)
    parser.add_argument("--max-players", type=int, default=5)
    parser.add_argument("--min-difficulty", type=int, default=6)
    parser.add_argument("--max-difficulty", type=int, default=10)
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

    run_training(
        iterations=args.iterations,
        games_per_iter=args.games_per_iter,
        num_simulations=args.num_simulations,
        epochs_per_iter=args.epochs_per_iter,
        batch_size=args.batch_size,
        lr=args.lr,
        buffer_size=args.buffer_size,
        checkpoint_dir=args.checkpoint_dir,
        players_range=(args.min_players, args.max_players),
        difficulty_range=(args.min_difficulty, args.max_difficulty),
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
