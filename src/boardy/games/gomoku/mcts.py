"""Standard AlphaZero PUCT search: real 2-player zero-sum minimax-by-backup.

Unlike Deep Sea Crew (cooperative, single shared value, no sign flips),
Gomoku is adversarial: each node's average value is stored from the
perspective of *that node's* player-to-move, and gets negated once per
ply on the way back up the tree (`value = -value` in the backup loop) —
the textbook AlphaZero convention. A child's value is therefore from the
opponent's perspective relative to its parent, hence the `-child.value`
in the PUCT score.
"""

from __future__ import annotations

import math

import numpy as np

from .board import Board
from .encoding import action_to_index
from .network import PolicyValueNet


class Node:
    __slots__ = ("board", "prior", "children", "visit_count", "value_sum", "expanded")

    def __init__(self, board: Board, prior: float = 0.0) -> None:
        self.board = board
        self.prior = prior
        self.children: dict[str, Node] = {}
        self.visit_count = 0
        self.value_sum = 0.0
        self.expanded = False

    @property
    def value(self) -> float:
        return self.value_sum / self.visit_count if self.visit_count else 0.0

    @property
    def is_terminal(self) -> bool:
        return self.board.winner is not None


def _terminal_value(board: Board) -> float:
    """Value from the perspective of `board.to_move` at a finished game.
    The winner (if any) is always the side that just moved, i.e. never
    to_move, so a decisive result is always a loss (-1) from this
    viewpoint; a draw is 0."""
    return 0.0 if board.winner == 0 else -1.0


def _expand(node: Node, net: PolicyValueNet) -> float:
    if node.is_terminal:
        return _terminal_value(node.board)

    probs, value = net.predict(node.board)
    size = node.board.size
    for r, c in node.board.legal_moves():
        action = f"{r},{c}"
        idx = action_to_index(action, size)
        child_board = node.board.clone()
        child_board.play(r, c)
        node.children[action] = Node(child_board, prior=float(probs[idx]))
    node.expanded = True
    return value


def _puct_select(node: Node, c_puct: float) -> tuple[str, Node]:
    total_visits = sum(c.visit_count for c in node.children.values())
    sqrt_total = math.sqrt(max(total_visits, 1))

    def score(child: Node) -> float:
        return -child.value + c_puct * child.prior * sqrt_total / (1 + child.visit_count)

    action, child = max(node.children.items(), key=lambda kv: score(kv[1]))
    return action, child


def add_dirichlet_noise(node: Node, alpha: float = 0.3, eps: float = 0.25) -> None:
    if not node.children:
        return
    noise = np.random.dirichlet([alpha] * len(node.children))
    for (action, child), n in zip(node.children.items(), noise):
        child.prior = (1 - eps) * child.prior + eps * n


def run_mcts(
    root_board: Board,
    net: PolicyValueNet,
    num_simulations: int = 100,
    c_puct: float = 1.5,
    add_noise: bool = False,
) -> dict[str, float]:
    """Return a visit-count policy (normalized) over legal actions at the root."""
    root = Node(root_board.clone())
    _expand(root, net)
    if add_noise:
        add_dirichlet_noise(root)

    for _ in range(num_simulations):
        path = [root]
        node = root
        while node.expanded and not node.is_terminal:
            _, node = _puct_select(node, c_puct)
            path.append(node)

        leaf_value = _expand(node, net) if not node.expanded else node.value

        value = leaf_value
        for n in reversed(path):
            n.visit_count += 1
            n.value_sum += value
            value = -value

    total = sum(c.visit_count for c in root.children.values())
    if total == 0:
        legal = [f"{r},{c}" for r, c in root_board.legal_moves()]
        return {a: 1.0 / len(legal) for a in legal}
    return {action: child.visit_count / total for action, child in root.children.items()}


def select_action(visit_probs: dict[str, float], temperature: float = 1.0) -> str:
    actions = list(visit_probs.keys())
    if temperature <= 1e-3:
        return max(actions, key=lambda a: visit_probs[a])
    weights = np.array([visit_probs[a] ** (1.0 / temperature) for a in actions], dtype=np.float64)
    weights /= weights.sum()
    return actions[np.random.choice(len(actions), p=weights)]
