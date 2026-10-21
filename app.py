"""AI Arena: thin Flask layer.

Serves the pages and a small JSON API. All game logic lives in ``engine/``;
this module only validates input, calls ``engine.api`` and serialises results.

Run with:  python app.py   ->  http://localhost:5050
"""

from __future__ import annotations

import math
import traceback

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

from engine import api as engine_api

app = Flask(__name__)
app.json.sort_keys = False

ROWS, COLS = 6, 7
AGENT_TYPES = ("random", "greedy", "minimax", "alphabeta", "mcts")
DEPTH_RANGE = (1, 8)
MINIMAX_DEPTH_MAX = 6  # plain minimax is exponential; the engine caps it here too
ITER_RANGE = (50, 20000)
GAMES_RANGE = (1, 50)
COMPARE_DEPTH_RANGE = (1, 7)
BIG = 1e9  # stand-in for +/- infinity in JSON (JSON has no Infinity)


class BadRequest(ValueError):
    """Raised for client errors; rendered as 400 {"error": message}."""


# --------------------------------------------------------------------------
# Validation helpers
# --------------------------------------------------------------------------

def _json_body() -> dict:
    data = request.get_json(silent=True)
    if data is None:
        raise BadRequest("Request body must be valid JSON (Content-Type: application/json).")
    if not isinstance(data, dict):
        raise BadRequest("Request body must be a JSON object.")
    return data


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _as_int(value, name: str) -> int:
    if _is_int(value):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            pass
    raise BadRequest(f"'{name}' must be an integer.")


def _clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def _validate_board(board) -> list:
    if not isinstance(board, list) or len(board) != ROWS:
        raise BadRequest(f"'board' must be a list of {ROWS} rows.")
    clean = []
    for r, row in enumerate(board):
        if not isinstance(row, list) or len(row) != COLS:
            raise BadRequest(f"Row {r} of 'board' must be a list of {COLS} cells.")
        clean_row = []
        for c, cell in enumerate(row):
            if not _is_int(cell) or cell not in (0, 1, 2):
                raise BadRequest(f"Cell [{r}][{c}] must be 0, 1 or 2.")
            clean_row.append(cell)
        clean.append(clean_row)

    validator = getattr(engine_api, "validate_board", None)
    if callable(validator):
        try:
            validator(clean)
        except ValueError as exc:
            raise BadRequest(f"Invalid board: {exc}") from exc
    else:  # fallback structural checks if the engine has no validator
        reds = sum(row.count(1) for row in clean)
        yellows = sum(row.count(2) for row in clean)
        if reds - yellows not in (0, 1):
            raise BadRequest("Invalid board: piece counts are impossible (Red moves first).")
        for c in range(COLS):
            seen_disc = False
            for r in range(ROWS):
                if clean[r][c]:
                    seen_disc = True
                elif seen_disc:
                    raise BadRequest(f"Invalid board: floating disc in column {c}.")
    return clean


def _validate_player(value) -> int:
    if not _is_int(value) or value not in (1, 2):
        raise BadRequest("'player' must be 1 or 2.")
    return value


def _validate_agent(cfg, name: str = "agent", trace: bool | None = None) -> dict:
    if isinstance(cfg, str):
        cfg = {"type": cfg}
    if not isinstance(cfg, dict):
        raise BadRequest(f"'{name}' must be an object like {{\"type\": \"alphabeta\", \"depth\": 5}}.")
    agent_type = cfg.get("type")
    if agent_type not in AGENT_TYPES:
        raise BadRequest(f"'{name}.type' must be one of: {', '.join(AGENT_TYPES)}.")

    out: dict = {"type": agent_type}
    if agent_type in ("minimax", "alphabeta"):
        depth = _as_int(cfg.get("depth", 5), f"{name}.depth")
        hi = MINIMAX_DEPTH_MAX if agent_type == "minimax" else DEPTH_RANGE[1]
        out["depth"] = _clamp(depth, DEPTH_RANGE[0], hi)
    if agent_type == "alphabeta":
        ordering = cfg.get("move_ordering", True)
        if not isinstance(ordering, bool):
            raise BadRequest(f"'{name}.move_ordering' must be true or false.")
        out["move_ordering"] = ordering
    if agent_type == "mcts":
        iterations = _as_int(cfg.get("iterations", 1500), f"{name}.iterations")
        out["iterations"] = _clamp(iterations, *ITER_RANGE)

    want_trace = cfg.get("trace", True) if trace is None else trace
    if not isinstance(want_trace, bool):
        raise BadRequest(f"'{name}.trace' must be true or false.")
    out["trace"] = want_trace

    seed = cfg.get("seed")
    if seed is not None:
        seed = _as_int(seed, f"{name}.seed")
    out["seed"] = seed
    return out


def _clean_json(obj):
    """Replace non-finite floats (inf / nan) so the response is valid JSON."""
    if isinstance(obj, float):
        if math.isnan(obj):
            return None
        if math.isinf(obj):
            return BIG if obj > 0 else -BIG
        return obj
    if isinstance(obj, dict):
        return {k: _clean_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean_json(v) for v in obj]
    return obj


def _ok(payload):
    return jsonify(_clean_json(payload))


