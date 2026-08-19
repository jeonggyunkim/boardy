"""Self-play training loop: generate games with MCTS, fit the network, repeat.

Uses AlphaZero-style gatekeeping: self-play always uses the current *best*
network; after each iteration's gradient updates, the freshly-trained
candidate has to beat the best network in a small arena match before it's
promoted to `best_net`. Without this, self-play can regress for a while
and there's nothing to notice or correct it -- which is exactly what an
early Gomoku run here demonstrated (see docs/PLAN.md): after 15 ungated
iterations, the "trained" network actually lost a real head-to-head
majority to an untrained one.

The candidate (`net`) trains continuously across iterations and is never
rolled back to `best_net`'s weights on rejection -- only `best_net` (the
self-play/deployment network) is gated. An earlier version of this loop
*did* reset `net`'s weights to `best_net` on rejection, but `optimizer`
is created once outside the loop and a `load_state_dict` call only
overwrites parameter values, not Adam's per-parameter momentum/variance
state -- so the optimizer kept accumulating history for a training
trajectory that no longer matched the (rolled-back) weights. A real run
(24 iterations, 2026-08-11, see docs/PLAN.md) showed `value_loss` rising
instead of converging, consistent with exactly this mismatch compounding
across the many rejected iterations. Letting the candidate train through
rejections (standard AlphaZero practice) keeps weights and optimizer
state consistent, and a losing arena match is often just noise anyway
(only `--arena-games` games) rather than a signal the last gradient step
was actually bad.

Self-play/arena games batch their leaf evaluations within each game-group
(see self_play.py / mcts.py's `run_mcts_batch`) -- a batch-size-1 NN call
per MCTS leaf leaves a GPU almost entirely idle. But profiling a real run
(2026-08-11, see docs/PLAN.md) showed the neural net is *not* actually the
bottleneck once it's batched: ~65% of wall time is pure-Python Renju
legal-move checking (`board.py`/`renju.py`), and another ~19% is
CPU<->GPU sync overhead from calling `.cpu()` every simulation round --
the NN forward pass itself is under 2%. So self-play/arena game
generation runs across `--self-play-workers` CPU processes (each still
doing its own batched-MCTS sub-batch, so within a worker the batching
benefit is kept), which spreads the real bottleneck -- Renju logic --
across physical cores instead of leaving it single-threaded, and avoids
the CUDA sync overhead entirely by keeping self-play on CPU. The GPU is
reserved for the training gradient step, where a batch of 128+ boards
going through real matmul/conv work is exactly what it's good at.

Usage:
    python -m boardy.games.gomoku.train --iterations 20 --games-per-iter 64 --device cuda --self-play-workers 10
"""

from __future__ import annotations

import argparse
import io
import json
import os
import random
import sys
import time
from collections import deque
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from .board import DEFAULT_SIZE
from .elo import match_score, update_elo
from .evaluate import arena
from .network import DEFAULT_CHANNELS, DEFAULT_NUM_BLOCKS, PolicyValueNet, load_checkpoint, save_checkpoint
from .remote_selfplay import collect_remote_batches, publish_checkpoint
from .self_play import Example, play_self_play_games_batch

DEFAULT_CHECKPOINT_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "checkpoints_gomoku"
DEFAULT_SELF_PLAY_BATCH_SIZE = 64
DEFAULT_ELO = 1000.0
# Leave a couple of logical cores for the main process (training step,
# checkpoint I/O) and OS/driver overhead. Capped at 16, not cpu_count-2:
# a worker-count sweep on this machine (13th Gen i5-13600KF, 14 physical /
# 20 logical -- 6 P-cores x2 hyperthreads + 8 E-cores x1) originally found
# ~12 workers best (2026-08-11, see docs/PLAN.md), matching exactly the
# P-core hyperthread count. Re-swept post-Numba (2026-08-13, see
# docs/PLAN.md) since that optimization cut each worker's per-game CPU
# cost substantially, changing the balance: throughput now peaks at 16
# workers (~9% faster than 12), i.e. using 2 of the 8 slower E-cores helps
# too now, but going further (18-20, using all of them) regresses again --
# E-cores don't hyperthread and are individually much slower, so beyond a
# handful the added contention outweighs the extra throughput.
DEFAULT_SELF_PLAY_WORKERS = min(16, max(1, (os.cpu_count() or 2) - 2))


