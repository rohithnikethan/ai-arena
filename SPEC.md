# AI Arena — Build Spec (shared contract)

"Watch minds think." A Connect Four arena where five classic game-playing agents,
each driven by a different decision algorithm (Random, Greedy, Minimax,
Alpha-Beta, MCTS), play you or each other, and their reasoning (the search tree,
pruning, MCTS statistics) is visualised live. Foundations of AI course project.
Terminology follows AIMA 4th ed. ch. 2: each player is an agent; the five names
are the algorithms inside the agent programs.

Stack: Python 3.10+ (developed on 3.13) + Flask. Frontend is plain HTML/CSS/vanilla
JS with Jinja templates. No CDN and no Google Fonts: D3 `7.8.5` and Chart.js `4.4.1`
are vendored in `static/vendor/` and the fonts (Montserrat, JetBrains Mono, `.woff2`)
in `static/fonts/`, so the app works offline. No Node, no build step, no API keys.
Runs with `python app.py` on http://localhost:5050.

## Layout

```
ai-arena/
  app.py                 # thin Flask layer: routes + JSON API, no game logic
  engine/                # pure Python, NO flask imports
    __init__.py
    board.py             # Board representation, rules, win detection
    evaluate.py          # heuristic evaluation function (window scoring)
    agents.py            # RandomAgent, GreedyAgent, MinimaxAgent, AlphaBetaAgent, MCTSAgent
    tracing.py           # search-tree capture for visualisation
    api.py               # the ONLY module app.py calls (functions below)
    review.py            # post-game review: exact per-move values, badges, explanations
  tests/                 # unittest (pytest NOT installed): python -m unittest discover -s tests
  benchmark.py           # CLI: python benchmark.py -> prints a markdown results table
  templates/  static/    # frontend (static/vendor: D3 + Chart.js; static/fonts: woff2)
  docs/                  # USER_GUIDE.md, VIVA_PREP.md
  README.md
```

## Board conventions

- `board` is a list of 6 rows, each a list of 7 ints, row 0 is the TOP row.
- 0 = empty, 1 = player 1 (Red, moves first), 2 = player 2 (Yellow).
- A move is a column index 0–6.

## engine/api.py — functions app.py calls

```python
AGENT_PRESETS: dict  # id -> {"type", "label", "description", params...}

def game_state(board) -> dict:
    # {"winner": 0|1|2, "draw": bool, "winning_cells": [[r,c],...],
    #  "valid_moves": [cols], "to_move": 1|2}

def choose_move(board, player, config) -> dict
    # player must equal game_state(board)["to_move"] (ValueError otherwise).
    # config: {"type": "random"|"greedy"|"minimax"|"alphabeta"|"mcts",
    #          "depth": int (minimax/alphabeta, 1..8, default 5),
    #          "iterations": int (mcts, 50..20000, default 1500),
    #          "move_ordering": bool (alphabeta, default True),
    #          "trace": bool (default True), "seed": int|None}
    #   move_ordering/trace must be real booleans ("false", 0 are rejected).
    #   A bare preset id string ("alphabeta") means that preset
    #   (Alpha-Beta depth 6, Minimax depth 4).
    # returns:
    # {
    #   "column": int,
    #   "board_after": board, "state_after": game_state(...),
    #   "column_scores": [float|None]*7,   # minimax value per root move, or MCTS win-rate 0..1; None if illegal
    #   "column_visits": [int|None]*7,     # MCTS only, else None entries
    #   "stats": {"nodes": int, "pruned": int, "time_ms": float, "nodes_per_sec": int,
    #             "depth": int|None, "iterations": int|None, "max_depth_reached": int},
    #   "explanation": str,   # plain English: why this move (e.g. "Blocks Yellow's
    #                         # immediate threat in column 4.", "Wins immediately: ...",
    #                         # "Most-explored move after 1,500 simulations: column 4
    #                         # (435 visits, 53% win rate); runner-up column 5 ...").
    #                         # MCTS plays the MOST-VISITED root child (ties: higher
    #                         # win rate, then the more central column).
    #   "principal_variation": [cols],  # expected line of play (minimax/alphabeta)
    #   "tree": TreeNode | None
    # }

def run_match(config_a, config_b, games=10, seed=0, opening_plies=0, openings=None) -> dict
    # agents alternate who moves first ("first" = the agent playing Red).
    # opening_plies k (clamped 0..6): games 2i and 2i+1 start from the same seeded
    # random k-ply opening with colours swapped (forced moves, not counted in the
    # time/node averages). openings: optional explicit list of openings instead.
    # returns
    # {"games": int, "a_wins": int, "b_wins": int, "draws": int,
    #  "a": {"avg_time_ms", "avg_nodes", "label"}, "b": {...},
    #  "results": [{"first": "a"|"b", "winner": "a"|"b"|"draw", "moves": [cols],
    #               "length": int, "opening": [cols]}],   # moves includes the opening
    #  "opening_plies": int}

def compare_depth(board=None, depths=(1, 2, 3, 4, 5, 6)) -> list
    # [{"depth", "minimax_nodes", "minimax_ms", "alphabeta_nodes", "alphabeta_ms",
    #   "alphabeta_ordered_nodes", "alphabeta_ordered_ms"}]; minimax fields None above depth 6

def analyze_game(moves, depth=7) -> dict
    # post-game review: calls engine.review.analyze_game(moves, depth=7,
    # research_plies=None, research_nodes=None) with exact full-window alpha-beta
    # values for every legal column of every position, badges, tags, explanations,
    # eval graph. research_plies / research_nodes (defaults 6 and 300_000; 0
    # switches it off) bound the consistency re-search of disputed positions.
```

