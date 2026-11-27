import sys

import pygame

from .game import HAND_SIZES, PLAYER_ORDER, Game, Peg, PegPos, Player, Zone
from .layout_data import PLAYERS, TRACK, VIEWBOX
from .rules import SPLIT_RANK, SPLIT_TOTAL, SWAP_RANK, IllegalMove, Move, MoveKind
from .rules import apply_partial_split, copy_pegs, position_after

# --- Configuration ---
WIDTH, HEIGHT = 800, 800
MARGIN = 10
HOLE_RES = 10  # Visual size of the hole

# Colors
COLOR_BG = (40, 40, 40)
COLOR_BOARD = (196, 154, 108)  # wood tone from the SVG
COLOR_TRACK = (60, 50, 40)
COLOR_LINE = (150, 120, 85)
COLOR_TEXT = (35, 31, 32)
COLOR_LOG = (80, 62, 45)
COLOR_SELECTABLE = (255, 255, 255)
PLAYER_COLORS = {
    "RED": (237, 28, 36),
    "GREEN": (0, 157, 72),
    "BLUE": (3, 78, 162),
    "YELLOW": (255, 212, 0),
}
SCALE = (min(WIDTH, HEIGHT) - 2 * MARGIN) / max(VIEWBOX)
OFFSET_X = (WIDTH - VIEWBOX[0] * SCALE) / 2
OFFSET_Y = (HEIGHT - VIEWBOX[1] * SCALE) / 2


def to_screen(p):
    """Map an SVG coordinate to window pixels."""
    return int(OFFSET_X + p[0] * SCALE), int(OFFSET_Y + p[1] * SCALE)


MAIN_TRACK_COORDS = [to_screen(p) for p in TRACK]
PLAYER_BASES = {c: [to_screen(p) for p in PLAYERS[c]["base"]] for c in PLAYER_ORDER}
PLAYER_HOMES = {c: [to_screen(p) for p in PLAYERS[c]["home"]] for c in PLAYER_ORDER}
START_INDEX_COLOR = {PLAYERS[c]["start_index"]: c for c in PLAYER_ORDER}
BOARD_CENTER = to_screen((VIEWBOX[0] / 2, VIEWBOX[1] / 2))
BOARD_RADIUS = int(min(VIEWBOX) / 2 * SCALE)

CARD_W, CARD_H, CARD_GAP = 50, 72, 8
CARD_FACE = (250, 248, 240)
SUIT_RED = (200, 20, 30)
SUIT_BLACK = (20, 20, 20)


def screen_pos(color: str, pos: PegPos):
    """Window pixels of a hole. Base and home holes belong to ``color``."""
    if pos.zone is Zone.BASE:
        return PLAYER_BASES[color][pos.index]
    if pos.zone is Zone.HOME:
        return PLAYER_HOMES[color][pos.index]
    return MAIN_TRACK_COORDS[pos.index]


def peg_screen_pos(peg: Peg):
    return screen_pos(peg.color, peg.pos)


def near(a, b, radius=HOLE_RES + 4) -> bool:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 <= radius**2


def peg_under(players: list[Player], pos) -> Peg | None:
    for player in players:
        for peg in player.pegs:
            if near(peg_screen_pos(peg), pos):
                return peg
    return None


# --- Choosing a play ---

