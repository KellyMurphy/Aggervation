import random

import pytest

from aggervation.cards import Card, Deck, full_deck
from aggervation.game import Game, PegPos, Zone
from aggervation.rules import IllegalMove


def make_game(seed: int = 1) -> Game:
    return Game(rng=random.Random(seed))


def play_one_turn(game: Game) -> None:
    """Make the current player's first available play."""
    player = game.current_player
    if game.skip_pending:
        game.play_card(player.hand[0])
        return
    card, move = next((c, m) for c in player.hand for m in game.legal_moves(c))
    game.play_card(card, move)


def play_whole_hand(game: Game) -> None:
    """Play until the next hand is dealt."""
    hand, deal = game.hand_number, game.deal_number
    while (game.hand_number, game.deal_number) == (hand, deal):
        play_one_turn(game)


def cards_held(game: Game) -> int:
    return sum(len(p.hand) for p in game.players)


def test_full_deck_is_52_unique_cards():
    deck = full_deck()
    assert len(deck) == 52
    assert len(set(deck)) == 52


def test_deck_is_shuffled_and_drawable():
    deck = Deck(random.Random(3))
    assert deck.cards != full_deck()
    drawn = [deck.draw() for _ in range(52)]
    assert set(drawn) == set(full_deck())
    with pytest.raises(IndexError):
        deck.draw()


def test_invalid_card_rejected():
    with pytest.raises(ValueError):
        Card("1", "S")


def test_all_pegs_start_in_base():
    game = make_game()
    for player in game.players:
        assert [p.pos for p in player.pegs] == [PegPos.base(n) for n in range(4)]
        assert not player.has_won()


def test_first_hand_is_five_cards_and_left_of_dealer_plays_first():
    game = make_game()
    assert game.dealer.color == "RED"
    assert len(game.deck) == 52 - 20
    # Everyone got 5; anyone who couldn't move has already folded.
    for player in game.players:
        folded = any(f"{player.color} can't play and folds (5 cards)" in line for line in game.log)
        assert len(player.hand) == (0 if folded else 5)
    first_active = next(p for p in game.players[1:] + game.players[:1] if p.hand)
    assert game.current_player is first_active


def test_turns_go_clockwise():
    game = make_game()
    for player in game.players:
        player.hand = [Card("A", s) for s in "SHD"]
    game.current_idx = 1
    order = []
    for _ in range(5):
        order.append(game.current_player.color)
        play_one_turn(game)
    assert order == ["GREEN", "BLUE", "YELLOW", "RED", "GREEN"]


def test_folded_players_are_skipped():
    game = make_game()
    for player in game.players:
        player.hand = [Card("A", "S")]
    game.player("BLUE").hand = []
    game.current_idx = 1
    play_one_turn(game)
    assert game.current_player.color == "YELLOW"


def test_deal_is_5_then_4_then_4_using_whole_deck():
    game = make_game()
    play_whole_hand(game)
    assert game.hand_number == 1
    assert len(game.deck) == 16
    assert cards_held(game) + len(game.discard) == 36

    play_whole_hand(game)
    assert game.hand_number == 2
    assert len(game.deck) == 0
    assert cards_held(game) + len(game.discard) == 52


def test_dealer_rotates_and_deck_resets_after_three_hands():
    game = make_game()
    for _ in range(3):
        play_whole_hand(game)
    assert game.deal_number == 2
    assert game.hand_number == 0
    assert game.dealer.color == "GREEN"
    assert len(game.deck) == 32
    assert cards_held(game) + len(game.discard) == 20


def test_every_card_dealt_once_per_deal():
    game = make_game()
    play_whole_hand(game)
    play_whole_hand(game)
    seen = game.discard + [c for p in game.players for c in p.hand]
    assert sorted(map(str, seen)) == sorted(map(str, full_deck()))


def test_cannot_play_card_not_in_hand():
    game = make_game()
    other = game.players[(game.current_idx + 1) % 4].hand[0]
    with pytest.raises(IllegalMove):
        game.play_card(other)


def test_peg_at_finds_pegs_by_zone():
    game = make_game()
    red = game.player("RED")
    assert game.peg_at(PegPos.base(0), "RED") is red.pegs[0]
    assert game.peg_at(PegPos.track(5)) is None
    red.pegs[1].pos = PegPos.track(5)
    assert game.peg_at(PegPos.track(5)) is red.pegs[1]
    assert game.peg_at(PegPos.track(5 + 96)) is red.pegs[1]  # wraps around


def test_winner_when_all_pegs_home():
    game = make_game()
    yellow = game.player("YELLOW")
    for n, peg in enumerate(yellow.pegs):
        peg.pos = PegPos.home(n)
    assert yellow.pegs_in(Zone.HOME) == yellow.pegs
    assert game.winner() is yellow
