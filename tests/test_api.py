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
             "pruned", "best", "terminal", "children", "bound"}


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


class TestRandomOpenings(unittest.TestCase):
    def test_deterministic_by_seed(self):
        a = {"type": "alphabeta", "depth": 2}
        b = {"type": "greedy"}
        r1 = api.run_match(a, b, games=8, seed=5, opening_plies=3)
        r2 = api.run_match(a, b, games=8, seed=5, opening_plies=3)
        self.assertEqual(r1["results"], r2["results"])
        self.assertEqual(r1["opening_plies"], 3)
        r3 = api.run_match(a, b, games=8, seed=6, opening_plies=3)
        self.assertNotEqual([g["opening"] for g in r1["results"]],
                            [g["opening"] for g in r3["results"]])
        json.dumps(r1, allow_nan=False)

    def test_pairs_share_opening_with_colours_swapped(self):
        r = api.run_match({"type": "alphabeta", "depth": 2}, {"type": "greedy"},
                          games=10, seed=1, opening_plies=2)
        res = r["results"]
        openings = [tuple(g["opening"]) for g in res[::2]]
        self.assertEqual(len(set(openings)), 5)              # drawn without replacement
        for i in range(0, 10, 2):
            self.assertEqual(res[i]["opening"], res[i + 1]["opening"])
            self.assertEqual(len(res[i]["opening"]), 2)
            self.assertEqual((res[i]["first"], res[i + 1]["first"]), ("a", "b"))
            for g in res[i:i + 2]:
                self.assertEqual(g["moves"][:2], g["opening"])
                self.assertEqual(g["length"], len(g["moves"]))

    def test_default_is_backward_compatible(self):
        r = api.run_match({"type": "greedy"}, {"type": "random"}, games=2, seed=0)
        self.assertEqual(r["opening_plies"], 0)
        self.assertTrue(all(g["opening"] == [] for g in r["results"]))
        r0 = api.run_match({"type": "greedy"}, {"type": "random"}, games=2, seed=0,
                           opening_plies=0)
        self.assertEqual(r["results"], r0["results"])

    def test_random_openings_helper(self):
        ops = api.random_openings(49, 2, seed=0)
        self.assertEqual(len({tuple(o) for o in ops}), 49)   # all 49 two-ply openings
        self.assertEqual(api.random_openings(60, 2, seed=0)[:49], ops)
        self.assertEqual(api.random_openings(3, 0, seed=0), [[], [], []])
        self.assertEqual(api.run_match("random", "random", games=2, opening_plies=99)
                         ["opening_plies"], 6)

    def test_explicit_openings(self):
        r = api.run_match("greedy", "random", games=4, openings=[[3, 3], [0]])
        self.assertEqual([g["opening"] for g in r["results"]], [[3, 3], [3, 3], [0], [0]])
        for bad in ([], [[7]], [[0] * 7], [["3"]], "33"):
            with self.assertRaises(ValueError):
                api.run_match("greedy", "random", games=2, openings=bad)


class TestIntegerPolicy(unittest.TestCase):
    def test_engine_policy(self):
        self.assertEqual(api.normalize_config({"type": "alphabeta", "depth": 5.0})["depth"], 5)
        self.assertEqual(api.normalize_config({"type": "alphabeta", "depth": 1e15})["depth"], 8)
        for bad in ("5", 5.5, True, float("nan"), float("inf"), 1e308, 2 ** 60 + 0.0):
            with self.assertRaises(ValueError, msg=repr(bad)):
                api.normalize_config({"type": "alphabeta", "depth": bad})
        with self.assertRaises(ValueError):
            api.normalize_config({"type": "mcts", "iterations": "1500"})
        with self.assertRaises(ValueError):
            api.choose_move(EMPTY, "1", {"type": "random"})
        self.assertEqual(api.choose_move(EMPTY, 1.0, "greedy")["column"], 3)
        g = [row[:] for row in EMPTY]
        g[5][3] = 1.0
        self.assertEqual(api.validate_board(g)[5][3], 1)
        self.assertEqual(api.apply_move(EMPTY, 3.0)[0][5][3], 1)
        with self.assertRaises(ValueError):
            api.apply_move(EMPTY, "3")

    def test_cost_estimate(self):
        cheap = api.estimate_match_seconds("random", "greedy", 50)
        heavy = api.estimate_match_seconds({"type": "mcts", "iterations": 20000},
                                           {"type": "mcts", "iterations": 20000}, 50)
        self.assertLess(cheap, 1)
        self.assertGreater(heavy, 1000)
        self.assertLess(api.estimate_match_seconds("alphabeta", "mcts", 50), 240)


class TestRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import app as app_module
        cls.app_module = app_module
        cls.client = app_module.app.test_client()

    def post(self, path, body):
        return self.client.post(path, json=body)

    def test_move_integer_policy(self):
        ok = {"board": EMPTY, "player": 1, "agent": {"type": "alphabeta", "depth": 3.0}}
        r = self.post("/api/move", ok)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["stats"]["depth"], 3)
        for agent in ({"type": "alphabeta", "depth": "5"}, {"type": "alphabeta", "depth": 5.5},
                      {"type": "alphabeta", "depth": 1e308}, {"type": "alphabeta", "depth": True},
                      {"type": "mcts", "iterations": "200"}, {"type": "random", "seed": "1"}):
            r = self.post("/api/move", {"board": EMPTY, "player": 1, "agent": agent})
            self.assertEqual(r.status_code, 400, agent)
            self.assertIn("integer", r.get_json()["error"])
        r = self.post("/api/move", {"board": EMPTY, "player": "1", "agent": {"type": "random"}})
        self.assertEqual(r.status_code, 400)
        r = self.post("/api/move", {"board": EMPTY, "player": 1.0, "agent": {"type": "random"}})
        self.assertEqual(r.status_code, 200)

    def test_apply_and_board_policy(self):
        self.assertEqual(self.post("/api/apply", {"board": EMPTY, "column": 3.0}).status_code, 200)
        self.assertEqual(self.post("/api/apply", {"board": EMPTY, "column": "3"}).status_code, 400)
        g = [row[:] for row in EMPTY]
        g[5][3] = 1.0
        self.assertEqual(self.post("/api/state", {"board": g}).status_code, 200)
        g[5][3] = "1"
        self.assertEqual(self.post("/api/state", {"board": g}).status_code, 400)

    def test_compare_depth_policy(self):
        self.assertEqual(self.post("/api/compare-depth", {"depths": [1.0, 2]}).status_code, 200)
        self.assertEqual(self.post("/api/compare-depth", {"depths": ["2"]}).status_code, 400)

    def test_match_work_cap(self):
        heavy = {"agent_a": {"type": "mcts", "iterations": 20000},
                 "agent_b": {"type": "mcts", "iterations": 20000}, "games": 50}
        r = self.post("/api/match", heavy)
        self.assertEqual(r.status_code, 400)
        err = r.get_json()["error"]
        self.assertIn("too long", err)
        self.assertIn("at most 4 games fit", err)
        r = self.post("/api/match", {**heavy, "agent_a": {"type": "alphabeta", "depth": 8},
                                     "agent_b": {"type": "alphabeta", "depth": 8}})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.post("/api/match", {**heavy, "games": "2"}).status_code, 400)

    def test_match_openings(self):
        r = self.post("/api/match", {"agent_a": {"type": "greedy"}, "agent_b": {"type": "random"},
                                     "games": 4, "seed": 2, "opening_plies": 2})
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertEqual(data["opening_plies"], 2)
        self.assertEqual(len(data["results"][0]["opening"]), 2)
        self.assertEqual(self.post("/api/match", {"agent_a": "greedy", "agent_b": "random",
                                                  "games": 2, "opening_plies": "2"}).status_code, 400)

    def test_debug_opt_in(self):
        import os
        old = os.environ.pop("AI_ARENA_DEBUG", None)
        try:
            self.assertFalse(self.app_module._debug_enabled())
            for v, want in (("1", True), ("true", True), ("ON", True), ("0", False), ("", False)):
                os.environ["AI_ARENA_DEBUG"] = v
                self.assertEqual(self.app_module._debug_enabled(), want, v)
        finally:
            os.environ.pop("AI_ARENA_DEBUG", None)
            if old is not None:
                os.environ["AI_ARENA_DEBUG"] = old


