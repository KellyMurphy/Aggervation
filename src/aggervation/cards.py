"""Playing cards and the deck."""

from __future__ import annotations

import random
from dataclasses import dataclass

RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
SUITS = ["S", "H", "D", "C"]  # spades, hearts, diamonds, clubs
SUIT_SYMBOLS = {"S": "♠", "H": "♥", "D": "♦", "C": "♣"}


@dataclass(frozen=True)
class Card:
    rank: str
    suit: str

    def __post_init__(self):
        if self.rank not in RANKS or self.suit not in SUITS:
            raise ValueError(f"Invalid card: {self.rank}{self.suit}")

    def __str__(self) -> str:
        return f"{self.rank}{self.suit}"

    @property
    def label(self) -> str:
        """Display form with a suit symbol, e.g. '10♥'."""
        return f"{self.rank}{SUIT_SYMBOLS[self.suit]}"


def full_deck() -> list[Card]:
    return [Card(rank, suit) for suit in SUITS for rank in RANKS]


class Deck:
    """A shuffled 52-card deck that cards are dealt from."""

    def __init__(self, rng: random.Random | None = None):
        self.rng = rng or random.Random()
        self.cards: list[Card] = full_deck()
        self.rng.shuffle(self.cards)

    def __len__(self) -> int:
        return len(self.cards)

    def draw(self) -> Card:
        if not self.cards:
            raise IndexError("Deck is empty")
        return self.cards.pop()
