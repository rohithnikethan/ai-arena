"""Connect Four board representation, rules and win detection.

Internally the board is stored as two *bitboards* (one Python int per player),
which makes moves, undo and win checks a handful of integer operations.

Bit layout (the classic 7-bits-per-column scheme)::

      6 13 20 27 34 41 48   <- sentinel row (always 0)
      5 12 19 26 33 40 47   <- top row      (grid row 0)
      4 11 18 25 32 39 46
      3 10 17 24 31 38 45
      2  9 16 23 30 37 44
      1  8 15 22 29 36 43
      0  7 14 21 28 35 42   <- bottom row   (grid row 5)

Bit index = col * 7 + height, where height 0 is the bottom cell.  The empty
sentinel row stops line patterns from wrapping from one column to the next,
so a four-in-a-row test is just four shift-and-mask operations.

The public API (engine/api.py) speaks the spec's 6x7 list-of-lists format;
:meth:`Board.from_grid` / :meth:`Board.to_grid` convert at that boundary.
"""

ROWS = 6
COLS = 7
H = ROWS + 1  # bits per column including the sentinel

#: Mask of the playable cells of each column.
COL_MASK = tuple(((1 << ROWS) - 1) << (c * H) for c in range(COLS))
#: Bit index one past the top playable cell of each column ("column full" mark).
COL_LIMIT = tuple(c * H + ROWS for c in range(COLS))
#: All 42 playable cells.
BOARD_MASK = sum(COL_MASK)
#: Center-first move ordering used by alpha-beta (and for tie-breaking).
CENTER_ORDER = (3, 2, 4, 1, 5, 0, 6)
#: Line directions as bit shifts: vertical, horizontal, diagonal /, diagonal \.
DIRECTIONS = (1, H, H + 1, H - 1)

PLAYER_NAMES = {1: "Red", 2: "Yellow"}


def has_four(bb):
    """Return True if bitboard ``bb`` contains four in a row in any direction."""
    m = bb & (bb >> 1)          # vertical
    if m & (m >> 2):
        return True
    m = bb & (bb >> 7)          # horizontal
    if m & (m >> 14):
        return True
    m = bb & (bb >> 8)          # diagonal /
    if m & (m >> 16):
        return True
    m = bb & (bb >> 6)          # diagonal \
    if m & (m >> 12):
        return True
    return False


def bit_to_cell(i):
    """Convert a bit index to a grid ``[row, col]`` (row 0 = top)."""
    return [ROWS - 1 - (i % H), i // H]


def cell_to_bit(r, c):
    """Convert grid ``(row, col)`` (row 0 = top) to a bit index."""
    return c * H + (ROWS - 1 - r)


class Board:
    """Mutable Connect Four position.

    Attributes:
        bb: ``[unused, red_bits, yellow_bits]`` so ``bb[player]`` works.
        heights: per column, the bit index of the next free cell.
        moves: number of discs on the board.
    """

    __slots__ = ("bb", "heights", "moves")

    def __init__(self):
        self.bb = [0, 0, 0]
        self.heights = [c * H for c in range(COLS)]
        self.moves = 0

    # ----------------------------------------------------------- conversion
    @classmethod
    def from_grid(cls, grid):
        """Build a Board from a (pre-validated) 6x7 list of lists."""
        b = cls()
        for c in range(COLS):
            for r in range(ROWS - 1, -1, -1):
                v = grid[r][c]
                if v:
                    bit = cell_to_bit(r, c)
                    b.bb[v] |= 1 << bit
                    b.heights[c] = bit + 1
                    b.moves += 1
        return b

    def to_grid(self):
        """Return the position as a fresh 6x7 list of lists (row 0 = top)."""
        grid = [[0] * COLS for _ in range(ROWS)]
        for p in (1, 2):
            bits = self.bb[p]
            while bits:
                low = bits & -bits
                r, c = bit_to_cell(low.bit_length() - 1)
                grid[r][c] = p
                bits ^= low
        return grid

    def copy(self):
        b = Board.__new__(Board)
        b.bb = self.bb[:]
        b.heights = self.heights[:]
        b.moves = self.moves
        return b

    def key(self):
        """Hashable key identifying the position."""
        return (self.bb[1], self.bb[2])

    # ----------------------------------------------------------------- rules
    @property
    def to_move(self):
        """Player to move: Red (1) moves first, so equal disc counts -> 1."""
        return 1 if self.moves % 2 == 0 else 2

    def can_play(self, col):
        return 0 <= col < COLS and self.heights[col] < COL_LIMIT[col]

    def valid_moves(self):
        h = self.heights
        return [c for c in range(COLS) if h[c] < COL_LIMIT[c]]

    def play(self, col, player=None):
        """Drop a disc for ``player`` (default: side to move) into ``col``."""
        if player is None:
            player = self.to_move
        if not self.can_play(col):
            raise ValueError(f"column {col + 1} is full or out of range")
        self.bb[player] |= 1 << self.heights[col]
        self.heights[col] += 1
        self.moves += 1
        return self

    def undo(self, col, player):
        """Remove the top disc of ``col`` (which must belong to ``player``)."""
        self.heights[col] -= 1
        self.bb[player] ^= 1 << self.heights[col]
        self.moves -= 1

    def landing_row(self, col):
        """Grid row (0 = top) where a disc dropped in ``col`` would land."""
        return ROWS - 1 - (self.heights[col] - col * H)

    def is_winning_move(self, col, player):
        """True if ``player`` dropping into ``col`` right now makes four."""
        if self.heights[col] >= COL_LIMIT[col]:
            return False
        return has_four(self.bb[player] | (1 << self.heights[col]))

    def winning_moves(self, player):
        """Columns where ``player`` would win immediately if it were to move."""
        bits = self.bb[player]
        h = self.heights
        return [c for c in range(COLS)
                if h[c] < COL_LIMIT[c] and has_four(bits | (1 << h[c]))]

    def winner(self):
        if has_four(self.bb[1]):
            return 1
        if has_four(self.bb[2]):
            return 2
        return 0

    def is_full(self):
        return self.moves >= ROWS * COLS

    def is_terminal(self):
        return self.winner() != 0 or self.is_full()

    def winning_cells(self):
        """All cells that belong to some four-in-a-row, as sorted [r, c] pairs."""
        cells = set()
        for p in (1, 2):
            b = self.bb[p]
            for s in DIRECTIONS:
                m = b & (b >> s) & (b >> 2 * s) & (b >> 3 * s)
                while m:
                    low = m & -m
                    i = low.bit_length() - 1
                    for k in range(4):
                        cells.add(tuple(bit_to_cell(i + k * s)))
                    m ^= low
        return [list(rc) for rc in sorted(cells)]

    def state(self):
        """The spec's ``game_state`` dict for this position."""
        w = self.winner()
        draw = w == 0 and self.is_full()
        return {
            "winner": w,
            "draw": draw,
            "winning_cells": self.winning_cells() if w else [],
            "valid_moves": [] if (w or draw) else self.valid_moves(),
            "to_move": self.to_move,
        }

    def __repr__(self):
        rows = ["".join(".XO"[v] for v in row) for row in self.to_grid()]
        return "Board(\n  " + "\n  ".join(rows) + "\n)"
