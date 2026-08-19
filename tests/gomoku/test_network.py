from boardy.games.gomoku.network import PolicyValueNet, load_checkpoint, save_checkpoint


def test_checkpoint_round_trip_preserves_config_and_weights(tmp_path):
    net = PolicyValueNet(board_size=6, channels=8, num_blocks=2)
    path = tmp_path / "net.pt"
    save_checkpoint(net, path)

    loaded = load_checkpoint(path, device="cpu")
    assert loaded.config == net.config

    for (name, p1), (_, p2) in zip(net.state_dict().items(), loaded.state_dict().items()):
        assert (p1 == p2).all(), name


def test_load_checkpoint_rejects_old_format(tmp_path):
    import torch

    net = PolicyValueNet(board_size=6, channels=8, num_blocks=1)
    path = tmp_path / "old.pt"
    torch.save(net.state_dict(), path)  # old format: raw state_dict, no config

    try:
        load_checkpoint(path, device="cpu")
        assert False, "expected ValueError"
    except ValueError:
        pass
