import random

import pytest

from aggervation.cards import Card
from aggervation.game import Game, PegPos, Zone
from aggervation.rules import IllegalMove, Move, MoveKind, position_after

# Red's start is track hole 0, Green's is 24; each home entry is 90 steps from start.


def card(rank: str) -> Card:
    return Card(rank, "S")


def new_game(turn: str = "RED") -> Game:
    game = Game(rng=random.Random(0))
    # Give everyone an ace so nobody folds unless a test arranges it.
    for player in game.players:
        player.hand = [card("A")]
    game.current_idx = [p.color for p in game.players].index(turn)
    return game


def place(game: Game, color: str, num: int, travelled: int, blocking: bool = False):
    peg = game.player(color).pegs[num]
    peg.travelled = travelled
    peg.pos = position_after(color, travelled)
    peg.blocking = blocking
    return peg


def give(game: Game, *ranks: str) -> list[Card]:
    hand = [card(r) for r in ranks]
    game.current_player.hand = list(hand)
    return hand


def fwd(peg: int, steps: int) -> Move:
    return Move(MoveKind.FORWARD, peg=peg, steps=steps)


# --- Getting out of base ---

@pytest.mark.parametrize("rank", ["A", "K"])
def test_ace_and_king_bring_a_peg_out_blocking(rank):
    game = new_game()
    (c,) = give(game, rank)
    moves = game.legal_moves(c)
    assert moves == [Move(MoveKind.ENTER, peg=0)]
    game.play_card(c, moves[0])
    peg = game.player("RED").pegs[0]
    assert peg.pos == PegPos.track(0)
    assert peg.blocking


@pytest.mark.parametrize("rank", ["2", "5", "7", "Q", "J", "6", "10"])
def test_other_cards_cannot_leave_base(rank):
    game = new_game()
    (c,) = give(game, rank)
    assert game.legal_moves(c) == []


def test_entering_kills_opponent_on_your_start():
    game = new_game()
    green = place(game, "GREEN", 0, 72)  # Green's start is 24, so 72 steps on = hole 0
    assert green.pos == PegPos.track(0)
    (c,) = give(game, "A")
    game.play_card(c, Move(MoveKind.ENTER, peg=0))
    assert green.pos.zone is Zone.BASE


def test_cannot_enter_onto_own_peg():
    game = new_game()
    place(game, "RED", 1, 0)
    (c,) = give(game, "K")
    assert Move(MoveKind.ENTER, peg=0) not in game.legal_moves(c)


# --- Must play / folding ---

def test_must_choose_a_move_for_a_playable_card():
    game = new_game()
    (c,) = give(game, "A")
    with pytest.raises(IllegalMove):
        game.play_card(c)


def test_cannot_throw_away_a_dead_card_while_holding_a_mover():
    game = new_game()
    (five, _) = give(game, "5", "A")
    with pytest.raises(IllegalMove):
        game.play_card(five)


def test_player_who_cannot_move_folds_and_is_skipped():
    game = new_game("YELLOW")
    game.player("RED").hand = [card("5"), card("9")]  # all Red pegs in base: no move
    (a,) = give(game, "A")
    game.play_card(a, Move(MoveKind.ENTER, peg=0))
    red = game.player("RED")
    assert red.hand == []
    assert any("RED can't play and folds" in line for line in game.log)
    assert game.current_player.color == "GREEN"


def test_folded_player_gets_new_cards_next_hand():
    game = new_game("YELLOW")
    for player in game.players:
        player.hand = []
    place(game, "RED", 0, 10)
    place(game, "YELLOW", 0, 91)  # in home, so Red's 10 has nobody to swap with
    game.player("RED").hand = [card("10")]
    (two,) = give(game, "2")
    game.play_card(two, fwd(0, 2))
    assert any("RED can't play and folds" in line for line in game.log)
    assert game.hand_number == 1
    assert len(game.player("RED").hand) == 4


def test_rejects_move_not_allowed_by_card():
    game = new_game()
    place(game, "RED", 0, 10)
    (c,) = give(game, "5")
    with pytest.raises(IllegalMove):
        game.play_card(c, fwd(0, 4))


# --- Moving and killing ---

def test_face_cards_move_their_value():
    game = new_game()
    peg = place(game, "RED", 0, 10)
    (c,) = give(game, "Q")
    game.play_card(c, fwd(0, 12))
    assert peg.pos == PegPos.track(22)
    assert peg.travelled == 22


