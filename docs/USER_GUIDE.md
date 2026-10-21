# AI Arena: User Guide and Demo Script

This guide explains how to use AI Arena and gives a five-minute demo script. For the theory, benchmarks and API reference, see the [README](../README.md).

## What it is

AI Arena is a Connect Four app where classic game-playing algorithms play you or each other, and their reasoning is drawn on screen: the search tree, the branches that alpha-beta pruning cuts off, and the score behind each column.

## Run it

```powershell
pip install flask
python app.py
```

Open http://localhost:5050. Run the tests with `python -m unittest discover -s tests` and the benchmark with `python benchmark.py`.

## The five agents

| Agent | How it decides | Typical strength |
|---|---|---|
| Random | Picks any legal column | Loses to everything |
| Greedy | Wins or blocks if it can, otherwise picks the best one-move heuristic score | Beats Random, easy for a person |
| Minimax | Searches the game tree to a fixed depth (up to 6) with no pruning | Solid, but slow at depth |
| Alpha-Beta | Same answer as Minimax, skipping branches that cannot change the result, centre columns first | Strongest and fastest in the benchmark |
| MCTS | Plays thousands of random-ish games and favours the moves that win most | Strong, and uses no hand-written heuristic |

## Pages

**Play.** Click a column or press 1 to 7 to drop a disc. After each AI reply the **AI Mind** panel shows:

- a plain-English reason for the move
- a score bar for each column (minimax value, or MCTS win rate)
- stats: positions searched, branches pruned, time, positions per second
- the search tree, as either a Tree or a Radial layout. Pruned branches are grey, the chosen line glows, and hovering a node shows its alpha/beta values or its MCTS visits and wins. Scroll to zoom and drag to pan.

Other keys: **U** undo, **N** new game, **H** hint (asks Alpha-Beta for the best move).

**Arena.** Pick Agent A and Agent B, set a speed, then Play, Pause or Step. Both minds are shown side by side, with a running scoreboard and a series mode.

**Lab.** Run a tournament between two agents and see wins, average time and average positions searched. The **Pruning power** experiment compares positions searched at each depth for Minimax, Alpha-Beta and Alpha-Beta with move ordering.

**Learn.** The theory behind each algorithm, with diagrams and a complexity table.

## Five-minute demo script

1. **Home (30 s).** Say what the app is: "Algorithms you can watch think."
2. **Play (90 s).** Choose Alpha-Beta at depth 5 and make a centre move. Point at the explanation sentence, then the grey pruned branches in the tree, then the pruned counter.
3. **Switch to MCTS (60 s).** Play another move. The tree grows unevenly toward promising moves and the column bars show win rates instead of minimax scores.
4. **Lab, pruning power (60 s).** Run it. At depth 6 plain Minimax searches about 137,000 positions, Alpha-Beta about 16,000, and Alpha-Beta with centre-first ordering about 1,400 (99% fewer).
5. **Arena (60 s).** Alpha-Beta against MCTS, speed set to medium. Close with the tournament numbers from the README.

## Questions a teacher may ask

- **Why does alpha-beta give the same answer as minimax?** It only skips branches that provably cannot change the final decision.
- **Why does move ordering help?** Good moves searched first set tight alpha/beta bounds early, so more of the remaining branches are cut.
- **Is the evaluation function admissible?** Admissibility is an A* idea. Here the heuristic is a scoring estimate for non-terminal positions, not a bound on cost.
- **Why is MCTS slower per move?** It runs thousands of simulations, where Alpha-Beta searches a pruned tree. MCTS needs no hand-written evaluation function.

## Troubleshooting

- **Port already in use:** another copy is running on 5050. Stop it, or change the port at the bottom of `app.py`.
- **Lab tournament feels stuck:** MCTS at 1,500 simulations over 10 or more games can take tens of seconds. Use fewer games or fewer iterations.
- **Page looks unstyled:** the fonts and chart libraries load from the internet, so check the connection.
