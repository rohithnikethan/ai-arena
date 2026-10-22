"""Game-playing agents for Connect Four.

Every agent exposes ``choose(board, player, trace=True)`` taking an internal
:class:`~engine.board.Board` and returning the full ``choose_move`` result
dict described in SPEC.md::

    {"column", "board_after", "state_after", "column_scores", "column_visits",
     "stats", "explanation", "principal_variation", "tree"}

Agents:

* :class:`RandomAgent`    - uniformly random legal move (seedable).
* :class:`GreedyAgent`    - win now > block the opponent's win > best 1-ply heuristic.
* :class:`MinimaxAgent`   - plain depth-limited minimax, no pruning.
* :class:`AlphaBetaAgent` - minimax with alpha-beta pruning, optional center-first ordering.
* :class:`MCTSAgent`      - UCT Monte Carlo Tree Search (c = sqrt(2)), seedable.

Search values are from the root player's perspective: a win found ``k``
plies below the root is worth ``1_000_000 - k`` (faster wins score higher), a
loss ``-(1_000_000 - k)``, a draw 0, and the heuristic in
:mod:`engine.evaluate` otherwise.  At the depth limit, a leaf whose side to
move can win immediately is scored as that (proven) win or loss one ply
later instead of heuristically; see :meth:`MinimaxAgent._leaf_value`.
"""

import math
import random
import time

from .board import (COLS, COL_LIMIT, CENTER_ORDER, PLAYER_NAMES, has_four,
                    threat_cells, playable_cells)
from .evaluate import evaluate
from . import tracing

WIN = 1_000_000
INF = 10 ** 12
NATURAL_ORDER = tuple(range(COLS))


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def col_name(c):
    """Human-facing, 1-indexed column label."""
    return f"column {c + 1}"


def fmt_score(v):
    if v is None:
        return "n/a"
    if v >= WIN - 100:
        return f"win in {WIN - int(v)} plies"
    if v <= -(WIN - 100):
        return f"loss in {WIN + int(v)} plies"
    return f"{v:+.0f}"


def _stats(nodes, pruned, elapsed, depth, iterations, max_depth):
    ms = elapsed * 1000.0
    return {
        "nodes": int(nodes),
        "pruned": int(pruned),
        "time_ms": round(ms, 3),
        "nodes_per_sec": int(nodes / elapsed) if elapsed > 0 else int(nodes),
        "depth": depth,
        "iterations": iterations,
        "max_depth_reached": int(max_depth),
    }


def tactical_reason(board, player, col):
    """Describe the immediate tactical meaning of ``player`` playing ``col``.

    Returns a sentence or None.  Checked in priority order: immediate win,
    blocking an opponent's immediate win, creating a double threat, creating
    a single threat.
    """
    me, opp = PLAYER_NAMES[player], PLAYER_NAMES[3 - player]
    if board.is_winning_move(col, player):
        return f"Wins immediately: {col_name(col)} completes four in a row for {me}."
    opp_wins = board.winning_moves(3 - player)
    if col in opp_wins:
        others = [c for c in opp_wins if c != col]
        s = f"Blocks {opp}'s immediate threat in {col_name(col)}."
        if others:
            s += (f" {opp} still threatens " + ", ".join(col_name(c) for c in others)
                  + ", so the position is critical.")
        return s
    b = board.copy()
    b.play(col, player)
    my_threats = b.winning_moves(player)
    opp_next = b.winning_moves(3 - player)
    if len(my_threats) >= 2 and not opp_next:
        cols = " and ".join(col_name(c) for c in my_threats)
        return (f"Sets up a double threat: {me} now threatens to win in {cols}, "
                f"and {opp} can only block one.")
    if opp_next:
        return None  # the move allows a reply win; let the search text speak
    if my_threats:
        return f"Creates a threat: {me} threatens to win next in {col_name(my_threats[0])}."
    return None


def _finish(board, player, col, scores, visits, stats, explanation, pv, tree):
    after = board.copy()
    after.play(col, player)
    return {
        "column": int(col),
        "board_after": after.to_grid(),
        "state_after": after.state(),
        "column_scores": scores,
        "column_visits": visits,
        "stats": stats,
        "explanation": explanation,
        "principal_variation": [int(c) for c in pv],
        "tree": tree,
    }