class Selection:
    """What the current player has picked so far this turn: a card, then peg(s)."""

    def __init__(self, game: Game):
        self.game = game
        self.reset()

    def reset(self, message: str = ""):
        self.card_idx: int | None = None
        self.moves: list[Move] = []
        self.swap_from: int | None = None  # 10: own peg chosen, waiting for partner
        self.split: list[tuple[int, int]] = []  # 7: segments chosen so far
        self.split_peg: int | None = None  # 7: peg chosen, waiting for a step count
        self.message = message

    @property
    def color(self) -> str:
        return self.game.current_player.color

    @property
    def card(self):
        return None if self.card_idx is None else self.game.current_player.hand[self.card_idx]

    # The board as the player sees it: with a 7's chosen segments already moved.
    def preview_players(self) -> list[Player]:
        if not self.split:
            return self.game.players
        players = copy_pegs(self.game.players)
        apply_partial_split(players, self.color, self.split)
        return players

    def _split_continuations(self) -> list[Move]:
        n = len(self.split)
        return [m for m in self.moves if list(m.splits[:n]) == self.split and len(m.splits) > n]

    def selectable(self) -> set[tuple[str, int]]:
        """Pegs (color, number) the player may click next."""
        if self.card is None:
            return set()
        if self.card.rank == SWAP_RANK:
            if self.swap_from is None:
                return {(self.color, m.peg) for m in self.moves if m.peg is not None}
            return {m.target for m in self.moves if m.peg == self.swap_from and m.target}
        if self.card.rank == SPLIT_RANK:
            if self.split_peg is not None:
                return {(self.color, self.split_peg)}
            return {(self.color, m.splits[len(self.split)][0]) for m in self._split_continuations()}
        result = {(self.color, m.peg) for m in self.moves if m.peg is not None}
        if any(m.kind is MoveKind.ENTER for m in self.moves):
            pegs = self.game.current_player.pegs
            result |= {(self.color, p.number) for p in pegs if p.pos.zone is Zone.BASE}
        return result

    def split_step_options(self) -> list[int]:
        n = len(self.split)
        return sorted(
            {m.splits[n][1] for m in self._split_continuations() if m.splits[n][0] == self.split_peg}
        )

    def split_destinations(self) -> list[tuple[int, tuple[int, int]]]:
        """For a 7: (steps, screen position) of each hole the chosen peg can reach."""
        if self.split_peg is None:
            return []
        peg = next(p for pl in self.preview_players() for p in pl.pegs
                   if (p.color, p.number) == (self.color, self.split_peg))
        result = []
        for steps in self.split_step_options():
            dest = position_after(self.color, peg.travelled + steps)
            if dest is not None:
                result.append((steps, screen_pos(self.color, dest)))
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
        if self.split_peg is not None and key == (self.color, self.split_peg):
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
            self.split_peg = peg.number
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
        self.split.append((self.split_peg, steps))
        self.split_peg = None
        done = next((m for m in self.moves if list(m.splits) == self.split), None)
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
            left = SPLIT_TOTAL - sum(s for _, s in self.split)
            return f"7: click a peg to move ({left} steps left)"
        return f"{card.label}: click a peg to move"

    def _play(self, card, move):
        try:
            self.game.play_card(card, move)
        except IllegalMove as e:
            self.reset(str(e))
            return
        self.reset()


# --- Drawing ---

def draw_board(screen, players: list[Player], selectable: set, chosen: set):
    pygame.draw.circle(screen, COLOR_BOARD, BOARD_CENTER, BOARD_RADIUS)

    n = len(MAIN_TRACK_COORDS)
    for i, pos in enumerate(MAIN_TRACK_COORDS):
        pygame.draw.line(screen, COLOR_LINE, pos, MAIN_TRACK_COORDS[(i + 1) % n], 2)
    for i, pos in enumerate(MAIN_TRACK_COORDS):
        start_color = START_INDEX_COLOR.get(i)
        if start_color:
            pygame.draw.circle(screen, PLAYER_COLORS[start_color], pos, HOLE_RES + 2)
            pygame.draw.circle(screen, (255, 255, 255), pos, HOLE_RES + 2, 1)
        else:
            pygame.draw.circle(screen, COLOR_TRACK, pos, HOLE_RES, 2)

    for color in PLAYER_ORDER:
        for pos in PLAYER_BASES[color]:
            pygame.draw.circle(screen, PLAYER_COLORS[color], pos, HOLE_RES, 1)
        for pos in PLAYER_HOMES[color]:
            pygame.draw.circle(screen, PLAYER_COLORS[color], pos, HOLE_RES, 2)

    for player in players:
        for peg in player.pegs:
            pos = peg_screen_pos(peg)
            key = (peg.color, peg.number)
            pygame.draw.circle(screen, PLAYER_COLORS[peg.color], pos, HOLE_RES - 3)
            pygame.draw.circle(screen, (255, 255, 255), (pos[0] - 2, pos[1] - 2), 2)
            if peg.blocking:
                pygame.draw.circle(screen, COLOR_TEXT, pos, HOLE_RES - 3, 2)
            if key in chosen:
                pygame.draw.circle(screen, COLOR_TEXT, pos, HOLE_RES + 4, 3)
            elif key in selectable:
                pygame.draw.circle(screen, COLOR_SELECTABLE, pos, HOLE_RES + 4, 3)


def draw_destinations(screen, font, destinations, color):
    for steps, (x, y) in destinations:
        pygame.draw.circle(screen, COLOR_SELECTABLE, (x, y), HOLE_RES + 2)
        pygame.draw.circle(screen, PLAYER_COLORS[color], (x, y), HOLE_RES + 2, 3)
        label = font.render(str(steps), True, COLOR_TEXT)
        screen.blit(label, label.get_rect(center=(x, y)))


