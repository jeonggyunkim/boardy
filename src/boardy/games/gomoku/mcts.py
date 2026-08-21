"""Standard AlphaZero PUCT search: real 2-player zero-sum minimax-by-backup.

Unlike Deep Sea Crew (cooperative, single shared value, no sign flips),
Gomoku is adversarial: each node's average value is stored from the
perspective of *that node's* player-to-move, and gets negated once per
ply on the way back up the tree (`value = -value` in the backup loop) --
the textbook AlphaZero convention. A child's value is therefore from the
opponent's perspective relative to its parent, hence the `-child.value`
in the PUCT score.

`BatchedMCTS` drives many independent trees (one per game) in lockstep so
leaf evaluations can be batched into a single NN forward pass per
simulation round -- a batch-size-1 GPU call is dominated by kernel-launch
overhead, so this is what actually lets a GPU help. It also supports
`advance()`-ing each tree to the child for the move actually played,
instead of discarding the whole tree and rebuilding from scratch next
ply: that child already carries visit statistics accumulated during the
previous search, so reaching the same effective search depth next ply
needs fewer *new* simulations (and therefore fewer NN calls and Renju
legal-move checks -- see self_play.py, which is the caller that actually
uses this). `run_mcts_batch`/`run_mcts` are one-shot convenience wrappers
around a throwaway `BatchedMCTS` for callers that don't need reuse
(arena -- a fresh tree per ply is fine there, see evaluate.py; human
play).
"""

from __future__ import annotations

import math

import numpy as np
import torch

from .board import Board
from .encoding import action_to_index, encode_board, legal_action_mask_from_moves
from .network import PolicyValueNet
from .tactics import tactical_result


class Node:
    # `board` is None until first visited -- see ensure_board(). Board.clone()
    # + play() aren't free (Black's move legality re-derives Renju forbidden
    # cells from scratch), and _expand() creates one child per legal move
    # (up to size*size of them on an empty board); with only num_simulations
    # visits to go around, most siblings of a popular child are never
    # actually traversed into, so building their boards eagerly was pure
    # waste. Selection itself (_puct_select) only needs prior/visit_count/
    # value, none of which require a materialized board.
    __slots__ = ("board", "parent_board", "move", "prior", "children", "visit_count", "value_sum", "expanded")

    def __init__(
        self,
        prior: float = 0.0,
        board: Board | None = None,
        parent_board: Board | None = None,
        move: tuple[int, int] | None = None,
    ) -> None:
        self.board = board
        self.parent_board = parent_board
        self.move = move
        self.prior = prior
        self.children: dict[str, Node] = {}
        self.visit_count = 0
        self.value_sum = 0.0
        self.expanded = False

    def ensure_board(self) -> Board:
        if self.board is None:
            self.board = self.parent_board.clone()
            self.board.play(*self.move)
            self.parent_board = None  # done with it, let it go
        return self.board

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


def _expand_with_prediction(node: Node, legal_moves: list[tuple[int, int]], probs: np.ndarray) -> None:
    size = node.board.size
    for r, c in legal_moves:
        action = f"{r},{c}"
        idx = action_to_index(action, size)
        # Board not built yet -- see Node.ensure_board(). Most of these
        # children will never be selected within this search's budget.
        node.children[action] = Node(prior=float(probs[idx]), parent_board=node.board, move=(r, c))
    node.expanded = True


def _expand_with_tactical_prior(node: Node, legal_moves: list[tuple[int, int]], winning_moves: list[tuple[int, int]] | None) -> None:
    """Expansion for a leaf `tactical_result` already resolved, no NN call
    needed. `winning_moves`, if given, split the entire prior mass evenly
    (all equally correct -- not just the first one found); otherwise the
    position is lost regardless of which move is played, so prior is
    split uniformly across every legal move instead."""
    winning_set = set(winning_moves) if winning_moves else set()
    fallback = 1.0 / len(legal_moves)
    win_share = 1.0 / len(winning_set) if winning_set else 0.0
    for r, c in legal_moves:
        prior = win_share if (r, c) in winning_set else (0.0 if winning_set else fallback)
        node.children[f"{r},{c}"] = Node(prior=prior, parent_board=node.board, move=(r, c))
    node.expanded = True


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


