from pathlib import Path

import easyocr
import numpy as np
import pytest
from PIL import Image

from screen import card_changed, find_board, find_score_card, find_start_button, read_board

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def load(name):
    return np.array(Image.open(FIXTURES / name).convert("RGB"))


@pytest.fixture(scope="module")
def reader():
    return easyocr.Reader(["en"], gpu=False, verbose=False)


def test_start_button_found_only_on_the_start_screen():
    assert find_start_button(load("how_to_play.png")) is not None
    assert find_start_button(load("board.png")) is None


def test_reads_every_letter_of_the_game_board(reader):
    image = load("board.png")

    grid, centers = read_board(image, find_board(image), reader)

    assert grid == ["GSYN", "ROAS", "RKNA", "EEVG"]
    assert len(centers) == 16


def test_score_card_found_on_the_game_screen_only():
    assert find_score_card(load("board.png")) == (45, 32, 328, 97)
    assert find_score_card(load("how_to_play.png")) is None


def test_card_change_detected_only_when_the_card_differs():
    image = load("board.png")
    card = find_score_card(image)
    edited = image.copy()
    x, y, w, h = card
    edited[y + 20:y + 40, x + 100:x + 120] = 0

    assert not card_changed(image, image.copy(), card)
    assert card_changed(image, edited, card)
