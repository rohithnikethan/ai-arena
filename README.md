# AI Arena — Watch AI Think

AI Arena is a Connect Four playground in which five classic game-playing agents (Random, Greedy, Minimax, Alpha-Beta and Monte Carlo Tree Search) play you or each other while their reasoning is drawn live: the search tree they explored, the branches alpha-beta cut away, the value or win rate of every column, and a sentence in plain English saying why the move was chosen. The engine is pure Python on a bitboard representation, every number on screen comes from the real search, and a benchmark script reproduces the results reported below. It was built as a Foundations of AI course project to make adversarial search something you can *see*, not just read about.

---

## Contents

1. [Features](#features)
2. [Quick start](#quick-start)
3. [Architecture](#architecture)
4. [Problem formulation](#problem-formulation)
5. [Algorithms](#algorithms)
6. [Heuristic evaluation function](#heuristic-evaluation-function)
7. [Bitboard representation](#bitboard-representation)
8. [Results](#results)
9. [Explainability](#explainability)
10. [API reference](#api-reference)
11. [Testing](#testing)
12. [Limitations and future work](#limitations-and-future-work)
13. [References](#references)

---

## Features

- **Five agents, one interface.** Random, Greedy (one-ply), Minimax, Alpha-Beta with center-first move ordering, and MCTS/UCT. Each can be tuned: search depth 1–8 (Minimax is capped at 6), MCTS iterations 50–20,000.
- **Live "AI Mind" panel.** After every AI move you see the search tree (up to 3 plies, at most 400 nodes), per-column scores or win rates, MCTS visit counts, nodes searched, branches pruned, time, nodes/sec, and the principal variation (the line of play the agent expects).
- **Plain-English explanations.** For example, "Blocks Red's immediate threat in column 4." or "Most-explored move after 1,500 simulations: column 4 (435 visits, 53% win rate); runner-up column 5 (271 visits, 49%)."
- **Five pages.**
  - **Home** (`/`): introduction, the agents as cards, calls to action.
  - **Play** (`/play`): you against any agent, with the AI Mind panel beside the board.
  - **Arena** (`/arena`): pick two agents and watch them play move by move, with both minds visible.
  - **Lab** (`/lab`): run tournaments and chart wins, time and nodes (Chart.js), plus a node-count comparison of Minimax and Alpha-Beta by depth.
  - **Learn** (`/learn`): how each algorithm works, with small diagrams and a complexity table.
- **Reproducible.** Stochastic agents are seedable, matches are deterministic for a given seed, and `benchmark.py` regenerates every table in this README.
- **Zero setup friction.** Python + Flask only: no Node, no build step, no API keys. Dark and light themes, keyboard controls (`1`–`7` drop a disc, `U` undo, `N` new game), responsive down to 360 px, and `prefers-reduced-motion` is respected.

---

## Quick start

Requires Python 3.10+ (developed on 3.13) and Flask.

```powershell
cd ai_arena
pip install flask
python app.py
```

Then open **http://localhost:5050**.

Run the test suite (standard-library `unittest`, no pytest needed):

```powershell
python -m unittest discover -s tests
```

Run the benchmark (about 45 seconds; it prints Markdown tables):

```powershell
python benchmark.py                    # presets, 6 games per pairing, seed 0
python benchmark.py --games 10 --seed 1
python benchmark.py --quick            # MCTS 400 iterations, Alpha-Beta depth 5
python benchmark.py --max-depth 7      # deeper node-count table
```

---

## Architecture

```
ai_arena/
  app.py              thin Flask layer: page routes + JSON API, no game logic
  engine/             pure Python, no Flask imports
    __init__.py
    board.py          bitboard representation, rules, win detection
    evaluate.py       heuristic evaluation (69-window scoring)
    agents.py         RandomAgent, GreedyAgent, MinimaxAgent, AlphaBetaAgent, MCTSAgent
    tracing.py        search-tree capture, capping and annotation for visualisation
    api.py            the only module app.py calls: validation, presets, choose_move, run_match, compare_depth
  tests/              unittest suites: test_board.py, test_agents.py, test_api.py
  benchmark.py        CLI tournament + minimax vs alpha-beta node counts
  templates/          Jinja templates (base.html + one per page)
  static/             vanilla CSS and JS (board rendering, tree view, charts)
  README.md
```

The code has three layers, and each layer depends only on the one below it:

| Layer | Responsibility | Knows about |
|---|---|---|
| `engine/` | Rules, search, evaluation, explanations, tree traces | Nothing outside the standard library |
| `app.py` | HTTP routing, JSON parsing, 400 errors, rendering templates | `engine.api` only |
| `static/` + `templates/` | Board UI, animations, tree and chart rendering | The JSON API |

Because the engine has no web dependency, it can be unit-tested, benchmarked from the command line, and reused without a server. The frontend is plain HTML/CSS/JS (D3 7.8.5 and Chart.js 4.4.1 from a CDN), so there is no build step.

### Request flow (one AI move)

```
 Browser (static/js)                Flask (app.py)                 engine/api.py              engine/agents.py
 -------------------                --------------                 -------------              ----------------
 POST /api/move  ------------------> parse JSON, basic checks
 {board, player, agent}              |
                                     +--> choose_move(board, player, config)
                                                    |  validate_board (shape, values,
                                                    |  gravity, disc counts)
                                                    |  normalize_config (defaults, clamping)
                                                    +--> Board.from_grid -> bitboards
                                                    +--> create_agent(cfg).choose(...)  ---> search + trace
                                                    <---------------------------------------  result dict
                                     <--- JSON (column, scores, stats, explanation, tree)
 animate drop, draw tree, bars <---- 200 OK   (or 400 {"error": "..."} on bad input)
```

---

## Problem formulation

Connect Four is a two-player, deterministic, turn-taking, zero-sum game of perfect information. It therefore fits the adversarial search framework of AIMA Chapter 5 (Russell & Norvig, 4th ed.).

| Element | Definition in this project |
|---|---|
| **State** | A 6×7 grid, each cell empty, Red (1) or Yellow (2). Internally this is two 49-bit integers (see [Bitboards](#bitboard-representation)). |
| **Initial state** | The empty board. Red moves first. |
| **PLAYER(s)** | Red if the number of discs is even, otherwise Yellow. |
| **ACTIONS(s)** | The columns `0..6` that hold fewer than 6 discs. |
| **RESULT(s, a)** | The mover's disc lands in the lowest empty cell of column `a`. |
| **TERMINAL-TEST(s)** | One player has four in a row (horizontal, vertical or either diagonal), or all 42 cells are full. |
| **UTILITY(s, p)** | Win +1, draw 0, loss −1. In search this is scaled to **±(1,000,000 − ply)**, so faster wins (and slower losses) are preferred. Draws are 0. |

**Size.** The branching factor is at most 7 and shrinks as columns fill, so it is about 7 for most of the game. A game lasts at most 42 plies, which gives a loose game-tree bound of 7^42 ≈ 3×10^35. The number of distinct legal positions is about **4.5×10^12** (4,531,985,219,092; Edelkamp & Kissmann 2008). That is far too many to enumerate in Python during play, so every agent here uses depth-limited search or sampling. The game is solved: with perfect play the first player wins by starting in the center column (Allis 1988).

---

## Algorithms

All agents expose the same method, `choose(board, player, trace=True)`, and return the same result shape. Search values are always reported from the root player's perspective.

### Random

Picks a uniformly random legal column using a seedable `random.Random`. It is the baseline every other agent must beat.
**Time** O(b) · **Space** O(1).

### Greedy (one-ply lookahead)

The priority order is:

1. Play an immediate win.
2. Otherwise block the opponent's immediate win (if there are several, block the one with the best heuristic score).
3. Otherwise play the move whose resulting position has the highest heuristic score. Ties are broken at random (seedable).

**Time** O(b · W), where W = 69 is the number of scoring windows · **Space** O(1).

### Minimax (depth-limited)

This is textbook MINIMAX-SEARCH, cut off at depth *d*. Below the cutoff, non-terminal leaves are scored with the heuristic. Terminal positions are detected right after each move: a win at ply *k* scores ±(1,000,000 − k) and a full board scores 0. Moves are made and unmade in place on the bitboards, so no position is copied. Leaf evaluations are memoised per search, keyed on the position. This saves time but does not change the node count.

**Time** O(b^d) · **Space** O(d) (one board, mutated in place, plus the recursion stack).

From the empty board the node count is exactly the full tree, 1 + 7 + 7² + … + 7^d (for example 400 nodes at d = 3), and a test checks this.

### Alpha-Beta pruning with move ordering

This is the same search with α (the best value Max can already guarantee) and β (the best value Min can already guarantee) carried down the tree. When α ≥ β at a node, its remaining siblings cannot affect the root decision and are skipped (fail-soft). `stats.pruned` counts the sibling subtrees skipped at cut-offs. The root value is **identical to plain Minimax at the same depth**, and the tests verify this on 7 positions × 4 depths × both orderings.

Move ordering matters a great deal. With `move_ordering=True`, columns are tried center-first, `(3, 2, 4, 1, 5, 0, 6)`. Central moves take part in the most four-in-a-row lines and are usually strongest, so good moves are found early and cut-offs come sooner.

**Time** best case O(b^(d/2)) with perfect ordering (Knuth & Moore 1975), about O(b^(3d/4)) with random ordering, and O(b^d) in the worst case · **Space** O(d).

For root moves that fail low, `column_scores` holds an upper bound rather than the exact value. This is the nature of alpha-beta: the search proves "no better than the best", not the exact score.

### Monte Carlo Tree Search (UCT)

Each iteration has four phases (Kocsis & Szepesvári 2006):

1. **Selection.** From the root, descend through fully expanded nodes, choosing the child that maximises UCB1:

   ```
   UCT(i) = w_i / n_i  +  c · sqrt( ln N / n_i ),      c = √2 ≈ 1.414
   ```

   Here `w_i` is the wins from the point of view of the player who moved into child *i*, `n_i` is that child's visit count, and `N` is the parent's visit count. The first term exploits moves that have done well. The second explores moves that have been tried rarely.
2. **Expansion.** Add one random untried move as a new node.
3. **Simulation.** Play the game out to the end. Moves are random, except that the rollout policy is lightly tactical (`smart_rollouts`, on by default): a player who can win immediately does so, and otherwise blocks an immediate opponent win. This removes a lot of noise from purely random playouts at little cost.
4. **Backpropagation.** Update every node on the path: +1 for a win by the node's mover, +0.5 for a draw.

The **most-visited** root child is played (the "robust child"). Ties are broken by win rate, then by closeness to the center. `column_scores` holds each move's win rate (0–1) and `column_visits` its visit count. The default is 1,500 iterations, and the allowed range is 50–20,000.

**Time** O(n · (D + L)) for *n* iterations, tree depth *D* and rollout length L ≤ 42 · **Space** O(n): one tree node per iteration.

### Complexity summary

| Agent | Time per move | Memory | Optimal? |
|---|---|---|---|
| Random | O(b) | O(1) | No |
| Greedy | O(b·W), W = 69 | O(1) | No |
| Minimax, depth d | O(b^d) | O(d) | Optimal *with respect to the heuristic* at depth d |
| Alpha-Beta, depth d | O(b^(d/2)) best, O(b^d) worst | O(d) | Same move value as Minimax at depth d |
| MCTS, n iterations | O(n·(D + L)) | O(n) | Converges to minimax as n → ∞ (UCT result) |

---

## Heuristic evaluation function

Depth-limited search needs an estimate for non-terminal leaves. `engine/evaluate.py` uses classic **window scoring**. All **69** four-cell lines ("windows") on the 6×7 board (24 horizontal, 21 vertical, 12 per diagonal direction) are precomputed as bit masks. A window that contains discs of both players can never become a four, so it scores nothing. Otherwise, from the evaluating player's view:

| Pattern | Weight |
|---|---:|
| Each own disc in the center column | **+3** |
| Each opponent disc in the center column | **−3** |
| Own 2 discs + 2 empty in a window | **+2** |
| Own 3 discs + 1 empty in a window | **+5** |
| Opponent 2 discs + 2 empty in a window | **−1** |
| Opponent 3 discs + 1 empty in a window (a threat) | **−4** |
| Four in a window (only if called on a won position) | ±100 |

In code: `CENTER_WEIGHT = 3`, `OWN_WEIGHTS = (0, 0, 2, 5, 100)`, `OPP_WEIGHTS = (0, 0, 1, 4, 100)`.

**On "admissibility".** Admissibility (never overestimating the true cost to a goal) is a property of heuristics for A* and other optimal path-finding searches. It does not apply here. An evaluation function in adversarial search is not a cost-to-go bound. AIMA §5.4 asks something different of it: that it order terminal states the same way as the true utility, that it be cheap to compute, and that on non-terminal states it correlate strongly with the actual chance of winning. This function is reasonable by those criteria:

- **It agrees with the utility on terminal states.** Search scores proven wins and losses as ±(1,000,000 − ply) before the heuristic is ever consulted, and every heuristic score is a small integer far below that magnitude. A proven result therefore always dominates an estimate.
- **It measures what actually wins the game.** It counts the four-in-a-row lines that are still possible. A window blocked by both colours is worth nothing, a three with an open cell is a real threat, and the center column takes part in the most windows (it can appear in lines in all four directions).
- **It favours the player to move.** Opponent threes (−4) are weighted slightly below own threes (+5), and opponent twos (−1) below own twos (+2), because the player to move gets to act on a threat first. The asymmetry makes the function only *approximately* zero-sum. That is harmless because search always evaluates from the root player's perspective.
- **It is cheap.** One call is 69 AND-and-popcount operations on Python integers.

It is hand-tuned, not learned or proven, and it knows nothing of Connect Four's deeper parity theory (see [Limitations](#limitations-and-future-work)).

---

## Bitboard representation

`engine/board.py` stores a position as **two Python integers**, one per player, using the classic 7-bits-per-column layout:

```
  6 13 20 27 34 41 48   <- sentinel row (always 0)
  5 12 19 26 33 40 47   <- top row
  4 11 18 25 32 39 46
  3 10 17 24 31 38 45
  2  9 16 23 30 37 44
  1  8 15 22 29 36 43
  0  7 14 21 28 35 42   <- bottom row
```

Bit index = `col * 7 + height`. A per-column `heights` array records the next free bit in each column.

- **Make a move:** `bb[p] |= 1 << heights[c]; heights[c] += 1`. **Undo:** the reverse XOR. Both are O(1), so search never copies a board.
- **Four-in-a-row test:** for each direction shift `s ∈ {1 (vertical), 7 (horizontal), 8 (diagonal /), 6 (diagonal \)}`, compute `m = bb & (bb >> s)`. A win exists if `m & (m >> 2s)` is non-zero. That is eight shift-and-AND operations in total, with no loops over cells.
- **The sentinel row** (bits 6, 13, …, 48) is always empty. It stops a line pattern from wrapping from the top of one column into the bottom of the next, and a dedicated test (`test_no_wraparound`) checks this.

The public API still speaks the spec's human-friendly 6×7 list-of-lists format (row 0 = top), and `Board.from_grid` / `Board.to_grid` convert at that boundary.

---

## Results

Generated by `python benchmark.py` (6 games per pairing, colours alternate, seed 0, total runtime 46.8 s on the development laptop, Python 3.13). Agents use the presets: Minimax depth 4, Alpha-Beta depth 6 with ordering, MCTS 1,500 iterations.

### Head-to-head

| Agent A | Agent B | A wins | B wins | Draws | A ms/move | B ms/move | Wall s |
|---|---|---:|---:|---:|---:|---:|---:|
| Random | Greedy | 0 | 6 | 0 | 0.0 | 0.1 | 0.0 |
| Random | Minimax (depth 4) | 0 | 6 | 0 | 0.0 | 15.2 | 0.4 |
| Random | Alpha-Beta (depth 6) | 0 | 6 | 0 | 0.0 | 16.0 | 0.6 |
| Random | MCTS (1,500 iterations) | 0 | 6 | 0 | 0.0 | 266.5 | 7.5 |
| Greedy | Minimax (depth 4) | 0 | 6 | 0 | 0.1 | 20.1 | 1.1 |
| Greedy | Alpha-Beta (depth 6) | 1 | 5 | 0 | 0.1 | 20.6 | 1.0 |
| Greedy | MCTS (1,500 iterations) | 0 | 6 | 0 | 0.1 | 141.3 | 7.6 |
| Minimax (depth 4) | Alpha-Beta (depth 6) | 0 | 6 | 0 | 7.6 | 8.5 | 1.7 |
| Minimax (depth 4) | MCTS (1,500 iterations) | 3 | 3 | 0 | 9.4 | 120.2 | 12.6 |
| Alpha-Beta (depth 6) | MCTS (1,500 iterations) | 4 | 2 | 0 | 16.1 | 119.5 | 13.6 |

### Standings

| Agent | W | L | D | Score % | avg ms/move | avg nodes/move |
|---|---:|---:|---:|---:|---:|---:|
| Alpha-Beta (depth 6) | 21 | 3 | 0 | 88 | 15.3 | 2,865 |
| MCTS (1,500 iterations) | 17 | 7 | 0 | 71 | 161.9 | 1,183 |
| Minimax (depth 4) | 15 | 9 | 0 | 62 | 13.1 | 1,822 |
| Greedy | 7 | 17 | 0 | 29 | 0.1 | 6 |
| Random | 0 | 24 | 0 | 0 | 0.0 | 7 |

### Minimax vs alpha-beta: nodes searched from the empty board

| Depth | Minimax nodes | Alpha-beta nodes | Alpha-beta + ordering | Minimax ms | Alpha-beta ms | Ordered ms | Saving (ordered) |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 8 | 8 | 8 | 0.1 | 0.1 | 0.1 | 0.0% |
| 2 | 57 | 33 | 21 | 0.5 | 0.3 | 0.2 | 63.2% |
| 3 | 400 | 200 | 76 | 2.7 | 1.4 | 0.5 | 81.0% |
| 4 | 2,801 | 849 | 180 | 14.5 | 5.2 | 1.1 | 93.6% |
| 5 | 19,608 | 4,175 | 621 | 77.3 | 30.5 | 4.2 | 96.8% |
| 6 | 137,257 | 15,976 | 1,371 | 409.1 | 76.3 | 6.2 | 99.0% |

### Interpretation

- **Pruning is where the power comes from.** At depth 6, alpha-beta with center-first ordering visits **1,371** nodes where Minimax visits **137,257**. That is **99.0% fewer nodes, a 100× reduction**, and a 66× speed-up (409 ms down to 6.2 ms), with the same root value. Even without ordering, pruning skips 88.4% of the tree (15,976 nodes).
- **Ordering is worth almost as much as pruning itself.** At depth 6, center-first ordering alone cuts alpha-beta's work by a further **11.7×** (15,976 down to 1,371). The effective branching factor, N^(1/d), falls from about 7.2 for Minimax to 5.0 for unordered alpha-beta and **3.3** for ordered alpha-beta. The Knuth–Moore ideal is √7 ≈ 2.65, and the minimal tree at depth 6 has 7³ + 7³ − 1 = 685 leaves, so the ordered search is within a small constant factor of the theoretical best case.
- **The savings let the agent search deeper for the same cost.** Alpha-Beta at depth 6 costs about the same per move as Minimax at depth 4 (15.3 vs 13.1 ms on average), and it won all 6 games between them. Two extra plies of lookahead is a large advantage in a game decided by threats.
- **MCTS is competitive without any domain heuristic.** With only win/loss/draw outcomes and lightly tactical rollouts, 1,500 iterations reached second place (71%), tied Minimax-4 3–3, and took 2 of 6 games from Alpha-Beta-6. It is the slowest agent per move (about 120–270 ms) because each iteration plays a full game in Python.
- **Greedy's one win over Alpha-Beta** shows the horizon effect and the limits of a hand-tuned heuristic. Depth 6 is still short of a 42-ply game, and Greedy's randomised tie-breaking occasionally steers into a line the heuristic misjudges.
- **Caveat on sample size.** Six games per pairing is enough to show clear gaps, not to rank close agents with confidence. Pairings of two deterministic agents (for example Minimax vs Alpha-Beta) effectively replay two distinct games, one per colour. Run `python benchmark.py --games 20` for tighter estimates.

---

## Explainability

The project is called "Watch AI Think", so every move comes with two artefacts: a sentence and a tree.

### Natural-language explanations

`tactical_reason()` in `engine/agents.py` first checks the chosen move against an ordered list of tactical facts, each verified on the bitboards:

1. **Immediate win:** "Wins immediately: column 4 completes four in a row for Red."
2. **Block:** "Blocks Yellow's immediate threat in column 4." If other threats remain it adds "…still threatens column 6, so the position is critical."
3. **Double threat:** "Sets up a double threat: Red now threatens to win in column 2 and column 5, and Yellow can only block one."
4. **Single threat:** "Creates a threat: Red threatens to win next in column 3."

Then each agent appends what its own algorithm saw:

- **Minimax / Alpha-Beta** report the depth, the number of positions, the branches pruned, and either a forced result ("found a forced win: Red wins within 2 of its own moves whatever Yellow does", or "sees a forced loss in 5 plies… holds out the longest") or the heuristic score compared with the runner-up. They also name any columns that would let the opponent force a win.
- **MCTS** reports simulations, visits and win rate for the chosen move and the runner-up.
- **Greedy / Random** say that they looked one move ahead or not at all. Random notes "By luck: …" if its random move happened to be tactically meaningful.

A real example (Alpha-Beta, depth 6): *"Alpha-beta with center-first ordering (depth 6, 2,636 positions, 3,109 branches pruned) rates column 4 best with a score of +4; pruning proved no other column scores higher."*

### Search-tree traces

- **Minimax / Alpha-Beta** build the trace *during* the search, but only for the first `MAX_PLIES = 3` plies. Each node records its move, the mover, its value (from the root's perspective), and the α/β window on entry. Infinite bounds are serialised as `null`. At a cut-off, the skipped siblings are added as stub nodes with `"pruned": true` and no children, so the UI can show exactly where pruning happened.
- **MCTS** builds the trace *after* search from the real tree, recording visits, wins (from the mover's view) and the root player's win rate as `value`.
- **The principal variation** is marked with `"best": true` along the expected line of play.
- **Capping** (`tracing.cap_tree`) trims the tree to at most `MAX_NODES = 400` nodes. Nodes are admitted breadth-first. Within each level, children on the best line come first, then the rest by visits or value, taken round-robin across parents so that every parent keeps its most relevant children.
- **Tracing is purely observational.** A test asserts that `stats.nodes`, `stats.pruned` and the chosen column are identical with tracing on or off. Matches and benchmarks run with `trace: false`.

---

## API reference

All endpoints take and return JSON. Bad input returns HTTP **400** with `{"error": "<message>"}`. The message is meant for a person to read, for example `"floating disc in column 2 (row 3 below it is empty)"` or `"impossible disc counts: Red has 4, Yellow has 1 (Red moves first, so Red must have the same number or one more)"`. Boards are 6×7 lists of lists with row 0 at the top (0 empty, 1 Red, 2 Yellow). Columns are 0-indexed in JSON, and explanations use 1-indexed "column 4" for people.

Board validation checks the shape, that cell values are 0/1/2, gravity (no floating discs), disc counts (Red has the same number as Yellow or one more), and that both players do not have four in a row. Configs are clamped: `depth` to 1–8 (Minimax to at most 6) and `iterations` to 50–20,000.

The JSON examples below are real engine output. The position is after the moves 4, 4, 3, 5, 5 (1-indexed columns), and Yellow is to move:

```json
"board": [[0,0,0,0,0,0,0],
          [0,0,0,0,0,0,0],
          [0,0,0,0,0,0,0],
          [0,0,0,0,0,0,0],
          [0,0,0,2,1,0,0],
          [0,0,1,1,2,0,0]]
```

### `GET /api/agents`

Returns the agent presets, keyed by id.

```json
{
  "alphabeta": {"type": "alphabeta", "label": "Alpha-Beta", "depth": 6, "move_ordering": true,
                "description": "Minimax 6 plies deep that skips branches which provably cannot change the decision, searching center columns first."},
  "mcts":      {"type": "mcts", "label": "Monte Carlo Tree Search", "iterations": 1500, "seed": null, "description": "..."},
  "minimax":   {"type": "minimax", "label": "Minimax", "depth": 4, "description": "..."},
  "greedy":    {"type": "greedy", "label": "Greedy", "seed": null, "description": "..."},
  "random":    {"type": "random", "label": "Random", "seed": null, "description": "..."}
}
```

### `POST /api/state`

```json
// request
{"board": [[0,0,0,0,0,0,0], ..., [0,0,1,1,2,0,0]]}
// response
{"winner": 0, "draw": false, "winning_cells": [], "valid_moves": [0,1,2,3,4,5,6], "to_move": 2}
```

`winning_cells` lists `[row, col]` pairs of every completed line once the game is won.

### `POST /api/apply`

Plays a human move. The server checks that the column is legal, so the browser never needs the rules.

```json
// request
{"board": [[0,0,0,0,0,0,0], ..., [0,0,1,1,2,0,0]], "column": 3}
// response
{"board": [[...]], "state": {"winner": 0, "draw": false, "winning_cells": [], "valid_moves": [0,1,2,3,4,5,6], "to_move": 1}}
```

### `POST /api/move`

Agent config fields: `type` (`random | greedy | minimax | alphabeta | mcts`), `depth` (default 5), `iterations` (default 1500), `move_ordering` (default `true`), `trace` (default `true`), `seed` (`int | null`).

```json
// request
{"board": [...], "player": 2, "agent": {"type": "alphabeta", "depth": 6}}
// response (board_after and tree abbreviated)
{
  "column": 3,
  "board_after": [[...]],
  "state_after": {"winner": 0, "draw": false, "winning_cells": [], "valid_moves": [0,1,2,3,4,5,6], "to_move": 1},
  "column_scores": [3.0, 1.0, 2.0, 4.0, 3.0, 1.0, 3.0],
  "column_visits": [null, null, null, null, null, null, null],
  "stats": {"nodes": 2636, "pruned": 3109, "time_ms": 14.206, "nodes_per_sec": 185555,
            "depth": 6, "iterations": null, "max_depth_reached": 6},
  "explanation": "Alpha-beta with center-first ordering (depth 6, 2,636 positions, 3,109 branches pruned) rates column 4 best with a score of +4; pruning proved no other column scores higher.",
  "principal_variation": [3, 3, 4, 4, 3, 0],
  "tree": {"id": "root", "move": null, "player": 2, "value": 4.0, "alpha": null, "beta": null,
           "visits": null, "wins": null, "pruned": false, "best": true, "terminal": false,
           "children": [{"id": "root.0", "move": 0, "player": 2, "...": "..."}]}
}
```

The same position with `{"type": "mcts", "iterations": 1500, "seed": 1}`:

```json
{
  "column": 3,
  "column_scores": [0.4624, 0.4436, 0.3837, 0.5345, 0.4852, 0.3366, 0.3951],
  "column_visits": [226, 195, 129, 435, 271, 101, 143],
  "stats": {"nodes": 1485, "pruned": 0, "time_ms": 274.017, "nodes_per_sec": 5419,
            "depth": null, "iterations": 1500, "max_depth_reached": 6},
  "explanation": "Most-explored move after 1,500 simulations: column 4 (435 visits, 53% win rate); runner-up column 5 (271 visits, 49%).",
  "principal_variation": [3, 1, 0, 4, 3, 5]
}
```

TreeNode fields: `id` (the move path, for example `"root.3.4"`), `move`, `player` (who dropped the disc for this move; for the root, who is choosing), `value` (root perspective), `alpha` / `beta` (alpha-beta, `null` when infinite), `visits` / `wins` (MCTS), `pruned`, `best`, `terminal`, `children`. JSON has no Infinity, so when the web layer sends a value that is infinite it uses ±1e9 instead.

### `POST /api/match`

Plays `games` games (1–50). Colours alternate: Agent A moves first in game 1, Agent B in game 2, and so on. Results are deterministic for a given `seed`.

```json
// request
{"agent_a": {"type": "alphabeta", "depth": 6}, "agent_b": {"type": "random"}, "games": 2}
// response
{
  "games": 2, "a_wins": 2, "b_wins": 0, "draws": 0,
  "a": {"avg_time_ms": 10.93, "avg_nodes": 1740.0, "label": "Alpha-Beta (depth 6)"},
  "b": {"avg_time_ms": 0.007, "avg_nodes": 7.0, "label": "Random"},
  "results": [
    {"first": "a", "winner": "a", "moves": [3, 1, 4, 4, 5, 6, 2], "length": 7},
    {"first": "b", "winner": "a", "moves": [1, 3, 4, 3, 4, 3, 1, 3], "length": 8}
  ]
}
```

### `POST /api/compare-depth`

`board` is optional (the default is the empty board). `depths` takes values from 1–7. Minimax is capped at depth 6; deeper rows report `null` for the Minimax fields. `alphabeta_*` is natural left-to-right ordering, and `alphabeta_ordered_*` is center-first.

```json
// request
{"depths": [1, 2, 3]}
// response
[
  {"depth": 1, "minimax_nodes": 8,   "alphabeta_nodes": 8,   "alphabeta_ordered_nodes": 8,  "minimax_ms": 0.128, "alphabeta_ms": 0.106, "alphabeta_ordered_ms": 0.113},
  {"depth": 2, "minimax_nodes": 57,  "alphabeta_nodes": 33,  "alphabeta_ordered_nodes": 21, "minimax_ms": 0.756, "alphabeta_ms": 0.511, "alphabeta_ordered_ms": 0.461},
  {"depth": 3, "minimax_nodes": 400, "alphabeta_nodes": 200, "alphabeta_ordered_nodes": 76, "minimax_ms": 4.248, "alphabeta_ms": 2.173, "alphabeta_ordered_ms": 0.932}
]
```

---

## Testing

```powershell
python -m unittest discover -s tests
```

```
Ran 41 tests in 3.769s
OK
```

**41 tests** in three suites, using only the standard library:

| Suite | Tests | What it covers |
|---|---:|---|
| `test_board.py` | 13 | Empty board; gravity and grid round-trip; horizontal, vertical and both diagonal wins; **no wrap-around across the sentinel row**; full columns; draws; `winning_moves`; exactly 69 windows; evaluation symmetry and center preference; opponent threats penalised |
| `test_agents.py` | 13 | Every agent takes an immediate win and blocks an immediate loss, with the correct explanation text; MCTS finds a win-in-one across seeds; alpha-beta finds a double-threat forced win; **alpha-beta returns the same value as minimax** on 7 positions × depths 1–4 × both orderings, with strictly fewer nodes from depth 3; ordering reduces nodes; exact full-tree node count (400 at depth 3); tracing does not change node or prune counts or the chosen move; tree ≤ 400 nodes and ≤ 3 plies with a correctly marked best line; pruned nodes are marked and childless; MCTS visit totals equal the iteration count; seeded agents are deterministic; Random only plays legal moves |
| `test_api.py` | 15 | Preset shapes and usability; `game_state` shape and wins; board validation errors (shape, non-integer and out-of-range values including booleans, floating discs, impossible disc counts); returning a copy of the input; `choose_move` errors for a bad player, unknown agent type, non-integer depth and finished games; depth and iteration clamping; result shapes for every agent; `trace: false`; preset strings; match shape and **determinism by seed**; strong agents beat Random; `compare_depth` on default and custom boards |

---

## Limitations and future work

**Limitations**

- **Python speed.** Alpha-beta runs at about 185k nodes/s and MCTS at about 5k tree nodes/s (each with a full rollout). A C or Rust bitboard engine would be 50–100× faster and reach far deeper.
- **No transposition table and no iterative deepening.** Minimax and alpha-beta memoise leaf evaluations only. Transpositions (the same position reached by different move orders) are searched again, and depth is fixed rather than time-controlled.
- **Fixed, simple move ordering.** Center-first is a static order. Killer moves, the history heuristic, or ordering by the previous iteration's PV would bring alpha-beta closer to the √b ideal.
- **Hand-tuned heuristic.** The window weights were chosen by reasoning, not fitted. The heuristic also ignores Connect Four's odd/even threat parity (zugzwang), which Allis showed is central to perfect play. That is a likely cause of the occasional loss to Greedy.
- **Plain UCT.** There is no RAVE/AMAF, no progressive bias, and no tree reuse between moves (the tree is rebuilt every turn). The fixed c = √2 was not tuned for this game.
- **Alpha-beta column scores** for non-best root moves are upper bounds, not exact values, so the UI's column bars are exact only for the chosen move.
- **Small benchmark samples.** Six games per pairing, and deterministic agents replay the same games. The results show orderings of strength, not precise ratings.

**Future work**

- A transposition table keyed by the bitboard pair, plus iterative deepening with a time budget and PV-first ordering.
- A perfect-play negamax solver for late-game positions, to show the gap between heuristic and solved play.
- Threat-parity features in the evaluation, and weights tuned by self-play or regression.
- MCTS improvements: tree reuse, RAVE, a tuned c, and heuristic-guided rollouts. A side-by-side "MCTS vs Alpha-Beta at equal time" lab experiment.
- Elo ratings computed from larger tournaments.

---

## References

1. S. Russell and P. Norvig. *Artificial Intelligence: A Modern Approach*, 4th ed. Pearson, 2020. Chapter 5, "Adversarial Search and Games" (minimax, alpha-beta, evaluation functions, MCTS).
2. D. E. Knuth and R. W. Moore. "An Analysis of Alpha-Beta Pruning." *Artificial Intelligence* 6(4):293–326, 1975.
3. L. Kocsis and C. Szepesvári. "Bandit Based Monte-Carlo Planning." *Proceedings of ECML 2006*, LNCS 4212, pp. 282–293. Springer, 2006.
4. L. V. Allis. *A Knowledge-Based Approach of Connect-Four. The Game is Solved: White Wins.* M.Sc. thesis, Vrije Universiteit Amsterdam, 1988.
5. S. Edelkamp and P. Kissmann. "Symbolic Classification of General Two-Player Games." *KI 2008*, LNCS 5243, pp. 185–192. Springer, 2008. (Source of the exact position count.)
