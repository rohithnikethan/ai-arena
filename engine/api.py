"""Public engine API - the only module app.py imports.

All functions take/return plain JSON-friendly Python data.  Boards are 6x7
lists of lists (row 0 = top, 0 empty, 1 Red, 2 Yellow); columns are 0-indexed
ints (explanations shown to humans use 1-indexed "column 4").
Invalid input raises ``ValueError`` with a human-readable message.
"""

import random
import time

from .board import Board, ROWS, COLS, has_four, parse_int
from .agents import create_agent, AlphaBetaAgent, MinimaxAgent
from . import review as _review

AGENT_TYPES = ("random", "greedy", "minimax", "alphabeta", "mcts")
DEPTH_RANGE = (1, 8)
MINIMAX_MAX_DEPTH = 6          # plain minimax is exponential; keep the UI responsive
ITER_RANGE = (50, 20000)
DEFAULT_DEPTH = 5
DEFAULT_ITERATIONS = 1500

AGENT_PRESETS = {
    "random": {
        "type": "random",
        "label": "Random",
        "description": "A uniform random policy: drops a disc in any legal column - the baseline policy every other agent must beat.",
        "seed": None,
    },
    "greedy": {
        "type": "greedy",
        "label": "Greedy",
        "description": "Looks one move ahead: wins if it can, blocks if it must, otherwise maximises a window-scoring heuristic.",
        "seed": None,
    },
    "minimax": {
        "type": "minimax",
        "label": "Minimax",
        "description": "Depth-limited heuristic minimax: searches every line 4 plies deep, assuming the opponent always picks the reply that hurts most.",
        "depth": 4,
    },
    "alphabeta": {
        "type": "alphabeta",
        "label": "Alpha-Beta",
        "description": "Minimax 6 plies deep with alpha-beta pruning and centre-first move ordering: the same value as Minimax, computed with far fewer nodes.",
        "depth": 6,
        "move_ordering": True,
    },
    "mcts": {
        "type": "mcts",
        "label": "Monte Carlo Tree Search",
        "description": "1,500 iterations of UCT (UCB1 selection) with a tactical playout policy (win if possible, else block, else random); plays the most-visited move.",
        "iterations": 1500,
        "seed": None,
    },
}


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------
def validate_board(board):
    """Check shape, cell values, gravity and disc counts; return a clean copy.

    Raises ValueError with a clear message on any problem.
    """
    if not isinstance(board, (list, tuple)) or len(board) != ROWS:
        raise ValueError(f"board must be a list of {ROWS} rows")
    clean = []
    for r, row in enumerate(board):
        if not isinstance(row, (list, tuple)) or len(row) != COLS:
            raise ValueError(f"board row {r} must be a list of {COLS} cells")
        out = []
        for c, v in enumerate(row):
            try:
                v = parse_int(v, "cell")
            except ValueError:
                v = None
            if v not in (0, 1, 2):
                raise ValueError(f"board cell [{r}][{c}] must be 0, 1 or 2 (got {row[c]!r})")
            out.append(v)
        clean.append(out)
    for c in range(COLS):
        seen_disc = False
        for r in range(ROWS):
            if clean[r][c]:
                seen_disc = True
            elif seen_disc:
                raise ValueError(f"floating disc in column {c} (row {r} below it is empty)")
    n1 = sum(v == 1 for row in clean for v in row)
    n2 = sum(v == 2 for row in clean for v in row)
    if n1 - n2 not in (0, 1):
        raise ValueError(f"impossible disc counts: Red has {n1}, Yellow has {n2} "
                         "(Red moves first, so Red must have the same number or one more)")
    b = Board.from_grid(clean)
    if has_four(b.bb[1]) and has_four(b.bb[2]):
        raise ValueError("impossible position: both players have four in a row")
    for w, name in ((1, "Red"), (2, "Yellow")):
        if has_four(b.bb[w]):
            _check_win_was_last_move(b, w, name, n1, n2)
    return clean


def _check_win_was_last_move(b, w, name, n1, n2):
    """A won position is only reachable if the winning disc was the last one.

    So the winner must have made the last move (Red: one disc more than
    Yellow; Yellow: equal counts), and removing one of the winner's
    top-of-column discs must leave no four in a row (otherwise play went on
    after the game was already won).
    """
    if (n1 != n2 + 1) if w == 1 else (n1 != n2):
        raise ValueError(f"impossible position: {name} has four in a row but "
                         f"{'Yellow' if w == 1 else 'Red'} moved after that "
                         f"(Red has {n1} discs, Yellow {n2})")
    bits = b.bb[w]
    for c in range(COLS):
        top = b.heights[c] - 1
        if top >= c * (ROWS + 1) and bits >> top & 1 and not has_four(bits ^ (1 << top)):
            return
    raise ValueError(f"impossible position: {name}'s four in a row could not all "
                     "have been completed by the last disc played (the game "
                     "continued after it was won)")


