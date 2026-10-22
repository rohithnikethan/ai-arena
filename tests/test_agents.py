import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.board import Board  # noqa: E402
from engine.agents import (  # noqa: E402
    RandomAgent, GreedyAgent, MinimaxAgent, AlphaBetaAgent, MCTSAgent, WIN, INF, _Node,
)
from engine.board import threat_cells, playable_cells  # noqa: E402
from engine.evaluate import evaluate  # noqa: E402
from engine import api, tracing  # noqa: E402


def play(moves):
    b = Board()
    for c in moves:
        b.play(c)
    return b


# Red (to move) wins immediately in column 3 (index); Yellow can't win next.
WIN_POS = [0, 6, 1, 6, 2, 5]
# Yellow (to move) must block Red's bottom-row three in column 3.
BLOCK_POS = [0, 6, 1, 6, 2]

TEST_POSITIONS = [
    [],
    [3],
    [3, 3, 2, 4],
    [3, 3, 2, 4, 4, 2, 5, 1, 1, 3],
    [3, 2, 3, 2, 4, 4, 5, 6, 1],
    [0, 1, 2, 3, 4, 5, 6, 0, 1, 2, 3, 4, 5],
    BLOCK_POS,
]


def tree_depth(node):
    if not node["children"]:
        return 0
    return 1 + max(tree_depth(c) for c in node["children"])


def all_agents(seed=7):
    return [GreedyAgent(seed=seed), MinimaxAgent(depth=3), AlphaBetaAgent(depth=4),
            AlphaBetaAgent(depth=4, move_ordering=False), MCTSAgent(iterations=600, seed=seed)]


class TestTactics(unittest.TestCase):
    def test_take_immediate_win(self):
        b = play(WIN_POS)
        for agent in all_agents():
            res = agent.choose(b, b.to_move)
            self.assertEqual(res["column"], 3, msg=agent.kind)
            self.assertEqual(res["state_after"]["winner"], 1, msg=agent.kind)
            self.assertIn("Wins immediately", res["explanation"], msg=agent.kind)
            self.assertIn("column 4", res["explanation"], msg=agent.kind)

    def test_block_immediate_loss(self):
        b = play(BLOCK_POS)
        for agent in all_agents():
            res = agent.choose(b, b.to_move)
            self.assertEqual(res["column"], 3, msg=agent.kind)
            self.assertIn("Blocks Red", res["explanation"], msg=agent.kind)

    def test_mcts_forced_win_in_one(self):
        # vertical threat for Yellow in column 6
        b = play([0, 6, 1, 6, 0, 6, 1])
        self.assertEqual(b.to_move, 2)
        for seed in range(3):
            res = MCTSAgent(iterations=300, seed=seed).choose(b, 2)
            self.assertEqual(res["column"], 6)
            self.assertGreater(res["column_scores"][6], 0.9)
            self.assertEqual(res["column_visits"][6], max(v for v in res["column_visits"] if v is not None))

    def test_minimax_finds_double_threat_win(self):
        # Red: bottom row 1,2 with 0,3,4 open -> playing 3 creates two threats.
        b = play([1, 1, 2, 2])
        res = AlphaBetaAgent(depth=5).choose(b, 1)
        self.assertIn(res["column"], (0, 3))
        self.assertGreaterEqual(max(s for s in res["column_scores"] if s is not None), WIN - 10)
        self.assertIn("forced win", res["explanation"])