def resolve_device(device: str) -> torch.device:
    if device == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return torch.device(device)


def _split_evenly(total: int, parts: int) -> list[int]:
    """Split `total` into `parts` chunks as evenly as possible, dropping any
    chunk that would be 0 (e.g. more workers than games)."""
    parts = max(1, min(parts, total))
    base, extra = divmod(total, parts)
    return [base + (1 if i < extra else 0) for i in range(parts)]


def _self_play_worker(
    payload: tuple[dict, dict, int, int, int, float, float],
) -> list[tuple[list[Example], int | None]]:
    """Runs in a worker process: rebuild the net from a plain state_dict +
    config (nn.Module instances aren't reliably picklable across the spawn
    boundary Windows uses) and play a chunk of games on CPU. One thread per
    process -- letting each of several worker processes also spin up
    torch's default multi-threaded CPU kernels would oversubscribe the
    machine's physical cores and make things slower, not faster."""
    state_dict, config, num_games, num_simulations, seed, dirichlet_alpha, dirichlet_eps = payload
    torch.set_num_threads(1)
    random.seed(seed)
    np.random.seed(seed)
    net = PolicyValueNet(**config)
    net.load_state_dict(state_dict)
    return play_self_play_games_batch(
        net,
        num_games=num_games,
        num_simulations=num_simulations,
        dirichlet_alpha=dirichlet_alpha,
        dirichlet_eps=dirichlet_eps,
    )


def train_on_batch(
    net: PolicyValueNet,
    optimizer: torch.optim.Optimizer,
    batch: list[Example],
    scaler: torch.amp.GradScaler | None = None,
) -> tuple[float, float]:
    net.train()
    device = next(net.parameters()).device
    obs = torch.from_numpy(np.stack([e.obs for e in batch])).float().to(device)
    target_policy = torch.from_numpy(np.stack([e.policy for e in batch])).float().to(device)
    target_value = torch.tensor([e.value for e in batch], dtype=torch.float32, device=device)

    use_amp = scaler is not None and scaler.is_enabled()
    optimizer.zero_grad()
    with torch.autocast(device_type=device.type, enabled=use_amp):
        logits, value = net(obs)
        legal_mask = target_policy > 0
        # -1e4, not -1e9: under autocast this is computed in float16, whose
        # max magnitude (~65504) would overflow on a -1e9 fill.
        masked_logits = logits.masked_fill(~legal_mask, -1e4)
        log_probs = F.log_softmax(masked_logits, dim=-1)
        policy_loss = -(target_policy * log_probs).sum(dim=-1).mean()
        value_loss = F.mse_loss(value, target_value)
        loss = policy_loss + value_loss

    if use_amp:
        scaler.scale(loss).backward()
        scaler.step(optimizer)
        scaler.update()
    else:
        loss.backward()
        optimizer.step()
    return float(policy_loss.item()), float(value_loss.item())


def _generate_self_play(
    best_net: PolicyValueNet,
    games_per_iter: int,
    num_simulations: int,
    self_play_batch_size: int,
    pool: ProcessPoolExecutor | None,
    workers: int,
    rng: random.Random,
    dirichlet_alpha: float = 0.3,
    dirichlet_eps: float = 0.25,
) -> tuple[list[Example], int, int, int]:
    buffer_add: list[Example] = []
    black_wins = white_wins = draws = 0

    if pool is not None:
        state_dict = {k: v.cpu() for k, v in best_net.state_dict().items()}
        config = best_net.config
        chunks = _split_evenly(games_per_iter, workers)
        payloads = [
            (state_dict, config, n, num_simulations, rng.randrange(1_000_000_000), dirichlet_alpha, dirichlet_eps)
            for n in chunks
            if n > 0
        ]
        all_results = [game for chunk_results in pool.map(_self_play_worker, payloads) for game in chunk_results]
    else:
        all_results = []
        remaining = games_per_iter
        while remaining > 0:
            n = min(self_play_batch_size, remaining)
            all_results.extend(
                play_self_play_games_batch(
                    best_net,
                    num_games=n,
                    num_simulations=num_simulations,
                    dirichlet_alpha=dirichlet_alpha,
                    dirichlet_eps=dirichlet_eps,
                )
            )
            remaining -= n

    for examples, winner in all_results:
        buffer_add.extend(examples)
        if winner == 1:
            black_wins += 1
        elif winner == -1:
            white_wins += 1
        else:
            draws += 1
    return buffer_add, black_wins, white_wins, draws


