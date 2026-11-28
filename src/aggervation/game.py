"""Game flow: dealing, turns, and playing cards through the rules.

No pygame here, so it can be tested without a window.
"""

from __future__ import annotations

import random

from .cards import Card, Deck
from .models import (  # noqa: F401  (re-exported for callers)
    HOME_LEN,
    PEGS_PER_PLAYER,
    PLAYER_ORDER,
    TRACK_LEN,
    Peg,
    PegPos,
    Player,
    Zone,
)
from .rules import (
    SPLIT_RANK,
    IllegalMove,
    Move,
    SevenChoice,
    apply_move,
    has_legal_move,
    is_legal_seven,
    legal_moves,
    seven_choices,
    seven_move,
    seven_preview,
)

# "4 Player - One 5 card hand & two 4 card hands per deal" (4 x 13 = 52 cards).
HAND_SIZES = (5, 4, 4)
JACK = "J"


class Game:
    def __init__(
        self,
        colors: list[str] | None = None,
        rng: random.Random | None = None,
        partners: bool = True,
    ):
        colors = colors or PLAYER_ORDER
        if len(colors) != 4:
            raise ValueError("Only the 4-player deal is defined so far")
        self.rng = rng or random.Random()
        # Partners sit opposite each other: Red & Blue, Green & Yellow.
        self.partners = partners
        self.players = [
            Player(c, [Peg(c, n, PegPos.base(n)) for n in range(PEGS_PER_PLAYER)]) for c in colors
        ]
        self.discard: list[Card] = []
        self.dealer_idx = 0
        self.current_idx = 0
        self.deal_number = 0  # how many deals (full decks) have started
        self.hand_number = 0  # 0, 1, 2 within the current deal
        # Set by a jack: the current player must play a card without moving.
        self.skip_pending = False
        self.log: list[str] = []  # what happened, newest last
        self.last_moved: set[tuple[str, int]] = set()
        self.folded: set[str] = set()  # players sitting out the rest of this hand  # pegs (color, number) moved by the last play
        self.deck = Deck(self.rng)
        self._start_deal()
        self._fold_stuck_players()

    # --- Queries ---

    @property
    def current_player(self) -> Player:
        return self.players[self.current_idx]

    @property
    def dealer(self) -> Player:
        return self.players[self.dealer_idx]

    def player(self, color: str) -> Player:
        return next(p for p in self.players if p.color == color)

    def peg_at(self, pos: PegPos, color: str | None = None) -> Peg | None:
        """The peg at a position. Base and home slots belong to a player, so pass ``color`` for those."""
        for player in self.players:
            if pos.zone is not Zone.TRACK and player.color != color:
                continue
            for peg in player.pegs:
                if peg.pos == pos:
                    return peg
        return None

    @property
    def last_action(self) -> str:
        return self.log[-1] if self.log else ""

    def partner_of(self, player: Player) -> Player | None:
        if not self.partners:
            return None
        idx = self.players.index(player)
        return self.players[(idx + 2) % len(self.players)]

    def team(self, player: Player) -> list[Player]:
        partner = self.partner_of(player)
        return [player, partner] if partner else [player]

    def controlled_color(self, player: Player | None = None) -> str:
        """Whose pegs ``player`` moves: their own, or their partner's once all theirs are home."""
        player = player or self.current_player
        partner = self.partner_of(player)
        if partner and player.has_won():
            return partner.color
        return player.color

    def _move_args(self, player: Player) -> tuple[str, str | None]:
        """(color whose pegs move, partner a 7 may finish on) for ``player``."""
        control = self.controlled_color(player)
        partner = self.partner_of(player)
        finish_on = partner.color if partner and control == player.color else None
        return control, finish_on

    def winners(self) -> list[Player]:
        """The winning player, or both partners once all 8 of their pegs are home."""
        for player in self.players:
            team = self.team(player)
            if all(p.has_won() for p in team):
                return team
        return []

    def winner(self) -> Player | None:
        winners = self.winners()
        return winners[0] if winners else None

    def winner_names(self) -> str:
        return " & ".join(p.color for p in self.winners())

    def legal_moves(self, card: Card) -> list[Move]:
        """Moves the current player could make with ``card`` (none while skipped by a jack)."""
        if self.skip_pending:
            return []
        control, finish_on = self._move_args(self.current_player)
        return legal_moves(self.players, control, card, finish_on)

    def can_play(self, card: Card) -> bool:
        """Can the current player move with ``card``? (Cheaper than listing every move.)"""
        if self.skip_pending:
            return False
        control, finish_on = self._move_args(self.current_player)
        return has_legal_move(self.players, control, [card], finish_on)

    # A 7 is chosen one piece at a time (see rules.seven_choices).
    def seven_choices(self, segments) -> list[SevenChoice]:
        control, finish_on = self._move_args(self.current_player)
        return seven_choices(self.players, control, finish_on, segments)

    def seven_preview(self, segments):
        control, finish_on = self._move_args(self.current_player)
        return seven_preview(self.players, control, finish_on, segments)

    def seven_move(self, segments) -> Move:
        control, finish_on = self._move_args(self.current_player)
        return seven_move(control, finish_on, segments)

    # --- Dealing ---

    def _left_of(self, idx: int) -> int:
        return (idx + 1) % len(self.players)

    def _start_deal(self) -> None:
        self.deck = Deck(self.rng)
        self.discard.clear()
        self.deal_number += 1
        self.hand_number = 0
        self._deal_hand()

    def _deal_hand(self) -> None:
        """Deal one card at a time, starting left of the dealer, who also plays first."""
        self.folded.clear()
        size = HAND_SIZES[self.hand_number]
        first = self._left_of(self.dealer_idx)
        for _ in range(size):
            for offset in range(len(self.players)):
                self.players[(first + offset) % len(self.players)].hand.append(self.deck.draw())
        self.current_idx = first

    # --- Turns ---

    def play_card(self, card: Card, move: Move | None = None) -> None:
        """The current player plays ``card`` with ``move``.

        Normally a move is required. The exception is a player skipped by a
        jack, who plays a card without moving (``move=None``). Players who
        can't move at all fold automatically when their turn comes.
        """
        if self.winner():
            raise IllegalMove("The game is over")
        player = self.current_player
        if card not in player.hand:
            raise IllegalMove(f"{player.color} does not hold {card}")

        if self.skip_pending:
            if move is not None:
                raise IllegalMove("A jack was played: play a card without moving")
            # Laying another jack passes the skip along; anything else ends it.
            self.skip_pending = card.rank == JACK
            self.last_moved = set()
            self.log.append(f"{player.color} was skipped and laid {card.label}")
        else:
            control, finish_on = self._move_args(player)
            moves = legal_moves(self.players, control, card, finish_on)
            if not moves:
                raise IllegalMove(f"{card.label} can't move; play a different card")
            if move is None:
                raise IllegalMove(f"Choose how to move with {card.label}")
            # A 7 chosen piece by piece may move a peg more than once, so it's checked directly.
            seven_ok = card.rank == SPLIT_RANK and is_legal_seven(self.players, control, finish_on, move)
            if move not in moves and not seven_ok:
                raise IllegalMove("That move isn't allowed")
            before = self._positions()
            apply_move(self.players, control, move)
            after = self._positions()
            self.last_moved = {k for k in before if before[k] != after[k]}
            action = f"{player.color} {card.label}: {move.describe()}"
            if control != player.color:
                action = f"{player.color} {card.label} (for {control}): {move.describe()}"
            sent = self._sent_to_base(before, player.color)
            if sent:
                action += f", sent {' & '.join(sent)} back to base"
            self.log.append(action)
            self.skip_pending = card.rank == JACK

        player.hand.remove(card)
        self.discard.append(card)
        if self.winner():
            self.log.append(f"{self.winner_names()} WIN!")
            return
        self._next_player()
        self._fold_stuck_players()

    def _positions(self) -> dict[tuple[str, int], PegPos]:
        return {(p.color, p.number): p.pos for pl in self.players for p in pl.pegs}

    def _sent_to_base(self, before: dict[tuple[str, int], PegPos], mover: str) -> list[str]:
        sent = []
        for pl in self.players:
            for peg in pl.pegs:
                was = before[(peg.color, peg.number)]
                if peg.pos.zone is Zone.BASE and was.zone is not Zone.BASE:
                    sent.append(peg.color if peg.color != mover else f"own peg {peg.number + 1}")
        return sent

    def _next_player(self) -> None:
        """Pass the turn to the next player still holding cards, or deal the next hand."""
        if any(p.hand for p in self.players):
            idx = self._left_of(self.current_idx)
            while not self.players[idx].hand:  # folded players sit out
                idx = self._left_of(idx)
            self.current_idx = idx
            return
        # Everyone is out of cards: next hand, or a fresh deal with the next dealer.
        self.hand_number += 1
        if self.hand_number < len(HAND_SIZES):
            self._deal_hand()
        else:
            self.dealer_idx = self._left_of(self.dealer_idx)
            self._start_deal()

    def _fold_stuck_players(self) -> None:
        """A player whose cards can't move folds the rest of this hand."""
        while not self.skip_pending:
            player = self.current_player
            control, finish_on = self._move_args(player)
            if has_legal_move(self.players, control, player.hand, finish_on):
                return
            self.log.append(f"{player.color} can't play and folds ({len(player.hand)} cards)")
            self.folded.add(player.color)
            self.discard.extend(player.hand)
            player.hand.clear()
            self._next_player()