class TestSearch(unittest.TestCase):
    def test_alphabeta_matches_minimax(self):
        for moves in TEST_POSITIONS:
            b = play(moves)
            p = b.to_move
            for depth in (1, 2, 3, 4):
                mm = MinimaxAgent(depth=depth).choose(b, p, trace=False)
                for ordering in (True, False):
                    ab = AlphaBetaAgent(depth=depth, move_ordering=ordering).choose(b, p, trace=False)
                    mm_v = max(s for s in mm["column_scores"] if s is not None)
                    ab_v = max(s for s in ab["column_scores"] if s is not None)
                    self.assertEqual(mm_v, ab_v, msg=f"{moves} depth {depth} ordering {ordering}")
                    # chosen move must achieve the minimax value
                    self.assertEqual(mm["column_scores"][ab["column"]], mm_v)
                    if depth >= 3:
                        self.assertLess(ab["stats"]["nodes"], mm["stats"]["nodes"])
                        self.assertGreater(ab["stats"]["pruned"], 0)

    def test_ordering_helps(self):
        b = Board()
        ordered = AlphaBetaAgent(depth=6, move_ordering=True).choose(b, 1, trace=False)
        plain = AlphaBetaAgent(depth=6, move_ordering=False).choose(b, 1, trace=False)
        self.assertLess(ordered["stats"]["nodes"], plain["stats"]["nodes"])

    def test_minimax_node_count_empty_board(self):
        # full-width tree: 1 + 7 + 49 + 343 nodes at depth 3
        res = MinimaxAgent(depth=3).choose(Board(), 1, trace=False)
        self.assertEqual(res["stats"]["nodes"], 400)
        self.assertEqual(res["stats"]["pruned"], 0)
        self.assertEqual(res["stats"]["max_depth_reached"], 3)

    def test_tracing_does_not_change_counts(self):
        b = play([3, 3, 2, 4])
        for agent_factory in (lambda: MinimaxAgent(depth=4), lambda: AlphaBetaAgent(depth=6),
                              lambda: MCTSAgent(iterations=400, seed=1)):
            a = agent_factory().choose(b, 1, trace=True)
            c = agent_factory().choose(b, 1, trace=False)
            self.assertEqual(a["stats"]["nodes"], c["stats"]["nodes"])
            self.assertEqual(a["stats"]["pruned"], c["stats"]["pruned"])
            self.assertEqual(a["column"], c["column"])
            self.assertIsNone(c["tree"])

    def test_tree_cap_and_marks(self):
        b = play([3, 3])
        for agent in (MinimaxAgent(depth=5), AlphaBetaAgent(depth=7),
                      MCTSAgent(iterations=3000, seed=2)):
            res = agent.choose(b, 1)
            tree = res["tree"]
            self.assertLessEqual(tracing.count_nodes(tree), tracing.MAX_NODES)
            self.assertLessEqual(tree_depth(tree), tracing.MAX_PLIES)
            self.assertTrue(tree["best"])
            best_children = [c for c in tree["children"] if c["best"]]
            self.assertEqual(len(best_children), 1)
            self.assertEqual(best_children[0]["move"], res["column"])
            self.assertEqual(res["principal_variation"][0], res["column"])

    def test_pruned_nodes_marked(self):
        res = AlphaBetaAgent(depth=5).choose(play([3, 3, 2, 4]), 1)
        flat = []

        def walk(n):
            flat.append(n)
            for c in n["children"]:
                walk(c)
        walk(res["tree"])
        pruned = [n for n in flat if n["pruned"]]
        self.assertTrue(pruned)
        self.assertTrue(all(not n["children"] for n in pruned))

    def test_mcts_tree_has_visits(self):
        res = MCTSAgent(iterations=500, seed=3).choose(Board(), 1)
        self.assertEqual(res["tree"]["visits"], 500)
        self.assertEqual(sum(v for v in res["column_visits"] if v), 500)
        for s in res["column_scores"]:
            self.assertTrue(0.0 <= s <= 1.0)


class TestDeterminism(unittest.TestCase):
    def test_seeded_agents_repeat(self):
        b = play([3, 2])
        for make in (lambda: RandomAgent(seed=5), lambda: MCTSAgent(iterations=300, seed=5),
                     lambda: GreedyAgent(seed=5)):
            self.assertEqual(make().choose(b, 1)["column"], make().choose(b, 1)["column"])
            self.assertEqual(make().choose(b, 1)["column_visits"],
                             make().choose(b, 1)["column_visits"])

    def test_random_only_legal(self):
        b = play([0] * 6 + [1] * 6)
        agent = RandomAgent(seed=1)
        for _ in range(50):
            self.assertNotIn(agent.choose(b, 1)["column"], (0, 1))


class TestLeafEvaluation(unittest.TestCase):
    """The horizon/parity fix: leaves where the side to move can win at once."""

    def leaf(self, moves, root):
        agent = MinimaxAgent(depth=1)
        agent.b = play(moves)
        agent.root = root
        return agent._leaf_value(5, agent.b.to_move)

    def test_side_to_move_win_is_a_proof_from_either_perspective(self):
        # WIN_POS: Red to move can complete the bottom row in column 4
        self.assertEqual(self.leaf(WIN_POS, root=1), WIN - 6)       # root's own win
        self.assertEqual(self.leaf(WIN_POS, root=2), -(WIN - 6))    # opponent's win
        # BLOCK_POS: Yellow to move has no win; Red's threat is only heuristic
        b = play(BLOCK_POS)
        self.assertEqual(self.leaf(BLOCK_POS, root=1), evaluate(b.bb[1], b.bb[2]))

    def test_static_evaluation_stays_root_perspective(self):
        # quiet leaf: the heuristic is still scored for the root player,
        # whoever is to move (the documented evaluation is unchanged)
        moves = [3, 3, 2, 4]
        b = play(moves)
        self.assertEqual(self.leaf(moves, root=2), evaluate(b.bb[2], b.bb[1]))
        self.assertEqual(self.leaf(moves, root=1), evaluate(b.bb[1], b.bb[2]))

    def test_odd_depth_sees_reply_win(self):
        # Yellow to move must block column 4.  At depth 1 every other move
        # leaves Red a winning reply; that is now scored as a loss in 2 plies
        # instead of a heuristic "-4 for an opponent three".
        b = play(BLOCK_POS)
        for agent in (MinimaxAgent(depth=1), AlphaBetaAgent(depth=1),
                      MinimaxAgent(depth=3)):
            res = agent.choose(b, 2, trace=False)
            self.assertEqual(res["column"], 3)
            for c in range(7):
                if c != 3:
                    self.assertEqual(res["column_scores"][c], -(WIN - 2), f"{agent.kind} {c}")

    def test_threat_cells_match_slow_check(self):
        import random
        rng = random.Random(4)
        for _ in range(300):
            b = Board()
            for _ in range(rng.randrange(0, 30)):
                b.play(rng.choice(b.valid_moves()))
                if b.winner():
                    break
            if b.winner() or b.is_full():
                continue
            for p in (1, 2):
                fast = threat_cells(b.bb[p]) & playable_cells(b.bb[1] | b.bb[2])
                slow = sum(1 << b.heights[c] for c in b.winning_moves(p))
                self.assertEqual(fast, slow)

    def test_regression_alphabeta_beats_greedy_at_every_depth(self):
        # Before the fix Greedy as Red beat Alpha-Beta at depths 1, 3 and 5
        # from the empty board (one replayed game), and AB-1 lost to Greedy
        # from random openings.  Now Alpha-Beta never loses this pair of games.
        for depth in range(2, 8):
            r = api.run_match({"type": "greedy"}, {"type": "alphabeta", "depth": depth},
                              games=2, seed=3)
            self.assertEqual(r["a_wins"], 0, f"depth {depth}")
        r = api.run_match({"type": "greedy"}, {"type": "alphabeta", "depth": 3},
                          games=20, seed=0, opening_plies=2)
        self.assertGreaterEqual(r["b_wins"] + 0.5 * r["draws"], 16)


