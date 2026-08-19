"""Strength evaluation: candidate-vs-incumbent arena (used for training
gatekeeping), a trained net vs. RandomPlayer sanity check, and an ad-hoc
two-checkpoint comparison with an Elo estimate.

Game generation batches games by whose turn it currently is, so each
side's MCTS search evaluates its leaves across many concurrent games in
one NN forward pass -- see mcts.py's `run_mcts_batch` docstring. Profiling
(2026-08-11, see docs/PLAN.md) showed this NN batching isn't actually the
bottleneck though -- pure-Python Renju legality checks dominate wall time
by a wide margin -- so `arena()` can optionally spread games across CPU
worker processes (`pool`/`workers`) to use multiple physical cores for
that Python-bound work, same as `train.py`'s self-play generation.
"""

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
from .elo import update_elo
from .engine import new_game
from .mcts import run_mcts_batch, select_action
from .network import PolicyValueNet, load_checkpoint

DEFAULT_ARENA_BATCH_SIZE = 64


def _split_evenly(total: int, parts: int) -> list[int]:
    """Split `total` into `parts` chunks as evenly as possible."""
    parts = max(1, min(parts, total))
    base, extra = divmod(total, parts)
    return [base + (1 if i < extra else 0) for i in range(parts)]


def play_game(black, white) -> int:
    """Single-game convenience wrapper around Player.choose_move (e.g. for
    human-vs-AI or scripts that don't care about batched throughput)."""
    board: Board = new_game()
    players = {1: black, -1: white}
    while board.winner is None:
        mover = players[board.to_move]
        action = mover.choose_move(board)
        r, c = (int(v) for v in action.split(","))
        board.play(r, c)
    return board.winner  # 1=black won, -1=white won, 0=draw


def _play_two_net_games(
    net_a: PolicyValueNet,
    net_b: PolicyValueNet,
    num_games: int,
    num_simulations: int,
    temperature: float,
    start_idx: int = 0,
) -> list[tuple[int, int]]:
    """Play `num_games` games between net_a and net_b concurrently,
    alternating who plays black. Within a single game, a color's MCTS
    search only ever calls that color's own net -- so each ply, games are
    split by whose turn it is and each side's boards are batched into one
    `run_mcts_batch` call. Returns (winner, a_color) per game.

    `start_idx` offsets the alternation pattern -- callers that split a
    match into several chunks (multiprocess workers, or batches capped at
    `batch_size`) must pass each chunk's starting position in the overall
    match, not just 0, or every chunk restarts at "a plays black" and the
    alternation never actually happens across chunk boundaries. This was a
    real bug here: with `arena_games=12, self_play_workers=12` every chunk
    was exactly 1 game, so the candidate played black in literally all 12
    arena games, every iteration (see docs/PLAN.md, 2026-08-11)."""
    boards = [new_game() for _ in range(num_games)]
    a_color = [1 if (start_idx + g) % 2 == 0 else -1 for g in range(num_games)]
    active = list(range(num_games))

    while active:
        a_turn = [i for i in active if boards[i].to_move == a_color[i]]
        b_turn = [i for i in active if boards[i].to_move != a_color[i]]

        for idxs, net in ((a_turn, net_a), (b_turn, net_b)):
            if not idxs:
                continue
            sub_boards = [boards[i] for i in idxs]
            visit_probs_list = run_mcts_batch(sub_boards, net, num_simulations=num_simulations)
            for i, visit_probs in zip(idxs, visit_probs_list):
                action = select_action(visit_probs, temperature=temperature)
                r, c = (int(v) for v in action.split(","))
                boards[i].play(r, c)

        active = [i for i in active if boards[i].winner is None]

    return [(boards[i].winner, a_color[i]) for i in range(num_games)]


