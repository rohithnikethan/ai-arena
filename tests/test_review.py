import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import api, review  # noqa: E402
from engine.agents import AlphaBetaAgent, MinimaxAgent, WIN  # noqa: E402
from engine.board import Board  # noqa: E402


def board_from(moves):
    b = Board()
    for c in moves:
        b.play(c)
    return b


# Red has 0-1-2 on the bottom row, Yellow 0-1-2 on the row above.
# Red to move can win in column 4 (index 3); so could Yellow next turn.
THREE_VS_THREE = [0, 0, 1, 1, 2, 2]


class TestMateHelpers(unittest.TestCase):
    def test_moves_to_win(self):
        self.assertEqual(review.moves_to_win(WIN - 1), 1)   # win on ply 1
        self.assertEqual(review.moves_to_win(WIN - 3), 2)   # win on ply 3 = 2nd own move
        self.assertEqual(review.moves_to_win(WIN - 5), 3)
        self.assertEqual(review.moves_to_win(-(WIN - 2)), 1)  # opponent wins on ply 2
        self.assertEqual(review.moves_to_win(-(WIN - 4)), 2)
        self.assertIsNone(review.moves_to_win(37))
        self.assertIsNone(review.moves_to_win(-37))

    def test_red_eval_labels(self):
        self.assertEqual(review.red_eval(WIN - 3, 1)["label"], "Red wins in 2 moves")
        self.assertEqual(review.red_eval(WIN - 3, 1)["mate"], 2)
        # Yellow to move and winning: from Red's view that is Yellow winning
        e = review.red_eval(WIN - 1, 2)
        self.assertEqual((e["mate"], e["label"]), (-1, "Yellow wins in 1 move"))
        e = review.red_eval(-(WIN - 4), 2)   # Yellow to move, Red mates in 2
        self.assertEqual((e["mate"], e["label"]), (2, "Red wins in 2 moves"))
        self.assertEqual(review.red_eval(7, 2)["score"], -7)


class TestClassify(unittest.TestCase):
    def test_equal_is_best(self):
        self.assertEqual(review.classify(12.0, 12.0), ("best", []))
        self.assertEqual(review.classify(WIN - 3, WIN - 3), ("best", []))

    def test_thresholds(self):
        g, i, m = review.GOOD_MAX_LOSS, review.INACCURACY_MAX_LOSS, review.MISTAKE_MAX_LOSS
        self.assertEqual(review.classify(10, 10 - g)[0], "good")
        self.assertEqual(review.classify(10, 10 - g - 1)[0], "inaccuracy")
        self.assertEqual(review.classify(10, 10 - i)[0], "inaccuracy")
        self.assertEqual(review.classify(10, 10 - i - 1)[0], "mistake")
        self.assertEqual(review.classify(10, 10 - m)[0], "mistake")
        self.assertEqual(review.classify(10, 10 - m - 1)[0], "blunder")

    def test_slower_win_is_not_a_blunder(self):
        self.assertEqual(review.classify(WIN - 1, WIN - 5), ("good", []))

    def test_missed_win(self):
        self.assertEqual(review.classify(WIN - 3, 4), ("blunder", ["missed_win"]))
        self.assertEqual(review.classify(WIN - 1, -(WIN - 2)),
                         ("blunder", ["missed_win", "allowed_forced_loss"]))

    def test_allowed_forced_loss(self):
        self.assertEqual(review.classify(-3, -(WIN - 6)), ("blunder", ["allowed_forced_loss"]))

    def test_already_lost_position(self):
        # every move loses; losing sooner is only an inaccuracy and gets no tag
        self.assertEqual(review.classify(-(WIN - 6), -(WIN - 2)), ("inaccuracy", []))
        self.assertEqual(review.classify(-(WIN - 6), -(WIN - 6)), ("best", []))


