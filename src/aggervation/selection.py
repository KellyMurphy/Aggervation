"""Turning clicks into a play: pick a card, then the peg(s)."""

from .game import Game, Peg, Player, Zone
from .rules import SPLIT_RANK, SPLIT_TOTAL, SWAP_RANK, IllegalMove, Move, MoveKind, SevenChoice
from .rules import seven_used
from .view import near, screen_pos

PegKey = tuple[str, int]  # (color, peg number)
Segment = tuple[str, int, int]  # (color, peg number, steps) - one part of a 7


class Selection:
    """What the current player has picked so far this turn: a card, then peg(s).

    A 7 is built a piece at a time: click any peg and how far it goes, again
    and again (the same peg too) until all 7 steps are used. A peg already
    moved can be clicked to take steps back. Once all 7 are used the player
    confirms with Enter or the Play button.
    """

    def __init__(self, game: Game):
        self.game = game
        self.reset()

    def reset(self, message: str = ""):
        self.card_idx: int | None = None
        self.moves: list[Move] = []
        self.swap_from: int | None = None  # 10: own peg chosen, waiting for partner
        self.split: tuple[Segment, ...] = ()  # 7: parts chosen so far
        self.split_peg: PegKey | None = None  # 7: peg chosen, waiting for where it goes
        self._choices: tuple[tuple[Segment, ...], list[SevenChoice]] | None = None
        self.message = message

    @property
    def color(self) -> str:
        """Whose pegs are being moved: the player's own, or their partner's once theirs are home."""
        return self.game.controlled_color()

    @property
    def card(self):
        return None if self.card_idx is None else self.game.current_player.hand[self.card_idx]

    @property
    def is_seven(self) -> bool:
        return self.card is not None and self.card.rank == SPLIT_RANK

    @property
    def seven_left(self) -> int:
        return SPLIT_TOTAL - seven_used(self.split)

    @property
    def seven_done(self) -> bool:
        """All 7 steps are used: waiting for the player to confirm."""
        return self.is_seven and self.seven_left == 0

    # The board as the player sees it: with a 7's chosen parts already moved.
    def preview_players(self) -> list[Player]:
        if not self.split:
            return self.game.players
        return self.game.seven_preview(self.split)

    def seven_choices(self) -> list[SevenChoice]:
        if not self.is_seven:
            return []
        if self._choices is None or self._choices[0] != self.split:
            self._choices = (self.split, self.game.seven_choices(self.split))
        return self._choices[1]

    def _peg_choices(self) -> list[SevenChoice]:
        if self.split_peg is None:
            return []
        return [c for c in self.seven_choices() if (c.color, c.num) == self.split_peg]

    def selectable(self) -> set[PegKey]:
        """Pegs (color, number) the player may click next."""
        if self.card is None:
            return set()
        color = self.color
        if self.card.rank == SWAP_RANK:
            if self.swap_from is None:
                return {(color, m.peg) for m in self.moves if m.peg is not None}
            return {m.target for m in self.moves if m.peg == self.swap_from and m.target}
        if self.is_seven:
            if self.split_peg is not None:
                return {self.split_peg}
            return {(c.color, c.num) for c in self.seven_choices()}
        result = {(color, m.peg) for m in self.moves if m.peg is not None}
        if any(m.kind is MoveKind.ENTER for m in self.moves):
            pegs = self.game.player(color).pegs
            result |= {(color, p.number) for p in pegs if p.pos.zone is Zone.BASE}
        return result

    def split_step_options(self) -> list[int]:
        """Step counts for the chosen peg: forward, or negative to take steps back."""
        return sorted(c.steps for c in self._peg_choices())

    def split_destinations(self) -> list[tuple[int, tuple[int, int]]]:
        """For a 7: (steps, screen position) of each hole the chosen peg can go to."""
        return [(c.steps, screen_pos(c.color, c.dest)) for c in self._peg_choices()]

    # --- Input ---

    def click_card(self, idx: int):
        game = self.game
        hand = game.current_player.hand
        if idx >= len(hand):
            return
        if game.skip_pending:
            self._play(hand[idx], None)
            return
        if idx == self.card_idx:
            self.reset()
            return
        card = hand[idx]
        moves = [] if card.rank == SPLIT_RANK else game.legal_moves(card)
        if not (game.can_play(card) if card.rank == SPLIT_RANK else moves):
            self.reset(f"{card.label} can't move right now - pick another card")
            return
        self.reset()
        self.card_idx, self.moves = idx, moves
        self.message = self._prompt()

    def click_peg(self, peg: Peg):
        key = (peg.color, peg.number)
        if self.split_peg is not None and key == self.split_peg:
            self.split_peg = None
            self.message = self._prompt()
            return
        if self.card is None or key not in self.selectable():
            return
        rank = self.card.rank
        if rank == SWAP_RANK:
            if self.swap_from is None:
                self.swap_from = peg.number
                self.message = "Now click the peg to swap places with"
            else:
                move = next(m for m in self.moves if m.peg == self.swap_from and m.target == key)
                self._play(self.card, move)
        elif rank == SPLIT_RANK:
            self.split_peg = key
            options = self.split_step_options()
            if len(options) == 1 and options[0] > 0:  # only one place to go: go there
                self.choose_split_steps(options[0])
            elif all(s < 0 for s in options):
                self.message = "Click where to take this peg back to"
            else:
                self.message = "Click where this peg goes (or press the number)"
        else:
            if peg.pos.zone is Zone.BASE:
                move = next(m for m in self.moves if m.kind is MoveKind.ENTER)
            else:
                move = next(m for m in self.moves if m.peg == peg.number)
            self._play(self.card, move)

    def click_board(self, pos) -> bool:
        """Handle a click on a 7's destination marker. True if one was hit."""
        for steps, spot in self.split_destinations():
            if near(spot, pos):
                self.choose_split_steps(steps)
                return True
        return False

    def choose_split_steps(self, steps: int):
        """Move the chosen peg ``steps`` (negative: take steps back)."""
        choice = next((c for c in self._peg_choices() if c.steps == steps), None)
        if choice is None:
            return
        self.split = choice.segments
        self.split_peg = None
        self.message = self._prompt()

    def finish_seven(self):
        """Play the 7 once all its steps are used."""
        if not self.seven_done:
            return
        try:
            move = self.game.seven_move(self.split)
        except IllegalMove as e:
            self.reset(str(e))
            return
        self._play(self.card, move)

    def _prompt(self) -> str:
        card = self.card
        if card is None:
            return ""
        rank = card.rank
        if rank == SWAP_RANK:
            return "10: click your peg to swap"
        if rank == SPLIT_RANK:
            left = self.seven_left
            if left == 0:
                return "7 used: press Enter or Play to finish, or click a moved peg to take steps back"
            undo = ", or a moved peg to take steps back" if self.split else ""
            return f"7: click a peg to move ({left} step{'s' if left != 1 else ''} left){undo}"
        return f"{card.label}: click a peg to move"

    def _play(self, card, move):
        try:
            self.game.play_card(card, move)
        except IllegalMove as e:
            self.reset(str(e))
            return
        self.reset()