def _arena_worker(
    payload: tuple[dict, dict, dict, dict, int, int, float, int, int],
) -> list[tuple[int, int]]:
    """Runs in a worker process (see train.py's `_self_play_worker` for why
    plain state_dicts + configs, not nn.Module instances, cross the
    process boundary, and why num_threads is pinned to 1 here)."""
    cand_state, cand_config, inc_state, inc_config, n, num_simulations, temperature, start_idx, seed = payload
    torch.set_num_threads(1)
    random.seed(seed)
    np.random.seed(seed)
    candidate = PolicyValueNet(**cand_config)
    candidate.load_state_dict(cand_state)
    incumbent = PolicyValueNet(**inc_config)
    incumbent.load_state_dict(inc_state)
    return _play_two_net_games(candidate, incumbent, n, num_simulations, temperature, start_idx=start_idx)


def arena(
    candidate: PolicyValueNet,
    incumbent: PolicyValueNet,
    num_games: int,
    num_simulations: int,
    temperature: float = 0.4,
    batch_size: int = DEFAULT_ARENA_BATCH_SIZE,
    pool: ProcessPoolExecutor | None = None,
    workers: int = 1,
) -> tuple[int, int, int]:
    """Play candidate vs incumbent, alternating colors. temperature > 0 so
    games are actually independent (not the same deterministic game
    replayed with colors swapped). Returns (candidate_wins, incumbent_wins,
    draws).

    Without a `pool`, plays in-process in batches of up to `batch_size`
    concurrent games (using whatever device the nets are already on). With
    a `pool`, splits `num_games` across `workers` CPU processes instead --
    see the module docstring for why that's the faster option whenever
    multiple cores are available."""
    cand_wins = inc_wins = draws = 0

    if pool is not None:
        rng = random.Random()
        cand_state = {k: v.cpu() for k, v in candidate.state_dict().items()}
        inc_state = {k: v.cpu() for k, v in incumbent.state_dict().items()}
        chunks = [n for n in _split_evenly(num_games, workers) if n > 0]
        payloads = []
        start_idx = 0
        for n in chunks:
            payloads.append(
                (
                    cand_state,
                    candidate.config,
                    inc_state,
                    incumbent.config,
                    n,
                    num_simulations,
                    temperature,
                    start_idx,
                    rng.randrange(1_000_000_000),
                )
            )
            start_idx += n
        all_results = [game for chunk in pool.map(_arena_worker, payloads) for game in chunk]
    else:
        all_results = []
        remaining = num_games
        start_idx = 0
        while remaining > 0:
            n = min(batch_size, remaining)
            all_results.extend(
                _play_two_net_games(candidate, incumbent, n, num_simulations, temperature, start_idx=start_idx)
            )
            remaining -= n
            start_idx += n

    for winner, cand_color in all_results:
        if winner == 0:
            draws += 1
        elif winner == cand_color:
            cand_wins += 1
        else:
            inc_wins += 1
    return cand_wins, inc_wins, draws


def _play_vs_random_games(
    net: PolicyValueNet,
    num_games: int,
    num_simulations: int,
    rng: random.Random,
    start_idx: int = 0,
) -> list[tuple[int, int]]:
    """Same batching idea as `_play_two_net_games` (including the same
    `start_idx` chunk-offset requirement -- see its docstring), but one
    side is a RandomPlayer (no NN call needed for it). Returns
    (winner, ai_color)."""
    boards = [new_game() for _ in range(num_games)]
    ai_color = [1 if (start_idx + g) % 2 == 0 else -1 for g in range(num_games)]
    active = list(range(num_games))

    while active:
        ai_turn = [i for i in active if boards[i].to_move == ai_color[i]]
        rand_turn = [i for i in active if boards[i].to_move != ai_color[i]]

        if ai_turn:
            sub_boards = [boards[i] for i in ai_turn]
            visit_probs_list = run_mcts_batch(sub_boards, net, num_simulations=num_simulations)
            for i, visit_probs in zip(ai_turn, visit_probs_list):
                action = select_action(visit_probs, temperature=0.0)
                r, c = (int(v) for v in action.split(","))
                boards[i].play(r, c)

        for i in rand_turn:
            r, c = rng.choice(boards[i].legal_moves())
            boards[i].play(r, c)

        active = [i for i in active if boards[i].winner is None]

    return [(boards[i].winner, ai_color[i]) for i in range(num_games)]