class TestExactValues(unittest.TestCase):
    POSITIONS = [[], [3], [3, 3, 2], [3, 2, 4, 4, 2, 3], [0, 6, 1, 6, 2],
                 [3, 3, 3, 3, 2, 4, 1], THREE_VS_THREE]

    def test_match_plain_minimax_for_every_move(self):
        """Every root value equals plain minimax's (which never prunes)."""
        for moves in self.POSITIONS:
            b = board_from(moves)
            for d in (1, 2, 3, 4):
                exact, _ = review.exact_move_values(b, b.to_move, d)
                mm = MinimaxAgent(depth=d).choose(b, b.to_move, trace=False)
                self.assertEqual(exact, mm["column_scores"], f"{moves} depth {d}")

    def test_alphabeta_root_scores_are_bounds(self):
        """Sanity check that the problem is real: at least one alpha-beta root
        score differs from the exact value, and never by being too low."""
        differs = False
        for moves in self.POSITIONS:
            b = board_from(moves)
            exact, _ = review.exact_move_values(b, b.to_move, 4)
            ab = AlphaBetaAgent(depth=4).choose(b, b.to_move, trace=False)["column_scores"]
            for e, a in zip(exact, ab):
                if e is None:
                    self.assertIsNone(a)
                    continue
                self.assertGreaterEqual(a, e)  # fail-low values are upper bounds
                differs = differs or a != e
        self.assertTrue(differs)

    def test_review_values_are_exact(self):
        moves = [3, 2, 4, 4, 2, 3]
        res = api.analyze_game(moves, depth=4)
        for i, m in enumerate(res["moves"]):
            b = board_from(moves[:i])
            mm = MinimaxAgent(depth=4).choose(b, b.to_move, trace=False)
            self.assertEqual(m["values"], mm["column_scores"])
            self.assertEqual(m["played_value"], mm["column_scores"][m["column"]])
            self.assertEqual(m["best_value"], max(v for v in m["values"] if v is not None))


