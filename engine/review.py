"""Post-game review: re-analyse every move of a finished game.

For each position of the game the reviewer computes the **exact** depth-``d``
minimax value of *every* legal move, then compares the move that was played
with the best one and gives it a badge (Best / Good / Inaccuracy / Mistake /
Blunder) plus special tags ("Missed win", "Allowed forced loss").

Why not just read ``AlphaBetaAgent.choose(...)["column_scores"]``?
---------------------------------------------------------------------
At the root, alpha-beta raises ``alpha`` to the best score found so far and
passes it down to later siblings.  A sibling that cannot beat ``alpha`` fails
low and returns an *upper bound* (fail-soft) rather than its true value: a
move reported as "+3" might really be "-40" or even a forced loss.  Grading a
move by such a bound would under-report mistakes, so it is never done here.

Instead :func:`exact_move_values` runs the root loop itself and searches each
child with a **full window** ``(-INF, +INF)`` using the existing
:meth:`AlphaBetaAgent._search` (same move ordering, same evaluation, same
win scoring - there is no second search implementation).  Alpha-beta below
each child still prunes, but a full-window call returns the exact minimax
value of that child at depth ``d - 1``, so every root value is exactly what
plain minimax at depth ``d`` would report.  The tests check this against
:class:`MinimaxAgent`.

Values are from the perspective of the player to move in that position, and
use the engine's convention: a win ``k`` plies ahead is ``1_000_000 - k``, a
loss ``-(1_000_000 - k)``, a draw 0, and :mod:`engine.evaluate` otherwise.
Forced wins and losses found within the horizon are *proofs* (the heuristic
never comes near +/-1_000_000); everything else is a heuristic estimate.

"Missed win" is therefore horizon-limited: it means a proven win was
available but none was found after the played move.  Two things keep
neighbouring rows consistent:

* The *next* position's search (one ply deeper from here, see
  :func:`graded_value`) is used for the played move: if it proves the
  opponent lost, the move wins (a slower win, or the best move if nothing
  else was proven to win); if it proves the opponent wins, the move loses.
* A consistency re-search: when a tag would rest on "nothing was proven"
  (a Missed win: no win found after the move; an Allowed forced loss: the
  position before it was not proven lost), that position is re-searched up
  to :data:`RESEARCH_EXTRA_PLIES` deeper with a null window, within a node
  budget shared by the whole review.  A proof found there is used by both
  rows that touch the position, so a row never says "Missed win" while the
  next one is proven lost, and "Allowed forced loss" is never given in a
  position already proven lost.

When no proof is found either way, the comment says within how many plies
it looked.
"""

import time

from .agents import AlphaBetaAgent, WIN, INF
from .board import Board, COLS, CENTER_ORDER, PLAYER_NAMES, has_four, parse_int

#: Default review depth (plies): one ply deeper than the strongest preset
#: opponent (alpha-beta depth 6).  Measured on CPython 3.13 for 31-42 ply
#: games: depth 6 ~0.2-0.4 s, depth 7 ~0.4-1.0 s (a full 42-ply draw: 0.96 s),
#: depth 8 ~1.5-3.4 s, depth 9 ~3-6 s.  Each position costs up to 7 full-window searches, because exact
#: values for every move are needed (see module docstring).
DEFAULT_REVIEW_DEPTH = 7
REVIEW_DEPTH_RANGE = (1, 8)

#: Any |value| at or above this is a proven win/loss (same margin as agents.py).
MATE = WIN - 100