def _int(value, name, default):
    """``None`` -> ``default``; otherwise :func:`engine.board.parse_int`."""
    if value is None:
        return default
    return parse_int(value, name)


def normalize_config(config):
    """Validate an agent config, fill defaults and clamp numeric ranges.

    Accepts a config dict, a preset id string (e.g. ``"mcts"``), or a dict
    with only ``{"preset": id}``.  Extra keys such as label/description are
    ignored.
    """
    if config is None:
        config = {"type": "alphabeta"}
    if isinstance(config, str):
        if config not in AGENT_PRESETS:
            raise ValueError(f"unknown agent preset {config!r}")
        config = AGENT_PRESETS[config]
    if not isinstance(config, dict):
        raise ValueError("agent config must be an object")
    if "type" not in config and config.get("preset") in AGENT_PRESETS:
        config = {**AGENT_PRESETS[config["preset"]], **config}
    t = config.get("type")
    if t not in AGENT_TYPES:
        raise ValueError(f"agent type must be one of {', '.join(AGENT_TYPES)} (got {t!r})")
    depth = _int(config.get("depth"), "depth", DEFAULT_DEPTH)
    depth = max(DEPTH_RANGE[0], min(DEPTH_RANGE[1], depth))
    if t == "minimax":
        depth = min(depth, MINIMAX_MAX_DEPTH)
    iters = _int(config.get("iterations"), "iterations", DEFAULT_ITERATIONS)
    iters = max(ITER_RANGE[0], min(ITER_RANGE[1], iters))
    seed = config.get("seed")
    if seed is not None:
        seed = _int(seed, "seed", None)
    return {
        "type": t,
        "depth": depth,
        "iterations": iters,
        "move_ordering": _bool(config.get("move_ordering"), "move_ordering", True),
        "trace": _bool(config.get("trace"), "trace", True),
        "seed": seed,
    }


def _bool(value, name, default):
    """``None`` -> ``default``; otherwise a real boolean (``"false"``, ``0`` rejected)."""
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be true or false (got {value!r})")
    return value


def agent_label(cfg):
    """Short human label for a normalised config, e.g. 'Alpha-Beta (depth 6)'."""
    t = cfg["type"]
    if t == "random":
        return "Random"
    if t == "greedy":
        return "Greedy"
    if t == "minimax":
        return f"Minimax (depth {cfg['depth']})"
    if t == "alphabeta":
        extra = "" if cfg["move_ordering"] else ", unordered"
        return f"Alpha-Beta (depth {cfg['depth']}{extra})"
    return f"MCTS ({cfg['iterations']:,} iterations)"


# --------------------------------------------------------------------------
# API functions
# --------------------------------------------------------------------------
def game_state(board):
    """{"winner", "draw", "winning_cells", "valid_moves", "to_move"}."""
    return Board.from_grid(validate_board(board)).state()


def choose_move(board, player, config):
    """Ask an agent for a move. See SPEC.md for the result shape."""
    grid = validate_board(board)
    try:
        player = parse_int(player, "player")
    except ValueError:
        player = None
    if player not in (1, 2):
        raise ValueError("player must be 1 (Red) or 2 (Yellow)")
    cfg = normalize_config(config)
    b = Board.from_grid(grid)
    st = b.state()
    if st["winner"]:
        raise ValueError("the game is already over: player "
                         f"{st['winner']} has four in a row")
    if st["draw"]:
        raise ValueError("the game is already over: the board is full")
    if player != b.to_move:
        raise ValueError(f"it is not player {player}'s turn "
                         f"(player {b.to_move} to move on this board)")
    agent = create_agent(cfg)
    return agent.choose(b, player, trace=cfg["trace"])


def apply_move(board, column, player=None):
    """Helper for app.py: validate and play ``column``; returns (board, state)."""
    grid = validate_board(board)
    b = Board.from_grid(grid)
    st = b.state()
    if st["winner"] or st["draw"]:
        raise ValueError("the game is already over")
    try:
        column = parse_int(column, "column")
    except ValueError:
        column = None
    if column is None or not 0 <= column < COLS:
        raise ValueError("column must be an integer 0-6")
    if not b.can_play(column):
        raise ValueError(f"column {column + 1} is full")
    if player is not None:
        try:
            player = parse_int(player, "player")
        except ValueError:
            player = None
        if player not in (1, 2):
            raise ValueError("player must be 1 (Red) or 2 (Yellow)")
        if player != b.to_move:
            raise ValueError(f"it is not player {player}'s turn "
                             f"(player {b.to_move} to move on this board)")
    b.play(column, b.to_move)
    return b.to_grid(), b.state()