def bottom_rows(*rows):
    """A board whose bottom rows are ``rows`` (last = bottom), empty above."""
    return [[0] * 7 for _ in range(6 - len(rows))] + [list(r) for r in rows]


class TestImpossibleWins(unittest.TestCase):
    """Regression: boards where play continued after a win were accepted."""

    def bad(self, board, fragment):
        with self.assertRaises(ValueError) as cm:
            api.validate_board(board)
        self.assertIn(fragment, str(cm.exception))

    def test_red_four_needs_red_to_have_moved_last(self):
        # audit repro: Red four, but Yellow has as many discs (Yellow moved after)
        self.bad(bottom_rows([2, 2, 2, 0, 0, 0, 0], [1, 1, 1, 1, 0, 0, 2]), "moved after")

    def test_yellow_four_needs_equal_counts(self):
        # Yellow four with 5 Red vs 4 Yellow: Red moved after Yellow had won
        self.bad(bottom_rows([1, 1, 1, 0, 0, 0, 0], [2, 2, 2, 2, 1, 1, 0]), "moved after")

    def test_fours_must_share_the_last_disc(self):
        # two separate Red fours (bottom row cols 1-4, column 7 vertical):
        # no single top-of-column Red disc completes both
        g = [[0] * 7 for _ in range(6)]
        for c in range(4):
            g[5][c] = 1
        for r in (4, 3, 2, 1):
            g[r][6] = 1
        for r, c in ((5, 4), (5, 5), (5, 6), (4, 0), (4, 1), (4, 2), (3, 0)):
            g[r][c] = 2
        self.assertEqual(sum(v == 1 for row in g for v in row), 8)
        self.assertEqual(sum(v == 2 for row in g for v in row), 7)
        self.bad(g, "could not all have been completed by the last disc")

    def test_genuine_wins_still_accepted(self):
        self.assertEqual(api.game_state(grid([0, 0, 1, 1, 2, 2, 3]))["winner"], 1)
        self.assertEqual(api.game_state(grid([0, 1, 0, 1, 0, 1, 6, 1]))["winner"], 2)
        # one last disc may complete several fours at once (7 in a row)
        g = [[0] * 7 for _ in range(6)]
        g[5] = [1] * 7
        g[4] = [2, 2, 2, 0, 2, 2, 2]
        self.assertEqual(api.game_state(g)["winner"], 1)


