"""The click flow: pick a card, then the peg(s). No window needed."""

import random

from aggervation.cards import Card
from aggervation.game import Game, PegPos, Zone
from aggervation.selection import Selection
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
    assert sel.split == (("RED", 0, 3),)
    assert game.current_player.color == "RED"  # still choosing
    assert "4 steps left" in sel.message
    # The preview shows the first part already moved.
    preview_a = sel.preview_players()[0].pegs[0]
    assert preview_a.pos == PegPos.track(13)
    sel.click_peg(b)
    assert sel.split_step_options() == [1, 2, 3, 4]  # peg 1 can still use the rest
    sel.choose_split_steps(4)
    assert sel.seven_done and game.current_player.color == "RED"  # waits to be confirmed
    sel.finish_seven()
    assert a.travelled == 13 and b.travelled == 34
    assert game.current_player.color == "GREEN"


def test_seven_all_on_one_peg_by_key():
    game, sel = setup("7")
    a = place(game, "RED", 0, 10)
    place(game, "RED", 1, 30)
    sel.click_card(0)
    sel.click_peg(a)
    sel.choose_split_steps(7)
    sel.finish_seven()
    assert a.travelled == 17


def test_seven_can_move_a_peg_twice():
    game, sel = setup("7")
    a = place(game, "RED", 0, 10)
    b = place(game, "RED", 1, 30)
    sel.click_card(0)
    for peg, steps in ((a, 2), (b, 3), (a, 2)):
        sel.click_peg(game.player("RED").pegs[peg.number])
        sel.choose_split_steps(steps)
    assert sel.split == (("RED", 0, 2), ("RED", 1, 3), ("RED", 0, 2))
    sel.finish_seven()
    assert a.travelled == 14 and b.travelled == 33
    assert game.current_player.color == "GREEN"


def test_seven_take_steps_back():
    """Move a peg 4, then decide on 2: take 2 back and have 5 left."""
    game, sel = setup("7")
    a = place(game, "RED", 0, 10)
    place(game, "RED", 1, 30)
    green = place(game, "GREEN", 0, 13 + 72)  # hole 13: in peg 1's way (Green starts at 24)
    sel.click_card(0)
    sel.click_peg(a)
    sel.choose_split_steps(4)  # passes Green on hole 13: sent home in the preview
    preview_green = sel.preview_players()[1].pegs[0]
    assert preview_green.pos.zone is Zone.BASE
    sel.click_peg(a)
    assert -2 in sel.split_step_options() and -4 in sel.split_step_options()
    sel.choose_split_steps(-2)
    assert sel.split == (("RED", 0, 2),)
    assert sel.seven_left == 5 and "5 steps left" in sel.message
    preview = sel.preview_players()
    assert preview[0].pegs[0].pos == PegPos.track(12)
    assert preview[1].pegs[0].pos == PegPos.track(13)  # Green is back: it was never passed
    assert green.pos == PegPos.track(13) and a.travelled == 10  # nothing real has moved yet


def test_seven_take_back_after_all_seven_used():
    game, sel = setup("7")
    a = place(game, "RED", 0, 10)
    b = place(game, "RED", 1, 30)
    sel.click_card(0)
    sel.click_peg(a)
    sel.choose_split_steps(7)
    assert sel.seven_done
    sel.click_peg(game.player("RED").pegs[0])
    sel.choose_split_steps(-3)
    assert not sel.seven_done and sel.seven_left == 3
    sel.click_peg(b)
    sel.choose_split_steps(3)
    sel.finish_seven()
    assert a.travelled == 14 and b.travelled == 33


def test_skipped_player_just_picks_a_card():
    game, sel = setup("9")
    game.skip_pending = True
    sel.click_card(0)
    assert game.player("RED").hand == []
    assert "skipped" in game.last_action


def test_seven_can_continue_onto_partners_pegs():
    game, sel = setup("7")
    for n, t in ((0, 94), (1, 93), (2, 92)):
        place(game, "RED", n, t)
    last = place(game, "RED", 3, 89)
    blue = place(game, "BLUE", 0, 10)
    sel.click_card(0)
    sel.click_peg(last)
    sel.choose_split_steps(2)  # into home: all Red's pegs are in
    assert sel.split == (("RED", 3, 2),)
    assert ("BLUE", 0) in sel.selectable()
    sel.click_peg(blue)
    sel.choose_split_steps(5)
    sel.finish_seven()
    assert blue.travelled == 15
    assert game.current_player.color == "GREEN"