# Classification thresholds on the *heuristic* loss, i.e. best value minus
# played value, both exact depth-d values from the mover's perspective.
# Scale (engine/evaluate.py): an open two is worth 2, an open three 5, an
# opponent three -4, a center disc 3; typical mid-game positions sit within
# about +/-40.  So:
#   loss == 0            -> Best        (ties count: several moves can be best)
#   loss <= 4            -> Good        (about one open two / one center disc)
#   loss <= 10           -> Inaccuracy  (roughly two threes' worth of shape)
#   loss <= 25           -> Mistake     (several threats' worth)
#   loss  > 25           -> Blunder
# Outcome changes override the thresholds: missing a proven win or walking
# into a proven loss is always a Blunder; a slower (but still forced) win is
# Good, and a quicker loss in an already-lost position is an Inaccuracy.
GOOD_MAX_LOSS = 4
INACCURACY_MAX_LOSS = 10
MISTAKE_MAX_LOSS = 25

BADGES = ("best", "good", "inaccuracy", "mistake", "blunder")

#: Consistency re-search (see :func:`analyze_game`): a disputed position is
#: re-searched up to this many plies beyond the review depth, with at most
#: this many nodes per review in total (node-based, so results do not depend
#: on the machine's speed).
RESEARCH_EXTRA_PLIES = 6
RESEARCH_NODE_BUDGET = 300_000


# --------------------------------------------------------------------------
# value helpers
# --------------------------------------------------------------------------
def is_win(v):
    return v is not None and v >= MATE


def is_loss(v):
    return v is not None and v <= -MATE


def mate_plies(v):
    """Plies until the game ends for a proven value (``None`` if heuristic)."""
    if v is None or abs(v) < MATE:
        return None
    return int(WIN - abs(v))


def moves_to_win(v):
    """For a proven value, how many moves the *winner* still has to play.

    A value of ``WIN - p`` means the mover's winning disc lands on ply ``p``
    (odd: the mover plays plies 1, 3, 5, ...), i.e. on its ``(p + 1) // 2``-th
    move.  A loss ``-(WIN - p)`` means the opponent's winning disc lands on an
    even ply ``p``, its ``p // 2``-th move.
    """
    p = mate_plies(v)
    if p is None:
        return None
    return (p + 1) // 2 if v > 0 else p // 2


def _plural(n, word):
    return f"{n} {word}" + ("" if n == 1 else "s")


def red_eval(value, mover):
    """Describe a mover-perspective value from Red's perspective for the graph.

    Returns ``{"score", "mate", "label"}`` where ``score`` is the raw value for
    Red, ``mate`` is ``+N`` (Red wins in N moves), ``-N`` (Yellow wins in N)
    or ``None``.
    """
    score = value if mover == 1 else -value
    n = moves_to_win(value)
    if n is None:
        return {"score": float(score), "mate": None, "label": _fmt_heur(score)}
    winner = 1 if score > 0 else 2
    return {"score": float(score), "mate": n if winner == 1 else -n,
            "label": f"{PLAYER_NAMES[winner]} wins in {_plural(n, 'move')}"}


def _graph_point(ply, value, shallow, mover):
    """Graph entry for a position: depth-d value, smoothed with depth d-1.

    ``value`` is the exact depth-``d`` value and ``shallow`` the exact
    depth-``(d-1)`` value of the same position (both mover's perspective;
    ``shallow`` may be None).  Fixed-depth search has an *odd-even effect*:
    whoever makes the last ply before the horizon looks better than they are,
    so raw values zigzag between Red-to-move and Yellow-to-move positions.
    For heuristic values the plotted ``score`` is the mean of the two depths,
    which cancels most of that.  Proven wins/losses are plotted as is (a
    proof at depth d-1 is also found at depth d, so the two cannot disagree
    on whether a position is won).  ``raw`` keeps the unsmoothed depth-d
    value.  Badges never use these numbers: they compare exact values of
    sibling moves searched to the same depth.
    """
    e = {"ply": ply, **red_eval(value, mover)}
    e["raw"] = e["score"]
    if shallow is not None and e["mate"] is None and abs(shallow) < MATE:
        sign = 1 if mover == 1 else -1
        e["score"] = round((value + shallow) * sign / 2.0, 1)
        e["label"] = _fmt_heur(e["score"])
    return e


def _fmt_heur(v):
    r = int(round(v))
    return f"+{r}" if r > 0 else str(r)


