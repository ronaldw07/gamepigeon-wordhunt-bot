from pathlib import Path

import easyocr
import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from screen import find_board, find_start_button, read_board, read_letter

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



@pytest.mark.parametrize("letter", ["I", "T", "L", "J"])
def test_thin_bar_reads_as_i_and_nothing_else_does(reader, letter):
    font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 40, index=1)
    tile = Image.new("RGB", (65, 65), (245, 200, 130))
    ImageDraw.Draw(tile).text((32, 32), letter, font=font, fill=(0, 0, 0), anchor="mm")

    assert read_letter(np.array(tile), (0, 0, 65, 65), reader) == letter
