"""Core data types: where pegs are and who owns them."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .cards import Card
from .layout_data import PLAYERS, TRACK

# Turn order follows the direction of play (clockwise on the board).
PLAYER_ORDER = ["RED", "GREEN", "BLUE", "YELLOW"]
PEGS_PER_PLAYER = 4
TRACK_LEN = len(TRACK)
HOME_LEN = 4


class Zone(Enum):
    BASE = "base"
    TRACK = "track"
    HOME = "home"


@dataclass(frozen=True)
class PegPos:
    """Where a peg is. ``index`` is the base slot, track hole, or home slot."""

    zone: Zone
    index: int

    @staticmethod
    def base(slot: int) -> PegPos:
        return PegPos(Zone.BASE, slot)

    @staticmethod
    def track(hole: int) -> PegPos:
        return PegPos(Zone.TRACK, hole % TRACK_LEN)

    @staticmethod
    def home(slot: int) -> PegPos:
        return PegPos(Zone.HOME, slot)


@dataclass
class Peg:
    color: str
    number: int  # 0-3, identifies the peg within its player
    pos: PegPos
    # Steps forward from this player's start hole (90 = the home entry hole).
    # Holes between the home entry and the start count as negative: a peg
    # there is just behind its start and must go round.
    travelled: int = 0
    # True when the peg came straight out of base onto its start hole (with an
    # A or K). Nobody may jump, land on, or kill it until it moves off.
    blocking: bool = False


@dataclass
class Player:
    color: str
    pegs: list[Peg]
    hand: list[Card] = field(default_factory=list)

    @property
    def start_index(self) -> int:
        return PLAYERS[self.color]["start_index"]

    @property
    def home_entry_index(self) -> int:
        return PLAYERS[self.color]["home_entry_index"]

    def pegs_in(self, zone: Zone) -> list[Peg]:
        return [p for p in self.pegs if p.pos.zone is zone]

    def has_won(self) -> bool:
        return all(p.pos.zone is Zone.HOME for p in self.pegs)
