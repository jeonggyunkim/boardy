"""Self-play training loop: generate games with MCTS, fit the network, repeat.

Uses AlphaZero-style gatekeeping: self-play always uses the current *best*
network; after each iteration's gradient updates, the freshly-trained
candidate has to beat the best network in a small arena match before it's
promoted. If it doesn't, the candidate is reset to the best network's
weights and training continues from there. Without this, a network can
regress for a while and there's nothing to notice or correct it -- which
is exactly what an early Gomoku run here demonstrated (see docs/PLAN.md):
after 15 ungated iterations, the "trained" network actually lost a real
head-to-head majority to an untrained one.

Usage:
    python -m boardy.games.gomoku.train --iterations 20 --games-per-iter 20
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

from .evaluate import arena
from .network import PolicyValueNet
from .self_play import Example, play_self_play_game

DEFAULT_CHECKPOINT_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "checkpoints_gomoku"


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
    value_loss = F.mse_loss(value, target_value)
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
    arena_games: int,
    arena_simulations: int,
    seed: int | None,
) -> None:
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    torch.manual_seed(seed or 0)

    net = PolicyValueNet()  # candidate being trained this iteration
    best_net = PolicyValueNet()  # incumbent: used for self-play + arena baseline
    best_path = checkpoint_dir / "best.pt"
    latest_path = checkpoint_dir / "latest.pt"  # mirrors best.pt; kept for compatibility with ai.py loaders
    if best_path.exists():
        state = torch.load(best_path, map_location="cpu")
        net.load_state_dict(state)
        best_net.load_state_dict(state)
        print(f"Resumed from {best_path}")
    else:
        best_net.load_state_dict(net.state_dict())

    optimizer = torch.optim.Adam(net.parameters(), lr=lr)
    buffer: deque[Example] = deque(maxlen=buffer_size)

    for it in range(1, iterations + 1):
        t0 = time.time()
        black_wins = white_wins = draws = 0
        for _ in range(games_per_iter):
            examples, winner = play_self_play_game(best_net, num_simulations=num_simulations)
            buffer.extend(examples)
            if winner == 1:
                black_wins += 1
            elif winner == -1:
                white_wins += 1
            else:
                draws += 1
        gen_time = time.time() - t0

        policy_losses, value_losses = [], []
        if len(buffer) >= batch_size:
            for _ in range(epochs_per_iter):
                batch = rng.sample(list(buffer), batch_size)
                pl, vl = train_on_batch(net, optimizer, batch)
                policy_losses.append(pl)
                value_losses.append(vl)

        t1 = time.time()
        cand_wins, inc_wins, arena_draws = arena(net, best_net, arena_games, arena_simulations)
        arena_time = time.time() - t1
        promoted = cand_wins > inc_wins
        if promoted:
            best_net.load_state_dict(net.state_dict())
            torch.save(best_net.state_dict(), best_path)
        else:
            net.load_state_dict(best_net.state_dict())  # reject: reset candidate to incumbent
        torch.save(net.state_dict(), latest_path)
        torch.save(best_net.state_dict(), checkpoint_dir / f"iter_{it:04d}.pt")

        pl_mean = np.mean(policy_losses) if policy_losses else float("nan")
        vl_mean = np.mean(value_losses) if value_losses else float("nan")
        print(
            f"iter {it}/{iterations}  selfplay(best): black={black_wins} white={white_wins} draw={draws}  "
            f"buffer={len(buffer)}  policy_loss={pl_mean:.3f}  value_loss={vl_mean:.3f}  "
            f"arena: cand={cand_wins} inc={inc_wins} draw={arena_draws} -> "
            f"{'PROMOTED' if promoted else 'rejected'}  "
            f"gen_time={gen_time:.1f}s arena_time={arena_time:.1f}s"
        )


def main() -> None:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    parser = argparse.ArgumentParser(description="Train the Gomoku policy/value net via self-play.")
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--games-per-iter", type=int, default=20)
    parser.add_argument("--num-simulations", type=int, default=100)
    parser.add_argument("--epochs-per-iter", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--buffer-size", type=int, default=50000)
    parser.add_argument("--checkpoint-dir", type=Path, default=DEFAULT_CHECKPOINT_DIR)
    parser.add_argument("--arena-games", type=int, default=12)
    parser.add_argument("--arena-simulations", type=int, default=80)
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
        arena_games=args.arena_games,
        arena_simulations=args.arena_simulations,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
