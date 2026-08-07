"""Player interface — human/random now, AlphaZero-style policy later."""

from __future__ import annotations

import random
from abc import ABC, abstractmethod

from .cards import Card
from .engine import GameState


class Player(ABC):
    name: str

    @abstractmethod
    def choose_card(self, state: GameState, seat: int) -> Card: ...

    def choose_communication(self, state: GameState, seat: int) -> Card | None:
        """Return a card to signal this turn, or None to skip."""
        return None


class RandomPlayer(Player):
    def __init__(self, name: str = "bot", rng: random.Random | None = None) -> None:
        self.name = name
        self.rng = rng or random.Random()

    def choose_card(self, state: GameState, seat: int) -> Card:
        return self.rng.choice(state.legal_cards_for(seat))


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