class TestAnalyzeGame(unittest.TestCase):
    def test_missed_immediate_win_flagged(self):
        res = api.analyze_game(THREE_VS_THREE + [6, 3])
        red = res["moves"][6]
        self.assertEqual(red["column"], 6)
        self.assertEqual(red["best_column"], 3)
        self.assertEqual(red["best_value"], WIN - 1)
        self.assertEqual(red["tags"], ["missed_win"])
        self.assertEqual(red["badge"], "blunder")
        self.assertEqual(red["reason"], "Column 4 wins immediately.")
        # depth 7 + the consistency re-search (up to 6 more plies) found nothing:
        # the comment states the deepest horizon actually checked
        self.assertEqual(red["comment"], "Misses an immediate win with column 4; after column 7 "
                                         "no forced win for Red was found within 14 plies.")
        yellow = res["moves"][7]                 # Yellow blocks the bottom row
        self.assertEqual(yellow["badge"], "best")
        self.assertIn("blocks Red's", yellow["reason"])
        self.assertEqual(res["evals"][6]["label"], "Red wins in 1 move")
        self.assertEqual(res["summary"]["1"]["missed_win"], 1)
        self.assertEqual(res["summary"]["1"]["blunder"], 1)

    def test_missed_win_and_allowed_loss(self):
        # Red threatens 0-1-2-(3) on the bottom row, Yellow has three stacked in
        # column 7.  Red plays column 6 instead: misses its win and lets Yellow win.
        res = api.analyze_game([0, 6, 1, 6, 2, 6, 5, 6])
        red = res["moves"][6]
        self.assertEqual(red["tags"], ["missed_win", "allowed_forced_loss"])
        self.assertEqual(red["badge"], "blunder")
        self.assertEqual(red["played_value"], -(WIN - 2))
        self.assertIn("lets Yellow force a win instead", red["comment"])
        self.assertEqual(res["moves"][7]["badge"], "best")
        self.assertEqual(res["moves"][7]["comment"], "Column 7 wins the game.")
        self.assertEqual(res["result"], {"winner": 2, "draw": False, "finished": True})
        self.assertEqual(res["evals"][7]["label"], "Yellow wins in 1 move")
        self.assertEqual(res["evals"][-1]["label"], "Yellow won")
        self.assertEqual(res["summary"]["1"]["allowed_forced_loss"], 1)

    def test_blunder_allowing_forced_loss(self):
        # Red threatens 0-1-2-(3); Yellow ignores it and plays column 6
        res = api.analyze_game([0, 6, 1, 6, 2, 5])
        y = res["moves"][5]
        self.assertEqual(y["player"], 2)
        self.assertEqual(y["badge"], "blunder")
        self.assertEqual(y["tags"], ["allowed_forced_loss"])
        self.assertEqual(review.moves_to_win(y["played_value"]), 1)
        self.assertEqual(y["best_column"], 3)
        self.assertIn("blocks Red's", y["reason"])
        self.assertIn("lets Red win immediately in column 4", y["comment"])
        self.assertEqual(res["evals"][-1]["mate"], 1)       # Red wins in 1
        self.assertFalse(res["result"]["finished"])

    def test_best_moves_flagged_best(self):
        moves = api.run_match({"type": "alphabeta", "depth": 3}, {"type": "random"},
                              games=1, seed=4)["results"][0]["moves"]
        res = api.analyze_game(moves, depth=5)
        self.assertEqual(len(res["evals"]), len(moves) + 1)
        for m in res["moves"]:
            self.assertEqual(m["badge"] == "best", m["played_value"] == m["best_value"])
            self.assertIn(m["best_column"], m["best_columns"])
            if m["column"] in m["best_columns"]:
                self.assertEqual(m["badge"], "best")
                self.assertEqual(m["best_column"], m["column"])
            if m["loss"] is not None:
                self.assertGreaterEqual(m["loss"], 0)
        for p in ("1", "2"):
            s = res["summary"][p]
            self.assertEqual(sum(s[k] for k in review.BADGES), s["moves"])
        self.assertEqual(res["summary"]["1"]["moves"] + res["summary"]["2"]["moves"], len(moves))

    def test_winning_move_is_best(self):
        res = api.analyze_game(THREE_VS_THREE + [3])
        self.assertEqual(res["moves"][6]["badge"], "best")
        self.assertEqual(res["moves"][6]["comment"], "Column 4 wins the game.")
        self.assertEqual(res["evals"][-1], {"ply": 7, "score": WIN, "mate": 0,
                                            "label": "Red won", "raw": WIN})

    def test_graph_smoothing_keeps_proofs(self):
        res = api.analyze_game([3, 3, 2, 4, 2, 2, 1], depth=5)
        for e in res["evals"]:
            if e["mate"] is None:
                self.assertLess(abs(e["score"]), review.MATE)
            else:
                self.assertEqual(e["score"], e["raw"])

    def test_depth_clamped(self):
        self.assertEqual(api.analyze_game([3], depth=99)["depth"], review.REVIEW_DEPTH_RANGE[1])
        self.assertEqual(api.analyze_game([3], depth=0)["depth"], 1)

    def test_validation(self):
        for moves, frag in (([], "at least one"), ("33", "list"), ([3, "4"], "integer"),
                            ([True], "integer"), ([7], "0-6"), ([-1], "0-6"),
                            ([3] * 7, "full"),
                            ([0, 1, 0, 1, 0, 1, 0, 2], "after the game")):
            with self.assertRaises(ValueError) as cm:
                api.analyze_game(moves)
            self.assertIn(frag, str(cm.exception))
        with self.assertRaises(ValueError):
            api.analyze_game([3], depth="deep")


# Greedy (Red) vs Alpha-Beta depth 5 (before the leaf fix), found by QA: at
# ply 19 Red keeps a forced win in 5 moves with column 5, one ply beyond what
# a depth-6 search of the position can prove.
KEPT_WIN_GAME = [3, 3, 4, 2, 4, 3, 4, 4, 3, 2, 1, 2, 2, 6, 3, 3, 2, 2, 4, 4, 1, 1, 1, 1, 1]


