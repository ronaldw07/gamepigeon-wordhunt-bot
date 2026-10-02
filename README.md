# GamePigeon Word Hunt Bot

Plays GamePigeon Word Hunt through iPhone Mirroring on a Mac: reads the board,
finds every dictionary word on it, and drags through them highest-scoring first.

## Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The first run asks for Screen Recording and Accessibility for your terminal.
Grant both, then restart the terminal. Input Monitoring enables the Esc stop key.

## Playing

1. Open iPhone Mirroring and open a Word Hunt game to the "How to play" screen
   with the Start button showing.
2. Run `python wordhunt_bot.py`.

It presses Start itself, reads the letters, and plays for the 80 second round.
Press **Esc** to stop at any time.

To check what it reads without touching the game, open a board and run
`python wordhunt_bot.py --dry-run`.

## How it works

- `screen.py` finds the board by its bright green border and the Start button
  by its solid green, so it works at any screen size or window position. Each
  tile is read separately with EasyOCR, limited to A–Z.
- `solver.py` searches the grid from every tile, pruning any path that isn't
  the start of a dictionary word. Words play longest first; at equal length,
  common words go before obscure Scrabble ones.
- `wordhunt_bot.py` drags through each word with real mouse-drag events, then
  spends any spare time resubmitting long words in case a touch was dropped.

`words.txt` combines Collins Scrabble Words and ENABLE; `common_words.txt` is
ENABLE alone.

## Tuning

If words come out wrong (tiles skipped mid-drag), raise `TILE_STEP_PAUSE` and
`BETWEEN_WORDS_PAUSE` at the top of `wordhunt_bot.py`. If everything goes in
cleanly, lower them to fit more words into the round.

## Tests

```bash
python -m pytest -q
```
