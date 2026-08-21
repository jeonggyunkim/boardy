"""Player interface — human/random now, AlphaZero-style policy later."""

from __future__ import annotations

import random
from abc import ABC, abstractmethod

from .cards import Card
from .communication import valid_marker
from .engine import GameState


class Player(ABC):
    name: str

    @abstractmethod
    def choose_card(self, state: GameState, seat: int) -> Card: ...

    @abstractmethod
    def choose_task(self, state: GameState, seat: int) -> str:
        """Return the id of one of state.available_tasks to draft."""
        ...

    def choose_communication(self, state: GameState, seat: int) -> Card | None:
        """Return a card to signal this turn, or None to skip. Only ever
        called while `seat` is actually allowed to communicate (see
        GameState.communicable_seats) -- implementations don't need to
        re-check phase/timing/leader themselves."""
        return None


def _random_signal_choice(state: GameState, seat: int, rng: random.Random) -> Card | None:
    """Shared placeholder strategy (no learned/scripted comm strategy
    exists yet, same simplification as random task-drafting): about half
    the time, reveal a random truthfully-markable card."""
    hand = state.hands[seat]
    candidates = [c for c in hand if valid_marker(c, hand)]
    if not candidates or rng.random() > 0.5:
        return None
    return rng.choice(candidates)


class RandomPlayer(Player):
    def __init__(self, name: str = "bot", rng: random.Random | None = None) -> None:
        self.name = name
        self.rng = rng or random.Random()

    def choose_card(self, state: GameState, seat: int) -> Card:
        return self.rng.choice(state.legal_cards_for(seat))

    def choose_task(self, state: GameState, seat: int) -> str:
        return self.rng.choice(state.draftable_tasks(seat)).id

    def choose_communication(self, state: GameState, seat: int) -> Card | None:
        return _random_signal_choice(state, seat, self.rng)


class NetPlayer(Player):
    """Plays using a trained PolicyValueNet, with or without ISMCTS search."""

    def __init__(
        self,
        net,
        name: str = "ai",
        use_search: bool = True,
        num_determinizations: int = 6,
        sims_per_determinization: int = 20,
        rng: random.Random | None = None,
    ) -> None:
        self.name = name
        self.net = net
        self.use_search = use_search
        self.num_determinizations = num_determinizations
        self.sims_per_determinization = sims_per_determinization
        self.rng = rng or random.Random()

    def choose_card(self, state: GameState, seat: int) -> Card:
        if self.use_search:
            from .mcts_inference import run_ismcts

            probs = run_ismcts(
                state,
                self.net,
                num_determinizations=self.num_determinizations,
                sims_per_determinization=self.sims_per_determinization,
                seed=self.rng.randrange(1_000_000_000),
            )
            return max(probs, key=probs.get)

        from .encoding import encode_observation, legal_action_mask

        obs = encode_observation(state, seat)
        mask = legal_action_mask(state, seat)
        probs, _ = self.net.predict(obs, mask)
        idx = int(probs.argmax())
        from .encoding import ACTION_CARDS

        return ACTION_CARDS[idx]

    def choose_task(self, state: GameState, seat: int) -> str:
        # No search-based drafting strategy yet (would need the network/MCTS
        # extended to cover task-choice actions, not just card play) -- picks
        # randomly among the drawn tasks, same as RandomPlayer.
        return self.rng.choice(state.draftable_tasks(seat)).id

    def choose_communication(self, state: GameState, seat: int) -> Card | None:
        # No learned communication strategy yet -- same simplification.
        return _random_signal_choice(state, seat, self.rng)
