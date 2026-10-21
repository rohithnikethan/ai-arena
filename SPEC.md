# AI Arena — Build Spec (shared contract)

"Watch minds think." A Connect Four arena where classic game-playing AI agents
play you or each other, and their reasoning (the search tree, pruning, MCTS
statistics) is visualised live. Foundations of AI course project.

Stack: Python 3.13 + Flask (already installed). Frontend is plain HTML/CSS/vanilla
JS with Jinja templates. CDN libs allowed only from cdnjs.cloudflare.com or
cdn.jsdelivr.net with exact versions (D3 `7.8.5`, Chart.js `4.4.1`). No Node, no
build step, no API keys. Runs with `python app.py` on http://localhost:5050.

## Layout

```
ai_arena/
  app.py                 # thin Flask layer: routes + JSON API, no game logic
  engine/                # pure Python, NO flask imports
    __init__.py
    board.py             # Board representation, rules, win detection
    evaluate.py          # heuristic evaluation function (window scoring)
    agents.py            # RandomAgent, GreedyAgent, MinimaxAgent, AlphaBetaAgent, MCTSAgent
    tracing.py           # search-tree capture for visualisation
    api.py               # the ONLY module app.py calls (functions below)
  tests/                 # unittest (pytest NOT installed): python -m unittest discover -s tests
  benchmark.py           # CLI: python benchmark.py -> prints a markdown results table
  templates/  static/    # frontend
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
    # config: {"type": "random"|"greedy"|"minimax"|"alphabeta"|"mcts",
    #          "depth": int (minimax/alphabeta, 1..8, default 5),
    #          "iterations": int (mcts, 50..20000, default 1500),
    #          "move_ordering": bool (alphabeta, default True),
    #          "trace": bool (default True), "seed": int|None}
    # returns:
    # {
    #   "column": int,
    #   "board_after": board, "state_after": game_state(...),
    #   "column_scores": [float|None]*7,   # minimax value per root move, or MCTS win-rate 0..1; None if illegal
    #   "column_visits": [int|None]*7,     # MCTS only, else None entries
    #   "stats": {"nodes": int, "pruned": int, "time_ms": float, "nodes_per_sec": int,
    #             "depth": int|None, "iterations": int|None, "max_depth_reached": int},
    #   "explanation": str,   # plain English: why this move (e.g. "Blocks Yellow's
    #                         # three-in-a-row in column 4", "Wins immediately",
    #                         # "Highest win rate after 1500 simulations (62%)")
    #   "principal_variation": [cols],  # expected line of play (minimax/alphabeta)
    #   "tree": TreeNode | None
    # }

def run_match(config_a, config_b, games=10, seed=0) -> dict
    # agents alternate who moves first. returns
    # {"games": int, "a_wins": int, "b_wins": int, "draws": int,
    #  "a": {"avg_time_ms", "avg_nodes", "label"}, "b": {...},
    #  "results": [{"first": "a"|"b", "winner": "a"|"b"|"draw", "moves": [cols], "length": int}]}
```

TreeNode (JSON-serialisable dict), capped for transfer size — at most
3 plies deep and ~400 nodes total; keep the most relevant children:

```
{"id": str, "move": int|None, "player": 1|2, "value": float|None,
 "alpha": float|None, "beta": float|None,
 "visits": int|None, "wins": float|None,   # MCTS
 "pruned": bool,     # this subtree was cut off by alpha-beta (children omitted)
 "best": bool,       # on the chosen/principal line
 "terminal": bool, "children": [TreeNode]}
```

Values: use +/- 1_000_000 (minus depth) for wins/losses, heuristic otherwise, from
the perspective of the player choosing at the root.

## Flask routes (app.py)

Pages (all extend `base.html`, share nav + breadcrumbs + light/dark toggle):
- `GET /`            Landing: hero, the 4 agents as cards, CTA buttons
- `GET /play`        Human vs AI: board + live "AI Mind" panel (tree, column bars, stats, explanation)
- `GET /arena`       AI vs AI: pick two agents, watch them play move by move, both minds visible
- `GET /lab`         Benchmark lab: run tournaments, Chart.js charts of wins / time / nodes; minimax vs alpha-beta node-count comparison by depth
- `GET /learn`       Theory: how each algorithm works, with small diagrams; complexity table
- 404 page

JSON API (JSON in/out, 400 with {"error": ...} on bad input; validate board shape/values, column legality, clamp depth/iterations):
- `GET  /api/agents`        -> AGENT_PRESETS
- `POST /api/state`         {board} -> game_state
- `POST /api/move`          {board, player, agent: config} -> choose_move result
- `POST /api/match`         {agent_a, agent_b, games (1..50)} -> run_match result
- `POST /api/compare-depth` {board?, depths:[1..7]} -> [{"depth", "minimax_nodes", "alphabeta_nodes", "alphabeta_ordered_nodes", "minimax_ms", "alphabeta_ms"}] (default board = empty; cap minimax depth at 6)

## Design direction

Clean, modern, "premium": dark-first with a light theme toggle (tokens on :root,
`data-theme` attribute on <html>, saved in localStorage with try/catch).
Inter + Space Grotesk + JetBrains Mono from Google Fonts. Glassy cards, subtle grid
backdrop, one accent gradient (violet→cyan). Red disc = #f43f5e-ish, Yellow =
#facc15-ish with glossy radial gradients. Smooth disc-drop animation, hover column
preview ghost disc, winning-line glow, confetti on human win (vanilla). Breadcrumbs
on every page. Keyboard: 1–7 drop disc, U undo, N new game. Responsive down to
360px. Respect prefers-reduced-motion. No lorem ipsum anywhere.
