import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.board import Board  # noqa: E402
from engine.agents import (  # noqa: E402
    RandomAgent, GreedyAgent, MinimaxAgent, AlphaBetaAgent, MCTSAgent, WIN,
)
from engine import tracing  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
