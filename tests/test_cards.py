from deepsea.cards import Card, Suit, deal, full_deck


def test_full_deck_size():
    assert len(full_deck()) == 40


def test_deal_equal_hands():
    hands = deal(4, rng=__import__("random").Random(1))
    assert all(len(h) == 10 for h in hands)


def test_deal_uneven_players_trims_remainder():
    hands = deal(3, rng=__import__("random").Random(1))
    sizes = {len(h) for h in hands}
    assert sizes == {13}  # 40 // 3 == 13, remainder discarded


def test_card_parse_roundtrip():
    c = Card(Suit.BLUE, 7)
    assert Card.parse(str(c)) == c
