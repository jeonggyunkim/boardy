"""Optional remote self-play helper: lets a second machine on the same LAN
(e.g. a weaker always-on laptop) contribute self-play games to `train.py`'s
buffer over a plain shared folder, with zero changes to the core self-play/
MCTS/training code -- it only reuses `play_self_play_games_batch`,
`save_checkpoint`/`load_checkpoint`, and `Example` as-is.

Design goals (from the actual failure modes we care about -- the laptop
being unplugged, taken elsewhere, or just never started):
  - The main training loop must NEVER block on or fail because of a remote
    worker. Every read from `--remote-dir` here is opportunistic: if the
    share is unreachable or empty, callers just get nothing back and
    training proceeds exactly as if `--remote-dir` had never been passed.
  - Writes (both the published checkpoint and each results batch) are
    staged to a `*.tmp` path and atomically renamed into place, so a
    reader can never observe a half-written file (e.g. the laptop losing
    its network mid-write).
  - Each results batch is tagged with the *global* iteration count (see
    train.py's `total_so_far`/`elo_state["history"]`) of the checkpoint
    that generated it. The trainer discards batches tagged more than
    `max_staleness` iterations behind its own current count -- a laptop
    that was offline for days and comes back with ancient self-play data
    shouldn't get blended in unbounded; a few iterations of staleness is
    fine (the local replay buffer already mixes ~20 iterations of data at
    steady state, so this only guards against *unbounded* staleness, not
    staleness itself).

Usage on the worker machine (after `pip install -e .` from a clone of this
repo):
    gomoku-remote-selfplay --remote-dir //main-pc/shared/gomoku_selfplay
"""

from __future__ import annotations

import argparse
import io
import random
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import torch

from .network import PolicyValueNet, load_checkpoint
from .self_play import Example, play_self_play_games_batch

CHECKPOINT_SUBDIR = "checkpoint"
INCOMING_SUBDIR = "incoming"


def _atomic_write(path: Path, write_fn) -> None:
    """`write_fn(tmp_path)` writes the file, then it's atomically renamed
    into place -- a reader can only ever see a fully-written file, whether
    it looks a moment before or a moment after this call."""
    tmp = path.with_suffix(path.suffix + f".tmp{uuid.uuid4().hex[:8]}")
    write_fn(tmp)
    tmp.replace(path)


def publish_checkpoint(remote_dir: Path, net: PolicyValueNet, iteration: int) -> None:
    """Called from train.py whenever best_net changes. Best-effort: any
    failure (share unplugged, permissions, whatever) is swallowed -- a
    failed publish just means remote workers keep training against
    whatever they last saw, which is fine (see module docstring)."""
    try:
        ckpt_dir = remote_dir / CHECKPOINT_SUBDIR
        ckpt_dir.mkdir(parents=True, exist_ok=True)
        payload = {"config": net.config, "state_dict": net.state_dict()}
        _atomic_write(ckpt_dir / "best.pt", lambda tmp: torch.save(payload, tmp))
        _atomic_write(ckpt_dir / "iteration.txt", lambda tmp: tmp.write_text(str(iteration)))
    except OSError:
        pass


def load_latest_remote_checkpoint(remote_dir: Path) -> tuple[PolicyValueNet, int] | None:
    """Used by the worker. Returns None (not raises) if nothing's been
    published yet or the share is currently unreachable."""
    try:
        ckpt_dir = remote_dir / CHECKPOINT_SUBDIR
        iteration = int((ckpt_dir / "iteration.txt").read_text().strip())
        net = load_checkpoint(ckpt_dir / "best.pt", device="cpu")
        return net, iteration
    except (OSError, ValueError, KeyError):
        return None


