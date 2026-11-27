"""Online play: room codes, the waiting room, turns, and the live connection."""

import random
import re

import pytest
from fastapi.testclient import TestClient

from aggervation.web import rooms as rooms_mod
from aggervation.web.rooms import (
    LOBBY,
    OVER,
    PLAYING,
    Room,
    RoomError,
    RoomManager,
    new_code,
    normalize_code,
)
from aggervation.web.server import app, manager

CODE_RE = re.compile(r"^[A-HJKMNP-Z2-9]{4}-[A-HJKMNP-Z2-9]{4}$")


# --- Codes ---

def test_codes_look_like_xu8r_d4fg():
    rng = random.Random(1)
    codes = {new_code(set(), rng) for _ in range(200)}
    assert all(CODE_RE.match(c) for c in codes)
    assert not any(ch in c for c in codes for ch in "IL01O")


def test_codes_are_unique():
    rng = random.Random(2)
    taken: set[str] = set()
    for _ in range(500):
        taken.add(new_code(taken, rng))
    assert len(taken) == 500


@pytest.mark.parametrize("text", ["XU8R-D4FG", "xu8rd4fg", " xu8r d4fg ", "XU8R_D4FG"])
def test_code_entry_is_forgiving(text):
    assert normalize_code(text) == "XU8R-D4FG"


def test_bad_codes_rejected():
    assert normalize_code("XU8R-D4F") is None
    assert normalize_code("") is None


# --- Waiting room ---

def make_room() -> Room:
    mgr = RoomManager()
    return mgr.create("host", "Kelly")


def test_host_sits_first_and_friends_fill_seats():
    room = make_room()
    for i, name in enumerate(["Ann", "Bo", "Cy"]):
        room.join(f"t{i}", name)
    seats = {c: room.holder(c).name for c in ("RED", "GREEN", "BLUE", "YELLOW")}
    assert seats == {"RED": "Kelly", "GREEN": "Ann", "BLUE": "Bo", "YELLOW": "Cy"}
    room.join("t9", "Dee")
    assert room.members["t9"].seat is None  # table full: watching


def test_change_seats():
    room = make_room()
    room.join("a", "Ann")  # GREEN
    room.sit("a", "YELLOW")
    assert room.members["a"].seat == "YELLOW"
    with pytest.raises(RoomError):
        room.sit("a", "RED")  # host is there


def test_only_host_can_start_and_empty_seats_become_computers():
    room = make_room()
    room.join("a", "Ann")
    with pytest.raises(RoomError):
        room.start("a")
    room.start("host")
    assert room.phase == PLAYING
    assert room.computers == {"BLUE", "YELLOW"}


def test_host_can_add_and_remove_computers():
    room = make_room()
    room.set_computer("host", "BLUE", True)
    assert room.seat_kind("BLUE") == "computer"
    room.set_computer("host", "BLUE", False)
    assert room.seat_kind("BLUE") == "empty"


def test_cannot_put_computer_on_connected_player():
    room = make_room()
    room.join("a", "Ann")
    with pytest.raises(RoomError):
        room.set_computer("host", "GREEN", True)
    room.leave("a")
    room.set_computer("host", "GREEN", True)  # disconnected: allowed
    assert room.members["a"].seat is None


def test_rejoining_keeps_your_seat():
    room = make_room()
    room.join("a", "Ann")
    room.leave("a")
    room.join("a", "Ann")
    assert room.members["a"].seat == "GREEN"


def test_host_passes_on_when_host_leaves():
    room = make_room()
    room.join("a", "Ann")
    room.leave("host")
    assert room.host_token == "a"


def test_partners_setting_carries_into_game():
    room = make_room()
    room.set_partners("host", False)
    room.start("host")
    assert room.game.partners is False


# --- Playing ---

def started_room(humans=("host", "a", "b", "c")) -> Room:
    room = make_room()
    for t in humans[1:]:
        room.join(t, t)
    room.rng = random.Random(4)
    room.start("host")
    return room


def token_for(room: Room, color: str) -> str:
    return room.holder(color).token


def play_first_legal(room: Room) -> None:
    game = room.game
    color = game.current_player.color
    token = token_for(room, color)
    if game.skip_pending:
        room.play(token, 0, None, room.turn_seq)
        return
    for i, card in enumerate(game.current_player.hand):
        if game.legal_moves(card):
            room.play(token, i, 0, room.turn_seq)
            return
    raise AssertionError("current player should have a move")


def test_only_current_player_can_play():
    room = started_room()
    current = room.game.current_player.color
    other = next(c for c in ("RED", "GREEN", "BLUE", "YELLOW") if c != current)
    with pytest.raises(RoomError):
        room.play(token_for(room, other), 0, 0, room.turn_seq)


