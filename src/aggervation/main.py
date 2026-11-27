"""The Aggravation window: choose players, play, pass the screen, play again."""

import random
import sys

import pygame

from .bot import choose_play
from .game import HAND_SIZES, PLAYER_ORDER, Game
from .selection import Selection
from .view import (
    BOARD_CENTER,
    COLOR_BG,
    COLOR_BOARD,
    COLOR_LOG,
    COLOR_TEXT,
    HEIGHT,
    PLAYER_COLORS,
    WIDTH,
    blit_centered,
    card_at,
    card_rects,
    draw_board,
    draw_card,
    draw_card_back,
    draw_corner_text,
    draw_destinations,
    peg_under,
)

HUMAN, COMPUTER = "Human", "Computer"
BOT_DELAY_MS = 900  # pause before each computer move so you can follow along
PANEL_W, ROW_H = 300, 40
COLOR_SEAT_TEXT = (220, 220, 220)


def setup_rects() -> tuple[dict[str, pygame.Rect], pygame.Rect]:
    """Click targets on the setup screen: one per seat, plus Start."""
    top = BOARD_CENTER[1] - 90
    seats = {
        color: pygame.Rect(BOARD_CENTER[0] - PANEL_W // 2, top + i * (ROW_H + 8), PANEL_W, ROW_H)
        for i, color in enumerate(PLAYER_ORDER)
    }
    start = pygame.Rect(BOARD_CENTER[0] - 90, top + 4 * (ROW_H + 8) + 12, 180, 44)
    return seats, start


def partners_rect() -> pygame.Rect:
    _, start = setup_rects()
    return pygame.Rect(BOARD_CENTER[0] - 140, start.bottom + 10, 280, 30)


def play_again_rect() -> pygame.Rect:
    return pygame.Rect(BOARD_CENTER[0] - 90, BOARD_CENTER[1] + 20, 180, 44)


def draw_button(screen, font, rect, text, fill, ink=COLOR_TEXT, hover=False):
    pygame.draw.rect(screen, fill, rect, border_radius=8)
    pygame.draw.rect(screen, COLOR_TEXT, rect, 3 if hover else 1, border_radius=8)
    label = font.render(text, True, ink)
    screen.blit(label, label.get_rect(center=rect.center))


class App:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("Aggravation")
        self.clock = pygame.time.Clock()
        # Segoe UI Symbol has the card suit glyphs on Windows.
        self.font = pygame.font.SysFont("Segoe UI Symbol,Arial", 20, bold=True)
        self.card_font = pygame.font.SysFont("Segoe UI Symbol,Arial", 22, bold=True)
        self.small = pygame.font.SysFont("Segoe UI Symbol,Arial", 15)
        self.small_bold = pygame.font.SysFont("Segoe UI Symbol,Arial", 15, bold=True)
        self.title_font = pygame.font.SysFont("Segoe UI Symbol,Arial", 34, bold=True)

        self.controllers = {c: (HUMAN if c == "RED" else COMPUTER) for c in PLAYER_ORDER}
        self.partners = True  # opposite seats play as a team
        self.rng = random.Random()
        self.state = "setup"  # setup -> play -> over -> setup ...
        self.game = Game()  # shown behind the setup screen
        self.sel = Selection(self.game)
        self.revealed_for: str | None = None  # whose hand is showing (when hands are hidden)
        self.bot_ready_at = 0

    # --- Who's playing ---

    def is_human(self, color: str) -> bool:
        return self.controllers[color] == HUMAN

    @property
    def human_count(self) -> int:
        return sum(self.is_human(c) for c in PLAYER_ORDER)

    @property
    def current(self) -> str:
        return self.game.current_player.color

    def needs_pass_screen(self) -> bool:
        """With 2+ people sharing the screen, hide the hand until the right person is looking."""
        return self.human_count >= 2 and self.is_human(self.current) and self.revealed_for != self.current

    def hand_visible(self) -> bool:
        return self.is_human(self.current) and not self.needs_pass_screen()

    # --- State changes ---

    def start_game(self):
        self.game = Game(partners=self.partners)
        self.sel = Selection(self.game)
        self.revealed_for = None
        self.state = "play"
        self.after_play()

    def after_play(self):
        """Called after every play (and at the start): set up the next turn."""
        self.bot_ready_at = pygame.time.get_ticks() + BOT_DELAY_MS
        if self.game.winner():
            self.state = "over"

    # --- Events ---

    def handle(self, event):
        if event.type == pygame.QUIT:
            pygame.quit()
            sys.exit()
        if event.type == pygame.KEYDOWN and event.key == pygame.K_n and self.state != "setup":
            self.state = "setup"
            return
        getattr(self, f"handle_{self.state}")(event)

    def handle_setup(self, event):
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_SPACE):
            self.start_game()
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return
        seats, start = setup_rects()
        for color, rect in seats.items():
            if rect.collidepoint(event.pos):
                self.controllers[color] = COMPUTER if self.is_human(color) else HUMAN
        if partners_rect().collidepoint(event.pos):
            self.partners = not self.partners
        if start.collidepoint(event.pos):
            self.start_game()

    def handle_over(self, event):
        clicked = event.type == pygame.MOUSEBUTTONDOWN and play_again_rect().collidepoint(event.pos)
        if clicked or (event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_SPACE)):
            self.state = "setup"

    def handle_play(self, event):
        if not self.is_human(self.current):
            # Space hurries the computer along.
            if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
                self.bot_ready_at = 0
            return
        if self.needs_pass_screen():
            if event.type == pygame.MOUSEBUTTONDOWN or (
                event.type == pygame.KEYDOWN and event.key in (pygame.K_SPACE, pygame.K_RETURN)
            ):
                self.revealed_for = self.current
            return

        sel, game = self.sel, self.game
        before = (game.current_idx, len(game.log), game.hand_number, game.deal_number)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            sel.reset()
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            idx = card_at(game, event.pos)
            if idx is not None:
                sel.click_card(idx)
            elif not sel.click_board(event.pos):
                peg = peg_under(sel.preview_players(), event.pos)
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
        if (game.current_idx, len(game.log), game.hand_number, game.deal_number) != before:
            self.after_play()

    def update(self):
        if self.state != "play" or self.is_human(self.current):
            return
        if pygame.time.get_ticks() >= self.bot_ready_at:
            self.game.play_card(*choose_play(self.game, self.rng))
            self.sel.reset()
            self.after_play()

    # --- Drawing ---

    def draw(self):
        screen, game, sel = self.screen, self.game, self.sel
        screen.fill(COLOR_BG)

        if self.state == "setup":
            draw_board(screen, game.players)
            self.draw_setup()
            return

        playing = self.state == "play" and self.hand_visible()
        players = sel.preview_players() if playing else game.players
        chosen = set()
        if playing and sel.swap_from is not None:
            chosen.add((sel.color, sel.swap_from))
        if playing and sel.split_peg is not None:
            chosen.add(sel.split_peg)
        selectable = (sel.selectable() - chosen) if playing else set()
        draw_board(screen, players, selectable, chosen, game.last_moved)
        if playing:
            draw_destinations(screen, self.small, sel.split_destinations(), sel.color)
        self.draw_seats()
        self.draw_center()

    def draw_setup(self):
        screen = self.screen
        seats, start = setup_rects()
        panel = pygame.Rect(0, 0, PANEL_W + 60, 420)
        panel.center = (BOARD_CENTER[0], BOARD_CENTER[1] + 28)
        pygame.draw.rect(screen, COLOR_BOARD, panel, border_radius=12)
        pygame.draw.rect(screen, COLOR_TEXT, panel, 2, border_radius=12)
        blit_centered(screen, self.title_font, "AGGRAVATION", COLOR_TEXT, panel.top + 14)
        blit_centered(screen, self.small, "Click a seat to switch Human / Computer", COLOR_TEXT, panel.top + 58)
        mouse = pygame.mouse.get_pos()
        for color, rect in seats.items():
            label = f"{color.title()}:  {self.controllers[color]}"
            draw_button(screen, self.font, rect, label, PLAYER_COLORS[color],
                        ink=(255, 255, 255) if color != "YELLOW" else COLOR_TEXT,
                        hover=rect.collidepoint(mouse))
        draw_button(screen, self.font, start, "Start game", (250, 248, 240), hover=start.collidepoint(mouse))
        prect = partners_rect()
        text = "Partners: Red & Blue vs Green & Yellow" if self.partners else "Partners: off (every player alone)"
        draw_button(screen, self.small, prect, text, COLOR_BOARD, hover=prect.collidepoint(mouse))

    def draw_seats(self):
        game = self.game
        for player in game.players:
            color = player.color
            # Lighten the player colour so it reads on the dark background.
            ink = tuple(int(v + (255 - v) * 0.35) for v in PLAYER_COLORS[color])
            name = ("▶ " if color == self.current and self.state == "play" else "") + color.title()
            if self.is_human(color):
                who = "You" if self.human_count == 1 else "Human"
            else:
                who = "Computer"
            if game.dealer is player:
                who += ", dealer"
            partner = game.partner_of(player)
            if partner:
                control = game.controlled_color(player)
                team_line = f"moving {control.title()}'s pegs" if control != color else f"partner: {partner.color.title()}"
            if player in game.winners():
                status = "WINNER"
            elif player.has_won():
                status = "all pegs home"
            elif color in game.folded:
                status = "folded"
            elif player.hand:
                status = f"{len(player.hand)} cards"
            else:
                status = "out of cards"
            lines = [(name, ink), (who, COLOR_SEAT_TEXT), (status, COLOR_SEAT_TEXT)]
            if partner:
                lines.append((team_line, COLOR_SEAT_TEXT))
            draw_corner_text(self.screen, self.small_bold, color, lines)

    def draw_center(self):
        screen, game, sel = self.screen, self.game, self.sel
        player = game.current_player
        pcolor = PLAYER_COLORS[player.color]
        small = self.small
        y = BOARD_CENTER[1] - 110
        blit_centered(screen, self.font, f"Deal {game.deal_number}, hand {game.hand_number + 1} of {len(HAND_SIZES)}", COLOR_TEXT, y)

        winner = game.winner()
        if self.state == "over" and winner:
            names = game.winner_names()
            verb = "WIN!" if " & " in names else "WINS!"
            blit_centered(screen, self.title_font, f"{names} {verb}", PLAYER_COLORS[winner.color], y + 36)
            rect = play_again_rect()
            draw_button(screen, self.font, rect, "Play again", (250, 248, 240),
                        hover=rect.collidepoint(pygame.mouse.get_pos()))
            self.draw_log(rect.bottom + 16)
            return

        turn = f"Turn: {player.color}"
        control = game.controlled_color(player)
        if control != player.color:
            turn += f" (moving {control}'s pegs)"
        blit_centered(screen, self.font, turn, pcolor, y + 28)
        rects = card_rects(len(player.hand))
        prompt_y = card_rects(1)[0].bottom + 26

        if self.hand_visible():
            mouse = pygame.mouse.get_pos()
            for i, (card, rect) in enumerate(zip(player.hand, rects)):
                selected = i == sel.card_idx
                lifted = selected or rect.collidepoint(mouse)
                r = rect.move(0, -8) if lifted else rect
                draw_card(screen, self.card_font, card, r, pcolor if lifted else COLOR_TEXT,
                          4 if selected else (3 if lifted else 1))
                key = small.render(str(i + 1), True, COLOR_TEXT)
                screen.blit(key, key.get_rect(midtop=(rect.centerx, rect.bottom + 4)))
            if game.skip_pending:
                prompt = "Skipped by a jack! Pick a card to lay without moving"
            else:
                prompt = sel.message or "Pick a card to play (click or press its number)"
        else:
            for rect in rects:
                draw_card_back(screen, rect)
            if self.needs_pass_screen():
                prompt = f"Pass to {player.color.title()} - click when ready"
            else:
                prompt = f"{player.color.title()} (computer) is thinking...  Space: hurry"
        blit_centered(screen, small, prompt, COLOR_TEXT, prompt_y)
        self.draw_log(prompt_y + 26)

    def draw_log(self, y):
        for line in self.game.log[-3:]:
            blit_centered(self.screen, self.small, line, COLOR_LOG, y)
            y += 19

    # --- Main loop ---

    def run(self):
        while True:
            for event in pygame.event.get():
                self.handle(event)
            self.update()
            self.draw()
            pygame.display.flip()
            self.clock.tick(30)


def main():
    App().run()


if __name__ == "__main__":
    main()
