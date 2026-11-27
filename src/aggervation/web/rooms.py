"""Game rooms for online play: codes, seats, the waiting room, and turns.

No networking here (see server.py), so it can be tested directly.
"""

from __future__ import annotations

import os
import random
import re
import secrets
import time
from dataclasses import dataclass, field

from ..bot import choose_play
from ..game import PLAYER_ORDER, Game
from ..rules import IllegalMove, MoveKind, apply_partial_split, copy_pegs
from ..models import Zone

# Codes look like XU8R-D4FG. Letters/digits that are easy to mix up (I/1/L, O/0) are left out.
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_GROUPS, CODE_GROUP_LEN = 2, 4
NAME_MAX = 20
LOG_LINES = 8
# Seconds before a computer plays, so people can follow (env var lets tests speed it up).
BOT_DELAY = float(os.environ.get("AGGRAVATION_BOT_DELAY", "1.0"))
DISCONNECT_GRACE = 30.0  # seconds a disconnected player's turn waits before a computer covers it

LOBBY, PLAYING, OVER = "lobby", "playing", "over"


class RoomError(Exception):
    """Something a player asked for isn't allowed (shown to them as a message)."""


def new_code(existing: set[str] | dict, rng: random.Random | None = None) -> str:
    choice = rng.choice if rng else secrets.choice
    while True:
        groups = ["".join(choice(CODE_ALPHABET) for _ in range(CODE_GROUP_LEN)) for _ in range(CODE_GROUPS)]
        code = "-".join(groups)
        if code not in existing:
            return code


def normalize_code(text: str) -> str | None:
    """'xu8r d4fg' -> 'XU8R-D4FG'. None if it can't be a code."""
    chars = re.sub(r"[^A-Za-z0-9]", "", text or "").upper()
    if len(chars) != CODE_GROUPS * CODE_GROUP_LEN:
        return None
    return "-".join(chars[i : i + CODE_GROUP_LEN] for i in range(0, len(chars), CODE_GROUP_LEN))


def clean_name(name: str) -> str:
    name = " ".join((name or "").split())[:NAME_MAX]
    return name or "Player"


@dataclass
class Member:
    token: str  # secret id kept in the browser, so a refresh rejoins the same seat
    name: str
    seat: str | None = None
    connected: bool = True
    disconnected_at: float | None = None


