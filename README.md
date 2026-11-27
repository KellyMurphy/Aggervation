# Aggravation

A pygame version of the Aggravation board game with house rules, played with a deck of cards instead of dice.
Four players race their pegs from base, around the board, and into home.

The house rules are in [basics/rules.txt](basics/rules.txt) and printed on the board art.

## Running it

Needs [uv](https://docs.astral.sh/uv/) (it installs Python 3.12 and pygame for you).

```
uv run aggervation
```

## How to play

- The current player's hand is shown in the middle of the board.
- **Pick a card** (click it or press its number), then **click the peg** to move. Pegs you can move have a white ring.
- **10:** click your peg, then the peg to swap with.
- **7:** click a peg, then the numbered marker where it should go. Keep going until all 7 spaces are used.
- **Esc** or right-click cancels a choice.
- Players who can't play any card fold automatically until the next hand.
- The last few moves are listed under the cards.

## Tests

```
uv run --with pytest pytest
```

## Project layout

| Path | What it is |
| --- | --- |
| `src/aggervation/main.py` | The window: drawing the board and handling clicks |
| `src/aggervation/game.py` | Dealing, turn order, folding, jack skips, winning |
| `src/aggervation/rules.py` | What each card allows and carrying out moves |
| `src/aggervation/models.py` | Pegs, positions, players |
| `src/aggervation/cards.py` | Cards and the deck |
| `src/aggervation/layout_data.py` | Hole positions, generated from the board art (don't edit) |
| `tools/extract_layout.py` | Reads the board SVG and writes `layout_data.py` |
| `basics/` | Board artwork (Illustrator + SVG) and the rules |
| `tests/` | Tests for the layout, rules, game flow and clicking |

## Changing the board art

The game reads hole positions from `basics/Aggravation 4 Player Full Size.svg`. After editing the board in Illustrator:

1. Export it over that SVG. Keep the named rectangles `Red_base_zone`, `Red_start_zone`, `Red_home_zone`
   (and the same for Green, Blue, Yellow) covering each player's holes.
2. Run `uv run python tools/extract_layout.py`. It checks there are 96 track holes and 4 base and 4 home holes
   per player, and stops with a message if not.
3. Run the tests.
