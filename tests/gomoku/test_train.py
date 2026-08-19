import time

from boardy.games.gomoku.train import _prune_iter_checkpoints


def test_prune_keeps_most_recently_written_files_not_highest_numbered(tmp_path):
    """Regression test: a fresh `run_training` call always restarts its
    iteration counter at 1, so a resumed run's iter_0001.pt can be written
    *after* a previous run's iter_0080.pt but sort *before* it by filename.
    Pruning must go by actual write time, not the number baked into the
    name -- otherwise every snapshot from the new run gets deleted in
    favor of the old run's stale leftovers (a real bug, 2026-08-12/13, see
    docs/PLAN.md: a 40-iteration continuation run lost 100% of its own
    checkpoints this way)."""
    # Simulate: an old run left behind high-numbered files...
    old_files = [tmp_path / f"iter_{n:04d}.pt" for n in (76, 77, 78, 79, 80)]
    for f in old_files:
        f.write_bytes(b"old")
        time.sleep(0.01)

    # ...then a *new* run starts, counter reset to 1, written later in time.
    new_files = [tmp_path / f"iter_{n:04d}.pt" for n in (1, 2, 3)]
    for f in new_files:
        f.write_bytes(b"new")
        time.sleep(0.01)

    _prune_iter_checkpoints(tmp_path, keep_last_n=5)

    remaining = {f.name for f in tmp_path.glob("iter_*.pt")}
    # The 5 most recently *written* files should survive -- that's the old
    # run's last two (79, 80) plus all three of the new run's (1, 2, 3).
    expected = {"iter_0079.pt", "iter_0080.pt", "iter_0001.pt", "iter_0002.pt", "iter_0003.pt"}
    assert remaining == expected