def card_rects(count: int) -> list[pygame.Rect]:
    """Screen rectangles for a hand of ``count`` cards, centred on the board."""
    total = count * CARD_W + (count - 1) * CARD_GAP
    left = BOARD_CENTER[0] - total // 2
    top = BOARD_CENTER[1] - 10
    return [pygame.Rect(left + i * (CARD_W + CARD_GAP), top, CARD_W, CARD_H) for i in range(count)]


def card_at(game: Game, pos) -> int | None:
    """Index of the current player's card under the mouse, if any."""
    for i, rect in enumerate(card_rects(len(game.current_player.hand))):
        if rect.collidepoint(pos):
            return i
    return None


def blit_centered(screen, font, text, color, y):
    surf = font.render(text, True, color)
    screen.blit(surf, (BOARD_CENTER[0] - surf.get_width() // 2, y))


def draw_panel(screen, fonts, game: Game, sel: Selection, mouse_pos):
    font, card_font, small = fonts
    player = game.current_player
    pcolor = PLAYER_COLORS[player.color]
    winner = game.winner()

    y = BOARD_CENTER[1] - 110
    blit_centered(screen, font, f"Deal {game.deal_number}, hand {game.hand_number + 1} of {len(HAND_SIZES)}", COLOR_TEXT, y)
    blit_centered(screen, font, f"Dealer: {game.dealer.color}", PLAYER_COLORS[game.dealer.color], y + 28)
    if winner:
        blit_centered(screen, font, f"{winner.color} WINS!", PLAYER_COLORS[winner.color], y + 56)
    else:
        blit_centered(screen, font, f"Turn: {player.color}", pcolor, y + 56)

        for i, (card, rect) in enumerate(zip(player.hand, card_rects(len(player.hand)))):
            lifted = i == sel.card_idx or rect.collidepoint(mouse_pos)
            r = rect.move(0, -8) if lifted else rect
            pygame.draw.rect(screen, CARD_FACE, r, border_radius=6)
            selected = i == sel.card_idx
            pygame.draw.rect(screen, pcolor if lifted else COLOR_TEXT, r, 4 if selected else (3 if lifted else 1), border_radius=6)
            ink = SUIT_RED if card.suit in ("H", "D") else SUIT_BLACK
            label = card_font.render(card.label, True, ink)
            screen.blit(label, label.get_rect(center=r.center))
            key = small.render(str(i + 1), True, COLOR_TEXT)
            screen.blit(key, key.get_rect(midtop=(rect.centerx, rect.bottom + 4)))

        if game.skip_pending:
            prompt = "Skipped by a jack! Pick a card to lay without moving"
        else:
            prompt = sel.message or "Pick a card to play (click or press its number)"
        blit_centered(screen, small, prompt, COLOR_TEXT, card_rects(1)[0].bottom + 26)

    log_y = card_rects(1)[0].bottom + 52
    for line in game.log[-3:]:
        blit_centered(screen, small, line, COLOR_LOG, log_y)
        log_y += 19


def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Aggravation")
    clock = pygame.time.Clock()

    game = Game()
    sel = Selection(game)
    # Segoe UI Symbol has the card suit glyphs on Windows.
    fonts = (
        pygame.font.SysFont("Segoe UI Symbol,Arial", 20, bold=True),
        pygame.font.SysFont("Segoe UI Symbol,Arial", 22, bold=True),
        pygame.font.SysFont("Segoe UI Symbol,Arial", 15),
    )

    while True:
        players = sel.preview_players()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if game.winner():
                continue
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                sel.reset()
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                idx = card_at(game, event.pos)
                if idx is not None:
                    sel.click_card(idx)
                elif sel.click_board(event.pos):
                    pass
                else:
                    peg = peg_under(players, event.pos)
                    if peg:
                        sel.click_peg(peg)
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    sel.reset()
                elif pygame.K_1 <= event.key <= pygame.K_9:
                    n = event.key - pygame.K_0
                    if sel.split_peg is not None:
                        sel.choose_split_steps(n)
                    else:
                        sel.click_card(n - 1)
            players = sel.preview_players()

        chosen = set()
        if sel.swap_from is not None:
            chosen.add((sel.color, sel.swap_from))
        if sel.split_peg is not None:
            chosen.add((sel.color, sel.split_peg))

        screen.fill(COLOR_BG)
        draw_board(screen, players, sel.selectable() - chosen, chosen)
        draw_destinations(screen, fonts[2], sel.split_destinations(), sel.color)
        draw_panel(screen, fonts, game, sel, pygame.mouse.get_pos())

        pygame.display.flip()
        clock.tick(30)


if __name__ == "__main__":
    main()