def _batch_predict(
    boards: list[Board],
    legal_moves_list: list[list[tuple[int, int]]],
    net: PolicyValueNet,
    device: torch.device,
) -> tuple[list[np.ndarray], list[float]]:
    """One forward pass over many boards at once -- this is the whole point
    of the batched search. Masking/softmax is done per-board since each
    board has its own legal-move set."""
    net.eval()
    obs = np.stack([encode_board(b) for b in boards])
    x = torch.from_numpy(obs).float().to(device)
    with torch.no_grad():
        logits, values = net(x)
    logits = logits.cpu().numpy()
    values = values.cpu().numpy()

    size = boards[0].size
    probs_list = []
    for i, moves in enumerate(legal_moves_list):
        mask = legal_action_mask_from_moves(moves, size).astype(bool)
        row = np.where(mask, logits[i], -1e9)
        row = np.exp(row - row.max())
        row *= mask
        total = row.sum()
        probs_list.append(row / total if total > 0 else mask.astype(np.float32) / max(mask.sum(), 1))
    return probs_list, [float(v) for v in values]


class BatchedMCTS:
    """A batch of independent PUCT search trees, one per game, advanced in
    lockstep so leaf evaluations batch into single NN forward passes.
    Supports re-rooting each tree at the move actually played (`advance`)
    to carry visit statistics forward across plies instead of discarding
    them -- see the module docstring."""

    def __init__(self, boards: list[Board], net: PolicyValueNet) -> None:
        self.net = net
        self.device = next(net.parameters()).device
        self.roots: list[Node] = [Node(board=b.clone()) for b in boards]

    def _expand_pending_roots(self) -> None:
        """Expand any root that isn't already expanded -- true for every
        root the first time `search()` is ever called, and also for a
        reused root whose move was never actually visited in the previous
        search (low-prior child PUCT never picked)."""
        pending = [i for i, root in enumerate(self.roots) if not root.expanded and not root.is_terminal]
        if not pending:
            return
        boards = [self.roots[i].board for i in pending]
        moves = [b.legal_moves() for b in boards]
        probs_list, _values = _batch_predict(boards, moves, self.net, self.device)
        for pos, i in enumerate(pending):
            _expand_with_prediction(self.roots[i], moves[pos], probs_list[pos])

    def search(
        self,
        num_simulations: int,
        c_puct: float = 1.5,
        add_noise: bool = False,
        dirichlet_alpha: float = 0.3,
        dirichlet_eps: float = 0.25,
    ) -> list[dict[str, float]]:
        """Return a visit-count policy (normalized) over legal actions at
        each root. `num_simulations` is a *target total* visit count at
        the root, not "always run this many more" -- a reused root (see
        `advance()`) already carries some visits forward from the previous
        ply's search, so only the shortfall is actually run. This is the
        entire point of reuse: without it, every ply would pay for
        `num_simulations` fresh simulations regardless of how much of that
        budget the previous search already effectively bought, and reuse
        would cost strictly more work for no benefit (this was a real bug
        in an earlier version of this method -- verified via cProfile that
        it produced ~0% speedup, see docs/PLAN.md 2026-08-11).

        Each root is stopped independently once it reaches its own target
        instead of running a single round count for the whole batch: with
        noise + a wide branching factor (up to 225 legal first moves),
        visit counts land very unevenly across a batch of reused roots --
        a single shared round count would get dragged down to whatever the
        *worst*-carryover game in the batch needs, which measured out to
        as little as ~1-3% savings in practice. Stopping each root on its
        own means every game gets the full benefit of however much of its
        own line was already explored."""
        self._expand_pending_roots()
        if add_noise:
            for root in self.roots:
                if root.children:  # not a childless (terminal) root
                    add_dirichlet_noise(root, alpha=dirichlet_alpha, eps=dirichlet_eps)

        # A root's own visit_count is how many of the *previous* search's
        # simulations passed through it while it was still a child node --
        # exactly the budget already spent on this specific line, whether
        # it was reused or (for a brand new tree) still 0.
        targets = [max(root.visit_count, num_simulations) for root in self.roots]

        while any(root.visit_count < target for root, target in zip(self.roots, targets)):
            active_idx = [i for i, (root, target) in enumerate(zip(self.roots, targets)) if root.visit_count < target]

            paths: list[list[Node]] = []
            leaf_values: list[float] = []
            pending_idx: list[int] = []  # indices into `paths` that need a real NN eval
            pending_boards: list[Board] = []
            pending_moves: list[list[tuple[int, int]]] = []

            for i in active_idx:
                root = self.roots[i]
                path = [root]
                node = root
                while node.expanded and not node.is_terminal:
                    _, node = _puct_select(node, c_puct)
                    node.ensure_board()
                    path.append(node)
                paths.append(path)
                leaf_values.append(0.0)

                leaf = path[-1]
                if leaf.is_terminal:
                    leaf_values[-1] = _terminal_value(leaf.board)  # game result, no NN needed
                    continue

                legal_moves = leaf.board.legal_moves()
                # Forced win/loss -- use the exact result and skip the NN
                # call for this leaf entirely (see tactics.py).
                forced = tactical_result(leaf.board, legal_moves=legal_moves)
                if forced is not None:
                    value, winning_moves = forced
                    _expand_with_tactical_prior(leaf, legal_moves, winning_moves)
                    leaf_values[-1] = value
                    continue

                pending_idx.append(len(paths) - 1)
                pending_boards.append(leaf.board)
                pending_moves.append(legal_moves)

            if pending_boards:
                probs_list, values = _batch_predict(pending_boards, pending_moves, self.net, self.device)
                for pos, idx in enumerate(pending_idx):
                    leaf = paths[idx][-1]
                    _expand_with_prediction(leaf, pending_moves[pos], probs_list[pos])
                    leaf_values[idx] = values[pos]

            for path, leaf_value in zip(paths, leaf_values):
                value = leaf_value
                for n in reversed(path):
                    n.visit_count += 1
                    n.value_sum += value
                    value = -value

        results = []
        for root in self.roots:
            total = sum(c.visit_count for c in root.children.values())
            if total == 0:
                legal = [f"{r},{c}" for r, c in root.board.legal_moves()]
                results.append({a: 1.0 / len(legal) for a in legal})
            else:
                results.append({action: child.visit_count / total for action, child in root.children.items()})
        return results

    def advance(self, actions: list[str]) -> None:
        """Re-root each tree at the child for the action actually played.
        The rest of that ply's tree (siblings and their subtrees) becomes
        unreachable and is garbage-collected normally -- nothing to do
        explicitly."""
        new_roots = []
        for root, action in zip(self.roots, actions):
            child = root.children[action]
            child.ensure_board()
            new_roots.append(child)
        self.roots = new_roots

    def drop(self, positions: list[int]) -> None:
        """Remove finished games from the batch by position (matching the
        caller's own active-game bookkeeping), keeping the rest in order."""
        drop_set = set(positions)
        self.roots = [root for i, root in enumerate(self.roots) if i not in drop_set]


