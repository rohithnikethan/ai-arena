import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import api  # noqa: E402
from engine.board import Board  # noqa: E402
from engine.tracing import count_nodes  # noqa: E402


def grid(moves):
    b = Board()
    for c in moves:
        b.play(c)
    return b.to_grid()


EMPTY = [[0] * 7 for _ in range(6)]
TREE_KEYS = {"id", "move", "player", "value", "alpha", "beta", "visits", "wins",
             "pruned", "best", "terminal", "children"}


class TestPresets(unittest.TestCase):
    def test_presets(self):
        for key in ("random", "greedy", "minimax", "alphabeta", "mcts"):
            p = api.AGENT_PRESETS[key]
            self.assertEqual(p["type"], key)
            self.assertTrue(p["label"])
            self.assertTrue(p["description"].endswith("."))
        self.assertEqual(api.AGENT_PRESETS["minimax"]["depth"], 4)
        self.assertEqual(api.AGENT_PRESETS["alphabeta"]["depth"], 6)
        self.assertTrue(api.AGENT_PRESETS["alphabeta"]["move_ordering"])
        self.assertEqual(api.AGENT_PRESETS["mcts"]["iterations"], 1500)
        json.dumps(api.AGENT_PRESETS)

    def test_presets_usable_as_configs(self):
        g = grid([3, 3])
        for p in api.AGENT_PRESETS.values():
            res = api.choose_move(g, 1, {**p, "seed": 1, "iterations": 200})
            self.assertIn(res["column"], range(7))


class TestGameState(unittest.TestCase):
    def test_shape(self):
        st = api.game_state(EMPTY)
        self.assertEqual(st, {"winner": 0, "draw": False, "winning_cells": [],
                              "valid_moves": list(range(7)), "to_move": 1})

    def test_win(self):
        st = api.game_state(grid([0, 0, 1, 1, 2, 2, 3]))
        self.assertEqual(st["winner"], 1)
        self.assertEqual(st["winning_cells"], [[5, 0], [5, 1], [5, 2], [5, 3]])
        self.assertEqual(st["valid_moves"], [])


class TestValidation(unittest.TestCase):
    def bad(self, board, fragment):
        with self.assertRaises(ValueError) as cm:
            api.validate_board(board)
        self.assertIn(fragment, str(cm.exception))

    def test_errors(self):
        self.bad(None, "6 rows")
        self.bad([[0] * 7] * 5, "6 rows")
        self.bad([[0] * 7] * 5 + [[0] * 6], "7 cells")
        g = [row[:] for row in EMPTY]
        g[5][0] = 3
        self.bad(g, "0, 1 or 2")
        g[5][0] = "1"
        self.bad(g, "0, 1 or 2")
        g[5][0] = True
        self.bad(g, "0, 1 or 2")
        g = [row[:] for row in EMPTY]
        g[4][2] = 1
        self.bad(g, "floating")
        g = [row[:] for row in EMPTY]
        g[5][0] = 2
        self.bad(g, "disc counts")
        g = [row[:] for row in EMPTY]
        g[5][0] = g[5][1] = 1
        self.bad(g, "disc counts")

    def test_valid_returns_copy(self):
        g = grid([3])
        clean = api.validate_board(g)
        self.assertEqual(clean, g)
        self.assertIsNot(clean, g)

    def test_choose_move_errors(self):
        with self.assertRaises(ValueError):
            api.choose_move(EMPTY, 3, {"type": "random"})
        with self.assertRaises(ValueError):
            api.choose_move(EMPTY, 1, {"type": "deep-blue"})
        with self.assertRaises(ValueError):
            api.choose_move(EMPTY, 1, {"type": "minimax", "depth": "deep"})
        with self.assertRaises(ValueError):
            api.choose_move(grid([0, 0, 1, 1, 2, 2, 3]), 2, {"type": "greedy"})

    def test_clamping(self):
        cfg = api.normalize_config({"type": "alphabeta", "depth": 99, "iterations": 1})
        self.assertEqual(cfg["depth"], 8)
        self.assertEqual(cfg["iterations"], 50)
        self.assertEqual(api.normalize_config({"type": "minimax", "depth": 8})["depth"], 6)
        self.assertEqual(api.normalize_config({"type": "mcts", "iterations": 10 ** 9})["iterations"], 20000)
        self.assertEqual(api.normalize_config("mcts")["iterations"], 1500)


