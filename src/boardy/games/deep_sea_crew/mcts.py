"""PUCT tree search.

Because Deep Sea Crew is fully cooperative (every player shares the same
mission-success reward) and turn-based (exactly one seat acts at a time),
search reduces to single-agent MCTS over an MDP: no minimax sign-flipping,
just backing up a shared scalar value (P(mission succeeds)) up the tree.

Two ways this module is used:
- Training (`run_mcts`): search directly over the *true* GameState (every
  hand visible) — an omniscient oracle used only to generate strong self-play
  targets. The network itself only ever sees a partial-info encoding of the
  seat to act, so what it learns still generalizes to hidden-information play.
- Inference (`run_ismcts` in mcts_inference.py): the real player doesn't get
  an oracle, so search runs over several *determinizations* (guessed
  complete deals consistent with public information) and averages results.
"""

from __future__ import annotations

import copy
import math

import numpy as np

from .cards import Card
from .encoding import CARD_TO_INDEX, encode_observation, legal_action_mask
from .engine import GameState
from .network import PolicyValueNet


class Node:
    __slots__ = ("state", "seat", "prior", "children", "visit_count", "value_sum", "expanded")

    def __init__(self, state: GameState, prior: float = 0.0) -> None:
        self.state = state
        self.seat = state.player_to_act
        self.prior = prior
        self.children: dict[Card, Node] = {}
        self.visit_count = 0
        self.value_sum = 0.0
        self.expanded = False

    @property
    def value(self) -> float:
        return self.value_sum / self.visit_count if self.visit_count else 0.0

    @property
    def is_terminal(self) -> bool:
        return self.state.outcome is not None


def _expand(node: Node, net: PolicyValueNet) -> float:
    """Evaluate `node` with the network, create children, return leaf value."""
    if node.is_terminal:
        return 1.0 if node.state.outcome else 0.0

    obs = encode_observation(node.state, node.seat)
    mask = legal_action_mask(node.state, node.seat)
    priors, value = net.predict(obs, mask)

    for card in node.state.legal_cards_for(node.seat):
        child_state = copy.deepcopy(node.state)
        child_state.play_card(node.seat, card)
        node.children[card] = Node(child_state, prior=float(priors[CARD_TO_INDEX[card]]))
    node.expanded = True
    return value


def _puct_select(node: Node, c_puct: float) -> tuple[Card, Node]:
    total_visits = sum(c.visit_count for c in node.children.values())
    sqrt_total = math.sqrt(max(total_visits, 1))

    def score(child: Node) -> float:
        return child.value + c_puct * child.prior * sqrt_total / (1 + child.visit_count)

    card, child = max(node.children.items(), key=lambda kv: score(kv[1]))
    return card, child


def add_dirichlet_noise(node: Node, alpha: float = 0.3, eps: float = 0.25) -> None:
    if not node.children:
        return
    noise = np.random.dirichlet([alpha] * len(node.children))
    for (card, child), n in zip(node.children.items(), noise):
        child.prior = (1 - eps) * child.prior + eps * n


def run_mcts(
    root_state: GameState,
    net: PolicyValueNet,
    num_simulations: int = 50,
    c_puct: float = 1.5,
    add_noise: bool = False,
) -> dict[Card, float]:
    """Return a visit-count policy (normalized) over legal cards at the root."""
    root = Node(copy.deepcopy(root_state))
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

        for n in path:
            n.visit_count += 1
            n.value_sum += leaf_value

    total = sum(c.visit_count for c in root.children.values())
    if total == 0:
        legal = root_state.legal_cards_for(root_state.player_to_act)
        return {c: 1.0 / len(legal) for c in legal}
    return {card: child.visit_count / total for card, child in root.children.items()}


def select_action(visit_probs: dict[Card, float], temperature: float = 1.0) -> Card:
    cards = list(visit_probs.keys())
    if temperature <= 1e-3:
        return max(cards, key=lambda c: visit_probs[c])
    weights = np.array([visit_probs[c] ** (1.0 / temperature) for c in cards], dtype=np.float64)
    weights /= weights.sum()
    return cards[np.random.choice(len(cards), p=weights)]