def test_moving_off_start_clears_blocking():
    game = new_game()
    peg = place(game, "RED", 0, 0, blocking=True)
    (c,) = give(game, "3")
    game.play_card(c, fwd(0, 3))
    assert not peg.blocking


def test_landing_on_opponent_sends_it_to_base():
    game = new_game()
    place(game, "RED", 0, 10)
    blue = place(game, "BLUE", 2, 63)  # Blue starts at 48; 63 steps on = hole 15
    assert blue.pos == PegPos.track(15)
    (c,) = give(game, "5")
    game.play_card(c, fwd(0, 5))
    assert blue.pos.zone is Zone.BASE
    assert "sent BLUE back to base" in game.last_action


def test_cannot_land_on_own_peg():
    game = new_game()
    place(game, "RED", 0, 10)
    place(game, "RED", 1, 15)
    (c,) = give(game, "5")
    assert fwd(0, 5) not in game.legal_moves(c)


def test_can_jump_ordinary_pegs():
    game = new_game()
    place(game, "RED", 0, 10)
    place(game, "RED", 1, 12)
    green = place(game, "GREEN", 0, 85)  # hole 13
    (c,) = give(game, "5")
    game.play_card(c, fwd(0, 5))
    assert green.pos == PegPos.track(13)  # jumped, not killed


def test_blocking_peg_cannot_be_jumped_or_landed_on():
    game = new_game()
    place(game, "RED", 0, 20)
    place(game, "GREEN", 0, 0, blocking=True)  # hole 24
    (four, five) = give(game, "4", "5")
    assert game.legal_moves(four) == []  # would land on it
    assert game.legal_moves(five) == []  # would jump it


def test_blocking_peg_blocks_its_own_side_too():
    game = new_game()
    place(game, "RED", 0, 0, blocking=True)
    place(game, "RED", 1, -3)  # just behind the start
    (c,) = give(game, "5")
    assert fwd(1, 5) not in game.legal_moves(c)


def test_non_blocking_peg_on_start_can_be_killed():
    game = new_game()
    place(game, "RED", 0, 20)
    green = place(game, "GREEN", 0, 0, blocking=False)
    (c,) = give(game, "4")
    game.play_card(c, fwd(0, 4))
    assert green.pos.zone is Zone.BASE


# --- Home ---

def test_peg_turns_into_home():
    game = new_game()
    peg = place(game, "RED", 0, 88)
    (c,) = give(game, "5")
    game.play_card(c, fwd(0, 5))
    assert peg.pos == PegPos.home(2)


def test_cannot_overshoot_home():
    game = new_game()
    place(game, "RED", 0, 88)
    (c,) = give(game, "8")
    assert game.legal_moves(c) == []


def test_cannot_jump_or_land_on_pegs_in_home():
    game = new_game()
    place(game, "RED", 0, 88)
    place(game, "RED", 1, 92)  # home slot 1
    (jump, land) = give(game, "5", "4")
    assert fwd(0, 5) not in game.legal_moves(jump)
    assert fwd(0, 4) not in game.legal_moves(land)


def test_pegs_can_move_up_inside_home():
    game = new_game()
    peg = place(game, "RED", 0, 91)
    (c,) = give(game, "3")
    game.play_card(c, fwd(0, 3))
    assert peg.pos == PegPos.home(3)


def test_home_pegs_are_safe_from_opponents():
    game = new_game()
    place(game, "RED", 0, 92)
    green = place(game, "GREEN", 0, 60)  # Green walks past Red's home entry
    game.current_idx = 1
    (c,) = give(game, "8")
    game.play_card(c, fwd(0, 8))
    assert green.pos == PegPos.track(92)
    assert game.player("RED").pegs[0].pos == PegPos.home(1)


# --- 6: backwards ---

def test_six_moves_backwards_and_can_kill():
    game = new_game()
    peg = place(game, "RED", 0, 20)
    green = place(game, "GREEN", 0, 86)  # hole 14
    (c,) = give(game, "6")
    assert game.legal_moves(c) == [Move(MoveKind.BACKWARD, peg=0, steps=6)]
    game.play_card(c, game.legal_moves(c)[0])
    assert peg.pos == PegPos.track(14)
    assert green.pos.zone is Zone.BASE


def test_six_back_from_start_lands_on_home_entry_then_turns_in():
    game = new_game()
    peg = place(game, "RED", 0, 0)
    (six, three) = give(game, "6", "3")
    game.play_card(six, Move(MoveKind.BACKWARD, peg=0, steps=6))
    assert peg.pos == PegPos.track(90)  # Red's home entry
    game.current_idx = 0
    game.play_card(three, fwd(0, 3))
    assert peg.pos == PegPos.home(2)