def _col(c):
    return f"Column {c + 1}"


# --------------------------------------------------------------------------
# exact search
# --------------------------------------------------------------------------
def exact_move_values(board, player, depth, agent=None):
    """Exact depth-``depth`` minimax value of every legal move for ``player``.

    Each root move is played and its child searched by
    ``AlphaBetaAgent._search`` with a full ``(-INF, INF)`` window, so no
    root-level alpha cut-off can turn a value into a bound.  Returns
    ``(values, nodes)`` where ``values`` is a 7-list (``None`` = illegal).
    """
    if agent is None:
        agent = AlphaBetaAgent(depth=depth, move_ordering=True)
    agent.b = b = board.copy()
    agent.root = player
    agent.nodes = 1
    agent.pruned = 0
    agent.max_ply = 0
    agent.cache = {}
    values = [None] * COLS
    for c in b.valid_moves():
        b.play(c, player)
        if has_four(b.bb[player]):
            v = WIN - 1
        elif b.moves >= 42:
            v = 0
        else:
            v, _ = agent._search(1, depth - 1, 3 - player, -INF, INF, None)
        b.undo(c, player)
        values[c] = float(v)
    return values, agent.nodes


def n_legal_of(values):
    return sum(v is not None for v in values)


def _best_columns(values):
    best = max(v for v in values if v is not None)
    cols = [c for c in CENTER_ORDER if values[c] == best]
    return best, cols


# --------------------------------------------------------------------------
# classification + explanations
# --------------------------------------------------------------------------
def graded_value(best, played, next_best):
    """The played move's value used for grading (mover's perspective).

    Normally the exact depth-``d`` value ``played``.  One exception: the
    played move may win by force just past the horizon.  The next position
    of the game has already been searched to depth ``d`` (``next_best``, from
    the opponent's perspective), which is depth ``d + 1`` from here; if that
    proves the opponent lost, the move wins, one ply later than the
    opponent's loss: ``WIN - (p + 1)``.  This applies whatever ``best`` is
    (``best`` is kept in the signature for callers): when the best move is a
    proven win the played move is a slower win, not a "Missed win"; when no
    move was proven to win at depth ``d``, the played move is itself the
    best move found (:func:`analyze_game` raises the position's best value to
    it).  Without this, a row could be graded "Inaccuracy" or "Missed win"
    while the very next row says the opponent is lost.  Symmetrically, if
    the next position is a proven win for the opponent, the move loses one
    ply after that (``-next_best + 1``), even if its own depth-``d`` value
    did not see it.
    """
    if is_win(played) or is_loss(played):
        return played
    if is_loss(next_best):
        return float(-next_best - 1)
    if is_win(next_best):
        return float(-next_best + 1)
    return played


class _OutOfBudget(Exception):
    pass


class _ProofAgent(AlphaBetaAgent):
    """The same alpha-beta search, stopped once ``limit`` nodes are used.

    Used only by :func:`_prove` for the consistency re-search: a null window
    around the proven-result threshold answers "is this a forced win (or
    loss) within ``D`` plies?" far more cheaply than an exact value.
    """

    def __init__(self):
        super().__init__(depth=1, move_ordering=True)
        self.limit = 0

    def _search(self, ply, depth, to_play, alpha, beta, tnode):
        if self.nodes >= self.limit:
            raise _OutOfBudget
        return AlphaBetaAgent._search(self, ply, depth, to_play, alpha, beta, tnode)


