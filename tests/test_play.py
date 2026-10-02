import time

import numpy as np

import wordhunt_bot

CARD = (0, 0, 40, 20)


class FakeGame:
    """Takes words in `valid` once each and shows the count on the card.
    Drops the first drag of each word in `dropped_once`."""

    def __init__(self, valid, dropped_once=()):
        self.valid = set(valid)
        self.dropped_once = set(dropped_once)
        self.found = []

    def drag(self, word):
        if word in self.dropped_once:
            self.dropped_once.discard(word)
        elif word in self.valid and word not in self.found:
            self.found.append(word)

    def capture(self):
        image = np.zeros((20, 40, 3), dtype=np.uint8)
        image[:, : len(self.found) % 40] = 255
        return (0, 0, 40, 20), image


def run(monkeypatch, game, words, seconds=3.0):
    monkeypatch.setattr(wordhunt_bot, "capture", game.capture)
    monkeypatch.setattr(wordhunt_bot, "VERIFY_TIMEOUT", 0.03)
    monkeypatch.setattr(wordhunt_bot, "SETTLE_TIMEOUT", 0.03)
    monkeypatch.setattr(wordhunt_bot, "VERIFY_POLL", 0.001)
    found = {w: [w] for w in words}
    points = {w: w for w in words}
    monkeypatch.setattr(wordhunt_bot, "drag_path", lambda path: game.drag(path[0]))
    monkeypatch.setattr(wordhunt_bot, "card_changed", lambda a, b, card: not np.array_equal(a, b))
    return wordhunt_bot.play(words, found, points, CARD, time.time() + seconds)


def test_dropped_drags_are_retried_and_invalid_words_learned(monkeypatch):
    game = FakeGame(valid={"STONE", "TONE", "ONE"}, dropped_once={"TONE"})

    accepted, rejected = run(monkeypatch, game, ["STONE", "XYZZY", "TONE", "ONE"])

    assert accepted == {"STONE", "TONE", "ONE"}
    assert rejected == {"XYZZY"}
    assert sorted(game.found) == ["ONE", "STONE", "TONE"]


def test_words_never_learned_as_rejected_without_a_check(monkeypatch):
    game = FakeGame(valid={"STONE"})

    accepted, rejected = run(monkeypatch, game, ["STONE", "XYZZY"], seconds=0)

    assert rejected == set()