class TestChooseMove(unittest.TestCase):
    def check_tree(self, node, depth=0):
        self.assertEqual(set(node), TREE_KEYS)
        self.assertIsInstance(node["id"], str)
        self.assertIn(node["player"], (1, 2))
        self.assertLessEqual(depth, 3)
        for ch in node["children"]:
            self.check_tree(ch, depth + 1)

    def test_result_shapes(self):
        g = grid([3, 3, 2, 4])
        for cfg in ({"type": "random", "seed": 1}, {"type": "greedy"},
                    {"type": "minimax", "depth": 3}, {"type": "alphabeta", "depth": 5},
                    {"type": "alphabeta", "depth": 4, "move_ordering": False},
                    {"type": "mcts", "iterations": 300, "seed": 2}):
            res = api.choose_move(g, 1, cfg)
            json.dumps(res, allow_nan=False)
            self.assertEqual(set(res), {"column", "board_after", "state_after", "column_scores",
                                        "column_visits", "stats", "explanation",
                                        "principal_variation", "tree"})
            self.assertIsInstance(res["column"], int)
            self.assertEqual(len(res["board_after"]), 6)
            self.assertEqual(res["state_after"]["to_move"], 2)
            self.assertEqual(len(res["column_scores"]), 7)
            self.assertEqual(len(res["column_visits"]), 7)
            for s in res["column_scores"]:
                self.assertTrue(s is None or isinstance(s, float))
            for v in res["column_visits"]:
                self.assertTrue(v is None or isinstance(v, int))
            st = res["stats"]
            self.assertEqual(set(st), {"nodes", "pruned", "time_ms", "nodes_per_sec", "depth",
                                       "iterations", "max_depth_reached"})
            self.assertIsInstance(st["nodes"], int)
            self.assertIsInstance(st["nodes_per_sec"], int)
            self.assertIsInstance(st["time_ms"], float)
            self.assertIsInstance(res["explanation"], str)
            self.assertGreater(len(res["explanation"]), 10)
            self.assertTrue(all(isinstance(c, int) for c in res["principal_variation"]))
            self.assertIsNotNone(res["tree"])
            self.check_tree(res["tree"])
            self.assertLessEqual(count_nodes(res["tree"]), 400)
            if cfg["type"] == "mcts":
                self.assertEqual(st["iterations"], 300)
                self.assertIsNone(st["depth"])
            if cfg["type"] in ("minimax", "alphabeta"):
                self.assertEqual(st["depth"], cfg["depth"])

    def test_trace_off(self):
        res = api.choose_move(EMPTY, 1, {"type": "alphabeta", "depth": 3, "trace": False})
        self.assertIsNone(res["tree"])

    def test_preset_string(self):
        res = api.choose_move(EMPTY, 1, "greedy")
        self.assertEqual(res["column"], 3)


class TestMatch(unittest.TestCase):
    def test_match_shape_and_determinism(self):
        a = {"type": "greedy"}
        b = {"type": "mcts", "iterations": 100}
        r1 = api.run_match(a, b, games=4, seed=3)
        r2 = api.run_match(a, b, games=4, seed=3)
        json.dumps(r1, allow_nan=False)
        self.assertEqual(r1["results"], r2["results"])
        self.assertEqual(r1["games"], 4)
        self.assertEqual(r1["a_wins"] + r1["b_wins"] + r1["draws"], 4)
        self.assertEqual([g["first"] for g in r1["results"]], ["a", "b", "a", "b"])
        for g in r1["results"]:
            self.assertEqual(g["length"], len(g["moves"]))
            self.assertIn(g["winner"], ("a", "b", "draw"))
        for side in ("a", "b"):
            self.assertEqual(set(r1[side]), {"avg_time_ms", "avg_nodes", "label"})

    def test_strong_beats_random(self):
        r = api.run_match({"type": "alphabeta", "depth": 4}, {"type": "random"}, games=4, seed=1)
        self.assertEqual(r["a_wins"], 4)


class TestCompareDepth(unittest.TestCase):
    def test_compare(self):
        rows = api.compare_depth(depths=[1, 2, 3, 4, 7])
        json.dumps(rows, allow_nan=False)
        self.assertEqual([r["depth"] for r in rows], [1, 2, 3, 4, 7])
        for r in rows:
            for k in ("depth", "minimax_nodes", "alphabeta_nodes", "alphabeta_ordered_nodes",
                      "minimax_ms", "alphabeta_ms"):
                self.assertIn(k, r)
        self.assertEqual(rows[2]["minimax_nodes"], 400)
        self.assertLess(rows[3]["alphabeta_nodes"], rows[3]["minimax_nodes"])
        self.assertLessEqual(rows[3]["alphabeta_ordered_nodes"], rows[3]["alphabeta_nodes"])
        self.assertIsNone(rows[4]["minimax_nodes"])  # minimax capped at depth 6

    def test_compare_with_board(self):
        rows = api.compare_depth(grid([3, 3]), depths=(2,))
        self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