def _flat_tree(board, player, scores, chosen, visits=None):
    """One-ply tree for the simple agents (root + one child per legal move)."""
    root = tracing.make_node("root", None, player)
    for c in board.valid_moves():
        ch = tracing.make_node(f"root.{c}", c, player)
        ch["value"] = scores[c]
        ch["terminal"] = board.is_winning_move(c, player) or board.moves + 1 >= 42
        if visits is not None:
            ch["visits"] = visits[c]
        root["children"].append(ch)
    tracing.mark_line(root, [chosen])
    root["value"] = scores[chosen]
    return root


# --------------------------------------------------------------------------
# Random
# --------------------------------------------------------------------------
class RandomAgent:
    """Picks a uniformly random legal column. Deterministic for a given seed."""

    kind = "random"

    def __init__(self, seed=None):
        self.rng = random.Random(seed)

    def choose(self, board, player, trace=True):
        t0 = time.perf_counter()
        moves = board.valid_moves()
        col = self.rng.choice(moves)
        elapsed = time.perf_counter() - t0
        scores = [None] * COLS
        tac = tactical_reason(board, player, col)
        expl = (f"Picked {col_name(col)} uniformly at random from {len(moves)} legal moves"
                " - no lookahead at all.")
        if tac:
            expl += f" By luck: {tac[0].lower() + tac[1:]}"
        tree = None
        if trace:
            tree = tracing.make_node("root", None, player)
            for c in moves:
                ch = tracing.make_node(f"root.{c}", c, player)
                root_child_best = c == col
                ch["best"] = root_child_best
                tree["children"].append(ch)
            tree["best"] = True
        return _finish(board, player, col, scores, [None] * COLS,
                       _stats(len(moves), 0, elapsed, None, None, 1),
                       expl, [col], tree)


# --------------------------------------------------------------------------
# Greedy
# --------------------------------------------------------------------------
class GreedyAgent:
    """One-ply tactician: win now > block the opponent's win > best heuristic.

    ``column_scores`` holds the heuristic value of the position after each
    move (``1_000_000 - 1`` for an immediate win).  Ties are broken at random
    (seedable), preferring central columns when the RNG is unseeded-equal.
    """

    kind = "greedy"

    def __init__(self, seed=None):
        self.rng = random.Random(seed)

    def choose(self, board, player, trace=True):
        t0 = time.perf_counter()
        opp = 3 - player
        moves = board.valid_moves()
        scores = [None] * COLS
        nodes = 0
        b = board.copy()
        wins, blocks = [], board.winning_moves(opp)
        for c in moves:
            nodes += 1
            b.play(c, player)
            if has_four(b.bb[player]):
                scores[c] = float(WIN - 1)
                wins.append(c)
            elif b.moves >= 42:
                scores[c] = 0.0
            else:
                scores[c] = float(evaluate(b.bb[player], b.bb[opp]))
            b.undo(c, player)
        if wins:
            col = wins[0]
            reason = "win"
        elif blocks:
            col = max(blocks, key=lambda c: scores[c])
            reason = "block"
        else:
            best = max(scores[c] for c in moves)
            cands = [c for c in moves if scores[c] == best]
            col = self.rng.choice(cands)
            reason = "heur"
        elapsed = time.perf_counter() - t0
        tac = tactical_reason(board, player, col)
        if reason == "heur":
            expl = (f"{tac + ' ' if tac else ''}Greedy one-move lookahead: {col_name(col)} "
                    f"gives the best heuristic score ({fmt_score(scores[col])}) among "
                    f"{len(moves)} legal moves.")
        else:
            expl = tac or f"Plays {col_name(col)}."
        tree = _flat_tree(board, player, scores, col) if trace else None
        return _finish(board, player, col, scores, [None] * COLS,
                       _stats(nodes, 0, elapsed, 1, None, 1), expl, [col], tree)


