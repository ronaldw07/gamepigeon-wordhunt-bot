import argparse
import subprocess
import tempfile
import threading
import time
from os import path

import easyocr
import numpy as np
from PIL import Image
from pynput import keyboard
from Quartz import (
    CGEventCreateMouseEvent,
    CGEventPost,
    CGWindowListCopyWindowInfo,
    kCGEventLeftMouseDown,
    kCGEventLeftMouseDragged,
    kCGEventLeftMouseUp,
    kCGHIDEventTap,
    kCGMouseButtonLeft,
    kCGNullWindowID,
    kCGWindowListOptionOnScreenOnly,
)

from screen import find_board, find_start_button, read_board
from solver import find_words, load_words, play_order, word_score

ROUND_SECONDS = 80
# Stop before the clock does so a drag never lands on the results screen.
TIME_SAFETY_MARGIN = 1.5
# Pauses that let iPhone Mirroring register each touch. Lower is faster but
# risks dropped tiles; raise them if words come out wrong.
TOUCH_DOWN_PAUSE = 0.03
TILE_STEP_PAUSE = 0.03
BETWEEN_WORDS_PAUSE = 0.04
CLICK_HOLD = 0.05
BOARD_WAIT_SECONDS = 10
POLL_INTERVAL = 0.3
RETRY_MIN_WORD_LENGTH = 5

stop_requested = threading.Event()


def start_kill_switch():
    def on_press(key):
        if key == keyboard.Key.esc:
            stop_requested.set()
            print("\nEsc pressed, stopping.")
            return False

    try:
        listener = keyboard.Listener(on_press=on_press)
        listener.daemon = True
        listener.start()
        print("Press Esc at any time to stop.")
    except Exception as error:
        print(f"Esc kill switch unavailable ({error}). Press Ctrl+C in the terminal to stop.")


def path_to_file(filename):
    return path.abspath(path.join(path.dirname(__file__), filename))


def find_mirroring_window():
    """Bounds (x, y, w, h) in screen points of the iPhone Mirroring window,
    on whichever display it is, or None."""
    windows = CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly, kCGNullWindowID)
    bounds = [
        w["kCGWindowBounds"] for w in windows
        if w.get("kCGWindowOwnerName") == "iPhone Mirroring"
        and w.get("kCGWindowName") == "iPhone Mirroring"
    ]
    if not bounds:
        return None
    b = max(bounds, key=lambda b: b["Width"] * b["Height"])
    return int(b["X"]), int(b["Y"]), int(b["Width"]), int(b["Height"])


def screenshot(window):
    """Capture just the mirroring window. Works on any display, unlike a
    full-screen grab, which only covers the main one."""
    x, y, w, h = window
    with tempfile.NamedTemporaryFile(suffix=".png") as f:
        subprocess.run(["screencapture", "-x", f"-R{x},{y},{w},{h}", f.name], check=True)
        return np.array(Image.open(f.name).convert("RGB"))


def to_screen_points(pixel, window, scale):
    """Screenshots are in display pixels (2x on Retina), the mouse moves in
    points measured from the main display's corner."""
    return window[0] + pixel[0] / scale, window[1] + pixel[1] / scale


def post_mouse(kind, point):
    CGEventPost(kCGHIDEventTap, CGEventCreateMouseEvent(None, kind, point, kCGMouseButtonLeft))


def drag_path(points):
    """Press on the first tile, slide through the rest, release. pyautogui's
    moveTo sends plain moves while the button is down, which the phone does
    not treat as a drag, so this posts real drag events."""
    post_mouse(kCGEventLeftMouseDown, points[0])
    time.sleep(TOUCH_DOWN_PAUSE)
    for point in points[1:]:
        post_mouse(kCGEventLeftMouseDragged, point)
        time.sleep(TILE_STEP_PAUSE)
    post_mouse(kCGEventLeftMouseUp, points[-1])
    time.sleep(BETWEEN_WORDS_PAUSE)


def click(point):
    post_mouse(kCGEventLeftMouseDown, point)
    time.sleep(CLICK_HOLD)
    post_mouse(kCGEventLeftMouseUp, point)


def press_start(window, scale):
    """Click Start if it is showing, then wait for the board. Returns the
    first in-game screenshot and board box, or (None, None) on timeout."""
    deadline = time.time() + BOARD_WAIT_SECONDS
    while time.time() < deadline and not stop_requested.is_set():
        image = screenshot(window)
        start = find_start_button(image)
        if start:
            click(to_screen_points(start, window, scale))
        else:
            board = find_board(image)
            if board:
                return image, board
        time.sleep(POLL_INTERVAL)
    return None, None


def read_board_until_complete(image, board, reader, window):
    """Tiles can still be animating in on the first frame, so reread until
    every tile gives exactly one letter."""
    deadline = time.time() + BOARD_WAIT_SECONDS
    while True:
        grid, centers = read_board(image, board, reader)
        complete = len(grid) > 0 and all(len(row) == len(grid) for row in grid)
        if complete or time.time() > deadline:
            return grid, centers
        time.sleep(POLL_INTERVAL)
        image = screenshot(window)
        board = find_board(image) or board


def play(words, found, centers, window, scale, deadline):
    def submit(word):
        drag_path([to_screen_points(centers[tile], window, scale) for tile in found[word]])

    for word in words:
        if time.time() > deadline or stop_requested.is_set():
            return
        submit(word)

    # Time left over means every word went in once. Resubmit the long ones to
    # recover any that a dropped touch spoiled; repeats are simply ignored.
    for word in words:
        if len(word) < RETRY_MIN_WORD_LENGTH:
            return
        if time.time() > deadline or stop_requested.is_set():
            return
        submit(word)


def print_results(grid, words):
    print("\n".join(" ".join(row) for row in grid))
    total = sum(word_score(w) for w in words)
    print(f"{len(words)} words, {total} points available")
    print(", ".join(words[:30]) + (" ..." if len(words) > 30 else ""))


def main():
    parser = argparse.ArgumentParser(description="Play GamePigeon Word Hunt through iPhone Mirroring.")
    parser.add_argument("--dry-run", action="store_true", help="read the board and list words without playing")
    args = parser.parse_args()

    start_kill_switch()
    print("Loading OCR and dictionary...")
    reader = easyocr.Reader(["en"], verbose=False)
    words = load_words(path_to_file("words.txt"))
    common_words = set(load_words(path_to_file("common_words.txt")))

    subprocess.run(["open", "-a", "iPhone Mirroring"], check=False)
    time.sleep(0.5)
    window = find_mirroring_window()
    if window is None:
        print("iPhone Mirroring isn't open. Open it, start a Word Hunt game, and try again.")
        return
    scale = screenshot(window).shape[1] / window[2]

    if args.dry_run:
        image = screenshot(window)
        board = find_board(image)
    else:
        image, board = press_start(window, scale)
    if board is None:
        print("No board found. Open a Word Hunt game in iPhone Mirroring to the Start screen and try again.")
        return
    round_start = time.time()

    grid, centers = read_board_until_complete(image, board, reader, window)
    if not grid or any(len(row) != len(grid) for row in grid):
        print(f"Could not read every tile: {grid}")
        return

    found = find_words(grid, words)
    ordered = play_order(found, common_words)
    print_results(grid, ordered)
    if args.dry_run:
        return

    play(ordered, found, centers, window, scale, round_start + ROUND_SECONDS - TIME_SAFETY_MARGIN)
    print(f"Done in {time.time() - round_start:.1f}s.")


if __name__ == "__main__":
    main()
