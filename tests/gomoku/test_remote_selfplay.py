import numpy as np
import torch

from boardy.games.gomoku.network import PolicyValueNet
from boardy.games.gomoku.remote_selfplay import (
    collect_remote_batches,
    load_latest_remote_checkpoint,
    publish_checkpoint,
    write_batch,
)
from boardy.games.gomoku.self_play import Example

TINY = dict(board_size=6, channels=8, num_blocks=1)


def _fake_game(n_positions: int = 3) -> tuple[list[Example], int | None]:
    examples = [
        Example(obs=np.zeros((4, 6, 6), dtype=np.float32), policy=np.ones(36, dtype=np.float32) / 36, value=1.0)
        for _ in range(n_positions)
    ]
    return examples, 1


def test_publish_and_load_remote_checkpoint_round_trip(tmp_path):
    net = PolicyValueNet(**TINY)
    publish_checkpoint(tmp_path, net, iteration=42)

    loaded = load_latest_remote_checkpoint(tmp_path)
    assert loaded is not None
    loaded_net, iteration = loaded
    assert iteration == 42
    assert loaded_net.config == net.config


def test_load_remote_checkpoint_missing_returns_none(tmp_path):
    # Nothing published yet -- must not raise, callers rely on this.
    assert load_latest_remote_checkpoint(tmp_path / "never_created") is None


def test_write_and_collect_batch_round_trip(tmp_path):
    results = [_fake_game(3), _fake_game(5)]
    write_batch(tmp_path, iteration=10, results=results)

    examples, games = collect_remote_batches(tmp_path, current_iteration=10, max_staleness=30)
    assert games == 2
    assert len(examples) == 3 + 5


def test_collect_batches_drops_stale_ones(tmp_path):
    write_batch(tmp_path, iteration=10, results=[_fake_game(3)])

    # Current iteration is way ahead -- this batch is older than max_staleness allows.
    examples, games = collect_remote_batches(tmp_path, current_iteration=100, max_staleness=30)
    assert examples == []
    assert games == 0


def test_collect_batches_consumes_files_only_once(tmp_path):
    write_batch(tmp_path, iteration=10, results=[_fake_game(3)])

    collect_remote_batches(tmp_path, current_iteration=10, max_staleness=30)
    # Second call, same iteration -- the file was already consumed (and
    # deleted) by the first call, so nothing should be collected again.
    examples, games = collect_remote_batches(tmp_path, current_iteration=10, max_staleness=30)
    assert examples == []
    assert games == 0


def test_collect_batches_skips_corrupt_file_without_raising(tmp_path):
    incoming = tmp_path / "incoming"
    incoming.mkdir(parents=True)
    (incoming / "batch_bad_1.pt").write_bytes(b"not a valid torch checkpoint")
    write_batch(tmp_path, iteration=10, results=[_fake_game(3)])

    # Must not raise despite the corrupt file sitting alongside a good one.
    examples, games = collect_remote_batches(tmp_path, current_iteration=10, max_staleness=30)
    assert games == 1
    assert len(examples) == 3
    # The corrupt file should have been removed too, not left to be retried forever.
    assert not (incoming / "batch_bad_1.pt").exists()


def test_collect_batches_with_no_remote_dir_returns_empty():
    examples, games = collect_remote_batches(None, current_iteration=10, max_staleness=30)
    assert examples == []
    assert games == 0