# --------------------------------------------------------------------------
# Minimax / Alpha-beta
# --------------------------------------------------------------------------
class MinimaxAgent:
    """Plain depth-limited minimax (no pruning).

    ``stats.nodes`` counts every position visited, including the root and
    terminal (won) positions.  Leaf values (immediate-win check, then the
    heuristic) are memoised per search by position, which saves time but does
    not change the node count.
    """

    kind = "minimax"
    prune = False

    def __init__(self, depth=4, move_ordering=False):
        self.depth = max(1, int(depth))
        self.order = CENTER_ORDER if move_ordering else NATURAL_ORDER

    # -- core recursive search ------------------------------------------------
    def _search(self, ply, depth, to_play, alpha, beta, tnode):
        self.nodes += 1
        if ply > self.max_ply:
            self.max_ply = ply
        b = self.b
        root = self.root
        if depth == 0:
            me, op = b.bb[root], b.bb[3 - root]
            k = (me << 64) | op
            v = self.cache.get(k)
            if v is None:
                v = self._leaf_value(ply, to_play)
                self.cache[k] = v
            return v, []
        heights = b.heights
        moves = [c for c in self.order if heights[c] < COL_LIMIT[c]]
        if not moves:
            return 0, []
        maximizing = to_play == root
        best = -INF if maximizing else INF
        best_pv = []
        prune = self.prune
        bbs = b.bb
        trace_children = tnode is not None and ply < tracing.MAX_PLIES
        n = len(moves)
        for i in range(n):
            c = moves[i]
            child_t = None
            if trace_children:
                child_t = tracing.make_node(f"{tnode['id']}.{c}", c, to_play)
                if prune:
                    child_t["alpha"] = tracing.bound(alpha)
                    child_t["beta"] = tracing.bound(beta)
                tnode["children"].append(child_t)
            bit = 1 << heights[c]
            bbs[to_play] |= bit
            heights[c] += 1
            b.moves += 1
            if has_four(bbs[to_play]):
                self.nodes += 1
                if ply + 1 > self.max_ply:
                    self.max_ply = ply + 1
                val = (WIN - (ply + 1)) if maximizing else -(WIN - (ply + 1))
                pv = []
                if child_t is not None:
                    child_t["terminal"] = True
            elif b.moves >= 42:
                self.nodes += 1
                if ply + 1 > self.max_ply:
                    self.max_ply = ply + 1
                val, pv = 0, []
                if child_t is not None:
                    child_t["terminal"] = True
            else:
                val, pv = self._search(ply + 1, depth - 1, 3 - to_play, alpha, beta, child_t)
                if child_t is not None and prune and depth > 1:
                    child_t["bound"] = tracing.bound_kind(val, alpha, beta)
            heights[c] -= 1
            bbs[to_play] ^= bit
            b.moves -= 1
            if child_t is not None:
                child_t["value"] = float(val)
            if maximizing:
                if val > best:
                    best = val
                    best_pv = [c] + pv
                if prune:
                    if best > alpha:
                        alpha = best
                    if alpha >= beta:
                        self._cut(moves, i, tnode, trace_children, to_play)
                        break
            else:
                if val < best:
                    best = val
                    best_pv = [c] + pv
                if prune:
                    if best < beta:
                        beta = best
                    if alpha >= beta:
                        self._cut(moves, i, tnode, trace_children, to_play)
                        break
        return best, best_pv

    def _leaf_value(self, ply, to_play):
        """Value of a horizon leaf, from the root player's perspective.

        The static evaluation does not know whose turn it is, so a leaf where
        the side to move can complete four *right now* would be scored as a
        mere open three (+5 / -4) although it is decided.  At odd depths that
        side is the opponent, so the search would happily walk into lines
        that lose on the very next move.  We therefore first check the side
        to move for an immediate win (a few whole-board bit operations, see
        :func:`engine.board.threat_cells`; no extra node is searched): if it
        has one, the leaf is a proven result at ply ``ply + 1``, scored like
        any other win or loss.  Otherwise the window heuristic is used.
        Because a position always sits at the same ply within one search,
        the result can be memoised by position.
        """
        bb = self.b.bb
        if threat_cells(bb[to_play]) & playable_cells(bb[1] | bb[2]):
            return (WIN - (ply + 1)) if to_play == self.root else -(WIN - (ply + 1))
        root = self.root
        return evaluate(bb[root], bb[3 - root])

    def _cut(self, moves, i, tnode, trace_children, to_play):
        rest = moves[i + 1:]
        self.pruned += len(rest)
        if trace_children:
            for c in rest:
                ch = tracing.make_node(f"{tnode['id']}.{c}", c, to_play)
                ch["pruned"] = True
                tnode["children"].append(ch)

    # -- root ---------------------------------------------------------------
    def choose(self, board, player, trace=True):
        t0 = time.perf_counter()
        self.b = board.copy()
        self.root = player
        self.nodes = 1
        self.pruned = 0
        self.max_ply = 0
        self.cache = {}
        b = self.b
        heights = b.heights
        moves = [c for c in self.order if heights[c] < COL_LIMIT[c]]
        tree = tracing.make_node("root", None, player) if trace else None
        if tree is not None and self.prune:
            tree["alpha"] = None
            tree["beta"] = None
        scores = [None] * COLS
        alpha, beta = -INF, INF
        best, best_col, best_pv = -INF, moves[0], [moves[0]]
        for c in moves:
            child_t = None
            if tree is not None:
                child_t = tracing.make_node(f"root.{c}", c, player)
                if self.prune:
                    child_t["alpha"] = tracing.bound(alpha)
                    child_t["beta"] = tracing.bound(beta)
                tree["children"].append(child_t)
            bit = 1 << heights[c]
            b.bb[player] |= bit
            heights[c] += 1
            b.moves += 1
            if has_four(b.bb[player]):
                self.nodes += 1
                self.max_ply = max(self.max_ply, 1)
                val, pv = WIN - 1, []
                if child_t is not None:
                    child_t["terminal"] = True
            elif b.moves >= 42:
                self.nodes += 1
                self.max_ply = max(self.max_ply, 1)
                val, pv = 0, []
                if child_t is not None:
                    child_t["terminal"] = True
            else:
                val, pv = self._search(1, self.depth - 1, 3 - player, alpha, beta, child_t)
                if child_t is not None and self.prune and self.depth > 1:
                    child_t["bound"] = tracing.bound_kind(val, alpha, beta)
            heights[c] -= 1
            b.bb[player] ^= bit
            b.moves -= 1
            scores[c] = float(val)
            if child_t is not None:
                child_t["value"] = float(val)
            if val > best:
                best, best_col, best_pv = val, c, [c] + pv
            if self.prune and best > alpha:
                alpha = best
        elapsed = time.perf_counter() - t0
        if tree is not None:
            tree["value"] = float(best)
            tracing.mark_line(tree, best_pv)
            tracing.cap_tree(tree)
        stats = _stats(self.nodes, self.pruned, elapsed, self.depth, None, self.max_ply)
        expl = self._explain(board, player, best_col, best, scores, moves)
        return _finish(board, player, best_col, scores, [None] * COLS, stats,
                       expl, best_pv, tree)

    def _algo_name(self):
        return "Minimax"

    def _explain(self, board, player, col, best, scores, moves):
        me, opp = PLAYER_NAMES[player], PLAYER_NAMES[3 - player]
        tac = tactical_reason(board, player, col)
        algo = f"{self._algo_name()} (depth {self.depth}, {self.nodes:,} positions"
        if self.prune:
            algo += f", {self.pruned:,} branches pruned"
        algo += ")"
        if tac and tac.startswith("Wins immediately"):
            return tac
        parts = []
        if tac:
            parts.append(tac)
        if best >= WIN - 100:
            plies = WIN - int(best)
            parts.append(f"{algo} found a forced win: {me} wins within {(plies + 1) // 2} "
                         f"of its own moves whatever {opp} does.")
        elif best <= -(WIN - 100):
            plies = WIN + int(best)
            parts.append(f"{algo} sees a forced loss in {plies} plies against best play; "
                         f"{col_name(col)} holds out the longest.")
        else:
            others = sorted((scores[c], c) for c in moves if c != col)
            line = (f"{algo} rates {col_name(col)} best with a score of {fmt_score(best)}")
            if others:
                v2, c2 = others[-1]
                if self.prune:
                    line += "; pruning proved no other column scores higher"
                elif v2 == best:
                    line += f", tied with {col_name(c2)} (ties go to the first column searched)"
                else:
                    line += f", ahead of {col_name(c2)} ({fmt_score(v2)})"
            parts.append(line + ".")
            losing = [c for c in moves if scores[c] <= -(WIN - 100)]
            if losing:
                parts.append("Avoids " + ", ".join(col_name(c) for c in losing)
                             + f", which would let {opp} force a win.")
        return " ".join(parts)