class TestMissedWinHorizon(unittest.TestCase):
    def test_graded_value(self):
        # best is a proven win, the played move is heuristic, but the next
        # position is proven lost for the opponent -> the move kept the win
        self.assertEqual(review.graded_value(WIN - 7, 24.0, -(WIN - 8)), WIN - 9)
        self.assertEqual(review.graded_value(WIN - 7, 24.0, -3.0), 24.0)
        self.assertEqual(review.graded_value(WIN - 7, 24.0, None), 24.0)
        # best not a proven win: the move still wins (regression: was 4.0, an
        # "Inaccuracy" while the next row said the opponent is lost)
        self.assertEqual(review.graded_value(12.0, 4.0, -(WIN - 8)), WIN - 9)
        self.assertEqual(review.graded_value(12.0, WIN - 3, -(WIN - 8)), WIN - 3)  # already proven
        # mirror: the next position is a proven win for the opponent
        self.assertEqual(review.graded_value(12.0, 4.0, WIN - 8), -(WIN - 9))
        self.assertEqual(review.classify(WIN - 7, WIN - 9), ("good", []))

    def test_kept_win_is_not_missed(self):
        res = api.analyze_game(KEPT_WIN_GAME, depth=7)
        m = res["moves"][18]
        self.assertEqual((m["ply"], m["player"], m["column"]), (19, 1, 4))
        self.assertLess(abs(m["played_value"]), review.MATE)    # depth-7 value: heuristic
        self.assertEqual(m["graded_value"], WIN - 9)            # next position: Red wins
        self.assertNotIn("missed_win", m["tags"])
        self.assertEqual(m["badge"], "good")
        self.assertEqual(m["comment"], "Still winning, but slower: 5 moves instead of 4.")
        nxt = res["moves"][19]
        self.assertIn("Loses sooner", nxt["comment"])
        self.assertEqual(res["summary"]["1"]["missed_win"], 0)

    def test_unproven_missed_win_is_worded_honestly(self):
        # at depth 5 neither this position nor the next can see Red's win,
        # so the tag stays, but the comment says what was actually checked
        # (consistency re-search switched off; see test_research_resolves_missed_win)
        res = review.analyze_game(KEPT_WIN_GAME, depth=6, research_plies=0)
        m = res["moves"][18]
        self.assertEqual(m["tags"], ["missed_win"])
        self.assertEqual(m["comment"], "Misses a forced win in 4 moves with column 2; after "
                                       "column 5 no forced win for Red was found within 7 plies.")

    def test_research_resolves_missed_win(self):
        # with the default re-search, the position after column 5 is searched
        # deeper, proves Yellow lost, and the move is graded as a slower win
        res = api.analyze_game(KEPT_WIN_GAME, depth=6)
        m = res["moves"][18]
        self.assertEqual(m["tags"], [])
        self.assertEqual(m["badge"], "good")
        self.assertEqual(m["graded_value"], WIN - 9)
        self.assertEqual(m["comment"], "Still winning, but slower: 5 moves instead of 4.")
        nxt = res["moves"][19]
        self.assertTrue(review.is_loss(nxt["best_value"]))
        self.assertNotIn("allowed_forced_loss", nxt["tags"])

    def test_missed_win_never_contradicts_next_row(self):
        for depth in (4, 5, 6, 7):
            res = api.analyze_game(KEPT_WIN_GAME, depth=depth)
            for i, m in enumerate(res["moves"][:-1]):
                if "missed_win" in m["tags"]:
                    nxt = res["moves"][i + 1]
                    self.assertFalse(review.is_loss(nxt["best_value"]), f"depth {depth} ply {i + 1}")

    def test_graded_equals_played_otherwise(self):
        res = api.analyze_game([3, 2, 4, 4, 2, 3], depth=4)
        for m in res["moves"]:
            self.assertEqual(m["graded_value"], m["played_value"])

    def test_integral_floats_accepted(self):
        a = api.analyze_game([3.0, 3, 2.0], depth=4.0)
        b = api.analyze_game([3, 3, 2], depth=4)
        self.assertEqual(a["moves"], b["moves"])
        for bad in (["3"], [3.5]):
            with self.assertRaises(ValueError):
                api.analyze_game(bad)
        for bad in ("4", 4.5, True):
            with self.assertRaises(ValueError):
                api.analyze_game([3], depth=bad)


