import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.board import Board, has_four  # noqa: E402
from engine.evaluate import evaluate, WINDOWS  # noqa: E402


def play(moves):
    b = Board()
    for c in moves:
        b.play(c)
    return b


# A full, legal (21 v 21) board with no four in a row.
DRAW_GRID = [
    [2, 2, 1, 2, 1, 2, 1],
    [1, 2, 1, 2, 1, 2, 1],
    [2, 1, 2, 1, 2, 1, 2],
    [2, 1, 2, 1, 2, 1, 2],
    [1, 2, 1, 2, 1, 2, 1],
    [1, 2, 1, 2, 1, 2, 1],
]


def empty_grid():
    return [[0] * 7 for _ in range(6)]


class TestRules(unittest.TestCase):
    def test_empty(self):
        b = Board()
        st = b.state()
        self.assertEqual(st["winner"], 0)
        self.assertFalse(st["draw"])
        self.assertEqual(st["valid_moves"], list(range(7)))
        self.assertEqual(st["to_move"], 1)

    def test_gravity_and_grid_roundtrip(self):
        b = play([3, 3, 0])
        g = b.to_grid()
        self.assertEqual(g[5][3], 1)
        self.assertEqual(g[4][3], 2)
        self.assertEqual(g[5][0], 1)
        self.assertEqual(Board.from_grid(g).key(), b.key())
        self.assertEqual(Board.from_grid(g).to_move, 2)

    def test_horizontal(self):
        b = play([0, 0, 1, 1, 2, 2, 3])
        self.assertEqual(b.winner(), 1)
        self.assertEqual(b.winning_cells(), [[5, 0], [5, 1], [5, 2], [5, 3]])

    def test_vertical(self):
        b = play([0, 1, 0, 1, 0, 1, 6, 1])
        self.assertEqual(b.winner(), 2)
        self.assertEqual(b.winning_cells(), [[2, 1], [3, 1], [4, 1], [5, 1]])

    def test_diagonal_up_right(self):
        g = empty_grid()
        for r, c in [(5, 0), (4, 1), (3, 2), (2, 3)]:
            g[r][c] = 1
        for r, c in [(5, 1), (5, 2), (4, 2), (5, 3), (4, 3), (3, 3)]:
            g[r][c] = 2
        b = Board.from_grid(g)
        self.assertTrue(has_four(b.bb[1]))
        self.assertEqual(b.winner(), 1)
        self.assertEqual(b.winning_cells(), [[2, 3], [3, 2], [4, 1], [5, 0]])

    def test_diagonal_down_right(self):
        g = empty_grid()
        for r, c in [(2, 3), (3, 4), (4, 5), (5, 6)]:
            g[r][c] = 2
        for r, c in [(5, 3), (4, 3), (3, 3), (5, 4), (4, 4), (5, 5)]:
            g[r][c] = 1
        b = Board.from_grid(g)
        self.assertEqual(b.winner(), 2)
        self.assertEqual(b.winning_cells(), [[2, 3], [3, 4], [4, 5], [5, 6]])

    def test_no_wraparound(self):
        # discs at the top of col 0 and bottom of col 1 must not connect
        g = empty_grid()
        for r, v in enumerate([1, 1, 2, 1, 2, 2]):
            g[r][0] = v
        g[5][1] = 1
        g[4][1] = 1
        b = Board.from_grid(g)
        self.assertEqual(b.winner(), 0)

    def test_full_column(self):
        b = play([0] * 6)
        self.assertFalse(b.can_play(0))
        self.assertNotIn(0, b.valid_moves())
        with self.assertRaises(ValueError):
            b.play(0)

    def test_draw(self):
        b = Board.from_grid(DRAW_GRID)
        self.assertEqual(b.moves, 42)
        self.assertEqual(b.winner(), 0, msg=repr(b))
        st = b.state()
        self.assertTrue(st["draw"])
        self.assertEqual(st["valid_moves"], [])

    def test_winning_moves(self):
        b = play([0, 6, 1, 6, 2])
        self.assertEqual(b.winning_moves(1), [3])
        self.assertTrue(b.is_winning_move(3, 1))
        self.assertFalse(b.is_winning_move(4, 1))


class TestEvaluate(unittest.TestCase):
    def test_window_count(self):
        self.assertEqual(len(WINDOWS), 69)

    def test_symmetry_and_center(self):
        self.assertEqual(evaluate(0, 0), 0)
        center = play([3])
        edge = play([0])
        self.assertGreater(evaluate(center.bb[1], 0), evaluate(edge.bb[1], 0))
        self.assertGreater(evaluate(center.bb[1], 0), 0)
        self.assertLess(evaluate(0, center.bb[1]), 0)

    def test_threat_penalised(self):
        b = play([0, 6, 1, 6, 2])  # Red has three in a row, open
        self.assertGreater(evaluate(b.bb[1], b.bb[2]), 0)
        self.assertLess(evaluate(b.bb[2], b.bb[1]), 0)


if __name__ == "__main__":
    unittest.main()