class AlphaBetaAgent(MinimaxAgent):
    """Minimax with alpha-beta pruning (fail-soft).

    With ``move_ordering`` the center columns are searched first, which finds
    good moves early and makes cut-offs far more frequent.  ``stats.pruned``
    counts sibling branches skipped at cut-offs.  The root value is identical
    to plain minimax at the same depth; for root moves that fail low,
    ``column_scores`` holds an upper bound rather than the exact value.
    """

    kind = "alphabeta"
    prune = True

    def __init__(self, depth=5, move_ordering=True):
        super().__init__(depth=depth, move_ordering=move_ordering)
        self.move_ordering = bool(move_ordering)

    def _algo_name(self):
        return "Alpha-beta" + (" with center-first ordering" if self.move_ordering else "")


# --------------------------------------------------------------------------
# MCTS
# --------------------------------------------------------------------------
class _Node:
    __slots__ = ("move", "parent", "children", "untried", "visits", "wins",
                 "player", "winner", "terminal", "depth")

    def __init__(self, move, parent, player, untried, winner, terminal, depth):
        self.move = move
        self.parent = parent
        self.children = []
        self.untried = untried
        self.visits = 0
        self.wins = 0.0
        self.player = player      # who made ``move`` into this node
        self.winner = winner      # 1/2 if this position is won, else 0
        self.terminal = terminal
        self.depth = depth