def _prove(board, root, ply0, first_depth, last_depth, want_win, budget):
    """Deeper re-search of one disputed position, in the root mover's frame.

    ``board`` has ``root`` to move if ``ply0 == 0`` (and the opponent to move
    if ``ply0 == 1``: the position after ``root``'s move).  Searches depth
    ``D = first_depth .. last_depth`` (skipping a ``D`` whose new reach,
    ply ``ply0 + D + 1``, has the wrong parity: ``root``'s winning discs land
    on odd plies and the opponent's on even ones), each with a null window that asks whether the
    value is a proven win for ``root`` (``want_win``) or a proven loss.
    The caller guarantees that depth ``first_depth - 1`` proved nothing, so
    the first success is the *exact* mate distance: it lies beyond the
    reach of depth ``D - 1`` (``ply0 + D`` plies) and within the reach of
    depth ``D`` (``ply0 + D + 1`` plies).  ``budget`` is a one-item list of
    remaining nodes, shared by all re-searches of one review.

    Returns ``(value_or_None, deepest_completed_depth, first_move)``;
    ``first_move`` (from the search's principal variation, ``ply0 == 0``
    only) is a column that achieves the proven value.
    """
    agent = _ProofAgent()
    last_depth = min(last_depth, 42 - board.moves)
    done = first_depth - 1
    to_play = root if ply0 == 0 else 3 - root
    for D in range(first_depth, last_depth + 1):
        if (ply0 + D + 1) % 2 != (1 if want_win else 0):
            done = D        # no result of the right parity lands at that ply
            continue
        agent.b = board.copy()
        agent.root = root
        agent.cache = {}
        agent.nodes = agent.pruned = agent.max_ply = 0
        agent.limit = budget[0]
        try:
            if want_win:
                v, pv = agent._search(ply0, D, to_play, MATE - 1, MATE, None)
            else:
                v, pv = agent._search(ply0, D, to_play, -MATE, -MATE + 1, None)
        except _OutOfBudget:
            budget[0] = 0
            return None, done, None
        budget[0] -= agent.nodes
        if (want_win and v >= MATE) or (not want_win and v <= -MATE):
            return float(v), D, (pv[0] if pv else None)
        done = D
    return None, done, None


def classify(best, played):
    """Return ``(badge, tags)`` for a played value against the best value.

    Both values must be exact and from the mover's perspective (``played``
    is the :func:`graded_value` of the move).
    """
    tags = []
    missed_win = is_win(best) and not is_win(played)
    allowed_loss = not is_loss(best) and is_loss(played)
    if missed_win:
        tags.append("missed_win")
    if allowed_loss:
        tags.append("allowed_forced_loss")
    if played == best:
        return "best", tags
    if missed_win or allowed_loss:
        return "blunder", tags
    if is_win(best):              # both win: played is merely slower
        return "good", tags
    if is_loss(best):             # both lose: played loses sooner
        return "inaccuracy", tags
    loss = best - played          # both heuristic (or a 0-valued draw)
    if loss <= GOOD_MAX_LOSS:
        return "good", tags
    if loss <= INACCURACY_MAX_LOSS:
        return "inaccuracy", tags
    if loss <= MISTAKE_MAX_LOSS:
        return "mistake", tags
    return "blunder", tags


def _best_reason(board, player, col, value, depth, proven_loss_depth=None,
                 faster_unknown=False):
    """One plain-English line on why ``col`` is the best move.

    ``proven_loss_depth`` is set when the position was only proven lost by
    the deeper re-search (searched that many plies): the loss distance is
    the position's, not necessarily that of ``col``, so no column is named.
    ``faster_unknown``: ``col`` is proven to win in that many moves, but the
    budget ran out before checking whether another column wins faster.
    """
    me, opp = PLAYER_NAMES[player], PLAYER_NAMES[3 - player]
    if proven_loss_depth is not None and is_loss(value):
        n = moves_to_win(value)
        return (f"Every move loses against best play: a deeper {proven_loss_depth}-ply "
                f"search shows {opp} forces a win ({opp} needs {_plural(n, 'more move')}).")
    if is_win(value) and faster_unknown:
        return (f"{_col(col)} forces a win in {_plural(moves_to_win(value), 'move')}; "
                f"no other column was proven to win within {depth + 1} plies.")
    if is_win(value):
        n = moves_to_win(value)
        if n == 1:
            return f"{_col(col)} wins immediately."
        return f"{_col(col)} forces a win in {_plural(n, 'move')} whatever {opp} does."
    if is_loss(value):
        n = moves_to_win(value)
        return (f"Every move loses against best play; {_col(col).lower()} holds out "
                f"longest ({opp} needs {_plural(n, 'more move')}).")
    if col in board.winning_moves(3 - player):
        return f"{_col(col)} blocks {opp}'s four-in-a-row threat."
    after = board.copy()
    after.play(col, player)
    threats = after.winning_moves(player)
    if not after.winning_moves(3 - player):
        if len(threats) >= 2:
            return (f"{_col(col)} creates a double threat ({', '.join(str(c + 1) for c in threats)}); "
                    f"{opp} can only block one.")
        if threats and threats[0] == col:
            return f"{_col(col)} sets up a threat to win on top of it."
        if threats:
            return f"{_col(col)} sets up a threat to win in column {threats[0] + 1}."
    return f"{_col(col)} has the best depth-{depth} evaluation ({_fmt_heur(value)} for {me})."