@dataclass
class Room:
    code: str
    host_token: str
    members: dict[str, Member] = field(default_factory=dict)
    computers: set[str] = field(default_factory=set)  # seats played by the computer
    partners: bool = True
    phase: str = LOBBY
    game: Game | None = None
    turn_seq: int = 0  # bumps on every play; stale plays are rejected
    last_change: float = field(default_factory=time.monotonic)
    rng: random.Random = field(default_factory=random.Random)

    # --- Seats ---

    def holder(self, color: str) -> Member | None:
        return next((m for m in self.members.values() if m.seat == color), None)

    def seat_kind(self, color: str) -> str:
        if color in self.computers:
            return "computer"
        return "human" if self.holder(color) else "empty"

    def _member(self, token: str) -> Member:
        if token not in self.members:
            raise RoomError("You're not in this game")
        return self.members[token]

    def _require_host(self, token: str) -> None:
        if token != self.host_token:
            raise RoomError("Only the host can do that")

    def _require_lobby(self) -> None:
        if self.phase != LOBBY:
            raise RoomError("The game has already started")

    def _touch(self) -> None:
        self.last_change = time.monotonic()

    def join(self, token: str, name: str) -> Member:
        """Add someone (or reconnect them). In the waiting room they get the first free seat."""
        member = self.members.get(token)
        if member:
            member.name = clean_name(name) if name else member.name
        else:
            member = Member(token, clean_name(name))
            self.members[token] = member
            if self.phase == LOBBY:
                free = next((c for c in PLAYER_ORDER if self.seat_kind(c) == "empty"), None)
                member.seat = free
        member.connected = True
        member.disconnected_at = None
        if self.host_token not in self.members or not self.members[self.host_token].connected:
            self.host_token = token
        self._touch()
        return member

    def leave(self, token: str) -> None:
        """Their connection dropped. They keep their seat and can come back."""
        member = self.members.get(token)
        if not member:
            return
        member.connected = False
        member.disconnected_at = time.monotonic()
        if token == self.host_token:
            other = next((m for m in self.members.values() if m.connected), None)
            if other:
                self.host_token = other.token
        self._touch()

    def sit(self, token: str, color: str) -> None:
        self._require_lobby()
        member = self._member(token)
        if color not in PLAYER_ORDER or self.seat_kind(color) != "empty":
            raise RoomError("That seat is taken")
        member.seat = color
        self._touch()

    def stand(self, token: str) -> None:
        self._require_lobby()
        self._member(token).seat = None
        self._touch()

    def set_computer(self, token: str, color: str, on: bool) -> None:
        """Host: put a computer in a seat (empty, or held by someone who's disconnected), or take it out."""
        self._require_host(token)
        self._require_lobby()
        if color not in PLAYER_ORDER:
            raise RoomError("No such seat")
        if on:
            holder = self.holder(color)
            if holder and holder.connected:
                raise RoomError(f"{holder.name} is sitting there")
            if holder:
                holder.seat = None
            self.computers.add(color)
        else:
            self.computers.discard(color)
        self._touch()

    def set_partners(self, token: str, on: bool) -> None:
        self._require_host(token)
        self._require_lobby()
        self.partners = bool(on)
        self._touch()

    def start(self, token: str) -> None:
        """Host starts the game. Any empty seats are filled with computers."""
        self._require_host(token)
        self._require_lobby()
        for color in PLAYER_ORDER:
            if self.seat_kind(color) == "empty":
                self.computers.add(color)
        self.game = Game(partners=self.partners, rng=self.rng)
        self.phase = PLAYING
        self.turn_seq += 1
        self._touch()

    def back_to_lobby(self, token: str) -> None:
        self._require_host(token)
        if self.phase != OVER:
            raise RoomError("The game isn't over yet")
        self.phase = LOBBY
        self.game = None
        self._touch()

    # --- Playing ---

    def _current_color(self) -> str:
        assert self.game is not None
        return self.game.current_player.color

    def play(self, token: str, card_idx: int, move_idx: int | None, turn_seq: int) -> None:
        if self.phase != PLAYING or self.game is None:
            raise RoomError("No game in progress")
        member = self._member(token)
        game = self.game
        if member.seat != self._current_color():
            raise RoomError("It's not your turn")
        if turn_seq != self.turn_seq:
            raise RoomError("The board changed - try again")
        hand = game.current_player.hand
        if not (0 <= card_idx < len(hand)):
            raise RoomError("No such card")
        card = hand[card_idx]
        move = None
        if move_idx is not None:
            moves = game.legal_moves(card)
            if not (0 <= move_idx < len(moves)):
                raise RoomError("That move isn't allowed")
            move = moves[move_idx]
        try:
            game.play_card(card, move)
        except IllegalMove as e:
            raise RoomError(str(e)) from e
        self._after_play()

    def _after_play(self) -> None:
        self.turn_seq += 1
        if self.game and self.game.winner():
            self.phase = OVER
        self._touch()

    def computer_should_play(self, now: float | None = None) -> bool:
        """True when it's a computer's turn (or a disconnected player's, after the grace period)."""
        if self.phase != PLAYING or self.game is None:
            return False
        now = time.monotonic() if now is None else now
        if now - self.last_change < BOT_DELAY:
            return False
        color = self._current_color()
        if color in self.computers:
            return True
        holder = self.holder(color)
        if holder is None:
            return True
        if not holder.connected and holder.disconnected_at is not None:
            return now - max(holder.disconnected_at, self.last_change) >= DISCONNECT_GRACE
        return False

    def play_computer_turn(self) -> None:
        assert self.game is not None
        self.game.play_card(*choose_play(self.game, self.rng))
        self._after_play()

    # --- What each person sees ---

    def view(self, token: str) -> dict:
        me = self.members.get(token)
        seats = {}
        for color in PLAYER_ORDER:
            holder = self.holder(color)
            seats[color] = {
                "kind": self.seat_kind(color),
                "name": "Computer" if color in self.computers else (holder.name if holder else None),
                "connected": holder.connected if holder else True,
                "host": bool(holder and holder.token == self.host_token),
            }
        data = {
            "type": "state",
            "code": self.code,
            "phase": self.phase,
            "partners": self.partners,
            "seats": seats,
            "you": {
                "name": me.name if me else None,
                "seat": me.seat if me else None,
                "host": token == self.host_token,
            },
            "watchers": [m.name for m in self.members.values() if m.seat is None and m.connected],
            "game": self._game_view(me) if self.game else None,
        }
        return data

    def _game_view(self, me: Member | None) -> dict:
        game = self.game
        assert game is not None
        current = game.current_player
        players = {}
        for p in game.players:
            partner = game.partner_of(p)
            players[p.color] = {
                "cards": len(p.hand),
                "folded": p.color in game.folded,
                "all_home": p.has_won(),
                "partner": partner.color if partner else None,
                "control": game.controlled_color(p),
            }
        view = {
            "turn_seq": self.turn_seq,
            "deal": game.deal_number,
            "hand_number": game.hand_number + 1,
            "dealer": game.dealer.color,
            "current": current.color,
            "control": game.controlled_color(),
            "skip_pending": game.skip_pending,
            "winners": [p.color for p in game.winners()],
            "log": game.log[-LOG_LINES:],
            "last_moved": [list(k) for k in game.last_moved],
            "players": players,
            "pegs": [
                {
                    "color": peg.color,
                    "num": peg.number,
                    "zone": peg.pos.zone.value,
                    "index": peg.pos.index,
                    "blocking": peg.blocking,
                }
                for p in game.players
                for peg in p.pegs
            ],
            "hand": [],
            "moves": None,
        }
        if me and me.seat:
            seat_player = game.player(me.seat)
            view["hand"] = [{"rank": c.rank, "suit": c.suit, "label": c.label} for c in seat_player.hand]
            if me.seat == current.color and self.phase == PLAYING and not game.skip_pending:
                view["moves"] = [
                    [self._move_json(m) for m in game.legal_moves(card)] for card in current.hand
                ]
        return view

    def _move_json(self, move) -> dict:
        game = self.game
        assert game is not None
        data = {
            "kind": move.kind.value,
            "peg": move.peg,
            "target": list(move.target) if move.target else None,
            "segments": [],
        }
        if move.kind is MoveKind.SPLIT:
            # Where each part of a 7 lands, and who it knocks back, so the page can preview it.
            trial = copy_pegs(game.players)
            for color, num, steps in move.segments(game.controlled_color()):
                before = {(p.color, p.number): p.pos for pl in trial for p in pl.pegs}
                apply_partial_split(trial, [(color, num, steps)])
                moved = next(p for pl in trial for p in pl.pegs if (p.color, p.number) == (color, num))
                sent = [
                    [p.color, p.number]
                    for pl in trial
                    for p in pl.pegs
                    if p.pos.zone is Zone.BASE and before[(p.color, p.number)].zone is not Zone.BASE
                ]
                data["segments"].append(
                    {
                        "color": color,
                        "num": num,
                        "steps": steps,
                        "dest": {"zone": moved.pos.zone.value, "index": moved.pos.index},
                        "sent": sent,
                    }
                )
        return data


class RoomManager:
    """All the games being played on this server."""

    IDLE_LIMIT = 6 * 60 * 60  # forget rooms nobody has touched for 6 hours

    def __init__(self):
        self.rooms: dict[str, Room] = {}

    def create(self, token: str, name: str) -> Room:
        code = new_code(self.rooms)
        room = Room(code=code, host_token=token)
        room.join(token, name)
        self.rooms[code] = room
        return room

    def get(self, code: str) -> Room | None:
        normalized = normalize_code(code)
        return self.rooms.get(normalized) if normalized else None

    def cleanup(self, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        for code, room in list(self.rooms.items()):
            nobody_here = not any(m.connected for m in room.members.values())
            if nobody_here and now - room.last_change > self.IDLE_LIMIT:
                del self.rooms[code]
