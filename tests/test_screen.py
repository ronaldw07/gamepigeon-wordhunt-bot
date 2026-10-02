from pathlib import Path

import easyocr
import numpy as np
import pytest
from PIL import Image

from screen import find_board, find_start_button, read_board

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

