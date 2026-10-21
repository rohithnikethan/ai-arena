"""Public engine API - the only module app.py imports.

All functions take/return plain JSON-friendly Python data.  Boards are 6x7
lists of lists (row 0 = top, 0 empty, 1 Red, 2 Yellow); columns are 0-indexed
ints (explanations shown to humans use 1-indexed "column 4").
Invalid input raises ``ValueError`` with a human-readable message.
"""

import time

from .board import Board, ROWS, COLS, has_four
from .agents import create_agent, AlphaBetaAgent, MinimaxAgent

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
        "description": "Drops a disc in a uniformly random legal column - the baseline every real AI must beat.",
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
        "description": "Exhaustively searches every line 4 plies deep, assuming the opponent always picks the reply that hurts most.",
        "depth": 4,
    },
    "alphabeta": {
        "type": "alphabeta",
        "label": "Alpha-Beta",
        "description": "Minimax 6 plies deep that skips branches which provably cannot change the decision, searching center columns first.",
        "depth": 6,
        "move_ordering": True,
    },
    "mcts": {
        "type": "mcts",
        "label": "Monte Carlo Tree Search",
        "description": "Plays 1,500 quick simulated games, steering exploration with the UCT formula, and picks the most-visited move.",
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
            if isinstance(v, bool) or not isinstance(v, int) or v not in (0, 1, 2):
                raise ValueError(f"board cell [{r}][{c}] must be 0, 1 or 2 (got {v!r})")
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
    return clean


def _int(value, name, default):
    if value is None:
        return default
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be an integer (got {value!r})") from None


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
        "move_ordering": bool(config.get("move_ordering", True)),
        "trace": bool(config.get("trace", True)),
        "seed": seed,
    }


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
    if isinstance(player, bool) or player not in (1, 2):
        raise ValueError("player must be 1 (Red) or 2 (Yellow)")
    cfg = normalize_config(config)
    b = Board.from_grid(grid)
    st = b.state()
    if st["winner"]:
        raise ValueError("the game is already over: player "
                         f"{st['winner']} has four in a row")
    if st["draw"]:
        raise ValueError("the game is already over: the board is full")
    agent = create_agent(cfg)
    return agent.choose(b, player, trace=cfg["trace"])


def apply_move(board, column, player=None):
    """Helper for app.py: validate and play ``column``; returns (board, state)."""
    grid = validate_board(board)
    b = Board.from_grid(grid)
    st = b.state()
    if st["winner"] or st["draw"]:
        raise ValueError("the game is already over")
    if isinstance(column, bool) or not isinstance(column, int) or not 0 <= column < COLS:
        raise ValueError("column must be an integer 0-6")
    if not b.can_play(column):
        raise ValueError(f"column {column + 1} is full")
    b.play(column, player or b.to_move)
    return b.to_grid(), b.state()


def run_match(config_a, config_b, games=10, seed=0):
    """Play ``games`` games between two agents, alternating who moves first.

    Deterministic for a given ``seed``: stochastic agents without an explicit
    seed get one derived from ``seed``, the game index and their side.
    """
    cfg_a = normalize_config(config_a)
    cfg_b = normalize_config(config_b)
    games = max(1, _int(games, "games", 10))
    seed = _int(seed, "seed", 0)
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
        moves = []
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
                        "length": len(moves)})

    def summary(side, cfg):
        t = totals[side]
        n = max(t[2], 1)
        return {"avg_time_ms": round(t[0] / n, 3), "avg_nodes": round(t[1] / n, 1),
                "label": agent_label(cfg)}

    return {"games": games, "a_wins": a_wins, "b_wins": b_wins, "draws": draws,
            "a": summary("a", cfg_a), "b": summary("b", cfg_b), "results": results}


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