OPENING_PLIES_RANGE = (0, 6)


def random_openings(count, plies, seed):
    """``count`` seeded random openings of ``plies`` moves each (lists of columns).

    Openings are drawn *without replacement* from all ``7 ** plies`` column
    sequences while there are enough of them (every sequence is legal: no
    column can overflow within 6 plies, and nobody can win in under 7), then
    with replacement.  The same ``(count, plies, seed)`` always gives the same
    list.
    """
    if plies <= 0 or count <= 0:
        return [[] for _ in range(max(count, 0))]
    rng = random.Random(f"opening-{seed}-{plies}")
    space = COLS ** plies
    codes = rng.sample(range(space), min(count, space))
    while len(codes) < count:
        codes.append(rng.randrange(space))
    out = []
    for code in codes:
        cols = []
        for _ in range(plies):
            code, c = divmod(code, COLS)
            cols.append(c)
        out.append(cols)
    return out


def _validate_openings(openings):
    if not isinstance(openings, (list, tuple)) or not openings:
        raise ValueError("openings must be a non-empty list of move lists")
    clean = []
    for i, op in enumerate(openings):
        if not isinstance(op, (list, tuple)) or len(op) > OPENING_PLIES_RANGE[1]:
            raise ValueError(f"opening {i} must be a list of at most "
                             f"{OPENING_PLIES_RANGE[1]} columns")
        b = Board()
        cols = []
        for c in op:
            try:
                col = parse_int(c, "opening move")
            except ValueError:
                col = None
            if col is None or not b.can_play(col):
                raise ValueError(f"opening {i} contains an illegal move {c!r}")
            b.play(col)
            cols.append(col)
        clean.append(cols)
    return clean