def test_stale_play_rejected():
    room = started_room()
    with pytest.raises(RoomError):
        room.play(token_for(room, room.game.current_player.color), 0, 0, room.turn_seq - 1)


def test_players_only_see_their_own_cards():
    room = started_room()
    view = room.view("a")  # GREEN
    assert len(view["game"]["hand"]) == len(room.game.player("GREEN").hand)
    assert "hand" not in view["game"]["players"]["RED"]
    assert view["game"]["players"]["RED"]["cards"] == len(room.game.player("RED").hand)


def test_current_player_gets_their_moves():
    room = started_room()
    current = room.game.current_player.color
    mine = room.view(token_for(room, current))["game"]
    theirs = room.view(token_for(room, "RED" if current != "RED" else "GREEN"))["game"]
    assert mine["moves"] is not None and len(mine["moves"]) == len(mine["hand"])
    assert theirs["moves"] is None


def test_seven_moves_include_landing_spots():
    room = started_room()
    view = room.view(token_for(room, room.game.current_player.color))
    for card, moves in zip(view["game"]["hand"], view["game"]["moves"]):
        for m in moves:
            if card["rank"] == "7":
                assert m["segments"] and all("dest" in s for s in m["segments"])
            else:
                assert m["segments"] == []


def test_humans_play_a_full_game_through_the_room():
    room = started_room()
    for _ in range(5000):
        if room.phase == OVER:
            break
        play_first_legal(room)
    assert room.phase == OVER
    room.back_to_lobby("host")
    assert room.phase == LOBBY and room.game is None


def test_computer_plays_its_turn_after_a_pause(monkeypatch):
    room = started_room(humans=("host",))
    t = room.last_change
    # Find a computer's turn.
    while room.game.current_player.color == "RED":
        play_first_legal(room)
    assert not room.computer_should_play(now=room.last_change)  # too soon
    assert room.computer_should_play(now=room.last_change + rooms_mod.BOT_DELAY)
    seq = room.turn_seq
    room.play_computer_turn()
    assert room.turn_seq == seq + 1


def test_disconnected_players_turn_is_covered_after_grace():
    room = started_room()
    color = room.game.current_player.color
    room.leave(token_for(room, color))
    now = room.last_change
    assert not room.computer_should_play(now=now + rooms_mod.BOT_DELAY)
    assert room.computer_should_play(now=now + rooms_mod.DISCONNECT_GRACE + 1)


def test_idle_empty_rooms_are_cleaned_up():
    mgr = RoomManager()
    room = mgr.create("host", "Kelly")
    room.leave("host")
    mgr.cleanup(now=room.last_change + RoomManager.IDLE_LIMIT + 1)
    assert room.code not in mgr.rooms


# --- Over the wire ---

@pytest.fixture
def client():
    manager.rooms.clear()
    with TestClient(app) as c:
        yield c


def test_pages_and_layout_served(client):
    assert client.get("/").status_code == 200
    assert "AGGRAVATION" in client.get("/g/XU8R-D4FG").text
    layout = client.get("/api/layout").json()
    assert len(layout["track"]) == 96


def test_create_join_and_start_over_websockets(client):
    code = client.post("/api/rooms", json={"token": "host", "name": "Kelly"}).json()["code"]
    assert CODE_RE.match(code)
    assert client.get(f"/api/rooms/{code.lower().replace('-', '')}").json()["code"] == code
    assert client.get("/api/rooms/AAAA-AAAA").status_code == 404

    with client.websocket_connect(f"/ws/{code}?token=host&name=Kelly") as host, \
            client.websocket_connect(f"/ws/{code}?token=ann&name=Ann") as ann:
        state = host.receive_json()
        assert state["phase"] == "lobby" and state["you"]["host"]
        # Ann joining makes both receive updates; drain until Ann is seated.
        while True:
            s = ann.receive_json()
            if s["you"]["seat"]:
                break
        assert s["you"]["seat"] == "GREEN" and not s["you"]["host"]

        ann.send_json({"type": "start"})
        err = ann.receive_json()
        assert err["type"] == "error" and "host" in err["message"]

        host.send_json({"type": "start"})
        while True:
            s = ann.receive_json()
            if s["type"] == "state" and s["phase"] == "playing":
                break
        game = s["game"]
        # Ann sees her own cards (none if she couldn't move and folded straight away).
        assert len(game["hand"]) == game["players"]["GREEN"]["cards"]
        assert game["players"]["GREEN"]["cards"] == 5 or game["players"]["GREEN"]["folded"]
        assert s["seats"]["BLUE"]["kind"] == "computer"


def test_unknown_code_gets_fatal_error(client):
    with client.websocket_connect("/ws/ZZZZ-ZZZZ?token=x") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "error" and msg["fatal"]
