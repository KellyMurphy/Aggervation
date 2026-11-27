"""Board geometry and drawing helpers (pygame)."""

from collections.abc import Set

import pygame

from .game import PLAYER_ORDER, Game, Peg, PegPos, Player, Zone
from .layout_data import PLAYERS, TRACK, VIEWBOX

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
COLOR_CARD_BACK = (120, 40, 40)
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


# --- Drawing ---

PegKeys = Set[tuple[str, int]]  # (color, peg number) pairs


def draw_board(
    screen,
    players: list[Player],
    selectable: PegKeys = frozenset(),
    chosen: PegKeys = frozenset(),
    last_moved: PegKeys = frozenset(),
):
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
            if key in last_moved:
                pygame.draw.circle(screen, PLAYER_COLORS[peg.color], pos, HOLE_RES + 6, 2)
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


def draw_card(screen, font, card, rect, border=COLOR_TEXT, width=1):
    pygame.draw.rect(screen, CARD_FACE, rect, border_radius=6)
    pygame.draw.rect(screen, border, rect, width, border_radius=6)
    ink = SUIT_RED if card.suit in ("H", "D") else SUIT_BLACK
    label = font.render(card.label, True, ink)
    screen.blit(label, label.get_rect(center=rect.center))


def draw_card_back(screen, rect):
    pygame.draw.rect(screen, COLOR_CARD_BACK, rect, border_radius=6)
    pygame.draw.rect(screen, CARD_FACE, rect.inflate(-10, -10), 1, border_radius=4)
    pygame.draw.rect(screen, COLOR_TEXT, rect, 1, border_radius=6)


def base_corner(color: str) -> tuple[bool, bool]:
    """(is_left, is_top) for the window corner nearest a player's base."""
    xs = [p[0] for p in PLAYER_BASES[color]]
    ys = [p[1] for p in PLAYER_BASES[color]]
    return sum(xs) / len(xs) < BOARD_CENTER[0], sum(ys) / len(ys) < BOARD_CENTER[1]


def draw_corner_text(screen, font, color: str, lines: list[tuple[str, tuple]]):
    """A few lines of text in the window corner by ``color``'s base."""
    left, top = base_corner(color)
    line_h = font.get_linesize()
    y = 8 if top else HEIGHT - 8 - line_h * len(lines)
    for text, ink in lines:
        surf = font.render(text, True, ink)
        x = 10 if left else WIDTH - 10 - surf.get_width()
        screen.blit(surf, (x, y))
        y += line_h

