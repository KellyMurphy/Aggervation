# Aggravation

A pygame version of the Aggravation board game with house rules, played with a deck of cards instead of dice.
Four players race their pegs from base, around the board, and into home.

The house rules are in [basics/rules.txt](basics/rules.txt) and printed on the board art.

## Running it

Needs [uv](https://docs.astral.sh/uv/) (it installs Python 3.12 and everything else for you).

## Playing online (website)

```
uv run aggervation-web
```

Then open http://localhost:8000.

- **Start a new game** gives you a code like `XU8R-D4FG` and an invite link to send to up to 3 friends.
- Friends enter the code (or open the link) to join the **waiting room**, where everyone can pick a seat.
  The host can put computers in seats, switch partners on/off, and start the game. Empty seats become computers.
- Each player sees the board and only their own cards. Any number of games can run at once, each with its own code.
- Refreshing or reconnecting puts you back in your seat. If a player drops out, the computer covers their turns
  after 30 seconds until they're back.

Settings (environment variables): `PORT` (default 8000), `HOST` (default `0.0.0.0`),
`AGGRAVATION_BOT_DELAY` (seconds before a computer moves, default 1).

To host it, build the included `Dockerfile` on any service that runs containers. Games are kept in memory,
so run a single instance; restarting the server ends games in progress.

## Desktop version

```
uv run aggervation
```

### How to play

- **Choose players:** click each seat to switch it between Human and Computer, then **Start game**.
- **Partners:** players opposite each other are a team (Red & Blue vs Green & Yellow). Once all your pegs
  are home you play your partner's. Switch partners off on the setup screen for every-player-alone games.
- The current player's hand is shown in the middle of the board.
- **Pick a card** (click it or press its number), then **click the peg** to move. Pegs you can move have a white ring.
- **10:** click your peg, then the peg to swap with.
- **7:** click a peg, then the numbered marker where it should go. Keep going until all 7 spaces are used.
- **Esc** or right-click cancels a choice.
- Players who can't play any card fold automatically until the next hand. The corner panels show each
  player's cards left, who's folded, and the dealer.
- Pegs moved by the last play have a coloured ring; the last few moves are listed under the cards.
- **Computer turns** pause briefly so you can follow them; press **Space** to hurry them.
- **Two or more people:** hands are hidden between turns. Pass the computer and click when ready.
- **N** starts over (back to choosing players). After a win, click **Play again**.

## Tests

```
uv run --with pytest pytest
```

## Project layout

| Path | What it is |
| --- | --- |
| `src/aggervation/main.py` | The window: setup screen, turns, pass-the-screen, game over |
| `src/aggervation/view.py` | Board geometry and drawing |
| `src/aggervation/selection.py` | Turning clicks into a play (card, then peg) |
| `src/aggervation/bot.py` | The computer player |
| `src/aggervation/web/server.py` | The website: pages, creating games, live connections |
| `src/aggervation/web/rooms.py` | Online games: codes, waiting room, seats, turns |
| `src/aggervation/web/static/` | The web page (HTML, CSS, JavaScript) |
| `src/aggervation/game.py` | Dealing, turn order, folding, jack skips, winning |
| `src/aggervation/rules.py` | What each card allows and carrying out moves |
| `src/aggervation/models.py` | Pegs, positions, players |
| `src/aggervation/cards.py` | Cards and the deck |
| `src/aggervation/layout_data.py` | Hole positions, generated from the board art (don't edit) |
| `tools/extract_layout.py` | Reads the board SVG and writes `layout_data.py` |
| `basics/` | Board artwork (Illustrator + SVG) and the rules |
| `tests/` | Tests for the layout, rules, game flow, clicking, the bot and the app |

## Changing the board art

The game reads hole positions from `basics/Aggravation 4 Player Full Size.svg`. After editing the board in Illustrator:

1. Export it over that SVG. Keep the named rectangles `Red_base_zone`, `Red_start_zone`, `Red_home_zone`
   (and the same for Green, Blue, Yellow) covering each player's holes.
2. Run `uv run python tools/extract_layout.py`. It checks there are 96 track holes and 4 base and 4 home holes
   per player, and stops with a message if not.
3. Run the tests.
