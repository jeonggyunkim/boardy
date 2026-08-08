"""Maps GameState -> the generic per-seat JSON view boardy.web expects.

This is the deep_sea_crew half of the GameSpec.serialize_seat contract
(see boardy/core/game_spec.py) — the shape here (hand/legal_moves/
trick_in_progress/tasks/...) is what the shared frontend renders. It's
game-specific content behind a generic key schema, not shared code.
"""

from __future__ import annotations

from .engine import GameState


def serialize_seat(state: GameState, seat: int, players_meta: list[dict]) -> dict:
    legal = [str(c) for c in state.legal_cards_for(seat)] if state.player_to_act == seat else []
    return {
        "players": players_meta,
        "num_players": state.num_players,
        "hand": [str(c) for c in state.hands[seat]],
        "hand_sizes": [len(h) for h in state.hands],
        "tricks_won": [state.wins_per_player.get(i, 0) for i in range(state.num_players)],
        "legal_moves": legal,
        "player_to_act": state.player_to_act,
        "current_leader": state.current_leader,
        "trick_number": state.trick_number,
        "hand_size": state.hand_size,
        "trick_in_progress": {p: str(c) for p, c in state.trick_in_progress.items()},
        "tasks": [
            {
                "id": t.id,
                "owner": t.owner,
                "describe": t.describe(),
                "resolved": t.resolved,
                "success": t.success,
            }
            for t in state.tasks
        ],
        "history": [
            {
                "number": rec.number,
                "leader": rec.leader,
                "cards": {p: str(c) for p, c in rec.cards.items()},
                "winner": rec.winner,
            }
            for rec in state.history
        ],
        "signals": {
            p: {"card": str(sig.card), "marker": sig.marker.value}
            for p, sig in state.comms.signals.items()
        },
        "can_communicate": state.comms.can_communicate(seat),
        "outcome": state.outcome,
    }
