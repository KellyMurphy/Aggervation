"""The click flow: pick a card, then the peg(s). No window needed."""

import random

from aggervation.cards import Card
from aggervation.game import Game, PegPos, Zone
from aggervation.main import Selection
from aggervation.rules import position_after


def setup(*ranks: str) -> tuple[Game, Selection]:
    game = Game(rng=random.Random(0))
    for player in game.players:
        player.hand = [Card("A", "S")]
    game.current_idx = 0  # RED
    game.skip_pending = False
    game.player("RED").hand = [Card(r, "H") for r in ranks]
    return game, Selection(game)


def place(game: Game, color: str, num: int, travelled: int):
    peg = game.player(color).pegs[num]
    peg.travelled, peg.pos, peg.blocking = travelled, position_after(color, travelled), False
    return peg


def test_pick_card_then_base_peg_to_enter():
    game, sel = setup("A")
    red = game.player("RED")
    sel.click_card(0)
    assert ("RED", 2) in sel.selectable()  # any base peg can be clicked
    sel.click_peg(red.pegs[2])
    assert len(red.pegs_in(Zone.TRACK)) == 1
    assert game.current_player.color == "GREEN"


def test_pick_card_then_peg_to_move():
    game, sel = setup("5")
    peg = place(game, "RED", 1, 10)
    sel.click_card(0)
    assert sel.selectable() == {("RED", 1)}
    sel.click_peg(peg)
    assert peg.pos == PegPos.track(15)


def test_card_that_cannot_move_is_not_selected():
    game, sel = setup("5", "A")
    sel.click_card(0)
    assert sel.card is None
    assert "can't move" in sel.message


def test_clicking_selected_card_again_deselects():
    game, sel = setup("A")
    sel.click_card(0)
    sel.click_card(0)
    assert sel.card is None


def test_ten_pick_own_peg_then_partner():
    game, sel = setup("10")
    red = place(game, "RED", 0, 10)
    blue = place(game, "BLUE", 0, 20)
    sel.click_card(0)
    sel.click_peg(blue)  # not yours: ignored
    assert sel.swap_from is None
    sel.click_peg(red)
    assert ("BLUE", 0) in sel.selectable()
    sel.click_peg(blue)
    assert red.pos == PegPos.track(68) and blue.pos == PegPos.track(10)


def test_seven_keeps_picking_until_seven_spaces_used():
    game, sel = setup("7")
    a = place(game, "RED", 0, 10)
    b = place(game, "RED", 1, 30)
    sel.click_card(0)
    sel.click_peg(a)
    dests = dict(sel.split_destinations())
    assert sorted(dests) == list(range(1, 8))
    sel.click_board(dests[3])  # move peg 1 three spaces
    assert sel.split == [(0, 3)]
    assert game.current_player.color == "RED"  # still choosing
    assert "4 steps left" in sel.message
    # The preview shows the first part already moved.
    preview_a = sel.preview_players()[0].pegs[0]
    assert preview_a.pos == PegPos.track(13)
    sel.click_peg(b)  # only 4 left, so it finishes automatically
    assert a.travelled == 13 and b.travelled == 34
    assert game.current_player.color == "GREEN"


def test_seven_all_on_one_peg_by_key():
    game, sel = setup("7")
    a = place(game, "RED", 0, 10)
    place(game, "RED", 1, 30)
    sel.click_card(0)
    sel.click_peg(a)
    sel.choose_split_steps(7)
    assert a.travelled == 17


def test_skipped_player_just_picks_a_card():
    game, sel = setup("9")
    game.skip_pending = True
    sel.click_card(0)
    assert game.player("RED").hand == []
    assert "skipped" in game.last_action
