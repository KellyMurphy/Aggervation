"""Card rules: which moves a card allows, and carrying them out.

House rules (see basics/rules.txt):
  A   Get out of base, or move 1.
  K   Get out of base, or move 13.
  J   Move 11. The next player must play a card without moving; if they also
      lay a jack, the skip passes on. (Handled in game.py.)
  10  Swap one of your pegs in play with another peg in play. The only card
      that can move someone's blocking peg off its start.
  7   Split 7 steps among your pegs. Opponent pegs you pass over go back to
      base. Can't bring a peg out of base.
  6   Move one of your pegs backwards 6.
  Others move their face value (Q = 12).
  Start spot: a peg brought straight out of base with A/K blocks everything:
      no peg may pass, land on, or kill it until it moves off.
  Home: pegs in home are safe; no peg may jump another in the home row.

Other rules the house rules don't spell out:
  - Landing on an opponent sends it back to base. You can't land on your own peg.
  - Normal moves may jump over pegs (except a blocking peg, or any peg in home).
  - A peg reaching its home entry must turn into home, by an exact count.
    A 6 that leaves the peg on or before its home entry (e.g. backing up
    6 from its start) is a shortcut: the next move can turn into home.
  - A 7 must use all 7 steps.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from enum import Enum
from itertools import permutations
from typing import Iterator

from .cards import Card
from .layout_data import PLAYERS
from .models import HOME_LEN, PEGS_PER_PLAYER, TRACK_LEN, Peg, PegPos, Player, Zone

CARD_STEPS = {
    "A": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7,
    "8": 8, "9": 9, "10": 10, "J": 11, "Q": 12, "K": 13,
}
ENTER_RANKS = {"A", "K"}
BACKWARD_RANK, BACKWARD_STEPS = "6", 6
SPLIT_RANK, SPLIT_TOTAL = "7", 7
SWAP_RANK = "10"


class IllegalMove(ValueError):
    pass


class MoveKind(Enum):
    ENTER = "enter"
    FORWARD = "forward"
    BACKWARD = "backward"
    SWAP = "swap"
    SPLIT = "split"


@dataclass(frozen=True)
class Move:
    kind: MoveKind
    peg: int | None = None  # the mover's peg number (all kinds except SPLIT)
    steps: int = 0  # FORWARD / BACKWARD
    target: tuple[str, int] | None = None  # SWAP: (color, peg number) to trade places with
    splits: tuple[tuple[int, int], ...] = ()  # SPLIT: (peg number, steps), applied in order

    def describe(self) -> str:
        if self.kind is MoveKind.ENTER:
            return "brought a peg out of base"
        if self.kind is MoveKind.FORWARD:
            return f"moved peg {self.peg + 1} forward {self.steps}"
        if self.kind is MoveKind.BACKWARD:
            return f"moved peg {self.peg + 1} back {self.steps}"
        if self.kind is MoveKind.SWAP:
            color, num = self.target
            return f"swapped peg {self.peg + 1} with {color} peg {num + 1}"
        parts = ", ".join(f"peg {n + 1} x{s}" for n, s in self.splits)
        return f"split 7: {parts}"


# --- Geometry ---

def home_entry_steps(color: str) -> int:
    """How far from its start a peg is when it reaches its home entry hole."""
    info = PLAYERS[color]
    return (info["home_entry_index"] - info["start_index"]) % TRACK_LEN


def position_after(color: str, travelled: int) -> PegPos | None:
    """Where a peg ``travelled`` steps from its start sits, or None if past the end of home."""
    entry = home_entry_steps(color)
    if travelled <= entry:
        return PegPos.track(PLAYERS[color]["start_index"] + travelled)
    slot = travelled - entry - 1
    return PegPos.home(slot) if slot < HOME_LEN else None


def travelled_at(color: str, hole: int) -> int:
    """Steps-from-start for a peg dropped onto ``hole`` (by a swap).

    Holes between the home entry and the start count as just behind the start.
    """
    progress = (hole - PLAYERS[color]["start_index"]) % TRACK_LEN
    return progress if progress <= home_entry_steps(color) else progress - TRACK_LEN


# --- Board helpers ---

def _player(players: list[Player], color: str) -> Player:
    return next(p for p in players if p.color == color)


def peg_at(players: list[Player], pos: PegPos, owner: str) -> Peg | None:
    """The peg at ``pos``. Base and home holes are private, so only ``owner``'s pegs count there."""
    for player in players:
        if pos.zone is not Zone.TRACK and player.color != owner:
            continue
        for peg in player.pegs:
            if peg.pos == pos:
                return peg
    return None


