import argparse
import subprocess
import threading
import time
from os import path

import easyocr
import numpy as np
from pynput import keyboard
from Quartz import (
    CGDataProviderCopyData,
    CGEventCreateMouseEvent,
    CGEventPost,
    CGImageGetBytesPerRow,
    CGImageGetDataProvider,
    CGImageGetHeight,
    CGImageGetWidth,
    CGRectNull,
    CGWindowListCopyWindowInfo,
    CGWindowListCreateImage,
    kCGEventLeftMouseDown,
    kCGEventLeftMouseDragged,
    kCGEventLeftMouseUp,
    kCGHIDEventTap,
    kCGMouseButtonLeft,
    kCGNullWindowID,
    kCGWindowImageBoundsIgnoreFraming,
    kCGWindowListOptionIncludingWindow,
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

# Words GamePigeon doesn't accept, skipped so they don't waste drag time.
REJECTED_WORDS_FILE = "rejected_words.txt"

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
    """(window id, bounds) of the iPhone Mirroring window, with bounds
    (x, y, w, h) in screen points on whichever display it is, or None."""
    windows = CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly, kCGNullWindowID)
    matches = [
        w for w in windows
        if w.get("kCGWindowOwnerName") == "iPhone Mirroring"
        and w.get("kCGWindowName") == "iPhone Mirroring"
    ]
    if not matches:
        return None
    w = max(matches, key=lambda w: w["kCGWindowBounds"]["Width"] * w["kCGWindowBounds"]["Height"])
    b = w["kCGWindowBounds"]
    return w["kCGWindowNumber"], (int(b["X"]), int(b["Y"]), int(b["Width"]), int(b["Height"]))


def screenshot(window_id):
    """Capture just the mirroring window as RGB, on any display and even if
    covered. In-process, so it takes milliseconds."""
    image = CGWindowListCreateImage(
        CGRectNull, kCGWindowListOptionIncludingWindow, window_id, kCGWindowImageBoundsIgnoreFraming,
    )
    width, height = CGImageGetWidth(image), CGImageGetHeight(image)
    data = CGDataProviderCopyData(CGImageGetDataProvider(image))
    bgra = np.frombuffer(data, dtype=np.uint8).reshape(height, CGImageGetBytesPerRow(image) // 4, 4)
    return np.ascontiguousarray(bgra[:, :width, 2::-1])


def capture():
    """(window bounds, image) taken together. The window moves and resizes as
    the phone changes screens, so positions are only valid for the bounds
    they were captured with."""
    found = find_mirroring_window()
    if found is None:
        return None, None
    window_id, window = found
    return window, screenshot(window_id)


def to_screen_points(pixel, window, image):
    """Screenshots are in display pixels (2x on Retina), the mouse moves in
    points measured from the main display's corner."""
    scale = image.shape[1] / window[2]
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


def wait_for_board(reader, should_press_start):
    """Press Start if it is showing, then read the board once it has settled:
    the same window, board position, and letters in two captures in a row, so
    nothing is read mid-animation. Returns (grid, points) with each tile's
    screen position, or (None, None)."""
    deadline = time.time() + BOARD_WAIT_SECONDS
    previous = None
    while time.time() < deadline and not stop_requested.is_set():
        window, image = capture()
        start = find_start_button(image) if image is not None else None
        board = find_board(image) if image is not None else None
        if start and should_press_start:
            click(to_screen_points(start, window, image))
            previous = None
        elif board:
            grid, centers = read_board(image, board, reader)
            complete = len(grid) > 0 and all(len(row) == len(grid) for row in grid)
            current = (window, board, tuple(grid)) if complete else None
            if current and current == previous:
                points = {tile: to_screen_points(c, window, image) for tile, c in centers.items()}
                return grid, points
            previous = current
        time.sleep(POLL_INTERVAL)
    return None, None


def play(words, found, points, deadline):
    """Drag every word, highest scoring first, then send them all once more to
    recover any a dropped touch spoiled; repeats are simply ignored."""
    for word in words + words:
        if time.time() > deadline or stop_requested.is_set():
            return
        drag_path([points[tile] for tile in found[word]])


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
    rejected = set(load_words(path_to_file(REJECTED_WORDS_FILE)))
    words = [w for w in load_words(path_to_file("words.txt")) if w not in rejected]
    common_words = set(load_words(path_to_file("common_words.txt")))

    subprocess.run(["open", "-a", "iPhone Mirroring"], check=False)
    time.sleep(0.5)
    if find_mirroring_window() is None:
        print("iPhone Mirroring isn't open. Open it, start a Word Hunt game, and try again.")
        return

    grid, points = wait_for_board(reader, should_press_start=not args.dry_run)
    if grid is None:
        print("Couldn't read the board. Open a Word Hunt game in iPhone Mirroring to the Start screen and try again.")
        return
    round_start = time.time()

    found = find_words(grid, words)
    ordered = play_order(found, common_words)
    print_results(grid, ordered)
    if args.dry_run:
        return

    play(ordered, found, points, round_start + ROUND_SECONDS - TIME_SAFETY_MARGIN)
    print(f"Done in {time.time() - round_start:.1f}s.")


if __name__ == "__main__":
    main()