def run_match(config_a, config_b, games=10, seed=0, opening_plies=0, openings=None):
    """Play ``games`` games between two agents, alternating who moves first.

    Deterministic for a given ``seed``: stochastic agents without an explicit
    seed get one derived from ``seed``, the game index and their side.

    With ``opening_plies = k > 0`` (clamped to 0-6) games are played in
    pairs: games ``2i`` and ``2i + 1`` both start from the same random
    ``k``-ply opening (see :func:`random_openings`), with colours swapped, so
    deterministic agents no longer replay the same one or two games and any
    advantage an opening gives one colour is cancelled out.  Opening moves
    are forced, not chosen by the agents: they are not counted in the
    agents' time/node averages, but they are included in each result's
    ``moves`` (the full game record) and listed again in ``opening``.
    ``first`` is the agent playing Red.

    ``openings`` (optional) is an explicit list of openings (lists of
    columns) used instead of random ones: games ``2i`` and ``2i + 1`` play
    ``openings[i % len(openings)]``.  benchmark.py uses it to split one
    experiment into independent chunks.
    """
    cfg_a = normalize_config(config_a)
    cfg_b = normalize_config(config_b)
    games = max(1, _int(games, "games", 10))
    seed = _int(seed, "seed", 0)
    opening_plies = _int(opening_plies, "opening_plies", 0)
    opening_plies = max(OPENING_PLIES_RANGE[0], min(OPENING_PLIES_RANGE[1], opening_plies))
    if openings is not None:
        openings = _validate_openings(openings)
        opening_plies = max(len(o) for o in openings)
    else:
        openings = random_openings((games + 1) // 2, opening_plies, seed)
    totals = {"a": [0.0, 0, 0], "b": [0.0, 0, 0]}  # time_ms, nodes, decisions
    results = []
    a_wins = b_wins = draws = 0
    for g in range(games):
        first = "a" if g % 2 == 0 else "b"
        agents = {}
        for side, cfg in (("a", cfg_a), ("b", cfg_b)):
            c = dict(cfg)
            if c["seed"] is None:
                c["seed"] = seed * 100_003 + g * 2 + (0 if side == "a" else 1)
            else:
                c["seed"] = c["seed"] + g
            agents[side] = create_agent(c)
        side_of = {1: first, 2: "b" if first == "a" else "a"}
        b = Board()
        opening = openings[(g // 2) % len(openings)]
        for col in opening:
            b.play(col)
        moves = list(opening)
        winner = "draw"
        while True:
            p = b.to_move
            side = side_of[p]
            res = agents[side].choose(b, p, trace=False)
            t = totals[side]
            t[0] += res["stats"]["time_ms"]
            t[1] += res["stats"]["nodes"]
            t[2] += 1
            col = res["column"]
            b.play(col, p)
            moves.append(col)
            if has_four(b.bb[p]):
                winner = side
                break
            if b.is_full():
                break
        if winner == "a":
            a_wins += 1
        elif winner == "b":
            b_wins += 1
        else:
            draws += 1
        results.append({"first": first, "winner": winner, "moves": moves,
                        "length": len(moves), "opening": list(opening)})

    def summary(side, cfg):
        t = totals[side]
        n = max(t[2], 1)
        return {"avg_time_ms": round(t[0] / n, 3), "avg_nodes": round(t[1] / n, 1),
                "label": agent_label(cfg)}

    return {"games": games, "a_wins": a_wins, "b_wins": b_wins, "draws": draws,
            "a": summary("a", cfg_a), "b": summary("b", cfg_b), "results": results,
            "opening_plies": opening_plies}


# Rough cost model for run_match, used by app.py to refuse requests that
# would run for many minutes.  Per-move milliseconds measured on CPython
# 3.13/3.14 on a mid-game sample (a slower laptop may need ~2x); a game is
# assumed to give each agent at most ~21 moves.
_MS_PER_MOVE = {
    "random": {None: 0.05},
    "greedy": {None: 0.2},
    "minimax": {1: 0.1, 2: 0.5, 3: 2.0, 4: 8.0, 5: 35.0, 6: 180.0},
    "alphabeta": {1: 0.1, 2: 0.2, 3: 0.6, 4: 1.5, 5: 4.0, 6: 15.0, 7: 45.0, 8: 170.0},
}
MCTS_MS_PER_ITERATION = 0.07
MOVES_PER_AGENT_PER_GAME = 21


def estimate_move_ms(config):
    """Estimated milliseconds per move for an agent config (see cost model)."""
    cfg = normalize_config(config)
    t = cfg["type"]
    if t == "mcts":
        return cfg["iterations"] * MCTS_MS_PER_ITERATION
    table = _MS_PER_MOVE[t]
    return table.get(cfg["depth"], table.get(None, 0.0)) if t in ("minimax", "alphabeta")         else table[None]


def estimate_match_seconds(config_a, config_b, games):
    """Pessimistic wall-clock estimate (seconds) for ``run_match``."""
    per_game = MOVES_PER_AGENT_PER_GAME * (estimate_move_ms(config_a) + estimate_move_ms(config_b))
    return max(1, _int(games, "games", 10)) * per_game / 1000.0


def compare_depth(board=None, depths=(1, 2, 3, 4, 5, 6)):
    """Node counts / timings of minimax vs alpha-beta at several depths.

    Returns ``[{"depth", "minimax_nodes", "alphabeta_nodes",
    "alphabeta_ordered_nodes", "minimax_ms", "alphabeta_ms",
    "alphabeta_ordered_ms"}]``.  ``alphabeta_nodes``/``alphabeta_ms`` are for
    natural left-to-right ordering; ``*_ordered_*`` for center-first.  Minimax
    is capped at depth 6: deeper rows report ``None`` for minimax fields.
    """
    if board is None:
        b = Board()
    else:
        b = Board.from_grid(validate_board(board))
        st = b.state()
        if st["winner"] or st["draw"]:
            raise ValueError("the game is already over on this board")
    if isinstance(depths, int):
        depths = [depths]
    clean = []
    for d in depths:
        d = _int(d, "depth", None)
        clean.append(max(DEPTH_RANGE[0], min(DEPTH_RANGE[1], d)))
    player = b.to_move
    rows = []
    for d in clean:
        row = {"depth": d}
        if d <= MINIMAX_MAX_DEPTH:
            r = MinimaxAgent(depth=d).choose(b, player, trace=False)
            row["minimax_nodes"] = r["stats"]["nodes"]
            row["minimax_ms"] = r["stats"]["time_ms"]
        else:
            row["minimax_nodes"] = None
            row["minimax_ms"] = None
        r = AlphaBetaAgent(depth=d, move_ordering=False).choose(b, player, trace=False)
        row["alphabeta_nodes"] = r["stats"]["nodes"]
        row["alphabeta_ms"] = r["stats"]["time_ms"]
        r = AlphaBetaAgent(depth=d, move_ordering=True).choose(b, player, trace=False)
        row["alphabeta_ordered_nodes"] = r["stats"]["nodes"]
        row["alphabeta_ordered_ms"] = r["stats"]["time_ms"]
        rows.append(row)
    return rows


def analyze_game(moves, depth=_review.DEFAULT_REVIEW_DEPTH):
    """Post-game review of ``moves`` (columns from the empty board, Red first).

    Every position is searched with exact (full-window) alpha-beta values for
    every legal move, and each played move gets a badge
    (best/good/inaccuracy/mistake/blunder) plus "missed_win" /
    "allowed_forced_loss" tags.  ``depth`` is clamped to 1-8.  See
    :mod:`engine.review` for the method, thresholds and result shape.
    Raises ``ValueError`` for illegal moves or moves after the game ended.
    """
    return _review.analyze_game(moves, depth=depth)
