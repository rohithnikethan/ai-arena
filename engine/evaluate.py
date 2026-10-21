"""Heuristic evaluation for non-terminal Connect Four positions.

Classic *window scoring*: every one of the 69 possible four-cell lines
("windows") on the 6x7 board is inspected.  A window that contains discs of
both players can never become a four, so it scores nothing.  Otherwise:

==========================================  ======
Pattern (from the evaluating player's view)  Weight
==========================================  ======
each own disc in the center column             +3
each opponent disc in the center column        -3
own 2 discs + 2 empty in a window              +2
own 3 discs + 1 empty in a window              +5
opponent 2 discs + 2 empty in a window         -1
opponent 3 discs + 1 empty (a threat)          -4
four in a window (only if called on a won       +/-100
position; search normally handles wins)
==========================================  ======

The center bonus reflects that the middle column takes part in the most
windows.  Opponent threes are weighted slightly less than our own threes
(the player to move gets to act on threats first), and opponent twos are
penalised lightly so the heuristic is close to zero-sum.

Scores are small integers, far below the +/-1_000_000 used by search for
proven wins and losses.
"""

from .board import ROWS, COLS, H, cell_to_bit

CENTER_WEIGHT = 3
OWN_WEIGHTS = (0, 0, 2, 5, 100)   # indexed by own-disc count in a clean window
OPP_WEIGHTS = (0, 0, 1, 4, 100)   # subtracted, indexed by opponent-disc count

CENTER_MASK = ((1 << ROWS) - 1) << (3 * H)


def _build_windows():
    wins = []
    for r in range(ROWS):
        for c in range(COLS):
            for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
                cells = [(r + k * dr, c + k * dc) for k in range(4)]
                if all(0 <= rr < ROWS and 0 <= cc < COLS for rr, cc in cells):
                    m = 0
                    for rr, cc in cells:
                        m |= 1 << cell_to_bit(rr, cc)
                    wins.append(m)
    return tuple(wins)


#: Bit masks of all 69 four-cell windows.
WINDOWS = _build_windows()
assert len(WINDOWS) == 69


def evaluate(me, opp):
    """Score bitboard ``me`` against bitboard ``opp`` (higher = better for me)."""
    score = CENTER_WEIGHT * ((me & CENTER_MASK).bit_count()
                             - (opp & CENTER_MASK).bit_count())
    own_w = OWN_WEIGHTS
    opp_w = OPP_WEIGHTS
    for w in WINDOWS:
        a = me & w
        if a:
            if not (opp & w):
                score += own_w[a.bit_count()]
        else:
            o = opp & w
            if o:
                score -= opp_w[o.bit_count()]
    return score


def evaluate_board(board, player):
    """Convenience wrapper: evaluate a :class:`Board` for ``player``."""
    return evaluate(board.bb[player], board.bb[3 - player])