def _prune_iter_checkpoints(checkpoint_dir: Path, keep_last_n: int) -> None:
    """Delete all but the last `keep_last_n` iter_XXXX.pt snapshots
    (best.pt/latest.pt are separate files and always kept).

    Sorts by mtime, not filename -- `it` (the iteration counter baked into
    each filename) always restarts at 1 for every fresh `run_training`
    call, whether starting clean or resuming from a checkpoint. Sorting by
    filename meant a brand-new run's iter_0001.pt sorted *before* a
    previous run's iter_0080.pt, so every snapshot from a resumed run got
    pruned immediately in favor of the previous run's stale leftovers,
    every single iteration, until the new run's own counter happened to
    exceed the old one's highest number. A real 40-iteration continuation
    run (2026-08-12/13, see docs/PLAN.md) lost 100% of its own snapshots
    this way -- confirmed by every surviving iter_*.pt file being from the
    *previous* run, none from the one that had just finished."""
    if keep_last_n <= 0:
        return
    iter_files = sorted(checkpoint_dir.glob("iter_*.pt"), key=lambda f: f.stat().st_mtime)
    for f in iter_files[:-keep_last_n]:
        f.unlink(missing_ok=True)


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
    device: str,
    channels: int,
    num_blocks: int,
    self_play_batch_size: int,
    keep_last_n: int,
    amp: bool,
    self_play_workers: int,
    remote_dir: Path | None,
    remote_max_staleness: int,
    dirichlet_alpha: float,
    dirichlet_eps: float,
) -> None:
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    torch.manual_seed(seed or 0)
    dev = resolve_device(device)
    print(f"Using device: {dev}  self_play_workers={self_play_workers}")

    # Ampere+ (compute capability 8.0+, includes the RTX 3060) can do conv/
    # matmul in TF32 -- much faster than full FP32 with negligible precision
    # loss for this. Harmless no-op if unsupported.
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True
    torch.backends.cudnn.benchmark = True

    pool = ProcessPoolExecutor(max_workers=self_play_workers) if self_play_workers > 1 else None

    best_path = checkpoint_dir / "best.pt"
    latest_path = checkpoint_dir / "latest.pt"  # mirrors candidate; kept for compatibility with ai.py loaders
    elo_path = checkpoint_dir / "elo_ratings.json"

    if best_path.exists():
        loaded = load_checkpoint(best_path, device=dev)
        net = PolicyValueNet(**loaded.config).to(dev)
        net.load_state_dict(loaded.state_dict())
        best_net = PolicyValueNet(**loaded.config).to(dev)
        best_net.load_state_dict(loaded.state_dict())
        print(f"Resumed from {best_path} (config={loaded.config})")
    else:
        net = PolicyValueNet(board_size=DEFAULT_SIZE, channels=channels, num_blocks=num_blocks).to(dev)
        best_net = PolicyValueNet(board_size=DEFAULT_SIZE, channels=channels, num_blocks=num_blocks).to(dev)
        best_net.load_state_dict(net.state_dict())

    if elo_path.exists():
        elo_state = json.loads(elo_path.read_text())
        if "candidate" not in elo_state or "best" not in elo_state:
            # Migrate the old single-rating format: both start from
            # whatever "current" (best_net's rating) had reached.
            legacy = elo_state.get("current", DEFAULT_ELO)
            elo_state = {"candidate": legacy, "best": legacy, "history": elo_state.get("history", [])}
    else:
        elo_state = {"candidate": DEFAULT_ELO, "best": DEFAULT_ELO, "history": []}

    # `it` below is only this *invocation's* counter -- it always restarts
    # at 1, whether starting fresh or resuming, so it can't answer "how
    # many iterations total, across every run so far". `elo_state["history"]`
    # gets exactly one entry appended per iteration and is never trimmed
    # (unlike iter_XXXX.pt snapshots, which get pruned), so its length is
    # the authoritative running total across every restart.
    total_so_far = len(elo_state["history"])
    print(f"Total iterations so far (all runs combined): {total_so_far}")

    if remote_dir is not None:
        # So a remote worker started right after a resume doesn't sit idle
        # waiting for the *next* promotion -- it gets today's best_net
        # immediately, same as local self-play does.
        publish_checkpoint(remote_dir, best_net, total_so_far)
        print(f"Publishing checkpoints for remote workers to: {remote_dir}")

    optimizer = torch.optim.Adam(net.parameters(), lr=lr)
    scaler = torch.amp.GradScaler(dev.type, enabled=(amp and dev.type == "cuda"))
    buffer: deque[Example] = deque(maxlen=buffer_size)

    for it in range(1, iterations + 1):
        t0 = time.time()
        new_examples, black_wins, white_wins, draws = _generate_self_play(
            best_net,
            games_per_iter,
            num_simulations,
            self_play_batch_size,
            pool,
            self_play_workers,
            rng,
            dirichlet_alpha=dirichlet_alpha,
            dirichlet_eps=dirichlet_eps,
        )
        # Remote games are purely additive -- local generation above always
        # targets the full `games_per_iter` on its own, so a remote worker
        # being slow, offline, or never started changes nothing about this
        # iteration's behavior or timing, only how much *extra* data shows
        # up in the buffer. Anything tagged with a checkpoint too old
        # (`remote_max_staleness`) is silently dropped inside this call.
        remote_examples, remote_games = collect_remote_batches(remote_dir, total_so_far + it, remote_max_staleness)
        new_examples = new_examples + remote_examples
        buffer.extend(new_examples)
        gen_time = time.time() - t0

        policy_losses, value_losses = [], []
        if len(buffer) >= batch_size:
            for _ in range(epochs_per_iter):
                batch = rng.sample(list(buffer), batch_size)
                pl, vl = train_on_batch(net, optimizer, batch, scaler)
                policy_losses.append(pl)
                value_losses.append(vl)

        t1 = time.time()
        cand_wins, inc_wins, arena_draws = arena(
            net,
            best_net,
            arena_games,
            arena_simulations,
            batch_size=self_play_batch_size,
            pool=pool,
            workers=self_play_workers,
        )
        arena_time = time.time() - t1
        promoted = cand_wins > inc_wins

        # `net` (candidate) now trains continuously across iterations (see
        # module docstring), so it needs its own persisted rating instead
        # of assuming it starts each match level with best_net -- after
        # several rejected iterations in a row it may have drifted well
        # away from best_net's last-measured strength.
        score = match_score(cand_wins, inc_wins, arena_draws)
        new_cand_elo, new_best_elo = update_elo(elo_state["candidate"], elo_state["best"], score)
        elo_state["candidate"] = new_cand_elo
        elo_state["best"] = new_cand_elo if promoted else new_best_elo
        elo_state["history"].append(
            {"iteration": it, "candidate": elo_state["candidate"], "best": elo_state["best"], "promoted": promoted}
        )
        elo_path.write_text(json.dumps(elo_state, indent=2))

        if promoted:
            best_net.load_state_dict(net.state_dict())
            save_checkpoint(best_net, best_path)
            if remote_dir is not None:
                publish_checkpoint(remote_dir, best_net, total_so_far + it)
        # else: rejected -- `net` is *not* rolled back, see module docstring.
        save_checkpoint(net, latest_path)
        save_checkpoint(best_net, checkpoint_dir / f"iter_{it:04d}.pt")
        _prune_iter_checkpoints(checkpoint_dir, keep_last_n)

        pl_mean = np.mean(policy_losses) if policy_losses else float("nan")
        vl_mean = np.mean(value_losses) if value_losses else float("nan")
        print(
            f"iter {it}/{iterations} (total={len(elo_state['history'])})  "
            f"selfplay(best): black={black_wins} white={white_wins} draw={draws} remote_games={remote_games}  "
            f"buffer={len(buffer)}  policy_loss={pl_mean:.3f}  value_loss={vl_mean:.3f}  "
            f"arena: cand={cand_wins} inc={inc_wins} draw={arena_draws} -> "
            f"{'PROMOTED' if promoted else 'rejected'}  "
            f"elo_best={elo_state['best']:.1f} elo_cand={elo_state['candidate']:.1f}  "
            f"gen_time={gen_time:.1f}s arena_time={arena_time:.1f}s"
        )

    if pool is not None:
        pool.shutdown()


