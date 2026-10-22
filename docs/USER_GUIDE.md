# AI Arena: User Guide and Demo Script

This guide explains how to use AI Arena and gives a five-minute demo script. For the theory, benchmarks and API reference, see the [README](../README.md). For viva questions and answers, see [VIVA_PREP.md](VIVA_PREP.md).

## What it is

AI Arena is a Connect Four app where five classic game-playing agents, each driven by a different decision algorithm, play you or each other, and their reasoning is drawn on screen: the search tree, the branches that alpha-beta pruning cuts off, and the score behind each column.

## Run it

```powershell
pip install flask
python app.py
```

Open http://localhost:5050. Debug mode (the Werkzeug debugger and auto-reload) is off unless you set `AI_ARENA_DEBUG=1`. Run the tests with `python -m unittest discover -s tests` and the benchmark with `python benchmark.py`. No internet connection is needed: the fonts and chart libraries are bundled in `static/`.

## The five agents

Each player is an *agent* in the AIMA sense (it perceives the board and acts by dropping a disc); the name says which algorithm runs inside its program.

| Agent | How it decides | Typical strength |
|---|---|---|
| Random | Picks a uniformly random legal column: the baseline policy | Loses to everything |
| Greedy | Wins or blocks if it can, otherwise picks the best one-move heuristic score | Beats Random, easy for a person |
| Minimax | Depth-limited heuristic minimax: searches the game tree to a fixed depth (up to 6) with no pruning | Solid, but slow at depth |
| Alpha-Beta | Minimax with alpha-beta pruning: the same value as Minimax with far fewer nodes, skipping branches that cannot change the result, centre columns first | Tied for strongest in the benchmark (77% at depth 6), at about 7 ms per move |
| MCTS | Plays thousands of random-ish games, steering them with UCT, and plays the most-visited move | Tied for strongest (76% at 1,500 iterations), uses no evaluation function, about 10× slower per move |

## Pages

**Play.** Click a column or press 1 to 7 to drop a disc. After each AI reply the **AI Mind** panel shows:

- a plain-English reason for the move
- a score bar for each column (minimax value, or MCTS win rate)
- stats: positions searched, branches pruned, time, positions per second
- the search tree, as either a Tree or a Radial layout. Pruned branches are grey, the chosen line glows, and hovering a node shows its alpha/beta values or its MCTS visits and wins. Scroll to zoom and drag to pan; click a node to expand or collapse it. With the keyboard, Tab into the tree, then **↑** / **↓** move between nodes, **→** / **←** go to a child or the parent (or expand / collapse), **Home** / **End** jump to the first and last node, and **Enter** or **Space** expands or collapses. Two buttons above the tree: **Fit** (crosshair) re-centres the whole tree in view, and **Expand** shows the tree full screen (**Esc** leaves).

Other keys: **U** undo, **N** new game, **H** hint (asks Alpha-Beta for the best move), **R** review the finished game.

**Who moves first** starts a new game at once if no move has been made yet or the game is over. In the middle of a game it applies to the next game (press **N** or New game to start it now).

**Arena.** Pick Agent A and Agent B, set a speed, then Play, Pause or Step. Both minds are shown side by side, with a running scoreboard and a series mode.

**Lab.** Run a tournament between two agents and see wins, average time and average positions searched. **Random opening** (0 to 6 plies, default 2) starts each game from that many random moves, and each opening is played twice with colours swapped, because deterministic agents would otherwise replay the same game. **Cancel** stops a running tournament or experiment and leaves the previous results unchanged. The **Pruning power** experiment compares positions searched at each depth for Minimax, Alpha-Beta and Alpha-Beta with move ordering.

**Learn.** The theory behind each algorithm, with diagrams, a complexity table and the alpha-beta stepper (below).

**Present.** A 15-slide deck about the project, for a talk or a viva (below).

## Game review (Play page)

1. Finish a game on **Play** (win, lose or draw).
2. Press **Review game** in the result banner, or press **R**. The engine re-searches every position at depth 7. This takes about 0.5–1.5 s for a typical game.
3. The review panel shows:
   - **A summary per player:** how many moves got each badge, and the share rated Best or Good.
   - **An evaluation graph** from Red's point of view: above the middle line Red is better, below it Yellow is better. Proven wins sit in the top and bottom bands, labelled for example "Red wins in 3 moves". Click a point to jump to that move.
   - **The move list** with a badge on every move. Click a move, or use **←** / **→** (or **↑** / **↓** in the list), to see the position, the best move and a one-line explanation. **Home** / **End** jump to the first and last move, and **Esc** closes the panel.

The panel opens on the key moment: your first Mistake or Blunder, if there is one.

**What the badges mean.** For every position the engine scores every legal column exactly (not just the one it would pick). The *loss* of a move is the best score minus the score of the move played, in heuristic points (an open three is worth 5, an open two 2, a centre disc 3).

| Badge | Meaning |
|---|---|
| Best | The move scored as well as the best one found by the depth-7 search (ties count) |
| Good | Loss of 4 points or less, or a forced win that is slower than the fastest one |
| Inaccuracy | Loss of 10 points or less, or losing sooner in a position that was already lost |
| Mistake | Loss of 25 points or less |
| Blunder | Loss of more than 25 points, or one of the two tags below |
| Missed win (tag) | A forced win was available and the move gave it up |
| Allowed forced loss (tag) | The position was not proven lost before the move (even after a deeper re-search), but the opponent can force a win after it |

