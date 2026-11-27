"""Smoke test: the whole window runs (headless) through setup, a full game, and back."""

import os
import random

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame  # noqa: E402

from aggervation.main import COMPUTER, HUMAN, App  # noqa: E402


def test_four_computers_play_a_game_and_return_to_setup():
    app = App()
    for color in app.controllers:
        app.controllers[color] = COMPUTER
    app.start_game()
    app.game.rng = random.Random(1)
    app.rng = random.Random(1)
    for _ in range(5000):
        app.bot_ready_at = 0
        app.update()
        app.draw()
        if app.state == "over":
            break
    assert app.state == "over"
    app.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    assert app.state == "setup"


def test_two_humans_get_a_pass_screen():
    app = App()
    app.controllers.update(RED=HUMAN, GREEN=HUMAN, BLUE=COMPUTER, YELLOW=COMPUTER)
    app.start_game()
    if app.controllers[app.current] == HUMAN:
        assert app.needs_pass_screen() and not app.hand_visible()
        app.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(0, 0)))
        assert app.hand_visible()


def test_setup_click_toggles_seat():
    from aggervation.main import setup_rects

    app = App()
    seats, _ = setup_rects()
    app.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=seats["GREEN"].center))
    assert app.controllers["GREEN"] == HUMAN
