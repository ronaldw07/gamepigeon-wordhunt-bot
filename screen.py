"""Find the Start button and the board in a screenshot, and read the letters.

Everything is located by color rather than by matching saved images, so it
works at any screen size or window position.
"""
import cv2
import numpy as np

LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
# Fraction of a board row/column that must be tile-colored to count as a tile.
TILE_PROFILE_THRESHOLD = 0.3
# Trim off each tile edge before OCR so tile shading isn't read as a letter.
TILE_INSET_FRACTION = 1 / 8
LETTER_DARKNESS = 90
OCR_PADDING = 20


def green_blobs(image):
    """Bounding boxes and fill ratios of the bright green used for the board
    border and the Start button."""
    r, g, b = (image[..., i].astype(int) for i in range(3))
    mask = ((g > 200) & (g - r > 60) & (g - b > 60)).astype(np.uint8)
    _, _, stats, _ = cv2.connectedComponentsWithStats(mask)
    return [
        (x, y, w, h, area / (w * h))
        for x, y, w, h, area in stats[1:]
    ]


def find_start_button(image):
    """Center of the Start button, a solid green pill, or None."""
    min_width = image.shape[1] * 0.03
    for x, y, w, h, fill in green_blobs(image):
        if w > min_width and 1.8 < w / h < 3.5 and fill > 0.8:
            return x + w // 2, y + h // 2
    return None


def find_board(image):
    """Bounding box (x, y, w, h) of the board's hollow green square, or None."""
    min_width = image.shape[1] * 0.08
    boards = [
        (x, y, w, h)
        for x, y, w, h, fill in green_blobs(image)
        if w > min_width and 0.9 < w / h < 1.1 and fill < 0.5
    ]
    return max(boards, key=lambda box: box[2], default=None)


def runs(profile):
    """(start, end) spans where the profile is above the tile threshold."""
    spans, start = [], None
    for i, on in enumerate(profile > TILE_PROFILE_THRESHOLD):
        if on and start is None:
            start = i
        elif not on and start is not None:
            spans.append((start, i))
            start = None
    if start is not None:
        spans.append((start, len(profile)))
    return spans


def tile_boxes(image, board):
    """Rows of tile boxes (x0, y0, x1, y1) in image coordinates."""
    x, y, w, h = board
    sub = image[y:y + h, x:x + w].astype(int)
    r, g, b = sub[..., 0], sub[..., 1], sub[..., 2]
    tan = (r > 200) & (g > 150) & (r - b > 50)
    cols = runs(tan.mean(axis=0))
    rows = runs(tan.mean(axis=1))
    return [
        [(x + x0, y + y0, x + x1, y + y1) for x0, x1 in cols]
        for y0, y1 in rows
    ]


def read_letter(image, box, reader):
    x0, y0, x1, y1 = box
    inset = int((x1 - x0) * TILE_INSET_FRACTION)
    tile = image[y0 + inset:y1 - inset, x0 + inset:x1 - inset]
    gray = cv2.cvtColor(tile, cv2.COLOR_RGB2GRAY)
    ink = np.where(gray < LETTER_DARKNESS, 0, 255).astype(np.uint8)
    padded = cv2.copyMakeBorder(
        ink, OCR_PADDING, OCR_PADDING, OCR_PADDING, OCR_PADDING,
        cv2.BORDER_CONSTANT, value=255,
    )
    result = reader.recognize(padded, allowlist=LETTERS, detail=0)
    return result[0] if result else ""


def read_board(image, board, reader):
    """Return (grid, centers): grid is a list of row strings, centers maps
    (row, col) to the tile center in image pixels."""
    boxes = tile_boxes(image, board)
    grid = ["".join(read_letter(image, box, reader) for box in row) for row in boxes]
    centers = {
        (r, c): ((x0 + x1) / 2, (y0 + y1) / 2)
        for r, row in enumerate(boxes)
        for c, (x0, y0, x1, y1) in enumerate(row)
    }
    return grid, centers