"Best" and "forced" are relative to the reviewer: depth-7 alpha-beta with the same heuristic the agents use, not the true value of the game. "Forced" means proven within that horizon (the next move's search adds one ply, and disputed positions are re-searched up to 6 plies deeper). A longer win is not seen; the comment then says within how many plies no win was found. Other scores are heuristic estimates, so treat the grades as the opinion of a depth-7 search, not as perfect play.

## Alpha-beta stepper (Learn page)

Open **Learn** and scroll to the end of the alpha-beta section, or go straight to `/learn#ab-stepper`.

1. **Choose a tree:** Textbook (the AIMA Fig. 5.2 tree, with pruning as in Fig. 5.5), Best-case ordering, Worst-case ordering, or Random leaves. **New random** draws another random tree.
2. **Choose the algorithm:** Plain minimax or Alpha-beta.
3. **Step:** press **Step**, or click the tree and use **→** (next) and **←** (back). **Space** plays or pauses, the slider sets the speed, **Home** (or Reset) goes back to the start and **End** jumps to the result. The arrow keys, **Home** and **End** also work while one of the stepper's buttons has focus (there **Space** and **Enter** press the button).

Each step has a caption saying what happened and why: the [α, β] window passed down, the value a node returns, and at a cut-off which ancestor's bound made the remaining children irrelevant. A value shown as "≤2" is only a bound, because part of that node was pruned. Below the tree, a line compares how many leaves minimax and alpha-beta needed on this tree. On the textbook tree it is 9 against 7, on the best-case tree 27 against 11, and on the worst-case tree 27 against 27 (nothing can be pruned).

## Presentation mode

Open **Present** (`/present`). Keys:

| Key | Action |
|---|---|
| → / PageDown / Space | Next slide |
| ← / PageUp / Shift+Space | Previous slide |
| Home / End | First / last slide |
| F | Full screen on or off (also the button in the control bar) |
| S | Speaker notes on or off |
| Esc | Leave full screen or the expanded view, close the notes |

If the browser blocks full screen (for example in an embedded preview or an iframe), a message says so and the slides expand to fill the page instead. Where full screen is unavailable from the start, the button is labelled "Expand slides". You can also click or tap the left or right edge of the slide. The address bar shows the slide number (`/present#10`), so you can link to or reload a slide. Slide 10 has the measured results and slide 11 the odd-depth bug we found and fixed. Slide 13 (Live demo) opens Play, Arena, Lab and Learn in new tabs; come back to the deck's tab to continue.

## Five-minute demo script

1. **Home (30 s).** Say what the app is: "Algorithms you can watch think."
2. **Play (90 s).** Choose Alpha-Beta (depth 6 is the default) and make a centre move. Point at the explanation sentence, then the grey pruned branches in the tree, then the pruned counter.
3. **Switch to MCTS (60 s).** Play another move. The tree grows unevenly toward promising moves and the column bars show win rates instead of minimax scores.
4. **Lab, pruning power (60 s).** Run it. At depth 6 plain Minimax searches 137,257 positions, Alpha-Beta 16,183, and Alpha-Beta with centre-first ordering 1,493 (98.9% fewer). Node counts are exact; the times depend on the machine.
5. **Arena (60 s).** Alpha-Beta against MCTS, speed set to medium. Close with the tournament numbers from the README: at the presets the two are statistically tied (77% and 76%, overlapping 95% intervals).

If there is more time, finish a game on Play and press **R** to show the review, or step through the textbook tree on Learn. A longer script that uses the slide deck is in [VIVA_PREP.md](VIVA_PREP.md).

## Questions a teacher may ask

- **Why does alpha-beta give the same value as minimax?** It only skips branches that provably cannot change the root value. The chosen column can differ only among equally valued moves, because ties go to whichever move is searched first.
- **Why does move ordering help?** Good moves searched first set tight alpha/beta bounds early, so more of the remaining branches are cut.
- **Is the evaluation function admissible?** Admissibility is an A* idea. Here the heuristic is a scoring estimate for non-terminal positions, not a bound on cost.
- **Why is MCTS slower per move?** It runs thousands of simulations, where Alpha-Beta searches a pruned tree. MCTS needs no hand-written evaluation function.

[VIVA_PREP.md](VIVA_PREP.md) has about thirty more, with answers that point to the code.

## Troubleshooting

- **Port already in use:** another copy is running on 5050. Stop it, or change the port at the bottom of `app.py`.
- **Lab tournament feels stuck:** MCTS at 1,500 simulations over 10 or more games can take tens of seconds. Use fewer games or fewer iterations. A match whose estimated run time exceeds 240 s is refused with a message saying how many games would fit.
- **Page looks unstyled or charts are missing:** the fonts are in `static/fonts/` and D3 and Chart.js in `static/vendor/`. Check that those folders are present; nothing is downloaded from the internet. A hard refresh (Ctrl+F5) clears an old cached copy.
- **Review game does nothing:** the review needs a finished game. Undo or New game clears it.
