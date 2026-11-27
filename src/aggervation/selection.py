"""Turning clicks into a play: pick a card, then the peg(s)."""

from .game import Game, Peg, Player, Zone
from .rules import SPLIT_RANK, SPLIT_TOTAL, SWAP_RANK, IllegalMove, Move, MoveKind
from .rules import apply_partial_split, copy_pegs, position_after
from .view import near, screen_pos

PegKey = tuple[str, int]  # (color, peg number)
Segment = tuple[str, int, int]  # (color, peg number, steps) - one part of a 7


class Selection:
    """What the current player has picked so far this turn: a card, then peg(s)."""

    def __init__(self, game: Game):
        self.game = game
        self.reset()

    def reset(self, message: str = ""):
        self.card_idx: int | None = None
        self.moves: list[Move] = []
        self.swap_from: int | None = None  # 10: own peg chosen, waiting for partner
        self.split: list[Segment] = []  # 7: parts chosen so far
        self.split_peg: PegKey | None = None  # 7: peg chosen, waiting for a step count
        self.message = message

    @property
    def color(self) -> str:
        """Whose pegs are being moved: the player's own, or their partner's once theirs are home."""
        return self.game.controlled_color()

    @property
    def card(self):
        return None if self.card_idx is None else self.game.current_player.hand[self.card_idx]

    # The board as the player sees it: with a 7's chosen parts already moved.
    def preview_players(self) -> list[Player]:
        if not self.split:
            return self.game.players
        players = copy_pegs(self.game.players)
        apply_partial_split(players, self.split)
        return players

    def _split_continuations(self) -> list[tuple[Move, list[Segment]]]:
        """7 moves that start with the parts chosen so far, with their parts."""
        n = len(self.split)
        result = []
        for m in self.moves:
            segs = m.segments(self.color)
            if segs[:n] == self.split and len(segs) > n:
                result.append((m, segs))
        return result

    def selectable(self) -> set[PegKey]:
        """Pegs (color, number) the player may click next."""
        if self.card is None:
            return set()
        color = self.color
        if self.card.rank == SWAP_RANK:
            if self.swap_from is None:
                return {(color, m.peg) for m in self.moves if m.peg is not None}
            return {m.target for m in self.moves if m.peg == self.swap_from and m.target}
        if self.card.rank == SPLIT_RANK:
            if self.split_peg is not None:
                return {self.split_peg}
            n = len(self.split)
            return {(segs[n][0], segs[n][1]) for _, segs in self._split_continuations()}
        result = {(color, m.peg) for m in self.moves if m.peg is not None}
        if any(m.kind is MoveKind.ENTER for m in self.moves):
            pegs = self.game.player(color).pegs
            result |= {(color, p.number) for p in pegs if p.pos.zone is Zone.BASE}
        return result

    def split_step_options(self) -> list[int]:
        if self.split_peg is None:
            return []
        n = len(self.split)
        return sorted(
            {segs[n][2] for _, segs in self._split_continuations() if segs[n][:2] == self.split_peg}
        )

    def split_destinations(self) -> list[tuple[int, tuple[int, int]]]:
        """For a 7: (steps, screen position) of each hole the chosen peg can reach."""
        if self.split_peg is None:
            return []
        color, num = self.split_peg
        peg = next(p for pl in self.preview_players() for p in pl.pegs if (p.color, p.number) == (color, num))
        result = []
        for steps in self.split_step_options():
            dest = position_after(color, peg.travelled + steps)
            if dest is not None:
                result.append((steps, screen_pos(color, dest)))
        return result

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
        moves = game.legal_moves(hand[idx])
        if not moves:
            self.reset(f"{hand[idx].label} can't move right now - pick another card")
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
            if len(options) == 1:
                self.choose_split_steps(options[0])
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
        if self.split_peg is None or steps not in self.split_step_options():
            return
        self.split.append((*self.split_peg, steps))
        self.split_peg = None
        done = next((m for m in self.moves if m.segments(self.color) == self.split), None)
        if done:
            self._play(self.card, done)
        else:
            self.message = self._prompt()

    def _prompt(self) -> str:
        card = self.card
        if card is None:
            return ""
        rank = card.rank
        if rank == SWAP_RANK:
            return "10: click your peg to swap"
        if rank == SPLIT_RANK:
            left = SPLIT_TOTAL - sum(s for _, _, s in self.split)
            return f"7: click a peg to move ({left} steps left)"
        return f"{card.label}: click a peg to move"

    def _play(self, card, move):
        try:
            self.game.play_card(card, move)
        except IllegalMove as e:
            self.reset(str(e))
            return
        self.reset()
