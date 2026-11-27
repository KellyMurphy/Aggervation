import random

from aggervation.bot import choose_play
from aggervation.cards import Card
from aggervation.game import Game, Zone
from aggervation.rules import MoveKind, position_after


def setup(*ranks: str) -> Game:
    game = Game(rng=random.Random(0))
    for player in game.players:
        player.hand = [Card("A", "S")]
    game.current_idx = 0  # RED
    game.skip_pending = False
    game.player("RED").hand = [Card(r, "H") for r in ranks]
    return game


def place(game: Game, color: str, num: int, travelled: int):
    peg = game.player(color).pegs[num]
    peg.travelled, peg.pos, peg.blocking = travelled, position_after(color, travelled), False
    return peg


def test_bot_brings_a_peg_out():
    game = setup("A")
    card, move = choose_play(game)
    assert move.kind is MoveKind.ENTER


def test_bot_prefers_sending_an_opponent_back():
    game = setup("5", "4")
    place(game, "RED", 0, 10)
    place(game, "GREEN", 0, 86)  # hole 14, four ahead of Red
    card, move = choose_play(game)
    assert card.rank == "4"


def test_bot_lays_a_jack_when_skipped():
    game = setup("A", "J", "7")
    game.skip_pending = True
    card, move = choose_play(game)
    assert card.rank == "J" and move is None


def test_bots_can_play_a_whole_game():
    rng = random.Random(5)
    game = Game(rng=random.Random(5))
    for _ in range(3000):
        game.play_card(*choose_play(game, rng))
        if game.winner():
            break
    assert game.winner() is not None
    assert all(p.pos.zone is Zone.HOME for p in game.winner().pegs)


def test_bot_does_not_knock_back_its_partner():
    game = setup("5", "4")
    place(game, "RED", 0, 11)
    blue = place(game, "BLUE", 0, 64)  # Blue starts at 48: hole 16, where a 5 would land
    assert blue.pos.index == 16
    place(game, "RED", 1, 40)
    card, move = choose_play(game)
    assert not (card.rank == "5" and move.peg == 0)


def test_bot_helps_partner_once_home():
    game = setup("Q")
    for n in range(4):
        place(game, "RED", n, 94 - n)
    blue = place(game, "BLUE", 0, 10)
    card, move = choose_play(game)
    game.play_card(card, move)
    assert blue.travelled == 22
