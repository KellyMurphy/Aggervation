import math

from aggervation.layout_data import PLAYERS, TRACK

ORDER = ["RED", "GREEN", "BLUE", "YELLOW"]


def test_track_is_closed_loop_of_96():
    assert len(TRACK) == 96
    assert len(set(TRACK)) == 96
    for a, b in zip(TRACK, TRACK[1:] + TRACK[:1]):
        assert math.dist(a, b) < 60


def test_each_player_has_four_base_and_home_holes():
    for info in PLAYERS.values():
        assert len(info["base"]) == 4
        assert len(info["home"]) == 4


def test_starts_are_evenly_spaced_in_turn_order():
    starts = [PLAYERS[c]["start_index"] for c in ORDER]
    assert starts == [0, 24, 48, 72]


def test_home_entry_is_just_before_own_start():
    for info in PLAYERS.values():
        assert (info["start_index"] - info["home_entry_index"]) % 96 == 6


def test_home_row_starts_next_to_entry():
    for info in PLAYERS.values():
        entry = TRACK[info["home_entry_index"]]
        assert math.dist(entry, info["home"][0]) < 120
        # Each subsequent home hole goes further in.
        dists = [math.dist(entry, h) for h in info["home"]]
        assert dists == sorted(dists)