def _played_comment(board, player, col, played, best, best_col, badge, tags, n_legal, ties,
                    horizon=None, lifted=False, unresolved_loss=False):
    """Sentence on the played move.  ``horizon`` is the number of plies from
    this position within which no forced win was found after the played move
    (None when the move ended the game, so its value is exact).  ``lifted``:
    the move's proven win was found only beyond the depth-``d`` search of
    this position (so the other columns' values are not comparable).
    ``unresolved_loss``: the position is proven lost, but this move's own
    loss distance was not settled (it is graded as the best defence)."""
    me, opp = PLAYER_NAMES[player], PLAYER_NAMES[3 - player]
    if n_legal == 1:
        return "The only legal move."
    if badge == "best":
        if is_win(played) and moves_to_win(played) == 1:
            return f"{_col(col)} wins the game."
        if unresolved_loss:
            return (f"Every move loses against best play; no quicker loss than "
                    f"the best defence was proven after {_col(col).lower()}.")
        if lifted:
            return (f"Best move: {me} forces a win in {_plural(moves_to_win(played), 'move')} "
                    f"(proven by the deeper search of the next position).")
        if len(ties) > 1:
            others = ", ".join(str(c + 1) for c in ties if c != col)
            return f"Best move (tied with column{'s' if len(ties) > 2 else ''} {others})."
        return "Best move."
    if "missed_win" in tags:
        n = moves_to_win(best)
        win = "an immediate win" if n == 1 else f"a forced win in {_plural(n, 'move')}"
        s = f"Misses {win} with column {best_col + 1}"
        if "allowed_forced_loss" in tags:
            s += f", and lets {opp} force a win instead"
        elif horizon is not None:
            # not a proof that the win is gone: only that none was found
            s += (f"; after {_col(col).lower()} no forced win for {me} was found "
                  f"within {horizon} plies")
        return s + "."
    if "allowed_forced_loss" in tags:
        after = board.copy()
        after.play(col, player)
        now = after.winning_moves(3 - player)
        if now:
            return f"{_col(col)} lets {opp} win immediately in column {now[0] + 1}."
        return f"{_col(col)} lets {opp} force a win in {_plural(moves_to_win(played), 'move')}."
    if is_win(best):
        return (f"Still winning, but slower: {_plural(moves_to_win(played), 'move')} "
                f"instead of {moves_to_win(best)}.")
    if is_loss(best):
        return (f"Loses sooner ({opp} needs {_plural(moves_to_win(played), 'move')} "
                f"instead of {moves_to_win(best)}).")
    return (f"{_col(col)} scores {_fmt_heur(played)} against {_fmt_heur(best)} for "
            f"column {best_col + 1} ({_plural(int(round(best - played)), 'point')} worse).")


