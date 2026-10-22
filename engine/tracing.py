"""Search-tree capture for visualisation.

Agents build plain-dict ``TreeNode`` objects while they search (only for the
first :data:`MAX_PLIES` plies) and this module provides helpers to create,
cap and annotate them.  Tracing is purely observational: it never changes the
order or number of nodes the search visits, so ``stats.nodes`` is identical
with ``trace`` on or off.

TreeNode shape (JSON-serialisable)::

    {"id": str, "move": int|None, "player": 1|2, "value": float|None,
     "alpha": float|None, "beta": float|None,
     "visits": int|None, "wins": float|None,
     "pruned": bool, "best": bool, "terminal": bool, "children": [TreeNode],
     "bound": "upper"|"lower"|None}

Conventions:

* ``id`` is the move path from the root, e.g. ``"root"``, ``"root.3"``,
  ``"root.3.4"``.
* ``player`` is the player who dropped the disc for ``move``; for the root
  (``move`` = None) it is the player about to choose.
* ``value`` is always from the root player's perspective.  Infinite alpha /
  beta bounds are reported as ``None`` (JSON has no infinity).
* ``wins`` (MCTS) is from the perspective of ``player`` (the mover), as in
  standard UCT bookkeeping; ``value`` is the root player's win rate.
* ``bound`` (alpha-beta only; an additive field beyond SPEC.md) says whether
  ``value`` is exact or only a bound.  A fail-soft search of a node with
  window ``(alpha, beta)`` that returns ``v <= alpha`` has *failed low*: the
  true minimax value is ``<= v`` (``"upper"``, show it as "<= v").  One that
  returns ``v >= beta`` *failed high*: the true value is ``>= v``
  (``"lower"``).  Otherwise, and always for terminal positions, horizon
  leaves, plain minimax and MCTS, it is ``None`` (exact).
"""

MAX_PLIES = 3
MAX_NODES = 400
INF_LIMIT = 10 ** 9  # |x| >= this is treated as an infinite bound


def make_node(node_id, move, player):
    return {
        "id": node_id, "move": move, "player": player, "value": None,
        "alpha": None, "beta": None, "visits": None, "wins": None,
        "pruned": False, "best": False, "terminal": False, "children": [],
        "bound": None,
    }


def bound_kind(value, alpha, beta):
    """``"upper"`` / ``"lower"`` / None for a fail-soft value searched with
    window ``(alpha, beta)`` (see the module docstring)."""
    if value <= alpha:
        return "upper"
    if value >= beta:
        return "lower"
    return None


def bound(x):
    """Convert a search bound to a JSON-friendly float or None if infinite."""
    if x is None or abs(x) >= INF_LIMIT:
        return None
    return float(x)


def count_nodes(node):
    if node is None:
        return 0
    return 1 + sum(count_nodes(ch) for ch in node["children"])


def mark_line(root, moves):
    """Flag ``best`` along the move sequence ``moves`` starting at the root."""
    node = root
    node["best"] = True
    for mv in moves:
        nxt = None
        for ch in node["children"]:
            if ch["move"] == mv:
                nxt = ch
                break
        if nxt is None:
            return
        nxt["best"] = True
        node = nxt


def cap_tree(root, max_nodes=MAX_NODES, key=None):
    """Trim ``root`` in place to at most ``max_nodes`` nodes.

    Nodes are admitted breadth-first; within a level, children on the best
    line come first, then children ordered by ``key`` (descending; default:
    MCTS visits, then value).  Children that do not fit are dropped, so the
    most relevant part of the tree survives.
    """
    if root is None:
        return root
    if key is None:
        def key(n):
            return (n["visits"] or 0, n["value"] if n["value"] is not None else -1e18)
    budget = max_nodes - 1
    level = [root]
    while level:
        candidates = []
        for parent in level:
            kids = sorted(parent["children"], key=lambda n: (n["best"], key(n)), reverse=True)
            for rank, ch in enumerate(kids):
                candidates.append((rank, parent, ch))
            parent["children"] = []
        # round-robin by rank so every parent keeps its top children first
        candidates.sort(key=lambda t: t[0])
        nxt = []
        for rank, parent, ch in candidates:
            if budget <= 0:
                break
            parent["children"].append(ch)
            nxt.append(ch)
            budget -= 1
        for parent in level:  # restore a stable column order for display
            parent["children"].sort(key=lambda n: n["move"])
        level = nxt
    return root