def test_six_back_from_just_after_start_passes_home_entry():
    game = new_game()
    place(game, "RED", 0, 10)
    peg = place(game, "RED", 1, 2)
    (six,) = give(game, "6")
    game.play_card(six, Move(MoveKind.BACKWARD, peg=1, steps=6))
    assert peg.pos == PegPos.track(92)  # between home entry (90) and start (0)
    assert peg.travelled == -4  # just behind the start: has to go round
    assert position_after("RED", peg.travelled + 5) == PegPos.track(1)


def test_six_back_twice_ends_before_home_entry_and_can_turn_in():
    game = new_game()
    peg = place(game, "RED", 0, -4)  # hole 92
    (six, five) = give(game, "6", "5")
    game.play_card(six, Move(MoveKind.BACKWARD, peg=0, steps=6))
    assert peg.pos == PegPos.track(86)
    assert peg.travelled == 86  # 4 short of the home entry
    game.current_idx = 0
    game.play_card(five, fwd(0, 5))
    assert peg.pos == PegPos.home(0)


def test_six_cannot_move_pegs_in_home():
    game = new_game()
    place(game, "RED", 0, 93)
    (c,) = give(game, "6")
    assert game.legal_moves(c) == []


# --- 10: swap ---

def test_ten_swaps_with_any_peg_in_play():
    game = new_game()
    red = place(game, "RED", 0, 10)
    blue = place(game, "BLUE", 0, 0, blocking=True)  # Blue's start, hole 48
    (c,) = give(game, "10")
    move = Move(MoveKind.SWAP, peg=0, target=("BLUE", 0))
    assert move in game.legal_moves(c)
    game.play_card(c, move)
    assert red.pos == PegPos.track(48) and red.travelled == 48
    assert blue.pos == PegPos.track(10) and not blue.blocking
    assert blue.travelled == 10 - 48 + 96


def test_ten_needs_your_own_peg_on_track():
    game = new_game()
    place(game, "RED", 0, 91)  # in home: not swappable
    place(game, "BLUE", 0, 5)
    (c,) = give(game, "10")
    assert game.legal_moves(c) == []


def test_swap_partner_in_home_not_allowed():
    game = new_game()
    place(game, "RED", 0, 10)
    place(game, "BLUE", 0, 92)
    (c,) = give(game, "10")
    assert game.legal_moves(c) == []


# --- 7: split ---

def test_seven_can_split_between_pegs():
    game = new_game()
    a = place(game, "RED", 0, 10)
    b = place(game, "RED", 1, 30)
    (c,) = give(game, "7")
    move = Move(MoveKind.SPLIT, splits=((0, 3), (1, 4)))
    assert move in game.legal_moves(c)
    game.play_card(c, move)
    assert a.travelled == 13 and b.travelled == 34


def test_seven_kills_pegs_it_passes():
    game = new_game()
    place(game, "RED", 0, 10)
    green = place(game, "GREEN", 0, 84)  # hole 12
    (c,) = give(game, "7")
    game.play_card(c, Move(MoveKind.SPLIT, splits=((0, 7),)))
    assert green.pos.zone is Zone.BASE


def test_seven_jumps_own_pegs_without_killing():
    game = new_game()
    place(game, "RED", 0, 10)
    own = place(game, "RED", 1, 12)
    (c,) = give(game, "7")
    game.play_card(c, Move(MoveKind.SPLIT, splits=((0, 7),)))
    assert own.pos == PegPos.track(12)


def test_seven_must_use_all_steps():
    game = new_game()
    place(game, "RED", 0, 91)  # only 3 steps left in home
    (c,) = give(game, "7")
    assert game.legal_moves(c) == []


def test_seven_cannot_pass_a_blocking_peg():
    game = new_game()
    place(game, "RED", 0, 20)
    place(game, "GREEN", 0, 0, blocking=True)
    (c,) = give(game, "7")
    assert game.legal_moves(c) == []


# --- J: skip ---

def test_jack_moves_eleven_and_skips_next_player():
    game = new_game("RED")
    place(game, "RED", 0, 10)
    place(game, "GREEN", 0, 5)
    (j,) = give(game, "J")
    game.play_card(j, fwd(0, 11))
    assert game.current_player.color == "GREEN"
    assert game.skip_pending
    (four,) = give(game, "4")
    assert game.legal_moves(four) == []
    with pytest.raises(IllegalMove):
        game.play_card(four, fwd(0, 4))
    game.play_card(four)
    assert not game.skip_pending
    assert game.current_player.color == "BLUE"


