from collections import Counter

MIN_WORD_LENGTH = 3
SHORT_WORD_SCORES = {3: 100, 4: 400, 5: 800, 6: 1400, 7: 1800}


def word_score(word):
    if len(word) >= 8:
        return 2200 + 400 * (len(word) - 8)
    return SHORT_WORD_SCORES[len(word)]


def load_words(filename):
    with open(filename) as f:
        return [line.strip() for line in f if line.strip()]


def candidate_words(grid, words):
    """Words whose letters the board actually has, so the search only
    builds prefixes for a few thousand words instead of the whole list."""
    board_counts = Counter("".join(grid))
    board_letters = set(board_counts)
    max_length = len(grid) * len(grid[0])
    return [
        word for word in words
        if MIN_WORD_LENGTH <= len(word) <= max_length
        and set(word) <= board_letters
        and not Counter(word) - board_counts
    ]


def neighbors(row, col, rows, cols):
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            r, c = row + dr, col + dc
            if (dr or dc) and 0 <= r < rows and 0 <= c < cols:
                yield r, c


def find_words(grid, words):
    """Map every dictionary word on the board to one tile path that spells it.

    grid is a list of equal-length strings, one per row. A path is a list of
    (row, col) tiles, each adjacent (8 directions) to the last, none reused.
    """
    candidates = candidate_words(grid, words)
    word_set = set(candidates)
    prefixes = {word[:i] for word in candidates for i in range(1, len(word) + 1)}
    rows, cols = len(grid), len(grid[0])
    found = {}

    def search(row, col, prefix, path):
        prefix += grid[row][col]
        if prefix not in prefixes:
            return
        path = path + [(row, col)]
        if prefix in word_set and prefix not in found:
            found[prefix] = path
        for r, c in neighbors(row, col, rows, cols):
            if (r, c) not in path:
                search(r, c, prefix, path)

    for row in range(rows):
        for col in range(cols):
            search(row, col, "", [])
    return found


def play_order(found, common_words):
    """Highest scoring first. Among equal lengths, common words go first since
    obscure Scrabble words are the ones the game is likeliest to reject."""
    return sorted(found, key=lambda w: (-len(w), w not in common_words, w))