def run_mcts_batch(
    boards: list[Board],
    net: PolicyValueNet,
    num_simulations: int = 100,
    c_puct: float = 1.5,
    add_noise: bool = False,
    dirichlet_alpha: float = 0.3,
    dirichlet_eps: float = 0.25,
) -> list[dict[str, float]]:
    """One-shot batched search with no tree reuse across calls -- see
    `BatchedMCTS` for the stateful version self-play uses."""
    return BatchedMCTS(boards, net).search(
        num_simulations,
        c_puct=c_puct,
        add_noise=add_noise,
        dirichlet_alpha=dirichlet_alpha,
        dirichlet_eps=dirichlet_eps,
    )


def run_mcts(
    root_board: Board,
    net: PolicyValueNet,
    num_simulations: int = 100,
    c_puct: float = 1.5,
    add_noise: bool = False,
    dirichlet_alpha: float = 0.3,
    dirichlet_eps: float = 0.25,
) -> dict[str, float]:
    """Return a visit-count policy (normalized) over legal actions at the root."""
    return run_mcts_batch(
        [root_board],
        net,
        num_simulations=num_simulations,
        c_puct=c_puct,
        add_noise=add_noise,
        dirichlet_alpha=dirichlet_alpha,
        dirichlet_eps=dirichlet_eps,
    )[0]


def select_action(visit_probs: dict[str, float], temperature: float = 1.0) -> str:
    actions = list(visit_probs.keys())
    if temperature <= 1e-3:
        return max(actions, key=lambda a: visit_probs[a])
    weights = np.array([visit_probs[a] ** (1.0 / temperature) for a in actions], dtype=np.float64)
    weights /= weights.sum()
    return actions[np.random.choice(len(actions), p=weights)]
