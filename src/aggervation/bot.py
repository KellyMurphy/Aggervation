"""A simple computer player.

It tries every legal play, scores the board that would result, and picks the
best. The score rewards getting your team's pegs (yours and your partner's)
round and safely home, and setting opponents back.
"""

from __future__ import annotations

import random

from .cards import Card
from .game import Game
from .models import Player, Zone
from .rules import Move, apply_move, copy_pegs

OPPONENT_WEIGHT = 0.7  # how much setting an opponent back is worth vs. moving yourself
HOME_BONUS = 20  # extra value for a peg being safe in home
OUT_OF_BASE = 10  # value of just being on the board
BLOCKING_BONUS = 3  # a blocking peg on its start protects the way in

# When skipped by a jack, lay the least useful card. Laying a jack passes the
# skip on to the next player, so it's the best card to lay.
SKIP_PREFERENCE = ["J", "Q", "9", "8", "5", "4", "3", "2", "6", "10", "7", "K", "A"]


def peg_value(peg) -> float:
    if peg.pos.zone is Zone.BASE:
        return 0
    if peg.pos.zone is Zone.HOME:
        return OUT_OF_BASE + peg.travelled + HOME_BONUS
    return OUT_OF_BASE + peg.travelled + (BLOCKING_BONUS if peg.blocking else 0)


def evaluate(players: list[Player], team: set[str]) -> float:
    """Score a board for a team (a player and, with partners, their partner)."""
    ours = sum(peg_value(p) for pl in players if pl.color in team for p in pl.pegs)
    theirs = sum(peg_value(p) for pl in players if pl.color not in team for p in pl.pegs)
    return ours - OPPONENT_WEIGHT * theirs


def choose_play(game: Game, rng: random.Random | None = None) -> tuple[Card, Move | None]:
    """The card (and move) the current player should play."""
    rng = rng or random.Random()
    player = game.current_player

    if game.skip_pending:
        card = min(player.hand, key=lambda c: SKIP_PREFERENCE.index(c.rank))
        return card, None

    team = {p.color for p in game.team(player)}
    control = game.controlled_color(player)
    best: list[tuple[Card, Move]] = []
    best_score = float("-inf")
    for card in player.hand:
        for move in game.legal_moves(card):
            trial = copy_pegs(game.players)
            apply_move(trial, control, move)
            score = evaluate(trial, team)
            if score > best_score + 1e-9:
                best, best_score = [(card, move)], score
            elif abs(score - best_score) <= 1e-9:
                best.append((card, move))
    if not best:
        raise RuntimeError(f"{player.color} has no legal play (should have folded)")
    return rng.choice(best)