class MCTSAgent:
    """UCT Monte Carlo Tree Search.

    * Selection: UCB1 = wins/visits + c * sqrt(ln(parent visits) / visits), c = sqrt(2).
    * Expansion: one random untried move per iteration.
    * Simulation: random playout; when ``smart_rollouts`` is on, a player who
      can win immediately does so, and otherwise blocks an immediate
      opponent win (cheap tactical awareness that makes rollouts far less noisy).
    * Backpropagation: win = 1, draw = 0.5, from each node's mover's view.

    The move with the most visits is played; ties in visits are broken by
    the higher win rate, then by the more central column (never at random),
    and the explanation says so.  ``column_scores`` is the root
    player's win rate (0..1) per move, ``column_visits`` the visit counts.
    ``stats.nodes`` counts tree nodes created.
    """

    kind = "mcts"
    C = math.sqrt(2)

    def __init__(self, iterations=1500, seed=None, smart_rollouts=True):
        self.iterations = max(1, int(iterations))
        self.rng = random.Random(seed)
        self.smart = smart_rollouts

    def choose(self, board, player, trace=True):
        t0 = time.perf_counter()
        rng = self.rng
        rand = rng.random
        C = self.C
        log = math.log
        sqrt = math.sqrt
        smart = self.smart
        root_moves = board.valid_moves()
        rng.shuffle(root_moves)
        root = _Node(None, None, 3 - player, root_moves, 0, False, 0)
        nodes = 1
        max_depth = 0
        base_bb = board.bb
        base_h = board.heights
        base_moves = board.moves

        for _ in range(self.iterations):
            bb = base_bb[:]
            h = base_h[:]
            nmoves = base_moves
            node = root
            # 1. selection
            while not node.untried and node.children:
                lnv = log(node.visits)
                best, bestv = None, -1.0
                for ch in node.children:
                    v = ch.wins / ch.visits + C * sqrt(lnv / ch.visits)
                    if v > bestv:
                        bestv, best = v, ch
                node = best
                c = node.move
                bb[node.player] |= 1 << h[c]
                h[c] += 1
                nmoves += 1
            # 2. expansion
            if node.untried and not node.terminal:
                c = node.untried.pop()
                mover = 3 - node.player
                bb[mover] |= 1 << h[c]
                h[c] += 1
                nmoves += 1
                won = has_four(bb[mover])
                full = nmoves >= 42
                if won or full:
                    untried = []
                else:
                    untried = [m for m in range(COLS) if h[m] < COL_LIMIT[m]]
                    rng.shuffle(untried)
                child = _Node(c, node, mover, untried, mover if won else 0,
                              won or full, node.depth + 1)
                node.children.append(child)
                node = child
                nodes += 1
                if child.depth > max_depth:
                    max_depth = child.depth
            # 3. simulation
            if node.terminal:
                winner = node.winner
            else:
                winner = 0
                turn = 3 - node.player
                valid = [m for m in range(COLS) if h[m] < COL_LIMIT[m]]
                while nmoves < 42:
                    c = -1
                    if smart:
                        mine, theirs = bb[turn], bb[3 - turn]
                        block = -1
                        for m in valid:
                            bit = 1 << h[m]
                            if has_four(mine | bit):
                                c = m
                                break
                            if block < 0 and has_four(theirs | bit):
                                block = m
                        if c < 0:
                            c = block
                    if c < 0:
                        c = valid[int(rand() * len(valid))]
                    bb[turn] |= 1 << h[c]
                    h[c] += 1
                    nmoves += 1
                    if h[c] >= COL_LIMIT[c]:
                        valid.remove(c)
                    if has_four(bb[turn]):
                        winner = turn
                        break
                    turn = 3 - turn
            # 4. backpropagation
            while node is not None:
                node.visits += 1
                if winner == node.player:
                    node.wins += 1.0
                elif winner == 0:
                    node.wins += 0.5
                node = node.parent

        elapsed = time.perf_counter() - t0
        scores = [None] * COLS
        visits = [None] * COLS
        for ch in root.children:
            scores[ch.move] = round(ch.wins / ch.visits, 4) if ch.visits else 0.0
            visits[ch.move] = ch.visits
        # most-visited child; break ties by win rate then center preference
        ranked = sorted(root.children, key=self._rank_key, reverse=True)
        best = ranked[0]
        col = best.move
        pv = [col]
        n = best
        while n.children:
            n = max(n.children, key=lambda ch: ch.visits)
            pv.append(n.move)
        tree = self._trace(root, player, pv) if trace else None
        stats = _stats(nodes, 0, elapsed, None, self.iterations, max_depth)
        expl = self._explain(board, player, ranked)
        return _finish(board, player, col, scores, visits, stats, expl, pv, tree)

    @staticmethod
    def _rank_key(ch):
        """Final move choice: most visits, then higher win rate, then the
        more central column (so equal statistics never fall to chance)."""
        return (ch.visits, ch.wins / max(ch.visits, 1), -CENTER_ORDER.index(ch.move))

    def _explain(self, board, player, ranked):
        best = ranked[0]
        col = best.move
        tac = tactical_reason(board, player, col)
        if tac and tac.startswith("Wins immediately"):
            return tac
        rate = best.wins / max(best.visits, 1)
        n = self.iterations
        line = (f"Most-explored move after {n:,} simulations: {col_name(col)} "
                f"({best.visits:,} visits, {rate:.0%} win rate)")
        if len(ranked) > 1:
            ru = ranked[1]
            ru_rate = ru.wins / max(ru.visits, 1)
            if ru.visits != best.visits:
                line += f"; runner-up {col_name(ru.move)} ({ru.visits:,} visits, {ru_rate:.0%})"
            else:
                tied = [ch for ch in ranked if ch.visits == best.visits]
                names = ", ".join(col_name(ch.move) for ch in tied[1:])
                line = (f"After {n:,} simulations {col_name(col)} is tied for most visits "
                        f"with {names} ({best.visits:,} each)")
                if ru.wins != best.wins:
                    line += (f"; the tie is broken by the higher win rate ({best.wins:g} vs "
                             f"{ru.wins:g} simulated wins, draws counting half)")
                else:
                    line += (f" and the same win rate ({rate:.0%}); the tie is broken by "
                             f"preferring the more central column, {col_name(col)}")
        line += "."
        return f"{tac} {line}" if tac else line

    def _trace(self, root, player, pv):
        def build(node, nid, ply):
            t = tracing.make_node(nid, node.move, player if node.move is None else node.player)
            t["visits"] = node.visits
            t["wins"] = round(node.wins, 2)
            if node.visits:
                rate = node.wins / node.visits
                t["value"] = round(rate if t["player"] == player else 1 - rate, 4)
            t["terminal"] = node.terminal
            if ply < tracing.MAX_PLIES:
                for ch in node.children:
                    t["children"].append(build(ch, f"{nid}.{ch.move}", ply + 1))
            return t
        tree = build(root, "root", 0)
        # the internal root's wins are credited to the opponent (its "mover");
        # report them for the root player, matching the node's ``player``
        tree["wins"] = round(root.visits - root.wins, 2)
        tree["value"] = None if not root.visits else round(
            max((c.wins / c.visits) for c in root.children if c.visits), 4)
        tracing.mark_line(tree, pv)
        return tracing.cap_tree(tree)


# --------------------------------------------------------------------------
# factory
# --------------------------------------------------------------------------
def create_agent(cfg):
    """Build an agent from a *normalised* config dict (see engine.api)."""
    t = cfg["type"]
    if t == "random":
        return RandomAgent(seed=cfg.get("seed"))
    if t == "greedy":
        return GreedyAgent(seed=cfg.get("seed"))
    if t == "minimax":
        return MinimaxAgent(depth=cfg.get("depth", 4))
    if t == "alphabeta":
        return AlphaBetaAgent(depth=cfg.get("depth", 5),
                              move_ordering=cfg.get("move_ordering", True))
    if t == "mcts":
        return MCTSAgent(iterations=cfg.get("iterations", 1500), seed=cfg.get("seed"))
    raise ValueError(f"unknown agent type {t!r}")