def main() -> None:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        # line_buffering=True -- without it this wrapper defaults to full
        # block buffering when stdout is redirected to a file (not a TTY),
        # silently swallowing every per-iteration progress line until the
        # buffer fills or the process exits. A ~13-hour background training
        # run with a UTF-8-hostile console codepage (cp949 on this Windows
        # machine) produced an empty log file for over an hour because of
        # this (2026-08-12, see docs/PLAN.md) -- easy to mistake for a hang.
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
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
    parser.add_argument("--device", type=str, default="auto", help="'cuda', 'cpu', or 'auto' (default).")
    parser.add_argument("--channels", type=int, default=DEFAULT_CHANNELS, help="Ignored when resuming a checkpoint.")
    parser.add_argument(
        "--num-blocks", type=int, default=DEFAULT_NUM_BLOCKS, help="Ignored when resuming a checkpoint."
    )
    parser.add_argument(
        "--self-play-batch-size",
        type=int,
        default=DEFAULT_SELF_PLAY_BATCH_SIZE,
        help="Concurrent games per self-play/arena batch when --self-play-workers=1 (in-process, GPU-batched path).",
    )
    parser.add_argument(
        "--self-play-workers",
        type=int,
        default=DEFAULT_SELF_PLAY_WORKERS,
        help=(
            "CPU worker processes for self-play/arena game generation (1 disables multiprocessing, "
            "falls back to the in-process --device path). Profiling shows Renju legal-move checking, "
            "not the neural net, dominates self-play time, so spreading games across CPU cores beats "
            f"GPU batching alone. Default is cpu_count-2 ({DEFAULT_SELF_PLAY_WORKERS} on this machine)."
        ),
    )
    parser.add_argument(
        "--keep-last-n",
        type=int,
        default=5,
        help="Keep only the last N per-iteration checkpoint snapshots (best.pt/latest.pt always kept). 0 keeps all.",
    )
    parser.add_argument("--amp", action=argparse.BooleanOptionalAction, default=True, help="Mixed precision on CUDA.")
    parser.add_argument(
        "--remote-dir",
        type=Path,
        default=None,
        help=(
            "Shared folder (e.g. a LAN SMB share) for optional remote self-play workers "
            "(see remote_selfplay.py). Publishes best_net there on every promotion and opportunistically "
            "collects any self-play games workers have dropped off, every iteration. Purely additive: "
            "unset (default), or the share being unreachable, changes nothing about local behavior."
        ),
    )
    parser.add_argument(
        "--remote-max-staleness",
        type=int,
        default=30,
        help=(
            "Discard remote self-play batches tagged more than this many total-iterations behind the "
            "current one -- guards against a worker that was offline a long time dumping ancient data "
            "back in. Roughly matches how much staleness the local replay buffer already tolerates."
        ),
    )
    parser.add_argument(
        "--dirichlet-alpha",
        type=float,
        default=0.3,
        help=(
            "Root exploration-noise concentration for self-play (arena/human play never use noise). "
            "Lower = noise spikes onto fewer candidates per draw; higher = spreads more evenly."
        ),
    )
    parser.add_argument(
        "--dirichlet-eps",
        type=float,
        default=0.25,
        help=(
            "Weight of that noise in the root prior mix (child.prior = (1-eps)*policy + eps*noise). "
            "Raising this gives moves the trained policy currently dismisses (e.g. a defensive move it "
            "hasn't learned matters yet) a better chance of being tried at least once per search -- "
            "without that one try, self-play never generates a training example showing what actually "
            "happens, and the blind spot can't self-correct (see docs/PLAN.md 2026-08-17)."
        ),
    )
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
        device=args.device,
        channels=args.channels,
        num_blocks=args.num_blocks,
        self_play_batch_size=args.self_play_batch_size,
        keep_last_n=args.keep_last_n,
        amp=args.amp,
        self_play_workers=args.self_play_workers,
        remote_dir=args.remote_dir,
        remote_max_staleness=args.remote_max_staleness,
        dirichlet_alpha=args.dirichlet_alpha,
        dirichlet_eps=args.dirichlet_eps,
    )


if __name__ == "__main__":
    main()