class TestEngineArgumentHygiene(unittest.TestCase):
    def test_choose_move_checks_side_to_move(self):
        with self.assertRaises(ValueError) as cm:
            api.choose_move(EMPTY, 2, {"type": "random"})
        self.assertIn("not player 2's turn", str(cm.exception))
        with self.assertRaises(ValueError):
            api.choose_move(grid([3]), 1, "greedy")
        self.assertIn(api.choose_move(grid([3]), 2, "greedy")["column"], range(7))

    def test_apply_move_checks_player(self):
        for bad in (3, 5, -1, 0, "1", True, 1.5):
            with self.assertRaises(ValueError, msg=repr(bad)):
                api.apply_move(EMPTY, 3, bad)
        with self.assertRaises(ValueError) as cm:
            api.apply_move(EMPTY, 3, 2)
        self.assertIn("not player 2's turn", str(cm.exception))
        self.assertEqual(api.apply_move(EMPTY, 3, 1)[0][5][3], 1)
        self.assertEqual(api.apply_move(grid([3]), 3, 2.0)[0][4][3], 2)

    def test_booleans_are_strict(self):
        for key in ("move_ordering", "trace"):
            for bad in ("false", "true", 0, 1, "", []):
                with self.assertRaises(ValueError, msg=f"{key}={bad!r}"):
                    api.normalize_config({"type": "alphabeta", key: bad})
            self.assertFalse(api.normalize_config({"type": "alphabeta", key: False})[key])
            self.assertTrue(api.normalize_config({"type": "alphabeta", key: None})[key])

    def test_openings_follow_integer_policy(self):
        res = api.run_match("greedy", "greedy", games=2, openings=[[3.0, 2]])
        self.assertEqual(res["results"][0]["opening"], [3, 2])
        self.assertIsInstance(res["results"][0]["opening"][0], int)
        for bad in ([[3.5]], [[True]], [["3"]], [[7]], [[-1]]):
            with self.assertRaises(ValueError, msg=repr(bad)):
                api.run_match("greedy", "random", games=2, openings=bad)


class TestRouteHardening(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import app as app_module
        cls.app_module = app_module
        cls.client = app_module.app.test_client()

    def test_deeply_nested_json_is_400(self):
        body = "[" * 50000 + "]" * 50000
        for path in ("/api/state", "/api/apply", "/api/move", "/api/match",
                     "/api/compare-depth", "/api/analyze"):
            for data in (body, '{"board": ' + body + "}"):
                r = self.client.post(path, data=data, content_type="application/json")
                self.assertEqual(r.status_code, 400, path)
                self.assertIn("valid JSON", r.get_json()["error"])

    def test_500_does_not_leak_internals(self):
        mod = self.app_module
        orig = mod.engine_api.game_state

        def boom(board):
            raise RuntimeError("secret internal detail")
        mod.engine_api.game_state = boom
        mod.app.logger.disabled = True
        try:
            r = self.client.post("/api/state", json={"board": EMPTY})
        finally:
            mod.engine_api.game_state = orig
            mod.app.logger.disabled = False
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json(), {"error": "Internal server error."})
        self.assertNotIn("secret", r.get_data(as_text=True))

    def test_impossible_board_is_400(self):
        r = self.client.post("/api/state", json={"board": bottom_rows(
            [2, 2, 2, 0, 0, 0, 0], [1, 1, 1, 1, 0, 0, 2])})
        self.assertEqual(r.status_code, 400)
        self.assertIn("Invalid board", r.get_json()["error"])

    def test_preset_string_matches_engine(self):
        for preset, depth in (("alphabeta", 6), ("minimax", 4)):
            r = self.client.post("/api/move", json={"board": EMPTY, "player": 1,
                                                    "agent": preset})
            self.assertEqual(r.status_code, 200, preset)
            self.assertEqual(r.get_json()["stats"]["depth"], depth, preset)
            self.assertEqual(api.normalize_config(preset)["depth"], depth)
        r = self.client.post("/api/move", json={"board": EMPTY, "player": 1, "agent": "mcts"})
        self.assertEqual(r.get_json()["stats"]["iterations"], 1500)
        r = self.client.post("/api/move", json={"board": EMPTY, "player": 1, "agent": "nope"})
        self.assertEqual(r.status_code, 400)

    def test_preset_descriptions(self):
        data = self.client.get("/api/agents").get_json()
        self.assertIn("baseline policy every other agent must beat", data["random"]["description"])
        self.assertIn("depth-limited heuristic minimax", data["minimax"]["description"].lower())
        self.assertIn("alpha-beta pruning", data["alphabeta"]["description"])
        self.assertIn("same value as Minimax", data["alphabeta"]["description"])
        self.assertIn("UCB1", data["mcts"]["description"])
        self.assertIn("most-visited", data["mcts"]["description"])


if __name__ == "__main__":
    unittest.main()
