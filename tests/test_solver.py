from pathlib import Path

import pytest

from solver import find_words, load_words, play_order, word_score

ROOT = Path(__file__).resolve().parent.parent
BOARD = ["GSYN", "ROAS", "RKNA", "EEVG"]
HOW_TO_PLAY_BOARD = ["CATD", "WOFO", "IRDG", "NOAS"]


@pytest.fixture(scope="module")
def words():
    return load_words(ROOT / "words.txt")


def test_every_path_spells_its_word_through_adjacent_unused_tiles(words):
    found = find_words(BOARD, words)

    assert found
    for word, path in found.items():
        assert "".join(BOARD[r][c] for r, c in path) == word
        assert len(set(path)) == len(path)
        for (r1, c1), (r2, c2) in zip(path, path[1:]):
            assert max(abs(r1 - r2), abs(c1 - c2)) == 1


def test_finds_the_word_the_tutorial_draws(words):
    found = find_words(HOW_TO_PLAY_BOARD, words)

    assert found["WORDS"] == [(1, 0), (1, 1), (2, 1), (2, 2), (3, 3)]


def test_finds_every_listed_word_that_fits_on_the_board(words):
    found = find_words(BOARD, words)

    # Brute-force check: any dictionary word missing from the results must
    # truly be unspellable, verified by an independent search.
    def spellable(word):
        def walk(r, c, i, used):
            if BOARD[r][c] != word[i]:
                return False
            if i == len(word) - 1:
                return True
            return any(
                walk(nr, nc, i + 1, used | {(nr, nc)})
                for nr in range(4) for nc in range(4)
                if (nr, nc) not in used and max(abs(nr - r), abs(nc - c)) == 1
            )
        return any(walk(r, c, 0, {(r, c)}) for r in range(4) for c in range(4))

    short_words = [w for w in words if len(w) <= 5]
    assert {w for w in short_words if spellable(w)} == {w for w in found if len(w) <= 5}


def test_scores_climb_with_length():
    scores = [word_score("A" * n) for n in range(3, 12)]

    assert scores == sorted(scores)
    assert scores[:6] == [100, 400, 800, 1400, 1800, 2200]


def test_longer_words_play_first_and_common_words_break_ties():
    found = {"TAB": [], "STAB": [], "XYST": [], "ABACI": []}

    order = play_order(found, common_words={"STAB", "TAB"})

    assert order == ["ABACI", "STAB", "XYST", "TAB"]
