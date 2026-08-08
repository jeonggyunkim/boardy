from boardy.games.deep_sea_crew.encoding import OBS_SIZE, NUM_CARDS, encode_observation, legal_action_mask
from boardy.games.deep_sea_crew.engine import new_game


def test_encode_observation_shape():
    state = new_game(3, difficulty_budget=8, seed=1)
    obs = encode_observation(state, 0)
    assert obs.shape == (OBS_SIZE,)


def test_legal_action_mask_matches_hand():
    state = new_game(4, difficulty_budget=8, seed=2)
    seat = state.player_to_act
    mask = legal_action_mask(state, seat)
    assert mask.sum() == len(state.legal_cards_for(seat))
    assert mask.shape == (NUM_CARDS,)