def send_to_base(players: list[Player], peg: Peg) -> None:
    owner = _player(players, peg.color)
    taken = {p.pos.index for p in owner.pegs if p.pos.zone is Zone.BASE}
    peg.pos = PegPos.base(min(set(range(PEGS_PER_PLAYER)) - taken))
    peg.travelled = 0
    peg.blocking = False


# --- Carrying out moves ---

def _move_forward(players: list[Player], peg: Peg, steps: int, kill_passed: bool) -> None:
    if peg.pos.zone is Zone.BASE:
        raise IllegalMove("That peg is still in base")
    for k in range(1, steps + 1):
        travelled = peg.travelled + k
        pos = position_after(peg.color, travelled)
        if pos is None:
            raise IllegalMove("That would go past the end of home")
        other = peg_at(players, pos, peg.color)
        if other is None:
            continue
        if pos.zone is Zone.HOME:
            raise IllegalMove("Pegs can't jump or land on each other in home")
        if other.blocking:
            raise IllegalMove("A peg on its start spot is blocking the way")
        if k == steps:
            if other.color == peg.color:
                raise IllegalMove("You already have a peg there")
            send_to_base(players, other)
        elif kill_passed and other.color != peg.color:
            send_to_base(players, other)
    peg.pos = position_after(peg.color, peg.travelled + steps)
    peg.travelled += steps
    peg.blocking = False


def _move_backward(players: list[Player], peg: Peg, steps: int) -> None:
    if peg.pos.zone is not Zone.TRACK:
        raise IllegalMove("Only pegs on the track can move backwards")
    start = PLAYERS[peg.color]["start_index"]
    for k in range(1, steps + 1):
        pos = PegPos.track(start + peg.travelled - k)
        other = peg_at(players, pos, peg.color)
        if other is None:
            continue
        if other.blocking:
            raise IllegalMove("A peg on its start spot is blocking the way")
        if k == steps:
            if other.color == peg.color:
                raise IllegalMove("You already have a peg there")
            send_to_base(players, other)
    peg.pos = PegPos.track(start + peg.travelled - steps)
    # Where the peg now sits is what counts: backing onto (or past) your home
    # entry means your next forward move turns into home.
    peg.travelled = travelled_at(peg.color, peg.pos.index)
    peg.blocking = False


def _enter(players: list[Player], peg: Peg) -> None:
    if peg.pos.zone is not Zone.BASE:
        raise IllegalMove("That peg isn't in base")
    start = PegPos.track(PLAYERS[peg.color]["start_index"])
    other = peg_at(players, start, peg.color)
    if other is not None:
        if other.color == peg.color:
            raise IllegalMove("Your start spot is occupied by your own peg")
        if other.blocking:
            raise IllegalMove("Your start spot is blocked")
        send_to_base(players, other)
    peg.pos = start
    peg.travelled = 0
    peg.blocking = True


def _swap(peg: Peg, other: Peg) -> None:
    if peg is other:
        raise IllegalMove("Pick a different peg to swap with")
    if peg.pos.zone is not Zone.TRACK or other.pos.zone is not Zone.TRACK:
        raise IllegalMove("Both pegs must be on the track")
    peg.pos, other.pos = other.pos, peg.pos
    for p in (peg, other):
        p.travelled = travelled_at(p.color, p.pos.index)
        p.blocking = False