def _error(message: str, status: int):
    resp = jsonify({"error": message})
    resp.status_code = status
    return resp


def _engine_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except BadRequest:
        raise
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc


# --------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------

def _page(template: str, active: str, crumbs: list, **ctx):
    return render_template(template, active=active, crumbs=crumbs, **ctx)


@app.get("/")
def index():
    return _page("index.html", "home", [("Home", None)])


@app.get("/play")
def play():
    return _page("play.html", "play", [("Home", "/"), ("Play", None)])


@app.get("/arena")
def arena():
    return _page("arena.html", "arena", [("Home", "/"), ("Arena", None)])


@app.get("/lab")
def lab():
    return _page("lab.html", "lab", [("Home", "/"), ("Lab", None)])


@app.get("/learn")
def learn():
    return _page("learn.html", "learn", [("Home", "/"), ("Learn", None)])


# --------------------------------------------------------------------------
# JSON API
# --------------------------------------------------------------------------

@app.get("/api/agents")
def api_agents():
    return _ok(engine_api.AGENT_PRESETS)


@app.post("/api/state")
def api_state():
    data = _json_body()
    board = _validate_board(data.get("board"))
    return _ok(_engine_call(engine_api.game_state, board))


@app.post("/api/apply")
def api_apply():
    """Play a (human) move: {board, column} -> {"board", "state"}.

    Validates column legality server-side so the client never needs rules.
    """
    data = _json_body()
    board = _validate_board(data.get("board"))
    column = data.get("column")
    if not _is_int(column) or not 0 <= column < COLS:
        raise BadRequest("'column' must be an integer from 0 to 6.")
    state = _engine_call(engine_api.game_state, board)
    if state.get("winner") or state.get("draw"):
        raise BadRequest("The game is already over; start a new game.")
    if column not in state.get("valid_moves", []):
        raise BadRequest(f"Column {column + 1} is full.")
    new_board, new_state = _engine_call(engine_api.apply_move, board, column)
    return _ok({"board": new_board, "state": new_state})


@app.post("/api/move")
def api_move():
    data = _json_body()
    board = _validate_board(data.get("board"))
    player = _validate_player(data.get("player"))
    config = _validate_agent(data.get("agent"), "agent")

    state = _engine_call(engine_api.game_state, board)
    if state.get("winner") or state.get("draw"):
        raise BadRequest("The game is already over; start a new game.")
    if not state.get("valid_moves"):
        raise BadRequest("There are no legal moves on this board.")
    if state.get("to_move") not in (None, player):
        raise BadRequest(f"It is not player {player}'s turn (player {state.get('to_move')} to move).")

    return _ok(_engine_call(engine_api.choose_move, board, player, config))


@app.post("/api/match")
def api_match():
    data = _json_body()
    cfg_a = _validate_agent(data.get("agent_a"), "agent_a", trace=False)
    cfg_b = _validate_agent(data.get("agent_b"), "agent_b", trace=False)
    games = _clamp(_as_int(data.get("games", 10), "games"), *GAMES_RANGE)
    seed = data.get("seed", 0)
    seed = 0 if seed is None else _as_int(seed, "seed")
    return _ok(_engine_call(engine_api.run_match, cfg_a, cfg_b, games=games, seed=seed))


@app.post("/api/compare-depth")
def api_compare_depth():
    data = _json_body()
    board = data.get("board")
    if board is not None:
        board = _validate_board(board)
        state = _engine_call(engine_api.game_state, board)
        if state.get("winner") or state.get("draw"):
            raise BadRequest("The game on this board is already over.")

    depths = data.get("depths", [1, 2, 3, 4, 5])
    if not isinstance(depths, list) or not depths:
        raise BadRequest("'depths' must be a non-empty list of integers between 1 and 7.")
    clean_depths = set()
    for d in depths:
        d = _as_int(d, "depths[]")
        if not COMPARE_DEPTH_RANGE[0] <= d <= COMPARE_DEPTH_RANGE[1]:
            raise BadRequest("Each depth must be between 1 and 7.")
        clean_depths.add(d)
    result = _engine_call(engine_api.compare_depth, board=board, depths=sorted(clean_depths))
    return _ok(result)


# --------------------------------------------------------------------------
# Errors: JSON for /api/*, HTML otherwise
# --------------------------------------------------------------------------

def _wants_json() -> bool:
    return request.path.startswith("/api/")


@app.errorhandler(BadRequest)
def handle_bad_request(exc):
    return _error(str(exc), 400)


@app.errorhandler(HTTPException)
def handle_http(exc: HTTPException):
    if _wants_json():
        messages = {
            404: f"No API endpoint at {request.path}.",
            405: f"Method {request.method} is not allowed for {request.path}.",
        }
        return _error(messages.get(exc.code, exc.description or exc.name), exc.code or 500)
    if exc.code == 404:
        return _page("404.html", "", [("Home", "/"), ("Not found", None)]), 404
    return exc


@app.errorhandler(Exception)
def handle_unexpected(exc):
    traceback.print_exc()
    if _wants_json():
        return _error(f"Internal error: {type(exc).__name__}: {exc}", 500)
    return _page("404.html", "", [("Home", "/"), ("Error", None)], error=True), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=True)
