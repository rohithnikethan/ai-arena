# AI Arena — Watch AI Think

AI Arena is a Connect Four playground in which five classic game-playing agents, each driven by a different decision algorithm (Random, Greedy, Minimax, Alpha-Beta and Monte Carlo Tree Search), play you or each other while their reasoning is drawn live: the search tree they explored, the branches alpha-beta cut away, the value or win rate of every column, and a sentence in plain English saying why the move was chosen. The engine is pure Python on a bitboard representation, every number in the AI Mind panel, the Lab and the game review comes from the real search (the animated board on the home page is a scripted illustration, not the real agents), and a benchmark script reproduces the results reported below. It was built as a Foundations of AI course project to make adversarial search something you can *see*, not just read about.

---

## Contents

1. [Features](#features)
2. [Quick start](#quick-start)
3. [Architecture](#architecture)
4. [Problem formulation](#problem-formulation)
5. [Algorithms](#algorithms)
6. [Heuristic evaluation function](#heuristic-evaluation-function)
7. [Bitboard representation](#bitboard-representation)
8. [Results](#results), including [What we found and fixed](#what-we-found-and-fixed-the-horizon-at-odd-depths)
9. [Explainability](#explainability), including [Game review](#game-review-post-game-analysis), the [Alpha-beta stepper](#alpha-beta-stepper-learn-page) and [Presentation mode](#presentation-mode)
10. [API reference](#api-reference)
11. [Testing](#testing)
12. [Limitations and future work](#limitations-and-future-work)
13. [References](#references)

---

## Features

- **Five agent programs, one interface.** Random, Greedy (one-ply), Minimax, Alpha-Beta with center-first move ordering, and MCTS/UCT. Each can be tuned: search depth 1–8 (Minimax is capped at 6), MCTS iterations 50–20,000.
- **Live "AI Mind" panel.** After every AI move you see the search tree (up to 3 plies, at most 400 nodes), per-column scores or win rates, MCTS visit counts, nodes searched, branches pruned, time, nodes/sec, and the principal variation (the line of play the agent expects). The tree can be zoomed, panned and navigated with the keyboard (Tab in, <kbd>↑</kbd>/<kbd>↓</kbd>/<kbd>←</kbd>/<kbd>→</kbd>, <kbd>Home</kbd>/<kbd>End</kbd>, <kbd>Enter</kbd> or <kbd>Space</kbd> to expand or collapse a node); **Fit** re-centres it and **Expand** shows it full screen.
- **Plain-English explanations.** For example, "Blocks Red's immediate threat in column 4." or "Most-explored move after 1,500 simulations: column 4 (435 visits, 53% win rate); runner-up column 5 (271 visits, 49%)."
- **Game review.** When a game on `/play` ends, **Review game** (or <kbd>R</kbd>) re-searches every position with exact full-window alpha-beta values (depth 7 by default), grades each move Best / Good / Inaccuracy / Mistake / Blunder, flags **Missed win** and **Allowed forced loss**, and draws an evaluation graph. See [Game review](#game-review-post-game-analysis).
- **Step-through alpha-beta debugger.** On `/learn`, alpha-beta (or plain minimax) really runs on a small tree and every event of its trace becomes one step: the [α, β] window passed down, bounds versus exact values, each cut-off and the principal variation. Trees: the AIMA Fig. 5.2 tree (pruning as in Fig. 5.5), best-case and worst-case ordering, and random trees. See [Alpha-beta stepper](#alpha-beta-stepper-learn-page).
- **Presentation mode.** `/present` is a 15-slide deck on the project with speaker notes (<kbd>S</kbd>), fullscreen (<kbd>F</kbd>) and deep links to a slide (`/present#10`). See [Presentation mode](#presentation-mode).
- **Six pages.**
  - **Home** (`/`): introduction, the agents as cards, and links to every page and feature.
  - **Play** (`/play`): you against any agent, with the AI Mind panel beside the board and the Game Review panel once the game is over.
  - **Arena** (`/arena`): pick two agents and watch them play move by move, with both minds visible.
  - **Lab** (`/lab`): run tournaments and chart wins, time and nodes (Chart.js), plus a node-count comparison of Minimax and Alpha-Beta by depth. A **Random opening** slider (0–6 plies, default 2) starts each game from random moves, each opening played twice with colours swapped; **Cancel** stops a running tournament or experiment.
  - **Learn** (`/learn`): how each algorithm works, with small diagrams, a complexity table and the step-through alpha-beta debugger.
  - **Present** (`/present`): the slide deck, for a talk or a viva.
- **Reproducible.** Stochastic agents are seedable, matches are deterministic for a given seed, and `benchmark.py` regenerates the benchmark tables in [Results](#results) (the "before the fix" columns there were measured with the pre-fix engine and are kept for comparison).
- **Zero setup friction.** Python + Flask only: no Node, no build step, no API keys. Dark and light themes in Rajalakshmi Engineering College (REC) purple, keyboard controls (`1`–`7` drop a disc, `U` undo, `N` new game, `H` hint, `R` review), responsive down to 360 px, and `prefers-reduced-motion` is respected.
- **Works offline.** No internet connection is needed at runtime. The fonts (Montserrat and JetBrains Mono, as `.woff2`) and the two libraries (D3 7.8.5 and Chart.js 4.4.1) are vendored in `static/fonts/` and `static/vendor/`. No template, stylesheet or script loads anything from a CDN or Google Fonts.

---

## Quick start

Requires Python 3.10+ (developed on 3.13) and Flask.

```powershell
cd ai-arena
pip install flask
python app.py
```

Then open **http://127.0.0.1:5050** (or http://localhost:5050). Debug mode (the Werkzeug debugger and auto-reload) is off by default; turn it on with the environment variable `AI_ARENA_DEBUG=1` (in PowerShell: `$env:AI_ARENA_DEBUG = "1"; python app.py`).

Run the test suite (standard-library `unittest`, no pytest needed):

```powershell
python -m unittest discover -s tests
```

Run the benchmark. It prints Markdown tables and spreads the games over worker processes; the full run took 26 s on a 24-thread machine and about 2 minutes with `--jobs 4`. Results do not depend on `--jobs`.

```powershell
python benchmark.py                    # 40 games per pairing from 20 random 2-ply openings
                                       # (colours swapped), seed 0, plus the depth sweep (98 games per cell)
python benchmark.py --quick            # 20 games, MCTS 400 iterations, Alpha-Beta depth 5, sweep 20 games (about 5 s)
python benchmark.py --games 80 --seed 1
python benchmark.py --openings 0       # old design: every game from the empty board (prints a warning:
                                       # the intervals are then not meaningful)
python benchmark.py --no-sweep         # skip the depth sweep; --sweep-games N sets its size
python benchmark.py --max-depth 7      # deeper node-count table
python benchmark.py --jobs 4           # number of worker processes (default: all CPUs)
```

---

## Architecture

```
ai-arena/
  app.py              thin Flask layer: page routes + JSON API, no game logic
  engine/             pure Python, no Flask imports
    __init__.py
    board.py          bitboard representation, rules, win detection
    evaluate.py       heuristic evaluation (69-window scoring)
    agents.py         RandomAgent, GreedyAgent, MinimaxAgent, AlphaBetaAgent, MCTSAgent
    tracing.py        search-tree capture, capping and annotation for visualisation
    api.py            the only module app.py calls: validation, presets, choose_move, run_match, compare_depth, analyze_game
    review.py         post-game review: exact per-move values, badges, explanations
  tests/              unittest suites (standard library only)
    test_board.py     rules, bitboards, evaluation
    test_agents.py    agent behaviour, alpha-beta = minimax, horizon-leaf check, tracing
    test_api.py       validation, integer policy, presets, matches and openings, compare_depth
    test_review.py    game review: exact values, badges, /api/analyze
    test_present.py   /present page and its static files
  benchmark.py        CLI tournament, alpha-beta depth sweep, minimax vs alpha-beta node counts
  templates/          Jinja templates
    base.html         shared layout: nav, breadcrumbs, theme toggle
    index.html, play.html, arena.html, lab.html, learn.html, 404.html
    _icons.html       inline SVG icon macro
    _ab_stepper.html  "Step through alpha-beta" widget, included by learn.html
    present.html      the 15-slide deck
  static/
    css/              style.css (tokens, layout, shared components), review.css,
                      stepper.css, present.css
    js/               common.js, board.js, mind.js, play.js, arena.js, lab.js,
                      review.js (Game Review panel), stepper.js (alpha-beta debugger),
                      present.js (deck: keys, fullscreen, notes, deep links)
    vendor/           d3-7.8.5.min.js, chart-4.4.1.umd.min.js (vendored, no CDN)
    fonts/            montserrat-latin-var.woff2, jetbrains-mono-latin-var.woff2
  docs/
    USER_GUIDE.md     how to use each page, demo script
    VIVA_PREP.md      pitch, demo script, likely viva questions with answers
  README.md
```

The code has three layers, and each layer depends only on the one below it:

| Layer | Responsibility | Knows about |
|---|---|---|
| `engine/` | Rules, search, evaluation, explanations, tree traces | Nothing outside the standard library |
| `app.py` | HTTP routing, JSON parsing, 400 errors, rendering templates | `engine.api` only |
| `static/` + `templates/` | Board UI, animations, tree and chart rendering | The JSON API |

Because the engine has no web dependency, it can be unit-tested, benchmarked from the command line, and reused without a server. The frontend is plain HTML/CSS/JS, with D3 7.8.5 and Chart.js 4.4.1 served from `static/vendor/`, so there is no build step and nothing is fetched from the internet.

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

Connect Four is a two-player, deterministic, turn-taking, zero-sum game of perfect information. It therefore fits the adversarial search framework of AIMA Chapter 5 (Russell & Norvig, 4th ed.). The function names below are the 4th edition's; the 3rd edition calls TO-MOVE and IS-TERMINAL `PLAYER` and `TERMINAL-TEST`.

| Element | Definition in this project |
|---|---|
| **State** | A 6×7 grid, each cell empty, Red (1) or Yellow (2). Internally this is two 49-bit integers (see [Bitboards](#bitboard-representation)). |
| **Initial state** | The empty board. Red moves first. |
| **TO-MOVE(s)** | Red if the number of discs is even, otherwise Yellow. |
| **ACTIONS(s)** | The columns `0..6` that hold fewer than 6 discs. |
| **RESULT(s, a)** | The mover's disc lands in the lowest empty cell of column `a`. |
| **IS-TERMINAL(s)** | One player has four in a row (horizontal, vertical or either diagonal), or all 42 cells are full. |
| **UTILITY(s, p)** | Win +1, draw 0, loss −1. In search this is scaled to **±(1,000,000 − ply)**, so faster wins (and slower losses) are preferred. Draws are 0. |

**Size.** The branching factor is at most 7 and shrinks as columns fill, so it is about 7 for most of the game. A game lasts at most 42 plies, which gives a loose game-tree bound of 7^42 ≈ 3×10^35. The number of distinct legal positions is about **4.5×10^12** (4,531,985,219,092; Edelkamp & Kissmann 2008). That is far too many to enumerate in Python during play, so every searching agent here (all but Random) uses depth-limited search or sampling. The game is solved: with perfect play the first player wins by starting in the center column. It was solved independently in 1988 by James D. Allen (announced on 1 October 1988) and Victor Allis (15 days later); see John Tromp's Connect Four page.

---

## Algorithms

All agents expose the same method, `choose(board, player, trace=True)`, and return the same result shape. Search values are always reported from the root player's perspective.

**Agents and algorithms.** In AI terms (Russell & Norvig, AIMA 4th ed., ch. 2), an *agent* is anything that perceives its environment and acts on it. Its behaviour is the *agent function*, a mapping from what it has perceived to an action, and the *agent program* is the code that implements it. Each player here is an agent: it sees the board and drops a disc. What differs is the algorithm inside its program: a uniform random policy (Random), one-ply lookahead with a heuristic (Greedy), depth-limited heuristic minimax search (Minimax), the same minimax computed with alpha-beta pruning and centre-first ordering (Alpha-Beta), and Monte Carlo Tree Search with UCT selection and tactical playouts (MCTS). Minimax and Alpha-Beta are two programs for essentially the same agent function: same values, fewer nodes, and they differ only in tie-breaking. So there are five agent programs but four distinct decision rules.

### Random

Picks a uniformly random legal column using a seedable `random.Random`. It is the baseline policy every other agent must beat.
**Time** O(b) · **Space** O(1).

### Greedy (one-ply lookahead)

The priority order is:

1. Play an immediate win.
2. Otherwise block the opponent's immediate win (if there are several, block the one with the best heuristic score).
3. Otherwise play the move whose resulting position has the highest heuristic score. Ties are broken at random (seedable).

**Time** O(b · W), where W = 69 is the number of scoring windows · **Space** O(1).

### Minimax (depth-limited)

This is AIMA's MINIMAX-SEARCH cut off at depth *d*, with a heuristic evaluation at the cut-off (H-MINIMAX, AIMA 4th ed. §5.3). Terminal positions are detected right after each move: a win at ply *k* scores ±(1,000,000 − k) and a full board scores 0. At the depth limit, a non-terminal leaf is scored in two steps (`MinimaxAgent._leaf_value`):

1. If the side to move at the leaf can complete four immediately, the leaf is a proven result one ply later and scores ±(1,000,000 − (ply + 1)): a win if that side is the root player, a loss otherwise. The check is a few whole-board shift-and-AND operations (`board.threat_cells` masked with `board.playable_cells`, the `compute_winning_position` trick of Pascal Pons' solver tutorial) and searches no extra node.
2. Otherwise the heuristic scores it, always from the root player's view.

Step 1 was added after we measured that its absence made odd depths play badly; see [What we found and fixed](#what-we-found-and-fixed-the-horizon-at-odd-depths). Moves are made and unmade in place on the bitboards, so no position is copied. Leaf values are memoised per search, keyed on the position. This saves time but does not change the node count.

**Time** O(b^d) · **Space** O(b·d) for the search (one board mutated in place, plus d stack frames that each hold a list of at most b moves), plus the per-search leaf-value memo, which grows with the number of distinct leaf positions.

From the empty board the node count is exactly the full tree, 1 + 7 + 7² + … + 7^d (for example 400 nodes at d = 3), and a test checks this.

### Alpha-Beta pruning with move ordering

This is the same search with α (the best value Max can already guarantee) and β (the best value Min can already guarantee) carried down the tree. When α ≥ β at a node, its remaining siblings cannot affect the root decision and are skipped (fail-soft). `stats.pruned` counts the sibling subtrees skipped at cut-offs. The root value is **identical to plain Minimax at the same depth**, and the tests verify this on 7 positions × 4 depths × both orderings. The *move* can differ, but only among moves of equal value: ties go to whichever move is searched first, and Minimax searches left to right while Alpha-Beta searches center-first. (On 400 random positions at depths 3 and 4 the value never differed, the chosen column differed in 30 and 41 positions against ordered Alpha-Beta, and in none against unordered Alpha-Beta.) The test therefore checks that Alpha-Beta's move has the Minimax value, not that it is the same column.

Move ordering matters a great deal. With `move_ordering=True`, columns are tried center-first, `(3, 2, 4, 1, 5, 0, 6)` 0-indexed, that is columns 4, 3, 5, 2, 6, 1, 7 in the UI. Central moves take part in the most four-in-a-row lines (the centre column lies in 51 of the 69 windows) and are usually strongest, so good moves are found early and cut-offs come sooner.

**Time** best case O(b^(d/2)) with perfect ordering (Knuth & Moore 1975), about O(b^(3d/4)) with random ordering for moderate b (AIMA 4th ed. §5.2.4; Pearl 1982 derived the exact branching factor for trees with random leaf values), and O(b^d) in the worst case · **Space** O(b·d) for the search, plus the leaf-value memo (as for Minimax).

For root moves that fail low, `column_scores` holds an upper bound rather than the exact value. This is the nature of alpha-beta: the search proves "no better than the best", not the exact score.

### Monte Carlo Tree Search (UCT)

Each iteration has the four standard phases (as surveyed by Browne et al. 2012); selection uses UCT (Kocsis & Szepesvári 2006):

1. **Selection.** From the root, descend through fully expanded nodes, choosing the child that maximises UCB1:

   ```
   UCT(i) = w_i / n_i  +  c · sqrt( ln N / n_i ),      c = √2 ≈ 1.414
   ```

   This is the UCB1 bandit rule (Auer, Cesa-Bianchi & Fischer 2002) applied at every tree node. Here `w_i` is the wins from the point of view of the player who moved into child *i*, `n_i` is that child's visit count, and `N` is the parent's visit count. The first term exploits moves that have done well. The second explores moves that have been tried rarely.
2. **Expansion.** Add one random untried move as a new node.
3. **Simulation.** Play the game out to the end. Moves are random, except that the rollout policy is lightly tactical (`smart_rollouts`, on by default): a player who can win immediately does so, and otherwise blocks an immediate opponent win. This removes a lot of noise from purely random playouts at little cost.
4. **Backpropagation.** Update every node on the path: +1 for a win by the node's mover, +0.5 for a draw.

The **most-visited** root child is played (the "robust child"). Ties in visits are broken by the higher win rate, then by the more central column, never at random, and the explanation says so (for example "After 1,500 simulations column 1 is tied for most visits with column 7 (320 each); the tie is broken by the higher win rate (111 vs 110.5 simulated wins, draws counting half)."). `column_scores` holds each move's win rate (0–1) and `column_visits` its visit count. The default is 1,500 iterations, and the allowed range is 50–20,000.

MCTS uses no evaluation function: its game knowledge is the rules, the final result of each playout, and the rollout policy's one-move tactics (take an immediate win, otherwise block an immediate loss).

**Time** O(n · (D + L)) for *n* iterations, where *D* is the depth of the selection path in the tree and *L* the rollout length. Every iteration ends at the end of the game, so D + L is at most the number of empty cells (≤ 42); each of those plies costs O(b) (UCB1 over at most b children, or the rollout's win/block check) · **Space** O(n): at most one new tree node per iteration.

### Complexity summary

| Agent | Time per move | Memory | Optimal? |
|---|---|---|---|
| Random | O(b) | O(1) | No |
| Greedy | O(b·W), W = 69 | O(1) | No |
| Minimax, depth d | O(b^d) | O(b·d) + leaf memo | Optimal *with respect to the heuristic* at depth d |
| Alpha-Beta, depth d | O(b^(d/2)) best, ≈ O(b^(3d/4)) random order, O(b^d) worst | O(b·d) + leaf memo | Same value as Minimax at depth d (the move may differ only among equally valued moves) |
| MCTS, n iterations | O(n·(D + L)), D + L ≤ 42 | O(n) | The probability of choosing a suboptimal root move tends to zero as n → ∞ (Kocsis & Szepesvári 2006) |

The leaf memo is a per-search dictionary of leaf values; it grows with the number of distinct leaf positions and is discarded after the move.

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

**On "admissibility".** Admissibility (never overestimating the true cost to a goal) is a property of heuristics for A* and other optimal path-finding searches. It does not apply here. An evaluation function in adversarial search is not a cost-to-go bound. AIMA (4th ed. §5.3.1) asks something different of it: that it order terminal states the same way as the true utility, that it be cheap to compute, and that on non-terminal states it correlate strongly with the actual chance of winning. This function is reasonable by those criteria:

- **It agrees with the utility on terminal states.** Search scores proven wins and losses as ±(1,000,000 − ply) before the heuristic is ever consulted, and every heuristic score is a small integer far below that magnitude. A proven result therefore always dominates an estimate.
- **It measures what actually wins the game.** It counts the four-in-a-row lines that are still possible. A window blocked by both colours is worth nothing, a three with an open cell is a real threat, and the center column takes part in the most windows: 51 of the 69, against 39 for columns 3 and 5, 27 for columns 2 and 6 and 15 for columns 1 and 7 (counted from `engine/evaluate.WINDOWS`).
- **It has a mild attacking bias.** Opponent threes (−4) are weighted slightly below own threes (+5), and opponent twos (−1) below own twos (+2). This makes the function only *approximately* zero-sum, which is harmless because search always evaluates from the root player's perspective. (An earlier version of this README justified the asymmetry by "the player to move acts on a threat first". That is not true of this function: it is *static* and does not know whose turn it is.)
- **It does not know whose turn it is, so search handles the one case where that decides everything.** A leaf where the side to move has a playable four is lost or won, not "a three". Search checks that case exactly before calling the heuristic (see [Minimax](#minimax-depth-limited)). We also tested making the weights symmetric and scoring leaves from the side to move's view; neither changed playing strength measurably (see [What we found and fixed](#what-we-found-and-fixed-the-horizon-at-odd-depths)).
- **It is cheap.** One call is 69 AND-and-popcount operations on Python integers.

It is hand-tuned, not learned or proven, and it knows nothing of Connect Four's deeper parity theory (see [Limitations](#limitations-and-future-work)).

---

## Bitboard representation

`engine/board.py` stores a position as **two Python integers**, one per player, using the 7-bits-per-column layout of John Tromp's Fhourstones solver (one bitboard per player plus a per-column heights array; Pascal Pons' tutorial uses a different position-plus-mask encoding):

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

Generated by `python benchmark.py` with the default settings (25.9 s wall time, 577 s of match CPU time on 24 worker processes, Python 3.13). Agents use the presets: Minimax depth 4, Alpha-Beta depth 6 with center-first ordering, MCTS 1,500 iterations.

**Design.** Two deterministic agents always play the same game from the same position, so starting every game from the empty board produces only one or two distinct games per pairing, however many are "played". Instead each pairing plays **40 games from 20 distinct random 2-ply openings** (drawn without replacement, seed 0; the opening moves are forced on both sides and are not counted in the time and node averages), and every opening is played twice with **colours swapped**, which cancels any advantage the opening gives one colour. A score counts a draw as half a win, and brackets are **Wilson 95% confidence intervals**. With draws counted as halves this is an approximation, since such a score is not strictly a binomial proportion; draws are rare here (at most 7 of an agent's 160 games in the standings). With 40 games an interval is roughly ±15 percentage points wide, so only clear gaps are significant.

### Head-to-head

| Agent A | Agent B | A wins | B wins | Draws | A score [95% CI] | A ms/move | B ms/move | CPU s |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Random | Greedy | 0 | 40 | 0 | 0% [0, 9] | 0.0 | 0.0 | 0.0 |
| Random | Minimax (depth 4) | 0 | 40 | 0 | 0% [0, 9] | 0.0 | 9.0 | 1.8 |
| Random | Alpha-Beta (depth 6) | 0 | 40 | 0 | 0% [0, 9] | 0.0 | 8.1 | 1.7 |
| Random | MCTS (1,500 iterations) | 0 | 40 | 0 | 0% [0, 9] | 0.0 | 94.6 | 17.8 |
| Greedy | Minimax (depth 4) | 0 | 40 | 0 | 0% [0, 9] | 0.1 | 5.7 | 2.2 |
| Greedy | Alpha-Beta (depth 6) | 1 | 39 | 0 | 2% [0, 13] | 0.0 | 8.4 | 3.1 |
| Greedy | MCTS (1,500 iterations) | 0 | 40 | 0 | 0% [0, 9] | 0.1 | 73.6 | 23.2 |
| Minimax (depth 4) | Alpha-Beta (depth 6) | 11 | 26 | 3 | 31% [19, 47] | 4.7 | 5.7 | 6.6 |
| Minimax (depth 4) | MCTS (1,500 iterations) | 21 | 18 | 1 | 54% [39, 68] | 5.3 | 52.7 | 36.1 |
| Alpha-Beta (depth 6) | MCTS (1,500 iterations) | 15 | 21 | 4 | 42% [29, 58] | 6.8 | 55.3 | 39.7 |

### Standings

| Agent | W | L | D | Score [95% CI] | avg ms/move | avg nodes/move |
|---|---:|---:|---:|---:|---:|---:|
| Alpha-Beta (depth 6) | 120 | 33 | 7 | 77% [70, 83] | 7.2 | 2,857 |
| MCTS (1,500 iterations) | 119 | 36 | 5 | 76% [69, 82] | 69.0 | 1,180 |
| Minimax (depth 4) | 112 | 44 | 4 | 71% [64, 78] | 6.2 | 1,815 |
| Greedy | 41 | 119 | 0 | 26% [19, 33] | 0.0 | 6 |
| Random | 0 | 160 | 0 | 0% [0, 2] | 0.0 | 7 |

### Alpha-beta depth sweep

Alpha-Beta (center-first ordering) at each depth against two fixed opponents, Greedy and MCTS with 1,000 iterations. Each cell is 98 games: all 49 two-ply openings, each played with both colours. The score is Alpha-Beta's.

| Depth | vs Greedy: W-L-D | Score [95% CI] | vs MCTS (1,000 it.): W-L-D | Score [95% CI] | AB ms/move |
|---:|---:|---:|---:|---:|---:|
| 1 | 59-37-2 | 61% [51, 70] | 18-79-1 | 19% [12, 28] | 0.1 |
| 2 | 66-31-1 | 68% [58, 76] | 40-57-1 | 41% [32, 51] | 0.2 |
| 3 | 92-6-0 | 94% [87, 97] | 39-52-7 | 43% [34, 53] | 0.5 |
| 4 | 86-12-0 | 88% [80, 93] | 50-47-1 | 52% [42, 61] | 1.1 |
| 5 | 96-1-1 | 98% [94, 100] | 48-44-6 | 52% [42, 62] | 2.9 |
| 6 | 96-2-0 | 98% [93, 99] | 59-38-1 | 61% [51, 70] | 7.0 |
| 7 | 98-0-0 | 100% [96, 100] | 56-41-1 | 58% [48, 67] | 21.0 |

### Minimax vs alpha-beta: nodes searched from the empty board

| Depth | Minimax nodes | Alpha-beta nodes | Alpha-beta + ordering | Minimax ms | Alpha-beta ms | Ordered ms | Saving (ordered) |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 8 | 8 | 8 | 0.1 | 0.0 | 0.0 | 0.0% |
| 2 | 57 | 33 | 21 | 0.3 | 0.2 | 0.1 | 63.2% |
| 3 | 400 | 200 | 76 | 1.6 | 0.8 | 0.3 | 81.0% |
| 4 | 2,801 | 849 | 180 | 8.6 | 2.9 | 0.6 | 93.6% |
| 5 | 19,608 | 4,175 | 621 | 40.7 | 11.9 | 1.8 | 96.8% |
| 6 | 137,257 | 16,183 | 1,493 | 239.0 | 41.3 | 3.4 | 98.9% |

Node counts are exact and machine-independent; the millisecond columns vary from run to run and machine to machine. With `--max-depth 7`, alpha-beta searches 69,144 nodes unordered and 5,085 ordered at depth 7 (Minimax is capped at 6).

### Interpretation

- **Pruning is where the power comes from.** At depth 6, alpha-beta with center-first ordering visits **1,493** nodes where Minimax visits **137,257**: **98.9% fewer nodes, about a 92× reduction**, for the same root value. In this run that was 239.0 ms down to 3.4 ms. Even without ordering, pruning skips 88.2% of the tree (16,183 nodes).
- **Ordering is worth almost as much as pruning itself.** At depth 6, center-first ordering cuts alpha-beta's work by a further **10.8×** (16,183 down to 1,493). The effective branching factor b*, defined as in AIMA by N + 1 = 1 + b* + (b*)² + … + (b*)^d, falls from **7.00** for Minimax (whose tree here is exactly the full tree) to 4.84 for unordered alpha-beta and **3.17** for ordered alpha-beta. The Knuth–Moore minimal tree at depth 6 has 7³ + 7³ − 1 = 685 leaves and 1,249 nodes in total (b* = 3.07), so ordered alpha-beta, at 1,493 nodes, visits **1.2× the minimal tree**.
- **The savings buy depth.** Alpha-Beta at depth 6 costs about the same per move as Minimax at depth 4 (7.2 vs 6.2 ms on average) and beat it 26–11–3 (Minimax scored 31% [19, 47]).
- **Alpha-Beta-6 and MCTS-1,500 are statistically tied.** Their overall scores, 77% [70, 83] and 76% [69, 82], have overlapping intervals, and their head-to-head went 21–15–4 to MCTS (Alpha-Beta 42% [29, 58]; the interval includes 50%). Neither can be called the stronger agent from these data. MCTS spends about ten times as long per move (69.0 vs 7.2 ms) because each iteration plays a full game in Python. Minimax-4 against MCTS (21–18–1, 54% [39, 68]) is also within the noise.
- **MCTS is competitive without an evaluation function.** Its only game knowledge is the rules, the result of each playout and the rollouts' one-move tactics (take a win, block a loss), yet at 1,500 iterations it matches depth-6 alpha-beta with a hand-tuned heuristic.
- **Depth pays, now at every step.** Alpha-Beta beats Greedy at every depth in the sweep: even at depth 1 the interval [51, 70] lies above 50%, from depth 2 its lower end is at least 58%, and from depth 3 at least 80%. Against MCTS-1,000 its score climbs from 19% at depth 1 to 52% at depths 4–5 and 58–61% at depths 6–7. Neighbouring depths are often within each other's intervals (3 vs 4 against Greedy, 4 vs 5 and 6 vs 7 against MCTS), so the trend is the result, not any single step. Before the fix described below, odd depths did not follow this trend.
- **Greedy still took one game of 40 from Alpha-Beta-6.** Depth 6 is short of a 42-ply game, and the heuristic is hand-tuned: a line whose decisive point lies beyond the horizon can still be misjudged.
- **Sample size.** 40 games per pairing (160 per agent in the standings) separates the clear gaps (everyone over Random and Greedy; Alpha-Beta-6 over Minimax-4) but not the top three agents from each other. Run `python benchmark.py --games 80` or more for tighter intervals. The earlier design of this benchmark (empty board, colours alternating) was misleading for exactly this reason: before the fix it reported Alpha-Beta-6 at 85% and Minimax-4 vs Alpha-Beta-6 as 0–40, but those 40 games were the same 2 games replayed 20 times.

### What we found and fixed: the horizon at odd depths

**Symptom.** In the old empty-board benchmark, Greedy against Alpha-Beta (40 games, seed 3) went 20–20 at depths 1, 3 and 5, but 0–40 at depths 2, 4 and 7 (3–36–1 at depth 6). At depths 1, 3 and 5 Red won every game whichever agent played it, so a depth-5 search did no better against a one-ply agent than a depth-1 search. The same pattern appeared in the new design's sweep against MCTS-1,000: 37% at depth 2, then **21%** at depth 3; 53% at depth 4, then **41%** at depth 5.

**Hypothesis.** The evaluation function is static: it does not know whose turn it is. At an odd depth the opponent is to move at every leaf. A leaf where the opponent can complete four on its next move is already lost, but the heuristic scored it as an ordinary "opponent three, −4". So the search would walk into lines that lose on the move just beyond its horizon.

**Measurement.** Over 300 random mid-game positions with no immediate win for either side, we followed the pre-fix principal variation to its leaf and asked whether the side to move there could win at once. At depths 3, 5 and 7 it could in **41 of 281 (15%), 48 of 274 (18%) and 37 of 267 (14%)** of the lines, and that side was always the opponent: in roughly one line in six, the line the agent expected to play ended one move before a loss it could not see. (At even depths 12–16% of lines ended in a win for the root player that was scored as a mere three; that undervalues good lines rather than walking into bad ones.)

**Three candidate fixes**, each tested head-to-head against the original engine at the same depth (games from random 4-ply openings, colours alternating; the variant's score):

| Variant | d1 | d2 | d3 | d4 | d5 | d6 | d7 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Score leaves from the side to move's view | 61% | 50% | 46% | 50% | 51% | 50% | 52% |
| Symmetric weights (−5 / −2 for opponent threes / twos) | 54% | 46% | 50% | 50% | 51% | 52% | 52% |
| **Leaf win check** (chosen) | **72%** | **60%** | **60%** | **56%** | **56%** | 51% | 52% |

The first two changed nothing measurable. The third, checking at each leaf whether the side to move can win immediately and scoring that as the proven result it is, scored above 50% at every depth from 1 to 5 and was never below 50% at 6 and 7. Combining it with either of the other two gave no consistent further gain against Greedy, so we kept the one change that is exactly correct rather than another tuned weight.

**The fix** (`MinimaxAgent._leaf_value` in `engine/agents.py`): at the depth limit, if the side to move has an immediately playable four, the leaf scores ±(1,000,000 − (ply + 1)); otherwise the unchanged heuristic. The check uses `board.threat_cells` and `board.playable_cells`, shift-and-AND operations over the whole board in the style of Pascal Pons' Connect Four solver, so no extra node is searched and node counts at depths 1–5 are unchanged. Minimax and Alpha-Beta share it, so their root values are still identical. Greedy is unchanged.

**Result**, same benchmark design (98 games per cell):

| Depth | vs Greedy, before | vs Greedy, after | vs MCTS-1,000, before | vs MCTS-1,000, after |
|---:|---:|---:|---:|---:|
| 1 | 36% [27, 46] | 61% [51, 70] | 1% [0, 6] | 19% [12, 28] |
| 2 | 60% [50, 69] | 68% [58, 76] | 37% [28, 47] | 41% [32, 51] |
| 3 | 65% [55, 74] | **94% [87, 97]** | 21% [14, 31] | **43% [34, 53]** |
| 4 | 89% [81, 94] | 88% [80, 93] | 53% [43, 62] | 52% [42, 61] |
| 5 | 95% [89, 98] | 98% [94, 100] | 41% [32, 51] | **52% [42, 62]** |
| 6 | 98% [94, 100] | 98% [93, 99] | 55% [45, 64] | 61% [51, 70] |
| 7 | 98% [93, 99] | 100% [96, 100] | 55% [45, 64] | 58% [48, 67] |

The odd depths gained the most, and strength now rises with depth instead of zigzagging. The tournament standings barely moved (before the fix: MCTS 78%, Alpha-Beta-6 77%, Minimax-4 69%), because the presets use even depths. Depth-6 node counts changed slightly (unordered 15,976 → 16,183, ordered 1,371 → 1,493), because leaves that are now scored as proven results change which branches get cut. Regression tests: `test_odd_depth_sees_reply_win` and `test_regression_alphabeta_beats_greedy_at_every_depth` in `tests/test_agents.py`.

In one paragraph, as we would say it:

> Our evaluation function is static: it doesn't know whose turn it is. At odd search depths the opponent moves next at the leaf, so a position where the opponent can win on the next move was scored as a mere "opponent three, −4". The agent walked into one-move losses just beyond its horizon, which is why depth 3 and 5 played no better than depth 2 and 4. We measured three candidate fixes; the one that worked, and is exactly correct, is to check at each leaf whether the side to move can win immediately and score that as the proven win or loss it is. After the fix, strength rises with depth.

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

A real example (Alpha-Beta, depth 6, the position used in the [API reference](#api-reference)): *"Alpha-beta with center-first ordering (depth 6, 2,657 positions, 3,088 branches pruned) rates column 4 best with a score of +4; pruning proved no other column scores higher."*

### Search-tree traces

- **Minimax / Alpha-Beta** build the trace *during* the search, but only for the first `MAX_PLIES = 3` plies. Each node records its move, the mover, its value (from the root's perspective), and the α/β window on entry. Infinite bounds are serialised as `null`. For alpha-beta's internal nodes, `bound` says whether `value` is exact (`null`) or only a bound: `"upper"` when the node failed low (true value ≤ value, shown as "≤" in the AI Mind panel) and `"lower"` when it failed high (true value ≥ value, shown as "≥"). Terminal positions, horizon leaves, plain Minimax and MCTS always have `bound: null`. At a cut-off, the skipped siblings are added as stub nodes with `"pruned": true` and no children, so the UI can show exactly where pruning happened.
- **MCTS** builds the trace *after* search from the real tree, recording visits, wins (from the mover's view) and the root player's win rate as `value`.
- **The principal variation** is marked with `"best": true` along the expected line of play.
- **Capping** (`tracing.cap_tree`) trims the tree to at most `MAX_NODES = 400` nodes. Nodes are admitted breadth-first. Within each level, children on the best line come first, then the rest by visits or value, taken round-robin across parents so that every parent keeps its most relevant children.
- **Tracing is purely observational.** A test asserts that `stats.nodes`, `stats.pruned` and the chosen column are identical with tracing on or off. Matches and benchmarks run with `trace: false`.

---

### Game review (post-game analysis)

After a game on `/play` ends, **Review game** (or <kbd>R</kbd>) sends the move list to `POST /api/analyze`. `engine/review.py` replays the game and, for every position, scores **every legal column exactly**, then grades the move that was played. "Exact" and "Best" are relative to the reviewer, not to perfect play: they mean the exact depth-7 alpha-beta value (by default) with the same heuristic the agents use, so the review inherits that heuristic's judgement and horizon.

- **Exact values, not bounds.** Alpha-beta's root `column_scores` are exact only for the chosen move. Every other column fails low against the root's `alpha` and returns an upper bound. Grading against a bound would hide mistakes. So `exact_move_values()` runs the root loop itself and searches each child with a **full window** `(-∞, +∞)` through the existing `AlphaBetaAgent._search`. Alpha-beta still prunes below each child, but every root value is the true depth-*d* minimax value. A unit test checks it against plain Minimax for every column.
- **Depth.** The default is 7, one ply deeper than the strongest opponent preset. The allowed range is 1–8. Each position costs up to seven full-window searches, plus a bounded consistency re-search (at most 6 extra plies, 300,000 nodes per review). Measured on CPython 3.13 for 25–42-ply games, re-search included: depth 7 takes about 0.5–1.5 s and depth 8 about 1.5–5.4 s (machine-dependent).
- **Forced results.** A win on ply *p* scores `1_000_000 − p`. The winner needs ⌈*p*/2⌉ of its own moves (the mover plays the odd plies), and a loss on ply *p* means the opponent needs *p*/2. Wins found within the horizon are proofs, not estimates.
- **Consistent rows.** The badge uses `graded_value`. It is the played value unless the next position's search (one ply deeper from here) proves the move wins (a slower win is Good; if nothing else was proven to win, the move is Best and `best_value`/`best_columns` become its) or loses (−next+1). When a tag would rest on nothing being proven (**Missed win**: no win found after the move; **Allowed forced loss**: the position before it not proven lost), that position is re-searched up to 6 plies deeper with a null window (300,000 nodes per review). A proof found there is used by both rows, so a Missed win never sits next to a row proving the opponent lost, and Allowed forced loss is not given in a position already proven lost. When nothing is proven, the comment states the deepest horizon checked, for example "…within 14 plies".
- **Badges.** The *loss* of a move is the best value minus the played value, in heuristic points. In `evaluate.py` an open three is worth 5, an open two 2 and a centre disc 3, and mid-game scores sit within about ±40. The named constants in `review.py` set the bands:

  | Badge | Rule |
  |---|---|
  | Best | loss 0 (ties count): as good as the best move at the review depth |
  | Good | loss ≤ 4, or a slower forced win |
  | Inaccuracy | loss ≤ 10, or losing sooner in an already lost position |
  | Mistake | loss ≤ 25 |
  | Blunder | loss > 25, **Missed win** (a proven win was available and the move gives it up), or **Allowed forced loss** (the position was not proven lost before the move, using the re-search, but is proven lost after it) |
- **Explanations.** Each move gets a one-line reason for the best move, such as "Column 4 blocks Yellow's four-in-a-row threat." or "Column 2 forces a win in 2 moves whatever Yellow does.". It also gets a comment on the played move, such as "Column 5 lets Red win immediately in column 4."
- **Graph.** Fixed-depth search has an odd-even effect: whoever makes the last ply before the horizon looks better than they are. Raw values therefore zigzag, by about 19 points per ply on average (225 consecutive heuristic positions in 10 reviewed games of Alpha-Beta-4 against MCTS-300). For heuristic scores the graph plots the mean of the depth-*d* and depth-(*d*−1) values of each position. The depth-(*d*−1) value comes free as the exact value of the move that led there. This cuts the mean step to about 2 points. Proven results are plotted in the top and bottom bands, labelled "Red wins in 3 moves". Grading never uses the averaged numbers.

### Alpha-beta stepper (Learn page)

At the end of the alpha-beta section of `/learn` (`/learn#ab-stepper`), `static/js/stepper.js` runs fail-soft minimax or alpha-beta, written as in the page's pseudocode, over a small tree. It records an event trace (enter a node, evaluate a leaf, update a value and window, prune, done) and replays it one event per step on an SVG. Nothing is scripted by hand, so the captions always describe what the algorithm actually did. Each step shows the [α, β] window passed down, whether a value is exact or only a bound (for example "≤2" for a node whose remaining children were pruned), which ancestor's bound caused each cut-off, and at the end the principal variation. Switching between plain minimax and alpha-beta compares how many leaves each needs. Counts from the code's own search on the presets:

| Tree | Leaves | Minimax evaluates | Alpha-beta evaluates | Root value |
|---|---:|---:|---:|---:|
| Textbook (AIMA Fig. 5.2 tree, pruning as in Fig. 5.5; 3 × 3) | 9 | 9 | 7 | 3 |
| Best-case ordering (depth 3, b = 3) | 27 | 27 | 11 | 5 |
| Worst-case ordering (depth 3, b = 3) | 27 | 27 | 27 | 9 |
| Random (depth 3, branching 2–3, leaf values 0–20) | varies | all | varies | varies |

The best case reaches the Knuth–Moore minimum of b^⌈d/2⌉ + b^⌊d/2⌋ − 1 = 3² + 3¹ − 1 = 11 leaves, and the worst case prunes nothing. Keys (click the tree first): <kbd>→</kbd> / <kbd>←</kbd> step, <kbd>Space</kbd> play or pause, <kbd>Home</kbd> reset, <kbd>End</kbd> jump to the result. The arrow keys, <kbd>Home</kbd> and <kbd>End</kbd> also work while one of the stepper's buttons has focus; <kbd>Space</kbd> and <kbd>Enter</kbd> then press the button.

### Presentation mode

`/present` (`templates/present.html`, `static/js/present.js`) is a 15-slide deck: title, why Connect Four, problem formulation, the five agents, minimax, alpha-beta and move ordering, the heuristic, MCTS, bitboards, results, the odd-depth bug we found and fixed (slide 11), explainability, live demo (slide 13), limitations, and thanks. The results slides use the measured numbers from [Results](#results). Keys: <kbd>→</kbd> / <kbd>PageDown</kbd> / <kbd>Space</kbd> next, <kbd>←</kbd> / <kbd>PageUp</kbd> / <kbd>Shift</kbd>+<kbd>Space</kbd> previous, <kbd>Home</kbd> / <kbd>End</kbd> first and last slide, <kbd>F</kbd> (or the control-bar button) fullscreen, <kbd>S</kbd> speaker notes, <kbd>Esc</kbd> leave fullscreen or close the notes. Fullscreen uses the real Fullscreen API; if the browser blocks it (an embedded preview or an iframe), a toast explains and the slides expand to fill the page instead. Where full screen is unavailable from the start, the button is labelled "Expand slides". Clicking or tapping the left or right edge of the slide also moves, and the URL hash links to a slide (`/present#13`). The live-demo slide opens Play, Arena, Lab and Learn in new tabs.

---

## API reference

All endpoints take and return JSON. Bad input returns HTTP **400** with `{"error": "<message>"}`. The message is meant for a person to read, for example `"floating disc in column 2 (row 3 below it is empty)"` or `"impossible disc counts: Red has 4, Yellow has 1 (Red moves first, so Red must have the same number or one more)"`. Boards are 6×7 lists of lists with row 0 at the top (0 empty, 1 Red, 2 Yellow). Columns are 0-indexed in JSON, and explanations use 1-indexed "column 4" for people. A body that is not valid JSON (including pathologically nested JSON) or not a JSON object is also a 400. Unexpected server errors return 500 `{"error": "Internal server error."}`; details go to the server log only.

Board validation checks the shape, that cell values are 0/1/2, gravity (no floating discs), disc counts (Red has the same number as Yellow or one more), that both players do not have four in a row, and that a won position ends with the winner's last disc (Red won → Red has one more disc; Yellow won → equal counts; removing one of the winner's top discs must leave no four).

**Integer policy** (every endpoint, every integer field: `depth`, `iterations`, `seed`, `games`, `opening_plies`, `player`, `column`, `moves[]`, `depths[]` and board cells). A JSON integer or an integral float (`5` or `5.0`) is accepted. Strings (`"5"`), booleans, fractions (`5.5`), NaN/Infinity and magnitudes above 2^53 are rejected with 400 (`board.parse_int` in the engine, `app._as_int` in the web layer). Out-of-range values are **clamped** for `depth` (1–8, Minimax at most 6), `iterations` (50–20,000), `games` (1–50) and `opening_plies` (0–6), and **rejected** for `player`, `column`, `moves[]` and the `depths[]` of `/api/compare-depth`.

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
                "description": "Minimax 6 plies deep with alpha-beta pruning and centre-first move ordering: the same value as Minimax, computed with far fewer nodes."},
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

Agent config fields: `type` (`random | greedy | minimax | alphabeta | mcts`), `depth` (default 5), `iterations` (default 1500), `move_ordering` (default `true`), `trace` (default `true`), `seed` (`int | null`). `move_ordering` and `trace` must be JSON booleans (`"false"` or `0` is a 400). A bare preset id string such as `"alphabeta"` in place of the object means that preset (Alpha-Beta depth 6, Minimax depth 4). `player` must be the side to move on the board.

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
  "stats": {"nodes": 2657, "pruned": 3088, "time_ms": 8.702, "nodes_per_sec": 305314,
            "depth": 6, "iterations": null, "max_depth_reached": 6},
  "explanation": "Alpha-beta with center-first ordering (depth 6, 2,657 positions, 3,088 branches pruned) rates column 4 best with a score of +4; pruning proved no other column scores higher.",
  "principal_variation": [3, 3, 4, 4, 3, 0],
  "tree": {"id": "root", "move": null, "player": 2, "value": 4.0, "alpha": null, "beta": null,
           "visits": null, "wins": null, "pruned": false, "best": true, "terminal": false,
           "bound": null,
           "children": [{"id": "root.0", "move": 0, "player": 2, "value": 3.0, "alpha": 4.0, "beta": null,
                         "best": false, "bound": "upper", "...": "..."}]}
}
```

The same position with `{"type": "mcts", "iterations": 1500, "seed": 1}`:

```json
{
  "column": 3,
  "column_scores": [0.4624, 0.4436, 0.3837, 0.5345, 0.4852, 0.3366, 0.3951],
  "column_visits": [226, 195, 129, 435, 271, 101, 143],
  "stats": {"nodes": 1485, "pruned": 0, "time_ms": 108.337, "nodes_per_sec": 13707,
            "depth": null, "iterations": 1500, "max_depth_reached": 6},
  "explanation": "Most-explored move after 1,500 simulations: column 4 (435 visits, 53% win rate); runner-up column 5 (271 visits, 49%).",
  "principal_variation": [3, 1, 0, 4, 3, 5]
}
```

TreeNode fields: `id` (the move path, for example `"root.3.4"`), `move`, `player` (who dropped the disc for this move; for the root, who is choosing), `value` (root perspective), `alpha` / `beta` (alpha-beta, `null` when infinite), `visits` / `wins` (MCTS), `pruned`, `best`, `terminal`, `children`, and `bound` (alpha-beta internal nodes: `"upper"` if the value is only an upper bound because the node failed low, `"lower"` if it failed high, otherwise `null` for an exact value; always `null` for Minimax and MCTS). The root-move example above shows it: column 1 failed low against α = 4, so its 3.0 means "at most 3". JSON has no Infinity, so when the web layer sends a value that is infinite it uses ±1e9 instead.

### `POST /api/match`

Plays `games` games (clamped to 1–50). Colours alternate: Agent A plays Red in game 1, Agent B in game 2, and so on (`first` names the agent playing Red). Results are deterministic for a given `seed`. With the optional `opening_plies` *k* (clamped to 0–6, default 0), games are played in pairs that start from the same seeded random *k*-ply opening with colours swapped; the opening moves are forced, are not counted in the time and node averages, and are listed in each game's `opening` (they are also the first moves of `moves`). The server refuses a match with 400 when its pessimistic run-time estimate (`api.estimate_match_seconds`) exceeds 240 s (`MATCH_TIME_LIMIT_S`), for example 50 games of MCTS-20,000 against itself: "This match is too long: about 2940 s of search estimated (limit 240 s). With these agents at most 4 games fit; use fewer games, fewer MCTS iterations or a smaller search depth."

```json
// request
{"agent_a": {"type": "alphabeta", "depth": 6}, "agent_b": {"type": "random"}, "games": 2, "opening_plies": 2}
// response
{
  "games": 2, "a_wins": 2, "b_wins": 0, "draws": 0,
  "a": {"avg_time_ms": 4.03, "avg_nodes": 1691.0, "label": "Alpha-Beta (depth 6)"},
  "b": {"avg_time_ms": 0.001, "avg_nodes": 7.0, "label": "Random"},
  "results": [
    {"first": "a", "winner": "a", "moves": [0, 5, 3, 1, 3, 4, 3, 6, 3], "length": 9, "opening": [0, 5]},
    {"first": "b", "winner": "a", "moves": [0, 5, 1, 3, 4, 3, 4, 4, 1, 3, 2, 3], "length": 12, "opening": [0, 5]}
  ],
  "opening_plies": 2
}
```

### `POST /api/compare-depth`

`board` is optional (the default is the empty board). `depths` takes values from 1–7 (others are rejected with 400; the default is `[1, 2, 3, 4, 5]`). Minimax is capped at depth 6; deeper rows report `null` for the Minimax fields. `alphabeta_*` is natural left-to-right ordering, and `alphabeta_ordered_*` is center-first.

```json
// request
{"depths": [1, 2, 3]}
// response
[
  {"depth": 1, "minimax_nodes": 8,   "minimax_ms": 0.048, "alphabeta_nodes": 8,   "alphabeta_ms": 0.037, "alphabeta_ordered_nodes": 8,  "alphabeta_ordered_ms": 0.035},
  {"depth": 2, "minimax_nodes": 57,  "minimax_ms": 0.279, "alphabeta_nodes": 33,  "alphabeta_ms": 0.139, "alphabeta_ordered_nodes": 21, "alphabeta_ordered_ms": 0.085},
  {"depth": 3, "minimax_nodes": 400, "minimax_ms": 1.382, "alphabeta_nodes": 200, "alphabeta_ms": 0.764, "alphabeta_ordered_nodes": 76, "alphabeta_ordered_ms": 0.267}
]
```

### `POST /api/analyze`

Post-game review (see [Game review](#game-review-post-game-analysis)). `moves` is the list of columns played from the empty board, Red first. `depth` is optional (default 7) and is clamped to 1–8. The endpoint returns 400 for a missing or empty `moves` list, non-integer or out-of-range columns, full columns, moves after the game is over, or more than 42 moves.

```json
// request
{"moves": [0, 6, 1, 6, 2, 5], "depth": 7}
// response (abridged; real output, time varies)
{"depth": 7, "time_ms": 208.6, "nodes": 117007,
 "evals": [{"ply": 0, "score": 5.0, "mate": null, "label": "+5", "raw": 9.0},
           "...",
           {"ply": 6, "score": 999999.0, "mate": 1, "label": "Red wins in 1 move", "raw": 999999.0}],
 "moves": ["...",
           {"ply": 6, "player": 2, "column": 5, "board_before": [[0, 0, 0, 0, 0, 0, 0], "..."],
            "values": [-999998.0, -999998.0, -999998.0, 10.0, -999998.0, -999998.0, -999998.0],
            "best_value": 10.0, "played_value": -999998.0, "graded_value": -999998.0,
            "best_column": 3, "best_columns": [3],
            "loss": null, "badge": "blunder", "tags": ["allowed_forced_loss"],
            "reason": "Column 4 blocks Red's four-in-a-row threat.",
            "comment": "Column 6 lets Red win immediately in column 4."}],
 "summary": {"1": {"best": 0, "good": 1, "inaccuracy": 2, "mistake": 0, "blunder": 0,
                   "missed_win": 0, "allowed_forced_loss": 0, "moves": 3, "accuracy": 33.3},
             "2": {"best": 0, "good": 0, "inaccuracy": 2, "mistake": 0, "blunder": 1,
                   "missed_win": 0, "allowed_forced_loss": 1, "moves": 3, "accuracy": 0.0}},
 "result": {"winner": 0, "draw": false, "finished": false},
 "thresholds": {"good": 4, "inaccuracy": 10, "mistake": 25}}
```

---

## Testing

```powershell
python -m unittest discover -s tests
```

```
Ran 114 tests in 16.137s
OK
```

**114 tests** in five suites, using only the standard library:

| Suite | Tests | What it covers |
|---|---:|---|
| `test_board.py` | 13 | Empty board; gravity and grid round-trip; horizontal, vertical and both diagonal wins; **no wrap-around across the sentinel row**; full columns; draws; `winning_moves`; exactly 69 windows; evaluation symmetry and center preference; opponent threats penalised |
| `test_agents.py` | 23 | Every agent takes an immediate win and blocks an immediate loss, with the correct explanation text; MCTS finds a win-in-one across seeds; alpha-beta finds a double-threat forced win; **alpha-beta returns the same value as minimax** on 7 positions × depths 1–4 × both orderings, with strictly fewer nodes from depth 3; ordering reduces nodes; exact full-tree node count (400 at depth 3); tracing does not change node or prune counts or the chosen move; tree ≤ 400 nodes and ≤ 3 plies with a correctly marked best line; pruned nodes are marked and childless; MCTS visit totals equal the iteration count; seeded agents are deterministic; Random only plays legal moves; **the horizon-leaf check**: a leaf whose side to move can win is scored as a proof from either perspective, quiet leaves keep the root-perspective heuristic, depth 1 and 3 see a reply win, `threat_cells` agrees with a slow per-column check on 300 random positions, and Alpha-Beta no longer loses the old Greedy regression games at depths 2–7; `bound` flags are honest (checked against full-window values) and never set for Minimax or MCTS; MCTS runner-up text and tie-breaks by win rate and by centre |
| `test_api.py` | 41 | Preset shapes and usability; `game_state` shape and wins; board validation errors (shape, non-integer and out-of-range values including booleans, floating discs, impossible disc counts); returning a copy of the input; `choose_move` errors for a bad player, unknown agent type, non-integer depth and finished games; depth and iteration clamping; result shapes for every agent; `trace: false`; preset strings; match shape and **determinism by seed**; strong agents beat Random; `compare_depth` on default and custom boards; random openings (paired games share an opening with colours swapped, the default is unchanged, explicit openings, the seeded helper); the integer policy in the engine and every endpoint (`5.0` accepted; `"5"`, `true`, `5.5` rejected); the match run-time cap and its estimate; `opening_plies` through the API; debug mode is opt-in; **impossible won boards** rejected (the winner must have moved last and the four must contain the last disc; genuine wins still accepted); `choose_move` checks the side to move and `apply_move` the player; `move_ordering`/`trace` are strict booleans; openings follow the integer policy; deeply nested JSON is a 400; an unexpected error is a generic 500 that leaks no internals; an impossible board is a 400 through the route; preset strings mean the same config as in the engine; preset descriptions |
| `test_review.py` | 35 | Game review: mate-distance conversion and labels; badge thresholds; a slower forced win is Good, not a Blunder; **exact values match plain Minimax for every column** (and alpha-beta root scores are shown to be upper bounds); a missed immediate win, a missed win that also allows a loss, and a failure to block are flagged; played-equals-best moves are always Best; summaries add up; graph smoothing never touches proven results; `graded_value` (a kept longer win is not a Missed win, the unproven case is worded with its horizon, a Missed win never contradicts the next move's row, otherwise graded equals played); integral floats accepted; `/api/analyze` 200/400 responses and depth clamping via the Flask test client; the **consistency pass** (a win past the horizon is Best, not an Inaccuracy; a Missed win / Allowed forced loss pair is resolved by the re-search; switching the re-search off keeps the depth-limited tags; `_prove` gives the exact win distance; no row ever contradicts its neighbour) |
| `test_present.py` | 2 | `/present` returns 200 with the deck markup, at least 10 slides, and its script and stylesheet; `present.js` and `present.css` are served |

The alpha-beta stepper's search core (`static/js/stepper.js`) is DOM-free and exports itself under Node, but it has no automated test in this suite; the counts in the [stepper table](#alpha-beta-stepper-learn-page) were produced by running that core under Node.

---

## Limitations and future work

**Limitations**

- **Python speed.** On the development machine alpha-beta runs at roughly 0.35–0.4 million nodes/s and MCTS at roughly 13k–17k tree nodes/s (each tree node with a full rollout): the benchmark averages are 2,857 nodes in 7.2 ms (about 400k/s) and 1,180 tree nodes in 69 ms (about 17k/s), and the API example position measures about 350k/s and 13k/s. The figures are machine-dependent. A compiled bitboard engine (C or Rust) would be substantially faster and could search deeper.
- **No transposition table and no iterative deepening.** Minimax and alpha-beta memoise leaf evaluations only. Transpositions (the same position reached by different move orders) are searched again, and depth is fixed rather than time-controlled.
- **Fixed, simple move ordering.** Center-first is a static order. Killer moves, the history heuristic, or ordering by the previous iteration's PV would bring alpha-beta closer to the √b ideal.
- **Hand-tuned heuristic.** The window weights were chosen by reasoning, not fitted, and the evaluation is static (it does not know whose turn it is). Search now covers the one decisive turn-dependent case, a playable four for the side to move, exactly ([What we found and fixed](#what-we-found-and-fixed-the-horizon-at-odd-depths)); we measured that this, not the weights, caused the odd-depth weakness. The heuristic still ignores Connect Four's odd/even threat parity (zugzwang), which Allis showed is central to perfect play. Whether that explains Alpha-Beta-6's one loss to Greedy in 40 games we have not measured.
- **Plain UCT.** There is no RAVE/AMAF, no progressive bias, and no tree reuse between moves (the tree is rebuilt every turn). The fixed c = √2 was not tuned for this game.
- **Alpha-beta column scores** for non-best root moves are upper bounds, not exact values, so the UI's column bars are exact only for the chosen move (the Game Review computes exact full-window values for every column instead).
- **Game review is depth-limited.** "Best" means best according to depth-7 alpha-beta with the same heuristic, not the true game value. "Missed win" means no proven win was found within the review horizon (the next position's search adds one ply, and disputed positions are re-searched up to 6 plies deeper within a node budget); a win longer than that can still be flagged, and the comment then says within how many plies it looked. Heuristic grades inherit the heuristic's blind spots, such as threat parity.
- **Benchmark samples are still modest.** 40 games per pairing gives 95% intervals about ±15 points wide, enough for clear gaps but not to separate Alpha-Beta-6, MCTS-1,500 and Minimax-4. Random openings with colours swapped fixed the old problem of deterministic agents replaying the same one or two games. The results show orderings of strength, not precise ratings.

**Future work**

- A transposition table keyed by the bitboard pair, plus iterative deepening with a time budget and PV-first ordering.
- A perfect-play negamax solver for late-game positions, to show the gap between heuristic and solved play.
- Threat-parity features in the evaluation, and weights tuned by self-play or regression.
- MCTS improvements: tree reuse, RAVE, a tuned c, and heuristic-guided rollouts. A side-by-side "MCTS vs Alpha-Beta at equal time" lab experiment.
- Elo ratings computed from larger tournaments.

---

## References

1. S. Russell and P. Norvig. *Artificial Intelligence: A Modern Approach*, 4th ed. Pearson, 2020. Chapter 2, "Intelligent Agents" (agents, agent functions and agent programs), and Chapter 5, "Adversarial Search and Games" (minimax, alpha-beta, evaluation functions, MCTS).
2. D. E. Knuth and R. W. Moore. "An Analysis of Alpha-Beta Pruning." *Artificial Intelligence* 6(4):293–326, 1975.
3. J. Pearl. "The Solution for the Branching Factor of the Alpha-Beta Pruning Algorithm and its Optimality." *Communications of the ACM* 25(8):559–564, 1982.
4. P. Auer, N. Cesa-Bianchi and P. Fischer. "Finite-time Analysis of the Multiarmed Bandit Problem." *Machine Learning* 47(2–3):235–256, 2002. (UCB1.)
5. L. Kocsis and C. Szepesvári. "Bandit Based Monte-Carlo Planning." *Proceedings of ECML 2006*, LNCS 4212, pp. 282–293. Springer, 2006.
6. C. B. Browne, E. Powley, D. Whitehouse, S. M. Lucas, P. I. Cowling, P. Rohlfshagen, S. Tavener, D. Perez, S. Samothrakis and S. Colton. "A Survey of Monte Carlo Tree Search Methods." *IEEE Transactions on Computational Intelligence and AI in Games* 4(1):1–43, 2012.
7. J. D. Allen. Solution of Connect Four announced in a rec.games.programmer posting, 1 October 1988; later published in *The Complete Book of Connect 4: History, Strategy, Puzzles*. Sterling, 2010.
8. L. V. Allis. *A Knowledge-Based Approach of Connect-Four. The Game is Solved: White Wins.* M.Sc. thesis, Vrije Universiteit Amsterdam, 1988.
9. J. Tromp. "John's Connect Four Playground" (history of the solution, the Fhourstones benchmark and its bitboard code, position counts). https://tromp.github.io/c4/c4.html
10. S. Edelkamp and P. Kissmann. "Symbolic Classification of General Two-Player Games." *KI 2008*, LNCS 5243, pp. 185–192. Springer, 2008. (Source of the exact position count, as listed on Tromp's page and in OEIS A212693.)
11. P. Pons. "Solving Connect 4: how to build a perfect AI" (blog tutorial), http://blog.gamesolver.org/solving-connect-four/01-introduction/
