"""Egocentric fixed-size feature encoding of a player's info-state.

Turns what a single seat can legally know (its own hand, the public trick
history, task list/status, and any communication signals) into a flat
vector for the policy/value network. Everything is expressed *relative to
the acting seat* (offset 0 = self) so the same network works for any seat
and any player count.

Card action space: the 40 cards in deck order (see cards.full_deck), fixed
so policy logits have a stable meaning across games.
"""

from __future__ import annotations

import numpy as np

from .cards import COLOR_SUITS, Card, Suit, full_deck
from .communication import SonarMarker
from .engine import GameState
from .tasks import TaskKind

MAX_PLAYERS = 5
MAX_TASKS = 6

ACTION_CARDS: list[Card] = full_deck()
CARD_TO_INDEX: dict[Card, int] = {c: i for i, c in enumerate(ACTION_CARDS)}
NUM_CARDS = len(ACTION_CARDS)  # 40

_TASK_KINDS = list(TaskKind)
_NUM_TASK_KINDS = len(_TASK_KINDS)
_MARKERS = list(SonarMarker)


def _one_hot(index: int | None, size: int) -> np.ndarray:
    v = np.zeros(size, dtype=np.float32)
    if index is not None:
        v[index] = 1.0
    return v


def _card_slot(card: Card | None) -> np.ndarray:
    """NUM_CARDS one-hot + 1 'absent' bit."""
    v = np.zeros(NUM_CARDS + 1, dtype=np.float32)
    v[CARD_TO_INDEX[card] if card is not None else NUM_CARDS] = 1.0
    return v


def relative_seat(seat: int, other: int, num_players: int) -> int:
    return (other - seat) % num_players


def encode_task(task, seat: int, num_players: int) -> np.ndarray:
    owner_rel = relative_seat(seat, task.owner, num_players)
    owner_vec = _one_hot(owner_rel, MAX_PLAYERS)
    kind_vec = _one_hot(_TASK_KINDS.index(task.kind), _NUM_TASK_KINDS)

    card_vec = np.zeros(NUM_CARDS + 1, dtype=np.float32)
    card_vec[NUM_CARDS] = 1.0  # default: not applicable
    n_val, n_na = 0.0, 1.0
    suit_vec = np.zeros(len(COLOR_SUITS) + 1, dtype=np.float32)
    suit_vec[-1] = 1.0

    p = task.params
    if task.kind == TaskKind.WIN_CARD:
        card_vec = _card_slot(Card.parse(p["card"]))
    elif task.kind in (TaskKind.WIN_TRICK_NUMBER, TaskKind.WIN_EXACT_COUNT, TaskKind.WIN_AT_LEAST):
        n_val, n_na = float(p["n"]) / 13.0, 0.0
    elif task.kind == TaskKind.NEVER_WIN_COLOR:
        suit_vec = np.zeros(len(COLOR_SUITS) + 1, dtype=np.float32)
        suit_vec[COLOR_SUITS.index(Suit(p["suit"]))] = 1.0

    status_vec = np.zeros(3, dtype=np.float32)
    if not task.resolved:
        status_vec[0] = 1.0
    elif task.success:
        status_vec[1] = 1.0
    else:
        status_vec[2] = 1.0

    return np.concatenate(
        [owner_vec, kind_vec, card_vec, np.array([n_val, n_na], dtype=np.float32), suit_vec, status_vec]
    )


_TASK_FEATURE_SIZE = MAX_PLAYERS + _NUM_TASK_KINDS + (NUM_CARDS + 1) + 2 + (len(COLOR_SUITS) + 1) + 3


def encode_observation(state: GameState, seat: int) -> np.ndarray:
    n = state.num_players

    hand_vec = np.zeros(NUM_CARDS, dtype=np.float32)
    for c in state.hands[seat]:
        hand_vec[CARD_TO_INDEX[c]] = 1.0

    played_vec = np.zeros(NUM_CARDS, dtype=np.float32)
    for rec in state.history:
        for c in rec.cards.values():
            played_vec[CARD_TO_INDEX[c]] = 1.0

    trick_vecs = []
    for rel in range(MAX_PLAYERS):
        if rel < n:
            other = (seat + rel) % n
            trick_vecs.append(_card_slot(state.trick_in_progress.get(other)))
        else:
            trick_vecs.append(_card_slot(None))
    trick_vec = np.concatenate(trick_vecs)

    comm_vecs = []
    for rel in range(MAX_PLAYERS):
        if rel < n:
            other = (seat + rel) % n
            sig = state.comms.signals.get(other)
            comm_vecs.append(_card_slot(sig.card if sig else None))
            comm_vecs.append(_one_hot(_MARKERS.index(sig.marker) if sig else None, len(_MARKERS) + 1))
        else:
            comm_vecs.append(_card_slot(None))
            comm_vecs.append(_one_hot(None, len(_MARKERS) + 1))
    comm_vec = np.concatenate(comm_vecs)

    task_vecs = []
    for i in range(MAX_TASKS):
        if i < len(state.tasks):
            task_vecs.append(encode_task(state.tasks[i], seat, n))
        else:
            task_vecs.append(np.zeros(_TASK_FEATURE_SIZE, dtype=np.float32))
    task_vec = np.concatenate(task_vecs)

    num_players_vec = _one_hot(n - 2, 4)  # 2..5 players
    leader_vec = _one_hot(relative_seat(seat, state.current_leader, n), MAX_PLAYERS)
    trick_progress = np.array([state.trick_number / max(state.hand_size, 1)], dtype=np.float32)
    to_act_is_me = np.array(
        [1.0 if state.player_to_act == seat else 0.0], dtype=np.float32
    )

    return np.concatenate(
        [
            hand_vec,
            played_vec,
            trick_vec,
            comm_vec,
            task_vec,
            num_players_vec,
            leader_vec,
            trick_progress,
            to_act_is_me,
        ]
    )


OBS_SIZE = (
    NUM_CARDS
    + NUM_CARDS
    + MAX_PLAYERS * (NUM_CARDS + 1)
    + MAX_PLAYERS * ((NUM_CARDS + 1) + (len(_MARKERS) + 1))
    + MAX_TASKS * _TASK_FEATURE_SIZE
    + 4
    + MAX_PLAYERS
    + 1
    + 1
)


def legal_action_mask(state: GameState, seat: int) -> np.ndarray:
    mask = np.zeros(NUM_CARDS, dtype=np.float32)
    for c in state.legal_cards_for(seat):
        mask[CARD_TO_INDEX[c]] = 1.0
    return mask
