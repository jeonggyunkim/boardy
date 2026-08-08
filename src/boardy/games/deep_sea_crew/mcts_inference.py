"""Information-Set MCTS for real play: seat S only knows its own hand.

Search runs over several *determinizations* — full deals sampled to be
consistent with everything publicly knowable (cards already played, cards
currently face-up on the trick table, revealed Sonar signals, and standard
trick-taking void inference: a player who didn't follow the led suit is
known to hold none of it) — and root visit counts are pooled across them.
Each determinization is then just an oracle GameState, so the same
`run_mcts` used for training self-play is reused unchanged.
"""

from __future__ import annotations

import copy
import random
from collections import Counter

from .cards import Card, Suit, full_deck
from .engine import GameState
from .mcts import run_mcts
from .network import PolicyValueNet


def infer_void_suits(state: GameState, seat: int) -> dict[int, set[Suit]]:
    """From seat's public knowledge: which suits each other player is known
    to be out of, because they didn't follow the suit that was led."""
    void: dict[int, set[Suit]] = {p: set() for p in range(state.num_players)}

    def note(player: int, led_suit: Suit, played: Card) -> None:
        if played.suit != led_suit:
            void[player].add(led_suit)

    for rec in state.history:
        led_suit = rec.cards[rec.leader].suit
        for player, card in rec.cards.items():
            note(player, led_suit, card)

    if state.trick_in_progress:
        leader = state.current_leader
        if leader in state.trick_in_progress:
            led_suit = state.trick_in_progress[leader].suit
            for player, card in state.trick_in_progress.items():
                note(player, led_suit, card)

    return void


def sample_determinization(state: GameState, seat: int, rng: random.Random) -> GameState:
    n = state.num_players
    void = infer_void_suits(state, seat)

    known_fixed: dict[int, Card] = {}
    for p, sig in state.comms.signals.items():
        if p != seat:
            known_fixed[p] = sig.card

    played = {c for rec in state.history for c in rec.cards.values()}
    on_table = set(state.trick_in_progress.values())
    seen = played | on_table | set(state.hands[seat]) | set(known_fixed.values())
    hidden_pool = [c for c in full_deck() if c not in seen]
    rng.shuffle(hidden_pool)

    slot_counts = {
        p: len(state.hands[p]) - (1 if p in known_fixed else 0) for p in range(n) if p != seat
    }
    # deal() discards any cards left over when the deck doesn't divide evenly among
    # players; those never belong to anyone. From seat's point of view any hidden
    # card is equally likely to be one of them, so just drop a random `excess` of
    # them from the pool before assigning the rest to players' hidden slots.
    excess = len(hidden_pool) - sum(slot_counts.values())
    assert excess >= 0, f"determinization pool too small: need {sum(slot_counts.values())}, have {len(hidden_pool)}"

    assignment: dict[int, list[Card]] = {p: [] for p in range(n) if p != seat}
    remaining = hidden_pool[excess:]

    for attempt in range(50):
        pools = {p: [] for p in assignment}
        pool = list(remaining)
        rng.shuffle(pool)
        needed = dict(slot_counts)
        ok = True
        for card in pool:
            candidates = [p for p, k in needed.items() if k > 0 and card.suit not in void[p]]
            if not candidates:
                candidates = [p for p, k in needed.items() if k > 0]
                if not candidates:
                    ok = False
                    break
            p = rng.choice(candidates)
            pools[p].append(card)
            needed[p] -= 1
        if ok and all(v == 0 for v in needed.values()):
            assignment = pools
            break
    else:
        # Constraints unsatisfiable together (rare) — fall back to ignoring void info.
        pool = list(remaining)
        rng.shuffle(pool)
        i = 0
        for p, k in slot_counts.items():
            assignment[p] = pool[i : i + k]
            i += k

    new_state = copy.deepcopy(state)
    for p in range(n):
        if p == seat:
            continue
        hand = list(assignment[p])
        if p in known_fixed:
            hand.append(known_fixed[p])
        new_state.hands[p] = hand
    return new_state


def run_ismcts(
    state: GameState,
    net: PolicyValueNet,
    num_determinizations: int = 8,
    sims_per_determinization: int = 15,
    c_puct: float = 1.5,
    seed: int | None = None,
) -> dict[Card, float]:
    seat = state.player_to_act
    assert seat is not None, "game already finished"
    rng = random.Random(seed)

    totals: Counter[Card] = Counter()
    for _ in range(num_determinizations):
        det_state = sample_determinization(state, seat, rng)
        visit_probs = run_mcts(det_state, net, num_simulations=sims_per_determinization, c_puct=c_puct)
        for card, p in visit_probs.items():
            totals[card] += p

    total = sum(totals.values())
    if total == 0:
        legal = state.legal_cards_for(seat)
        return {c: 1.0 / len(legal) for c in legal}
    return {card: v / total for card, v in totals.items()}