class TestBoundFlags(unittest.TestCase):
    """TreeNode["bound"]: "upper"/"lower" for fail-low/fail-high values."""

    DEPTH = 5

    def exact(self, root_board, root, path):
        """Full-window (exact) value of the node reached by ``path``."""
        agent = AlphaBetaAgent(depth=self.DEPTH)
        agent.b = b = root_board.copy()
        agent.root = root
        agent.nodes = agent.pruned = agent.max_ply = 0
        agent.cache = {}
        for c in path:
            b.play(c)
        v, _ = agent._search(len(path), self.DEPTH - len(path), b.to_move, -INF, INF, None)
        return v

    def test_bounds_are_honest(self):
        kinds = set()
        for moves in ([3, 3, 2, 4], [3, 2, 3, 2, 4, 4, 5, 6, 1], []):
            b = play(moves)
            root = b.to_move
            res = AlphaBetaAgent(depth=self.DEPTH).choose(b, root)

            def walk(node, path):
                for ch in node["children"]:
                    p = path + [ch["move"]]
                    if ch["pruned"] or ch["terminal"] or ch["value"] is None:
                        self.assertIsNone(ch["bound"])
                    elif len(p) < self.DEPTH:
                        exact = self.exact(b, root, p)
                        kinds.add(ch["bound"])
                        if ch["bound"] == "upper":
                            self.assertLessEqual(exact, ch["value"])
                        elif ch["bound"] == "lower":
                            self.assertGreaterEqual(exact, ch["value"])
                        else:
                            self.assertEqual(exact, ch["value"], p)
                    walk(ch, p)
            walk(res["tree"], [])
            chosen = [ch for ch in res["tree"]["children"] if ch["best"]][0]
            self.assertIsNone(chosen["bound"])
        self.assertTrue({"upper", "lower", None} <= kinds, kinds)

    def test_minimax_and_mcts_never_flag_bounds(self):
        b = play([3, 3, 2, 4])
        for agent in (MinimaxAgent(depth=3), MCTSAgent(iterations=200, seed=1)):
            flat = [agent.choose(b, 1)["tree"]]
            while flat:
                n = flat.pop()
                self.assertIsNone(n["bound"])
                flat.extend(n["children"])


class TestMCTSExplanation(unittest.TestCase):
    def node(self, move, visits, wins):
        n = _Node(move, None, 1, [], 0, False, 1)
        n.visits, n.wins = visits, wins
        return n

    def explain(self, *stats):
        agent = MCTSAgent(iterations=1500)
        ranked = sorted((self.node(*s) for s in stats), key=agent._rank_key, reverse=True)
        return ranked[0].move, agent._explain(Board(), 1, ranked)

    def test_runner_up(self):
        col, text = self.explain((3, 900, 500.0), (4, 600, 300.0))
        self.assertEqual(col, 3)
        self.assertIn("column 4 (900 visits, 56% win rate); runner-up column 5 (600 visits, 50%)",
                      text)

    def test_tie_broken_by_win_rate(self):
        col, text = self.explain((4, 750, 15.0), (6, 750, 16.0))
        self.assertEqual(col, 6)
        self.assertIn("column 7 is tied for most visits with column 5 (750 each)", text)
        self.assertIn("broken by the higher win rate (16 vs 15 simulated wins", text)
        self.assertNotIn("runner-up", text)

    def test_tie_broken_by_center(self):
        col, text = self.explain((6, 750, 15.0), (2, 750, 15.0))
        self.assertEqual(col, 2)                      # column 3 is more central than 7
        self.assertIn("the same win rate (2%)", text)
        self.assertIn("preferring the more central column, column 3", text)


if __name__ == "__main__":
    unittest.main()