# --------------------------------------------------------------------------
# main entry point
# --------------------------------------------------------------------------
def analyze_game(moves, depth=DEFAULT_REVIEW_DEPTH, research_plies=None,
                 research_nodes=None):
    """Review a game given as columns played from the empty board (Red first).

    ``moves`` must be legal and must not continue after the game is over
    (``ValueError`` otherwise); the game need not be finished.  ``depth`` is
    clamped to :data:`REVIEW_DEPTH_RANGE`.

    Returns::

        {"depth": int, "time_ms": float, "nodes": int,
         "evals": [{"ply", "score", "raw", "mate", "label"}, ...],  # len(moves)+1
         "moves": [{"ply", "player", "column", "board_before", "values",
                    "best_value", "played_value", "graded_value", "best_column",
                    "best_columns", "loss", "badge", "tags", "reason", "comment"}, ...],
         "summary": {"1": {...counts...}, "2": {...}},
         "result": {"winner": 0|1|2, "draw": bool, "finished": bool},
         "thresholds": {...}}

    ``evals[i]`` is position ``i`` (before move ``i + 1``; the last entry is
    the final position) from Red's perspective: the best exact value at that
    position (heuristic scores smoothed over depths d and d-1, see
    :func:`_graph_point`; ``raw`` is unsmoothed).  ``loss`` is ``best_value - played_value`` when both are
    heuristic, else ``None``.  ``graded_value`` is the value the badge is
    based on: ``played_value``, except when the next position's search (or
    the consistency re-search) proves the played move wins or loses beyond
    its own horizon (see :func:`graded_value`).  ``best_value`` is the
    maximum of ``values`` unless a deeper proof is known for the position:
    the played move's proven win when no other move was proven to win (the
    move is then the only entry of ``best_columns``), or the position's proven
    loss / win from the re-search.  ``research_plies`` and
    ``research_nodes`` (defaults :data:`RESEARCH_EXTRA_PLIES`,
    :data:`RESEARCH_NODE_BUDGET`) bound the re-search; 0 switches it off.
    """
    if not isinstance(moves, (list, tuple)):
        raise ValueError("moves must be a list of column numbers (0-6)")
    if not moves:
        raise ValueError("moves must contain at least one move")
    if len(moves) > 42:
        raise ValueError("a game has at most 42 moves")
    depth = parse_int(depth, "depth")
    depth = max(REVIEW_DEPTH_RANGE[0], min(REVIEW_DEPTH_RANGE[1], depth))
    if research_plies is None:
        research_plies = RESEARCH_EXTRA_PLIES
    if research_nodes is None:
        research_nodes = RESEARCH_NODE_BUDGET

    # replay + validate first, so bad input fails fast before any search
    b = Board()
    clean = []
    for i, c in enumerate(moves):
        try:
            c = parse_int(c, f"move {i + 1}")
        except ValueError:
            raise ValueError(f"move {i + 1} must be an integer column 0-6 (got {c!r})") from None
        if b.winner() or b.is_full():
            raise ValueError(f"move {i + 1} comes after the game is already over")
        if not 0 <= c < COLS:
            raise ValueError(f"move {i + 1}: column must be 0-6 (got {c})")
        if not b.can_play(c):
            raise ValueError(f"move {i + 1}: column {c + 1} is full")
        b.play(c)
        clean.append(c)
    moves = clean

    t0 = time.perf_counter()
    agent = AlphaBetaAgent(depth=depth, move_ordering=True)
    nodes = 0

    # pass 1: exact depth-d values of every legal move in every position,
    # including the final position if the game is unfinished
    b = Board()
    positions = []        # (board copy, player, values)
    for col in moves:
        player = b.to_move
        values, n = exact_move_values(b, player, depth, agent)
        nodes += n
        positions.append((b.copy(), player, values))
        b.play(col, player)
    w = b.winner()
    final_values = None
    if not w and not b.is_full():
        final_values, n = exact_move_values(b, b.to_move, depth, agent)
        nodes += n

    # pass 2: grade each move, looking one position ahead where that helps
    evals, out = [], []
    summary = {str(p): {**{k: 0 for k in BADGES}, "missed_win": 0,
                        "allowed_forced_loss": 0, "moves": 0, "accuracy": None}
               for p in (1, 2)}
    shallow = None    # exact depth-(d-1) value of the current position
    if depth > 1:
        vals0, n = exact_move_values(Board(), 1, depth - 1, AlphaBetaAgent(depth=depth - 1))
        nodes += n
        shallow = max(v for v in vals0 if v is not None)
    # Consistency pass.  Every proven value is a proof, but "not proven" only
    # means "nothing found within the horizon".  Where a row's grade would
    # rest on such a non-result, the disputed position is re-searched a few
    # plies deeper (null window, shared node budget):
    #   * Missed win (no win found after the move): is the next position lost?
    #   * Allowed forced loss (this position was not proven lost): is it?
    #   * a position proven lost only by such a re-search, where the played
    #     move's own value is heuristic: how fast does the opponent now win?
    # A proof is stored for its position (in that position's mover's view)
    # and used by *both* rows that touch it when they are graded below.
    proven = {}        # position index -> proven value for its mover (re-search)
    proven_depth = {}  # ... the re-search depth that proved it
    proven_col = {}    # ... a column achieving a proven win, when known
    checked = {}       # (position index, "win" or "loss") -> deepest depth that proved nothing
    budget = [research_nodes]
    extra = max(0, int(research_plies))

    def best_at(k):
        vals = positions[k][2] if k < len(positions) else final_values
        if vals is None:
            return None
        v = max(x for x in vals if x is not None)
        return proven[k] if k in proven and not (is_win(v) or is_loss(v)) else v

    def research(k, board, root, ply0, want_win):
        """Settle position ``k``: does its mover lose (``"loss"``) or win?

        ``ply0 == 1``: ``board`` is position ``k`` seen from the previous
        mover ``root`` (who wins iff k's mover loses); ``ply0 == 0``: ``root``
        is k's mover.
        """
        question = "loss" if (ply0 == 1) == want_win else "win"
        if k in proven or (k, question) in checked or not extra or budget[0] <= 0:
            return
        v, done, c = _prove(board, root, ply0, depth + 1, depth + extra, want_win, budget)
        if v is None:
            if done > depth:
                checked[(k, question)] = done
            return
        proven[k] = -v - 1 if ply0 == 1 else v     # position k's own frame
        proven_depth[k] = done
        if ply0 == 0 and is_win(v) and c is not None:
            proven_col[k] = c

    for i, col in enumerate(moves):
        pos, player, values = positions[i]
        after = pos.copy()
        after.play(col, player)
        if after.winner() or after.is_full():
            continue
        best = best_at(i)
        graded = graded_value(best, values[col], best_at(i + 1))
        unproven = not (is_win(graded) or is_loss(graded))
        if is_win(best) and unproven:
            research(i + 1, after, player, 1, True)          # would be a Missed win
        elif not is_win(best) and not is_loss(best) and is_loss(graded):
            research(i, pos, player, 0, False)               # would be an Allowed forced loss
        if is_loss(best_at(i)) and unproven:
            research(i + 1, after, 3 - player, 0, True)      # lost anyway: how fast?

    for i, col in enumerate(moves):
        pos, player, values = positions[i]
        raw_best, ties = _best_columns(values)
        played = values[col]
        best_col = col if col in ties else ties[0]
        best = best_at(i)
        proven_loss_depth = None
        if best != raw_best:
            if is_loss(best):
                proven_loss_depth = proven_depth[i]
            elif i in proven_col:          # exact fastest win and a column achieving it
                ties = [proven_col[i]]
                best_col = proven_col[i]
        next_best = best_at(i + 1)
        graded = graded_value(best, played, next_best)
        lifted = is_win(graded) and not is_win(played) and graded > best
        faster_unknown = False
        if lifted:
            # The move wins, beyond anything proven for the other columns.
            # No other column wins within depth + 1 plies, so a win the next
            # position's own search proves (<= depth + 2 plies) is also the
            # fastest.  A longer one (from a deeper re-search) need not be:
            # then search this position itself to the same depth for its
            # fastest win and the column that achieves it.
            best, ties, best_col = graded, [col], col
            if mate_plies(graded) > depth + 2:
                v, _, c = _prove(pos, player, 0, depth + 1, mate_plies(graded),
                                 True, budget) if budget[0] > 0 else (None, 0, None)
                if v is None:
                    faster_unknown = True
                elif v > graded and c is not None:
                    best, ties, best_col = v, [c], c
                    lifted = False      # graded below as a slower win
        unresolved_loss = is_loss(best) and not (is_win(graded) or is_loss(graded))
        if unresolved_loss:
            # lost anyway (deeper proof), but how fast this move loses was
            # not settled within the budget: grade it as the best defence
            graded = best
        after = pos.copy()
        after.play(col, player)
        terminal_after = bool(after.winner() or after.is_full())
        # plies after this position within which "no forced win" was checked
        horizon = depth + 1 if next_best is not None else depth
        if (i + 1, "loss") in checked:
            horizon = max(horizon, checked[(i + 1, "loss")] + 1)
        badge, tags = classify(best, graded)
        n_legal = n_legal_of(values)
        loss = None
        if not (is_win(best) or is_loss(best) or is_win(graded) or is_loss(graded)):
            loss = float(best - played)
        evals.append(_graph_point(i, best, shallow, player))
        # the played move's value is the next position's depth-(d-1) value
        shallow = -played if depth > 1 else None
        out.append({
            "ply": i + 1,
            "player": player,
            "column": col,
            "board_before": pos.to_grid(),
            "values": values,
            "best_value": best,
            "played_value": played,
            "graded_value": graded,
            "best_column": best_col,
            "best_columns": ties,
            "loss": loss,
            "badge": badge,
            "tags": tags,
            "reason": _best_reason(pos, player, best_col, best, depth,
                                   proven_loss_depth=proven_loss_depth,
                                   faster_unknown=faster_unknown),
            "comment": _played_comment(pos, player, col, graded, best, best_col,
                                       badge, tags, n_legal, ties,
                                       horizon=None if terminal_after else horizon,
                                       lifted=lifted, unresolved_loss=unresolved_loss),
        })
        s = summary[str(player)]
        s[badge] += 1
        s["moves"] += 1
        for t in tags:
            s[t] += 1

    # final position
    if w:
        evals.append({"ply": len(moves), "score": float(WIN if w == 1 else -WIN),
                      "mate": 0, "label": f"{PLAYER_NAMES[w]} won",
                      "raw": float(WIN if w == 1 else -WIN)})
    elif b.is_full():
        evals.append({"ply": len(moves), "score": 0.0, "mate": None, "label": "Draw",
                      "raw": 0.0})
    else:
        best, _ = _best_columns(final_values)
        if len(moves) in proven and not is_loss(best):
            best = proven[len(moves)]
        evals.append(_graph_point(len(moves), best, shallow, b.to_move))

    for s in summary.values():
        if s["moves"]:
            s["accuracy"] = round(100.0 * (s["best"] + s["good"]) / s["moves"], 1)
    nodes += research_nodes - max(budget[0], 0)    # consistency re-search
    elapsed = time.perf_counter() - t0
    return {
        "depth": depth,
        "time_ms": round(elapsed * 1000.0, 1),
        "nodes": nodes,
        "evals": evals,
        "moves": out,
        "summary": summary,
        "result": {"winner": w, "draw": not w and b.is_full(),
                   "finished": bool(w or b.is_full())},
        "thresholds": {"good": GOOD_MAX_LOSS, "inaccuracy": INACCURACY_MAX_LOSS,
                       "mistake": MISTAKE_MAX_LOSS},
    }