def apply_move(players: list[Player], color: str, move: Move) -> None:
    """Carry out ``move`` for ``color``. May leave ``players`` half-changed if it raises."""
    own = _player(players, color).pegs
    kind = move.kind
    if kind is MoveKind.ENTER:
        _enter(players, own[move.peg])
    elif kind is MoveKind.FORWARD:
        _move_forward(players, own[move.peg], move.steps, kill_passed=False)
    elif kind is MoveKind.BACKWARD:
        _move_backward(players, own[move.peg], move.steps)
    elif kind is MoveKind.SWAP:
        target_color, target_num = move.target
        _swap(own[move.peg], _player(players, target_color).pegs[target_num])
    elif kind is MoveKind.SPLIT:
        if sum(s for _, s in move.splits) != SPLIT_TOTAL:
            raise IllegalMove("A 7 must use all 7 steps")
        for num, steps in move.splits:
            _move_forward(players, own[num], steps, kill_passed=True)


def apply_partial_split(players: list[Player], color: str, splits) -> None:
    """Apply the first part(s) of a 7 split, e.g. to preview it while the player is still choosing."""
    own = _player(players, color).pegs
    for num, steps in splits:
        _move_forward(players, own[num], steps, kill_passed=True)


def copy_pegs(players: list[Player]) -> list[Player]:
    """A copy of the board (pegs only) that can be changed freely."""
    return [Player(p.color, [copy.copy(peg) for peg in p.pegs]) for p in players]


# --- Finding legal moves ---

def _compositions(total: int, parts: int) -> Iterator[tuple[int, ...]]:
    if parts == 1:
        yield (total,)
        return
    for first in range(1, total - parts + 2):
        for rest in _compositions(total - first, parts - 1):
            yield (first, *rest)


def _split_candidates(peg_numbers: list[int]) -> Iterator[tuple[tuple[int, int], ...]]:
    for count in range(1, len(peg_numbers) + 1):
        for order in permutations(peg_numbers, count):
            for parts in _compositions(SPLIT_TOTAL, count):
                yield tuple(zip(order, parts))


def _is_legal(players: list[Player], color: str, move: Move) -> bool:
    trial = copy_pegs(players)  # pegs only; much cheaper than a deepcopy
    try:
        apply_move(trial, color, move)
    except IllegalMove:
        return False
    return True


def _candidates(players: list[Player], color: str, card: Card) -> list[Move]:
    """Every move the card could mean, legal or not."""
    pegs = _player(players, color).pegs
    on_track = [p for p in pegs if p.pos.zone is Zone.TRACK]
    in_play = [p for p in pegs if p.pos.zone is not Zone.BASE]
    in_base = [p for p in pegs if p.pos.zone is Zone.BASE]

    if card.rank == SWAP_RANK:
        everyone_on_track = [p for pl in players for p in pl.pegs if p.pos.zone is Zone.TRACK]
        candidates = [
            Move(MoveKind.SWAP, peg=a.number, target=(b.color, b.number))
            for a in on_track
            for b in everyone_on_track
            if b is not a
        ]
    elif card.rank == SPLIT_RANK:
        candidates = [
            Move(MoveKind.SPLIT, splits=s) for s in _split_candidates([p.number for p in in_play])
        ]
    elif card.rank == BACKWARD_RANK:
        candidates = [Move(MoveKind.BACKWARD, peg=p.number, steps=BACKWARD_STEPS) for p in on_track]
    else:
        steps = CARD_STEPS[card.rank]
        candidates = [Move(MoveKind.FORWARD, peg=p.number, steps=steps) for p in in_play]
        if card.rank in ENTER_RANKS and in_base:
            # All base pegs are alike; offer one.
            candidates.insert(0, Move(MoveKind.ENTER, peg=in_base[0].number))

    return candidates


def legal_moves(players: list[Player], color: str, card: Card) -> list[Move]:
    return [m for m in _candidates(players, color, card) if _is_legal(players, color, m)]


def has_legal_move(players: list[Player], color: str, cards: list[Card]) -> bool:
    """True if any of ``cards`` has a legal move. Stops at the first one found."""
    return any(
        _is_legal(players, color, m) for card in cards for m in _candidates(players, color, card)
    )
