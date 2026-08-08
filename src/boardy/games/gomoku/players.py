"""Player interface — human/random now, AlphaZero MCTS player for real play."""

from __future__ import annotations

import random
from abc import ABC, abstractmethod

from .board import Board
from .mcts import run_mcts, select_action


class Player(ABC):
    name: str

    @abstractmethod
    def choose_move(self, board: Board) -> str: ...


class RandomPlayer(Player):
    def __init__(self, name: str = "bot", rng: random.Random | None = None) -> None:
        self.name = name
        self.rng = rng or random.Random()

    def choose_move(self, board: Board) -> str:
        r, c = self.rng.choice(board.legal_moves())
        return f"{r},{c}"


class NetPlayer(Player):
    """Plays using a trained PolicyValueNet + PUCT search (real MCTS, no
    determinization needed — Gomoku is perfect information)."""

    def __init__(
        self,
        net,
        name: str = "ai",
        num_simulations: int = 200,
        c_puct: float = 1.5,
        temperature: float = 0.0,
    ) -> None:
        self.name = name
        self.net = net
        self.num_simulations = num_simulations
        self.c_puct = c_puct
        self.temperature = temperature

    def choose_move(self, board: Board) -> str:
        probs = run_mcts(board, self.net, num_simulations=self.num_simulations, c_puct=self.c_puct)
        return select_action(probs, temperature=self.temperature)