def test_jack_skip_passes_on_when_skipped_player_lays_a_jack():
    game = new_game("RED")
    place(game, "RED", 0, 10)
    (j,) = give(game, "J")
    game.play_card(j, fwd(0, 11))
    (j2,) = give(game, "J")  # Green, skipped, lays a jack
    game.play_card(j2)
    assert game.current_player.color == "BLUE"
    assert game.skip_pending
    (c,) = give(game, "A")  # Blue is skipped too, even holding an ace
    assert game.legal_moves(c) == []
    game.play_card(c)
    assert not game.skip_pending


# --- Winning ---

def test_last_peg_home_wins():
    game = new_game()
    for n in range(3):
        place(game, "RED", n, 94 - n)
    place(game, "RED", 3, 89)
    (c,) = give(game, "2")
    game.play_card(c, fwd(3, 2))
    assert game.winner().color == "RED"
    assert "WINS" in game.last_action
    with pytest.raises(IllegalMove):
        game.play_card(game.players[1].hand[0])


# --- Whole games ---

def check_board(game: Game) -> None:
    track = [p.pos for pl in game.players for p in pl.pegs if p.pos.zone is Zone.TRACK]
    assert len(track) == len(set(track)), "two pegs in one track hole"
    for pl in game.players:
        for zone in (Zone.BASE, Zone.HOME):
            slots = [p.pos.index for p in pl.pegs if p.pos.zone is zone]
            assert len(slots) == len(set(slots)) and all(0 <= s < 4 for s in slots)
        for p in pl.pegs:
            if p.pos.zone is not Zone.BASE:
                assert position_after(p.color, p.travelled) == p.pos


@pytest.mark.parametrize("seed", range(8))
def test_random_games_keep_board_valid(seed):
    rng = random.Random(seed)
    game = Game(rng=random.Random(seed))
    for _ in range(3000):
        player = game.current_player
        if game.skip_pending:
            game.play_card(rng.choice(player.hand))
        else:
            options = [(c, m) for c in player.hand for m in game.legal_moves(c)]
            assert options, "a player with no moves should have folded"
            game.play_card(*rng.choice(options))
        check_board(game)
        held = sum(len(p.hand) for p in game.players)
        assert len(game.deck) + len(game.discard) + held == 52
        if game.winner():
            break


# --- Home row: exact counts (user's examples) ---

def test_two_spaces_left_allows_ace_or_two_but_not_three():
    game = new_game()
    place(game, "RED", 0, 92)  # home slot 1; slots 2 and 3 are free
    (ace, two, three) = give(game, "A", "2", "3")
    assert fwd(0, 1) in game.legal_moves(ace)  # (the ace could also bring a peg out)
    assert game.legal_moves(two) == [fwd(0, 2)]
    assert game.legal_moves(three) == []


def test_peg_passing_its_home_entry_must_turn_in():
    game = new_game()
    peg = place(game, "RED", 0, 89)  # one hole before the home entry
    (c,) = give(game, "3")
    game.play_card(c, fwd(0, 3))
    assert peg.pos == PegPos.home(1)  # turned in rather than carrying on round


def test_full_home_row_stops_peg_at_the_turn():
    game = new_game()
    place(game, "RED", 0, 87)
    place(game, "RED", 1, 91)  # first home slot taken
    (two, five) = give(game, "2", "5")
    assert fwd(0, 2) in game.legal_moves(two)  # lands on track before the turn
    assert fwd(0, 5) not in game.legal_moves(five)  # can't jump the home peg or go round


def test_home_peg_can_move_up_to_but_not_past_another():
    game = new_game()
    place(game, "RED", 0, 91)  # slot 0
    place(game, "RED", 1, 94)  # slot 3
    (one, two, three) = give(game, "A", "2", "3")
    assert fwd(0, 1) in game.legal_moves(one)
    assert fwd(0, 2) in game.legal_moves(two)
    assert fwd(0, 3) not in game.legal_moves(three)


def test_seven_split_obeys_home_rules():
    game = new_game()
    place(game, "RED", 0, 92)  # 2 spaces left in home
    place(game, "RED", 1, 10)
    (c,) = give(game, "7")
    moves = game.legal_moves(c)
    assert Move(MoveKind.SPLIT, splits=((0, 2), (1, 5))) in moves
    assert all(steps <= 2 for m in moves for num, steps in m.splits if num == 0)