class TestAnalyzeRoute(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import app as app_module
        cls.client = app_module.app.test_client()

    def post(self, body):
        return self.client.post("/api/analyze", json=body)

    def test_ok(self):
        r = self.post({"moves": THREE_VS_THREE + [6, 3], "depth": 4})
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertEqual(data["depth"], 4)
        self.assertEqual(len(data["moves"]), 8)
        self.assertEqual(data["moves"][6]["badge"], "blunder")

    def test_integral_floats(self):
        r = self.post({"moves": [3.0, 3], "depth": 3.0})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["depth"], 3)

    def test_depth_clamped(self):
        self.assertEqual(self.post({"moves": [3], "depth": 50}).get_json()["depth"], 8)
        self.assertEqual(self.post({"moves": [3], "depth": -2}).get_json()["depth"], 1)

    def test_bad_input(self):
        cases = [
            {"moves": "3,3"}, {"moves": []}, {}, {"moves": [3, 3.5]},
            {"moves": [3, True]}, {"moves": [3, 9]}, {"moves": [3] * 7},
            {"moves": [0, 1, 0, 1, 0, 1, 0, 2]}, {"moves": [3], "depth": "x"},
            {"moves": [3] * 43}, {"moves": ["3"]}, {"moves": [3], "depth": "3"},
            {"moves": [3], "depth": 3.5}, {"moves": [3], "depth": 1e308},
        ]
        for body in cases:
            r = self.post(body)
            self.assertEqual(r.status_code, 400, body)
            self.assertIn("error", r.get_json())
        r = self.client.post("/api/analyze", data="nope", content_type="application/json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("after the game", self.post({"moves": [0, 1, 0, 1, 0, 1, 0, 2]}).get_json()["error"])


# Audit repro (bug 3): ply 30, Yellow column 1 wins (exact solver: winning
# disc 38, i.e. 5 Yellow moves; column 7 wins equally fast) one ply past
# what the depth-7 search of that position sees; ply 31 proves Red lost.
WIN_PAST_HORIZON_GAME = [4, 1, 3, 5, 4, 4, 3, 5, 5, 4, 1, 6, 1, 4, 4, 3, 3, 5, 1, 1, 3, 3,
                         5, 0, 0, 1, 5, 0, 0, 0, 0, 6, 6, 6, 6, 6, 2, 2]
# Audit repro (bug 4), reviewed at depth 5: ply 29 Red column 7 still wins
# (solver: disc 37, 5 Red moves) and ply 30's position is already lost for
# Yellow (solver: best defence column 2 loses at disc 37, 4 Red moves; the
# played column 7 at disc 35, 3 Red moves).
HORIZON_PAIR_GAME = [2, 3, 3, 3, 3, 2, 2, 2, 3, 5, 6, 5, 2, 3, 5, 2, 6, 1, 1, 0, 1, 4, 4,
                     5, 5, 5, 6, 6, 6, 6, 0, 1, 1, 1, 0, 4, 4]


class TestConsistency(unittest.TestCase):
    def test_win_past_horizon_is_best_not_inaccuracy(self):
        res = api.analyze_game(WIN_PAST_HORIZON_GAME, depth=7)
        m = res["moves"][29]
        self.assertEqual((m["ply"], m["player"], m["column"]), (30, 2, 0))
        self.assertLess(abs(m["played_value"]), review.MATE)   # depth-7 value: heuristic
        self.assertEqual(m["graded_value"], WIN - 9)
        self.assertEqual(m["best_value"], WIN - 9)              # raised to the proven win
        self.assertEqual((m["badge"], m["tags"]), ("best", []))
        self.assertEqual(m["best_columns"], [0])
        self.assertIsNone(m["loss"])
        self.assertEqual(m["reason"], "Column 1 forces a win in 5 moves whatever Red does.")
        self.assertEqual(m["comment"], "Best move: Yellow forces a win in 5 moves "
                                       "(proven by the deeper search of the next position).")
        self.assertEqual(res["evals"][29]["mate"], -5)          # graph agrees
        self.assertTrue(review.is_loss(res["moves"][30]["best_value"]))

    def test_horizon_pair_resolved_by_research(self):
        res = api.analyze_game(HORIZON_PAIR_GAME, depth=5)
        red, yellow = res["moves"][28], res["moves"][29]
        self.assertEqual((red["ply"], red["column"], yellow["column"]), (29, 6, 6))
        self.assertEqual(red["tags"], [])                       # was missed_win
        self.assertEqual(red["badge"], "good")
        self.assertEqual(red["graded_value"], WIN - 9)
        self.assertEqual(red["comment"], "Still winning, but slower: 5 moves instead of 3.")
        self.assertEqual(yellow["tags"], [])                    # was allowed_forced_loss
        self.assertEqual(yellow["badge"], "inaccuracy")
        self.assertEqual(yellow["best_value"], -(WIN - 8))
        self.assertEqual(yellow["comment"], "Loses sooner (Red needs 3 moves instead of 4).")
        self.assertIn("deeper 7-ply search", yellow["reason"])

    def test_research_off_keeps_depth_limited_tags(self):
        res = review.analyze_game(HORIZON_PAIR_GAME, depth=5, research_plies=0)
        self.assertEqual(res["moves"][28]["tags"], ["missed_win"])
        self.assertEqual(res["moves"][29]["tags"], ["allowed_forced_loss"])
        # a zero node budget behaves the same
        res = review.analyze_game(HORIZON_PAIR_GAME, depth=5, research_nodes=0)
        self.assertEqual(res["moves"][28]["tags"], ["missed_win"])

    def test_prove_gives_exact_distance(self):
        # position before ply 30 of HORIZON_PAIR_GAME: Yellow to move is lost,
        # Red's fastest forced win lands 8 plies later (solver: disc 37)
        b = board_from(HORIZON_PAIR_GAME[:29])
        v, d, _ = review._prove(b, 2, 0, 6, 9, False, [10 ** 7])
        self.assertEqual(v, -(WIN - 8))
        self.assertEqual(d, 7)
        self.assertEqual(review._prove(b, 2, 0, 6, 6, False, [10 ** 7])[0], None)  # too shallow
        self.assertEqual(review._prove(b, 2, 0, 6, 9, False, [10])[0], None)       # out of budget

    def test_rows_never_contradict(self):
        games = (WIN_PAST_HORIZON_GAME, HORIZON_PAIR_GAME, KEPT_WIN_GAME,
                 THREE_VS_THREE + [6, 3], [3, 3, 5, 2, 3, 2, 2, 1, 2, 5, 6, 4, 4])
        for g in games:
            for depth in (3, 4, 5, 6, 7):
                rows = api.analyze_game(g, depth=depth)["moves"]
                for i, m in enumerate(rows):
                    where = f"{g[:4]}... depth {depth} ply {m['ply']}"
                    self.assertGreaterEqual(m["best_value"], m["graded_value"], where)
                    if i + 1 < len(rows):
                        nb = rows[i + 1]["best_value"]
                        self.assertEqual(review.is_loss(nb), review.is_win(m["graded_value"]), where)
                        if "missed_win" in m["tags"]:
                            self.assertFalse(review.is_loss(nb), where)
                    if "allowed_forced_loss" in m["tags"]:
                        self.assertFalse(review.is_loss(m["best_value"]), where)
                        if i:
                            self.assertFalse(review.is_win(rows[i - 1]["graded_value"]), where)


if __name__ == "__main__":
    unittest.main()
