import random

from boardy.games.deep_sea_crew.cards import Card, Suit
from boardy.games.deep_sea_crew.engine import GameState, resolve_trick, new_game
from boardy.games.deep_sea_crew.communication import CommunicationBoard
from boardy.games.deep_sea_crew.players import RandomPlayer


def make_bare_state(num_players=3, hand_size=2) -> GameState:
    return GameState(
        num_players=num_players,
        hands=[[] for _ in range(num_players)],
        tasks=[],
        comms=CommunicationBoard(num_players),
        current_leader=0,
        hand_size=hand_size,
    )


def test_resolve_trick_highest_led_suit_wins():
    cards = {0: Card(Suit.BLUE, 5), 1: Card(Suit.BLUE, 9), 2: Card(Suit.GREEN, 8)}
    assert resolve_trick(cards, Suit.BLUE) == 1


def test_resolve_trick_trump_beats_everything():
    cards = {0: Card(Suit.BLUE, 9), 1: Card(Suit.SUBMARINE, 1), 2: Card(Suit.GREEN, 8)}
    assert resolve_trick(cards, Suit.BLUE) == 1


def test_must_follow_suit():
    state = make_bare_state()
    state.hands = [[Card(Suit.BLUE, 3), Card(Suit.GREEN, 4)], [Card(Suit.BLUE, 7)], [Card(Suit.GREEN, 2)]]
    state.play_card(0, Card(Suit.BLUE, 3))
    assert state.legal_cards_for(1) == [Card(Suit.BLUE, 7)]


def test_cannot_play_out_of_turn():
    state = make_bare_state()
    state.hands = [[Card(Suit.BLUE, 3)], [Card(Suit.BLUE, 7)], [Card(Suit.GREEN, 2)]]
    try:
        state.play_card(1, Card(Suit.BLUE, 7))
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_full_random_game_terminates_with_outcome():
    for seed in range(20):
        state = new_game(num_players=3, difficulty_budget=6, seed=seed)
        players = [RandomPlayer(rng=random.Random(seed + i)) for i in range(3)]
        guard = 0
        while state.outcome is None:
            seat = state.player_to_act
            assert seat is not None
            card = players[seat].choose_card(state, seat)
            state.play_card(seat, card)
            guard += 1
            assert guard < 1000
        assert state.outcome in (True, False)
        if state.outcome:
            assert all(t.resolved and t.success for t in state.tasks)
        else:
            # mission aborts as soon as any task fails; others may be left moot
            assert any(t.resolved and not t.success for t in state.tasks)