def write_batch(remote_dir: Path, iteration: int, results: list[tuple[list[Example], int | None]]) -> None:
    """Called from the worker after finishing a chunk of self-play games."""
    incoming_dir = remote_dir / INCOMING_SUBDIR
    incoming_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "iteration": iteration,
        "games": [
            {
                "obs": np.stack([e.obs for e in examples]) if examples else np.empty((0,)),
                "policy": np.stack([e.policy for e in examples]) if examples else np.empty((0,)),
                "value": np.array([e.value for e in examples], dtype=np.float32),
                "winner": winner,
            }
            for examples, winner in results
        ],
    }
    name = f"batch_{int(time.time())}_{uuid.uuid4().hex[:8]}.pt"
    _atomic_write(incoming_dir / name, lambda tmp: torch.save(payload, tmp))


def collect_remote_batches(
    remote_dir: Path | None, current_iteration: int, max_staleness: int
) -> tuple[list[Example], int]:
    """Called from train.py's main loop, once per iteration. Opportunistic
    and best-effort throughout: any single unreadable/corrupt batch file
    (e.g. one caught mid-write despite the atomic rename, or left over
    from an old run) is skipped and removed rather than raising -- one
    bad file must never take down the training loop. Returns ([], 0) (not
    an error) if `remote_dir` is None, doesn't exist, or nothing's
    arrived. Second element is the number of *games* collected (for
    logging) -- distinct from len(examples), which counts positions."""
    if remote_dir is None:
        return [], 0
    incoming_dir = remote_dir / INCOMING_SUBDIR
    if not incoming_dir.exists():
        return [], 0

    collected: list[Example] = []
    games_count = 0
    try:
        batch_files = list(incoming_dir.glob("batch_*.pt"))
    except OSError:
        return [], 0

    for f in batch_files:
        try:
            payload = torch.load(f, map_location="cpu", weights_only=False)
            staleness = current_iteration - int(payload["iteration"])
            if 0 <= staleness <= max_staleness:
                for game in payload["games"]:
                    n = len(game["value"])
                    games_count += 1
                    for i in range(n):
                        collected.append(
                            Example(obs=game["obs"][i], policy=game["policy"][i], value=float(game["value"][i]))
                        )
        except Exception:
            pass  # corrupt/partial/unreadable -- drop it, never crash the trainer
        finally:
            try:
                f.unlink(missing_ok=True)  # processed (or unreadable) -- don't look at it again
            except OSError:
                pass
    return collected, games_count


def main() -> None:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
    parser = argparse.ArgumentParser(
        description="Contribute self-play games to a train.py run over a shared folder."
    )
    parser.add_argument("--remote-dir", type=Path, required=True, help="Shared folder path, e.g. a LAN SMB share.")
    parser.add_argument("--games-per-batch", type=int, default=8, help="Kept small -- weak/laptop CPUs shouldn't try to match the main machine's batch size.")
    parser.add_argument("--num-simulations", type=int, default=100, help="Should match train.py's --num-simulations so policy targets are comparable.")
    parser.add_argument("--poll-seconds", type=float, default=5.0, help="How often to retry when no checkpoint has been published yet.")
    args = parser.parse_args()

    print(f"Remote self-play worker starting. remote_dir={args.remote_dir}")
    cached: tuple[PolicyValueNet, int] | None = None
    while True:
        latest = load_latest_remote_checkpoint(args.remote_dir)
        if latest is not None:
            cached = latest
        if cached is None:
            print(f"No checkpoint published yet at {args.remote_dir} -- waiting...")
            time.sleep(args.poll_seconds)
            continue

        net, iteration = cached
        rng_seed = random.randrange(1_000_000_000)
        random.seed(rng_seed)
        np.random.seed(rng_seed)
        t0 = time.time()
        results = play_self_play_games_batch(net, num_games=args.games_per_batch, num_simulations=args.num_simulations)
        elapsed = time.time() - t0
        write_batch(args.remote_dir, iteration, results)
        print(f"iteration={iteration}  games={args.games_per_batch}  time={elapsed:.1f}s  -> batch written")


if __name__ == "__main__":
    main()