def run_eval(
    checkpoint: Path | None,
    num_games: int,
    num_simulations: int,
    seed: int,
    batch_size: int = DEFAULT_ARENA_BATCH_SIZE,
) -> None:
    if checkpoint is not None:
        net = load_checkpoint(checkpoint, device="cpu")
        print(f"Loaded checkpoint: {checkpoint} (config={net.config})")
    else:
        net = PolicyValueNet()
        print("No checkpoint given - evaluating an UNTRAINED network (sanity check only).")

    rng = random.Random(seed)
    ai_wins = ai_losses = draws = 0
    remaining = num_games
    start_idx = 0
    while remaining > 0:
        n = min(batch_size, remaining)
        for winner, ai_color in _play_vs_random_games(net, n, num_simulations, rng, start_idx=start_idx):
            if winner == 0:
                draws += 1
            elif winner == ai_color:
                ai_wins += 1
            else:
                ai_losses += 1
        remaining -= n
        start_idx += n

    print(f"\nGames: {num_games}, sims/move={num_simulations}")
    print(f"AI wins:   {ai_wins}/{num_games} = {ai_wins / num_games:.1%}")
    print(f"AI losses: {ai_losses}/{num_games} = {ai_losses / num_games:.1%}")
    print(f"Draws:     {draws}/{num_games} = {draws / num_games:.1%}")


def run_vs_checkpoint(
    checkpoint_a: Path,
    checkpoint_b: Path,
    num_games: int,
    num_simulations: int,
    seed: int,
    batch_size: int = DEFAULT_ARENA_BATCH_SIZE,
    workers: int = 1,
) -> None:
    """Ad-hoc two-checkpoint comparison outside the training loop, with a
    one-shot Elo estimate (both nets assumed to start at 1000 -- this is a
    relative estimate from this match alone, not a calibrated rating)."""
    net_a = load_checkpoint(checkpoint_a, device="cpu")
    net_b = load_checkpoint(checkpoint_b, device="cpu")
    random.seed(seed)
    np.random.seed(seed)
    pool = ProcessPoolExecutor(max_workers=workers) if workers > 1 else None
    try:
        a_wins, b_wins, draws = arena(
            net_a, net_b, num_games, num_simulations, batch_size=batch_size, pool=pool, workers=workers
        )
    finally:
        if pool is not None:
            pool.shutdown()

    total = a_wins + b_wins + draws
    score_a = (a_wins + 0.5 * draws) / total
    elo_a, elo_b = update_elo(1000.0, 1000.0, score_a)

    print(f"A={checkpoint_a}  B={checkpoint_b}")
    print(f"A wins: {a_wins}/{total}  B wins: {b_wins}/{total}  draws: {draws}/{total}")
    print(f"One-shot Elo estimate (both start at 1000): A={elo_a:.1f}  B={elo_b:.1f}  diff={elo_a - elo_b:+.1f}")


def main() -> None:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        # line_buffering=True -- see train.py's identical fix for why.
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
    parser = argparse.ArgumentParser(description="Evaluate a trained Gomoku net.")
    parser.add_argument("--checkpoint", type=Path, default=None)
    parser.add_argument("--vs-checkpoint", type=Path, default=None, help="Compare --checkpoint against this one.")
    parser.add_argument("--num-games", type=int, default=30)
    parser.add_argument("--num-simulations", type=int, default=200)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_ARENA_BATCH_SIZE)
    parser.add_argument(
        "--workers", type=int, default=1, help="CPU worker processes for --vs-checkpoint (1 = no multiprocessing)."
    )
    args = parser.parse_args()

    if args.vs_checkpoint is not None:
        if args.checkpoint is None:
            parser.error("--vs-checkpoint requires --checkpoint")
        run_vs_checkpoint(
            args.checkpoint,
            args.vs_checkpoint,
            num_games=args.num_games,
            num_simulations=args.num_simulations,
            seed=args.seed,
            batch_size=args.batch_size,
            workers=args.workers,
        )
    else:
        run_eval(
            checkpoint=args.checkpoint,
            num_games=args.num_games,
            num_simulations=args.num_simulations,
            seed=args.seed,
            batch_size=args.batch_size,
        )


if __name__ == "__main__":
    main()