TreeNode (JSON-serialisable dict), capped for transfer size — at most
3 plies deep and ~400 nodes total; keep the most relevant children:

```
{"id": str, "move": int|None, "player": 1|2, "value": float|None,
 "alpha": float|None, "beta": float|None,
 "visits": int|None, "wins": float|None,   # MCTS
 "pruned": bool,     # this subtree was cut off by alpha-beta (children omitted)
 "best": bool,       # on the chosen/principal line
 "terminal": bool, "children": [TreeNode],
 "bound": "upper"|"lower"|None}   # additive: alpha-beta internal nodes only.
                                  # "upper" = failed low (true value <= value),
                                  # "lower" = failed high (true value >= value),
                                  # None = exact (always None for minimax and MCTS)
```

Values: use +/- 1_000_000 (minus depth) for wins/losses, heuristic otherwise, from
the perspective of the player choosing at the root.

## Flask routes (app.py)

Pages (all extend `base.html`, share nav + breadcrumbs + light/dark toggle):
- `GET /`            Landing: hero (its animated board is a scripted illustration, not the real agents), the 5 agents as cards, CTA buttons
- `GET /play`        Human vs AI: board + live "AI Mind" panel (tree, column bars, stats, explanation)
- `GET /arena`       AI vs AI: pick two agents, watch them play move by move, both minds visible
- `GET /lab`         Benchmark lab: run tournaments, Chart.js charts of wins / time / nodes; minimax vs alpha-beta node-count comparison by depth
- `GET /learn`       Theory: how each algorithm works, with small diagrams; complexity table; step-through alpha-beta debugger (`/learn#ab-stepper`)
- `GET /present`     15-slide deck with speaker notes (S), fullscreen (F) and deep links (`/present#N`)
- 404 page

JSON API (JSON in/out, 400 with {"error": ...} on bad input; validate board shape/values, column legality, clamp depth/iterations):
- `GET  /api/agents`        -> AGENT_PRESETS
- `POST /api/state`         {board} -> game_state
- `POST /api/apply`         {board, column} -> {board, state} (human move, legality checked server-side)
- `POST /api/move`          {board, player, agent: config} -> choose_move result
- `POST /api/match`         {agent_a, agent_b, games (1..50), seed?, opening_plies? (0..6)} -> run_match result; 400 if the estimated run time exceeds 240 s
- `POST /api/compare-depth` {board?, depths:[1..7]} -> [{"depth", "minimax_nodes", "alphabeta_nodes", "alphabeta_ordered_nodes", "minimax_ms", "alphabeta_ms", "alphabeta_ordered_ms"}] (default board = empty, default depths [1..5]; cap minimax depth at 6)
- `POST /api/analyze`       {moves: [cols], depth? (default 7, clamped 1..8)} -> analyze_game result; 400 for illegal or empty move lists

## Design direction

Clean, modern, "premium": dark-first with a light theme toggle (tokens on :root,
`data-theme` attribute on <html>, saved in localStorage with try/catch).
Montserrat + JetBrains Mono, self-hosted from `static/fonts/`. Colour scheme is
Rajalakshmi Engineering College (REC) purple (#6a1b9a primary, #8e24aa mid,
#b756f2 bright, lavender #f3e8ff). Glassy cards, subtle grid backdrop, one accent
gradient (REC purple). Red disc = #f43f5e-ish, Yellow =
#facc15-ish with glossy radial gradients. Smooth disc-drop animation, hover column
preview ghost disc, winning-line glow, confetti on human win (vanilla). Breadcrumbs
on every page. Keyboard: 1–7 drop disc, U undo, N new game, H hint, R review. Responsive down to
360px. Respect prefers-reduced-motion. No lorem ipsum anywhere.
