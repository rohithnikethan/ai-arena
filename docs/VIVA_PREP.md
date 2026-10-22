# AI Arena: Viva and Demo Preparation

Preparation for presenting and defending AI Arena in a Foundations of AI viva at Rajalakshmi Engineering College (REC). It has a 60-second pitch, a 5-minute demo script tied to the `/present` slides, and the questions an examiner is most likely to ask, each with a short answer and the file or function that backs it up. Every number here comes from the [README](../README.md) (measured by `benchmark.py` and the test suite) or from running the code.

Start the app with `python app.py` and open http://localhost:5050. Nothing needs the internet.

---

## 60-second pitch

> AI Arena is Connect Four where you can watch classic game-playing AI think. Five game-playing agents, each driven by a different decision algorithm (Random, Greedy, Minimax, Alpha-Beta and Monte Carlo Tree Search), play you or each other, and after every move the app draws the search tree they explored, greys out the branches alpha-beta pruned, shows each column's score or win rate, and states in plain English why the move was chosen.
>
> The engine is pure Python on bitboards: a position is two integers, and a win check is eight shift-and-AND operations. Every number in the AI Mind panel comes from the real search. The headline result: at depth 6 from the empty board, alpha-beta with centre-first move ordering visits 1,493 nodes where minimax visits 137,257. That is 98.9% fewer nodes for the same value, and it is what lets Alpha-Beta search depth 6 for about the cost of Minimax at depth 4. In a 40-games-per-pairing tournament from random openings, depth-6 Alpha-Beta (77%) and 1,500-iteration MCTS (76%) come out statistically tied at the top.
>
> We also found and fixed a real bug by measuring it: our evaluation does not know whose turn it is, so at odd depths the search walked into losses one move past its horizon. A one-line, exactly correct leaf check fixed it, and strength now rises with depth.
>
> There is also a post-game review that grades every move with exact alpha-beta values, a step-by-step alpha-beta debugger on the textbook tree, and 114 unit tests, including one that checks alpha-beta returns the same value as minimax.

---

## 5-minute demo script

Open `/present` in one tab and the app in another. Press **F** for fullscreen and **S** for speaker notes. If the browser blocks full screen (an embedded preview or an iframe), a message says so and the slides expand to fill the page instead; open the deck in its own tab, or press F11. `/present#N` jumps to slide N.

| Time | Where | What to do and say |
|---|---|---|
| 0:00–0:30 | Slides 1–3 (`/present#1`) | Title, why Connect Four (deterministic, two-player, zero-sum, perfect information, solved), and the formal problem: state, TO-MOVE, ACTIONS, RESULT, IS-TERMINAL, UTILITY (AIMA 4th ed. names). |
| 0:30–1:15 | Slides 4–6 | The five agent programs behind one interface (each player is an agent; the name is the algorithm inside it). Minimax assumes a perfect opponent. Alpha-beta gives the same value but skips provably irrelevant branches, and centre-first ordering makes the cut-offs happen early. |
| 1:15–2:00 | `/learn#ab-stepper` | Leave the tree on **Textbook (AIMA Fig. 5.2/5.5)** (the AIMA Fig. 5.2 tree, pruning as in Fig. 5.5) and press **Step** (or →) a few times. Point at the [α, β] window and read the "Prune!" caption: after the first MIN node returns 3, the second MIN node sees a 2 and stops, because MAX already has 3. Switch to **Plain minimax**: 9 leaves against 7. Pick **Best-case ordering**: 27 against 11, the Knuth–Moore minimum. |
| 2:00–3:00 | `/play` | Choose Alpha-Beta (depth 5 or 6) and play the centre. Read the explanation sentence, then show the tree: grey pruned stubs, the glowing principal variation, and the pruned counter. Switch to MCTS for one move: the tree is lopsided toward promising moves and the bars show win rates. |
| 3:00–3:45 | `/play`, game review | Finish a quick game (losing on purpose is fastest), press **R**. Show the accuracy summary, the evaluation graph, and a Blunder tagged "Allowed forced loss" with its one-line explanation. Say why the values are exact: each column is searched with a full window. |
| 3:45–4:30 | Slides 10–11, then `/lab` | Results: 137,257 → 16,183 → 1,493 nodes at depth 6, and the standings with their intervals (Alpha-Beta-6 and MCTS tied). Slide 11: the odd-depth bug, as hypothesis → measurement → three candidate fixes → the exact one → result. If time allows, run **Pruning power** in the Lab to reproduce the node counts live. |
| 4:30–5:00 | Slides 14–15 | Limitations (Python speed, no transposition table, hand-tuned heuristic, modest samples) and what would come next. Thank you. |

Back-up if something fails: slide 13 (`/present#13`) links to every page, and slides 10–11 have the measured numbers.

---

## Likely questions and answers

### Problem formulation

**1. How did you formulate Connect Four as a search problem?**
As in AIMA (4th ed.) Chapter 5, using its function names (the 3rd edition calls TO-MOVE and IS-TERMINAL PLAYER and TERMINAL-TEST). The state is a 6×7 grid (two 49-bit integers internally), the initial state is the empty board, TO-MOVE(s) is Red if the disc count is even, ACTIONS(s) are the non-full columns, RESULT drops the disc to the lowest empty cell, IS-TERMINAL is four in a row or a full board, and UTILITY is win +1, draw 0, loss −1. In search it is scaled to ±(1,000,000 − ply). Code: `engine/board.py` (`Board.valid_moves`, `play`, `winner`, `is_full`).

**1a. Aren't these just algorithms rather than agents?**
Both words are right, at different levels. In AIMA (Russell & Norvig, 4th ed., ch. 2) an *agent* is anything that perceives its environment through sensors and acts on it through actuators. Its behaviour is the *agent function*, a mapping from percept sequences to actions, and the *agent program* is the code that implements that function. Each player in the app is an agent in exactly that sense: it perceives the board and acts by dropping a disc. Random, Greedy, Minimax, Alpha-Beta and MCTS name the algorithm inside each agent program: a uniform random policy, one-ply lookahead with a heuristic, depth-limited heuristic minimax (AIMA's H-MINIMAX), the same minimax computed with alpha-beta pruning and centre-first ordering (AIMA §5.3, heuristic alpha-beta tree search), and MCTS with UCT (UCB1) selection and a tactical playout policy. Minimax and Alpha-Beta are two agent programs for essentially the same agent function: same values, far fewer nodes, and they differ only in tie-breaking. So there are five agent programs but four distinct decision rules. In the app's own words: "five game-playing agents, each driven by a different decision algorithm".

**2. What kind of environment is it?**
Fully observable, deterministic, sequential, discrete, static, two-agent, competitive and zero-sum: perfect-information adversarial search. That is why minimax applies directly, with no expectations over chance nodes and no belief states.

**3. How big is the search space, and why can't you just search all of it?**
The branching factor is at most 7 and a game lasts at most 42 plies, so the loose game-tree bound is 7^42 ≈ 3×10^35. There are about 4.5×10^12 legal positions (Edelkamp & Kissmann 2008). Python alpha-beta runs at roughly 0.4 million nodes/s on the development machine (benchmark average: 2,857 nodes in 7.2 ms), so every searching agent uses depth-limited search or sampling.

**4. Why is a win scored 1,000,000 − ply and not just +1?**
So that a faster win is preferred to a slower one, and a slower loss to a faster one. Without it, a search that has found a forced win can delay it forever. The heuristic only produces small integers (mid-game scores sit within about ±40), so a proven result always outweighs an estimate. Code: `MinimaxAgent._search` in `engine/agents.py`.

### Minimax and alpha-beta

**5. Why is alpha-beta guaranteed to return the same value as minimax?**
It only skips a subtree once it is proven that the subtree cannot affect the value at the root. α is the best value MAX can already guarantee on the path, β the best MIN can guarantee. At a MIN node, once a child returns a value ≤ α, MAX above already has something at least as good elsewhere and will never let play reach this node, so its other children are irrelevant (and symmetrically at MAX nodes with β). Formally, for a call with window (α, β) the fail-soft result v is exact when α < v < β, an upper bound when v ≤ α and a lower bound when v ≥ β. The root is searched with (−∞, +∞), so its value is exact. `tests/test_agents.py::test_alphabeta_matches_minimax` checks this on 7 positions × depths 1–4 × both orderings, and the move chosen must have the minimax value. Note: the same *value*, not necessarily the same *column*. When several moves tie, each algorithm keeps the first one it searched, and our Minimax searches left to right while Alpha-Beta searches centre-first. On 400 random positions at depths 3 and 4 the value never differed; the column differed in 30 and 41 positions against ordered Alpha-Beta and in none against unordered Alpha-Beta.

**6. Then why are the other column scores in the AI Mind panel only bounds?**
At the root, α is raised to the best score found so far. Each later column is searched with window (α, +∞) and, if it cannot beat α, it fails low and returns an upper bound, not its true value. Only the chosen move's value is exact. This is why the game review does not reuse `column_scores`: `exact_move_values()` in `engine/review.py` searches every root move with a full window. `tests/test_review.py` checks that its values match plain Minimax for every column, and that ordinary root scores really are bounds.

**7. Why does move ordering matter so much?**
Cut-offs happen when a good move is found early. With perfect ordering alpha-beta examines about b^(d/2) nodes, so it can search roughly twice as deep for the same cost (Knuth & Moore 1975). With random ordering it is about b^(3d/4) for moderate b (AIMA 4th ed. §5.2.4; Pearl 1982 derived the exact branching factor for random leaf values), and with the worst ordering b^d (no pruning at all). Our ordering is the static centre-first order `CENTER_ORDER = (3, 2, 4, 1, 5, 0, 6)` from `engine/board.py`, because centre columns take part in the most four-in-a-row windows (the centre column is in 51 of the 69). Measured at depth 6 from the empty board: unordered alpha-beta 16,183 nodes, ordered 1,493, a further 10.8× reduction. The stepper's worst-case tree shows the other extreme: 27 of 27 leaves evaluated.

**8. What is the effective branching factor and what did you measure?**
AIMA defines it as the branching factor b* that a uniform tree of depth d would need to contain N + 1 nodes: N + 1 = 1 + b* + (b*)² + … + (b*)^d. Solving that for our depth-6 node counts gives Minimax **7.00** (its tree from the empty board is exactly the full tree), unordered alpha-beta 4.84, ordered alpha-beta **3.17**. The Knuth–Moore minimal tree at depth 6 has 7³ + 7³ − 1 = 685 leaves and 1,249 nodes in all (b* = 3.07), so ordered alpha-beta, at 1,493 nodes, visits 1.2× the theoretical minimum. (Do not compare 1,493 nodes with 685 leaves: one counts all nodes, the other only leaves.) Source: README "Results", `benchmark.py`, `api.compare_depth`.

**9. What are the time and space complexities?**
Minimax O(b^d) time. Alpha-beta O(b^(d/2)) best case, about O(b^(3d/4)) random ordering, O(b^d) worst case. Both use O(b·d) space for the search itself: one board, mutated in place, plus d stack frames that each hold a list of at most b moves. On top of that, our implementation memoises leaf values in a per-search dictionary (`self.cache` in `MinimaxAgent._search`), which grows with the number of distinct leaf positions. It saves time and does not change the node count. MCTS is O(n·(D + L)) time for n iterations, selection depth D and rollout length L, where D + L ≤ 42 because every iteration runs to the end of the game (each ply costs O(b) for UCB1 or the rollout's win/block check), and O(n) space (at most one new tree node per iteration). Greedy is O(b·W) with W = 69 windows. The README, the Learn page and the slides state these same bounds.

**10. Why is the minimax node count from the empty board exactly 400 at depth 3?**
Nothing can end in 3 plies, so the tree is full: 1 + 7 + 7² + 7³ = 400. `tests/test_agents.py::test_minimax_node_count_empty_board` checks it. It is a good sanity check that the node counter counts what it claims.

**11. Why is Minimax capped at depth 6?**
It is exponential: 137,257 nodes and about 200–400 ms at depth 6 from the empty board, depending on the machine (239 ms in the benchmark run in the README). Depth 7 would be roughly another factor of 7. Alpha-Beta can go to 8. The caps are in `engine/api.py` (`MINIMAX_MAX_DEPTH`) and `app.py`.

**12. Is Minimax optimal?**
It is optimal against an optimal opponent *with respect to its evaluation at depth d*: it maximises the worst-case heuristic value d plies ahead. It is not optimal for the real game, because the heuristic is an estimate and the horizon is short. It also does not try to exploit a weak opponent, because it assumes the best reply every time.

### Heuristic

**13. Is your heuristic admissible?**
It is a trick question: admissibility (never overestimating the cost to a goal) is a property of heuristics for A* and other optimal path-finding searches. It does not apply to an evaluation function in adversarial search, which is not a bound on any cost. AIMA (4th ed. §5.3.1) asks something else of an evaluation function: order terminal states the same way as the true utility, be cheap, and correlate with the actual chance of winning on non-terminal states. Ours does: proven results (±(1,000,000 − ply)) always dominate, it counts still-open four-in-a-row windows, and it is 69 AND-and-popcount operations per call. See the README section "On admissibility".

**14. How does the evaluation function work, and why those weights?**
`engine/evaluate.py` precomputes all 69 four-cell windows (24 horizontal, 21 vertical, 12 per diagonal) as bit masks. A window holding both colours scores nothing. Otherwise: own two +2, own three +5, opponent two −1, opponent three −4, and ±3 per disc in the centre column (`CENTER_WEIGHT`, `OWN_WEIGHTS`, `OPP_WEIGHTS`). The centre bonus reflects that the centre column takes part in the most windows: 51 of the 69, against 39, 27 and 15 for columns further out (every column has lines in all four directions, so that is not the reason). The opponent weights are slightly lower (−4 vs +5, −1 vs +2): a mild attacking bias, nothing more. An earlier draft justified it with "the side to move acts on a threat first", but that is wrong for this function: it is static and does not know whose turn it is (see question 31). We tested symmetric weights and found no measurable difference. The weights were chosen by reasoning, not fitted, and that is listed as a limitation.

**15. What is the horizon effect, and where does it show up in your project?**
A depth-limited search cannot see past its cut-off, so it misjudges positions whose decisive event is just beyond the horizon, and it can play delaying moves that push an unavoidable loss out of view. It shows up in four places. First, the odd-depth bug (question 31): before the fix, odd-depth searches walked into losses one move beyond the horizon. Second, Greedy (one ply) still took one game of 40 from depth-6 Alpha-Beta in the benchmark: depth 6 is far short of 42 plies and the heuristic is hand-tuned. Third, the game review says "Missed win" only for wins it can prove within its horizon (7 plies by default, one more from the next position's search, and up to 6 more where a disputed position is re-searched within a node budget), so a longer win can be missed or misjudged. Fourth, a related fixed-depth artefact, the *odd/even effect*: whoever makes the last ply before the horizon looks better than they are, so raw review values zigzag, by about 19 points per ply on average in our measurement. `_graph_point()` in `engine/review.py` plots the mean of the depth-d and depth-(d−1) values, which cuts the mean step to about 2 points. Grading never uses the averaged numbers, only exact values of sibling moves at the same depth.

### Monte Carlo Tree Search

**16. Explain the four phases of MCTS in your code.**
All in `MCTSAgent.choose` in `engine/agents.py`. *Selection*: from the root, descend through fully expanded nodes by maximum UCB1. *Expansion*: add one random untried move. *Simulation*: play to the end of the game. Moves are random, except that a player who can win immediately does so and otherwise blocks an immediate opponent win (`smart_rollouts`, on by default). That one-move tactic is the only game knowledge MCTS has beyond the rules. *Backpropagation*: on the way up, each node gets +1 if the winner is the player who moved into it, +0.5 for a draw.

**17. Why UCB1, and why c = √2?**
Choosing which child to try is a multi-armed bandit problem. UCB1 = w/n + c·√(ln N / n) balances exploitation (the mean reward) against exploration (a bonus that grows for rarely tried moves and shrinks as they are tried). With rewards in [0, 1], c = √2 is the constant in UCB1 (Auer, Cesa-Bianchi & Fischer 2002, *Machine Learning* 47:235–256), which gives logarithmic regret, and Kocsis & Szepesvári (2006, ECML, LNCS 4212, pp. 282–293) showed that for UCT the probability of selecting a suboptimal root move tends to zero as the number of iterations grows. We did not tune c for Connect Four, and that is listed as a limitation (`MCTSAgent.C = math.sqrt(2)`).

**18. How does MCTS handle draws?**
A rollout that fills the board with no four (`nmoves` reaches 42) has winner 0. Backpropagation then adds 0.5 to every node on the path, so a draw counts as half a win for both sides and win rates stay in [0, 1]. Full-board and won positions found during expansion become terminal nodes, and their stored result is reused without a rollout.

**19. Which move does MCTS play, and why not the one with the highest win rate?**
The most-visited root child (the "robust child"), with ties broken by the higher win rate and then the more central column, never at random; the explanation says when a tie was broken and how. A move with a few lucky playouts can have a high win rate from very little evidence, while visit count reflects where UCB1 kept investing after many iterations. Example from the README: column 4 with 435 visits and a 53% win rate.

**20. MCTS has no evaluation function. How did it do?**
At 1,500 iterations it is statistically tied with depth-6 Alpha-Beta: 76% [69, 82] against 77% [70, 83] overall, and it led their head-to-head 21–15–4 (Alpha-Beta 42% [29, 58], an interval that includes 50%). Against Minimax-4 it went 18–21–1, also within the noise. So we do not claim either is the strongest. It is the slowest agent per move (69 ms on average against Alpha-Beta's 7.2 ms in the benchmark run) because every iteration plays a full game in Python. The point for the viva: MCTS needs only the rules and the terminal outcome, which is why it works in games where a good heuristic is hard to write.

### Representation and engineering

**21. Why bitboards?**
Speed in pure Python, and simplicity. A position is two integers using 7 bits per column, with one sentinel bit on top of each column: the layout of John Tromp's Fhourstones solver (Pascal Pons' tutorial uses a position-plus-mask encoding instead; we borrow his whole-board threat computation for the horizon check). A move is `bb |= 1 << heights[c]` and undo is the reverse XOR, both O(1), so search never copies a board. A win test is `m = bb & (bb >> s); m & (m >> 2s)` for shifts 1, 7, 8 and 6 (`has_four` in `engine/board.py`), which is eight shift-and-AND operations with no loops over cells. The sentinel row stops a line from wrapping from the top of one column to the bottom of the next (`test_no_wraparound`). The pair of integers is also a natural hash key (`Board.key()`), used for the leaf memo.

**22. How do you know your code is correct?**
114 unit tests in five suites (`python -m unittest discover -s tests`, standard library only): `test_board.py` 13, `test_agents.py` 23, `test_api.py` 41, `test_review.py` 35, `test_present.py` 2. The key ones: alpha-beta equals minimax (`test_alphabeta_matches_minimax`), the exact full-tree node count (400 at depth 3), every agent takes a win and blocks a loss, tracing does not change the move or the node and prune counts (`test_tracing_does_not_change_counts`), MCTS visit totals equal the iteration count, seeded agents are deterministic, review values equal plain Minimax for every column, board validation rejects malformed boards (floating discs, impossible disc counts, impossible won positions), the integer policy rejects `"5"`, `true` and `5.5` everywhere, `/api/analyze` answers bad input with 400, unexpected errors return a generic 500 that leaks no internals, the review's consistency pass never leaves neighbouring rows contradicting each other (`test_rows_never_contradict`), and regression tests pin the odd-depth fix (`test_odd_depth_sees_reply_win`, `test_regression_alphabeta_beats_greedy_at_every_depth`). The benchmark is a second check: the results are reproducible for a given seed and do not depend on the number of worker processes.

**23. Does drawing the search tree slow down or change the search?**
It does not change it. Minimax and alpha-beta build the trace during the search, but only for the first 3 plies (`tracing.MAX_PLIES`), and `tracing.cap_tree` trims it to at most 400 nodes for the browser. A test asserts that the chosen move, `stats.nodes` and `stats.pruned` are identical with tracing on and off. Matches and benchmarks run with `trace: false`.

**24. Where do the plain-English explanations come from? Is it an LLM?**
No. `tactical_reason()` in `engine/agents.py` checks the chosen move against facts verified on the bitboards (immediate win, block, double threat, single threat), and each agent then adds its own search statistics: depth, positions, branches pruned, and a forced result or the score. MCTS adds visits and win rates. The sentence can only state what the code has checked.

**25. How does the game review grade moves, and are the thresholds justified?**
For every position, `exact_move_values()` plays each legal column and searches the reply with a full (−∞, +∞) window using the same `AlphaBetaAgent._search`, at depth 7 by default. So "Best" means best according to depth-7 alpha-beta with the same heuristic, not the true game value. The *loss* is the best value minus the played value. Best is loss 0 (ties count), Good ≤ 4, Inaccuracy ≤ 10, Mistake ≤ 25, otherwise Blunder. Missing a proven win or walking into a proven loss is always a Blunder ("Missed win", "Allowed forced loss"). The next position's search is checked first: if it proves the opponent is lost, the move kept a longer win and is graded as a slower win (Good), not a miss, or Best if no other move was proven to win; if it proves the opponent wins, the move loses (`graded_value` in `engine/review.py`). When a tag would rest on nothing being proven, a consistency re-search looks at that position up to 6 plies deeper with a null window (300,000 nodes per review), and a proof found there is used by both rows, so a "Missed win" never sits next to a row proving the opponent lost and "Allowed forced loss" is never given in a position already proven lost. The bands are set against the heuristic's scale (an open three is 5, an open two 2, a centre disc 3, mid-game scores within about ±40) and are named constants in `engine/review.py`. They are a judgement call, not derived, and say so. A review of a 25–42-ply game at depth 7 takes about 0.5–1.5 s, re-search included.

### Solving and limitations

**26. What would make the agent play perfectly?**
Connect Four is solved: the first player wins by starting in the centre. James D. Allen announced a solution on 1 October 1988 and Victor Allis, independently, 15 days later (John Tromp's Connect Four page, https://tromp.github.io/c4/c4.html). To get there you would turn the search into a solver. Use negamax alpha-beta on win/draw/loss values only, without a heuristic. Add a transposition table keyed by the bitboard pair, so positions reached by different move orders are not searched again. Add iterative deepening with the previous iteration's best move searched first, plus null-window searches. Order moves by threats (moves that create or block threats first), and exploit left-right symmetry. Allis' own solution added knowledge-based rules about threats and zugzwang, such as the odd/even threat parity. In Python this would be far too slow from the empty board, but a late-game solver for the last 15–20 plies is realistic and is listed as future work.

**27. What is the odd/even threat (zugzwang) idea your heuristic ignores?**
Because discs stack, a threat on a given cell can only be played once the cell below it is filled, and at the end of the game the players fill the remaining cells alternately. Allis showed that, roughly, the first player (Red) benefits from threats on odd rows and the second player (Yellow) from threats on even rows, counting rows from the bottom. Our heuristic counts threats but ignores which row they are on, so it can overvalue a threat that will never be playable. We have not measured how much this costs. (We had guessed it caused the odd-depth weakness; measuring showed the real cause was the static evaluation at the horizon, question 31.)

**28. What are the main limitations?**
Python speed (roughly 0.4 million nodes/s for alpha-beta and 17k tree nodes/s for MCTS on the development machine, from the benchmark averages). No transposition table and no iterative deepening, so depth is fixed, not time-controlled. Static centre-first move ordering. A hand-tuned heuristic with no threat parity. Plain UCT with no RAVE and no tree reuse, and an untuned c. Alpha-beta column bars are exact only for the chosen move. The game review is depth-limited. 40 games per pairing gives intervals about ±15 points wide, too wide to separate the top three agents. The README "Limitations and future work" section lists each of these.

**29. How fair is the tournament? Is 40 games enough?**
Two deterministic agents always play the same game from the same position, so the old design (every game from the empty board) produced only one or two distinct games per pairing; for example it reported Minimax-4 vs Alpha-Beta-6 as 0–40, which was 2 games replayed 20 times. The benchmark now plays each pairing from 20 distinct random 2-ply openings, each twice with colours swapped (which cancels any advantage an opening gives one colour), and stochastic agents are seeded, so results are reproducible and do not depend on `--jobs`. Scores count a draw as half and carry Wilson 95% intervals; with draws counted as halves that interval is an approximation, because the score is not strictly binomial (draws are rare, at most 7 of an agent's 160 games). 40 games is enough for clear gaps (every agent beat Random 40–0; Alpha-Beta-6 beat Minimax-4 26–11–3, Minimax 31% [19, 47]) but not to rank Alpha-Beta-6, MCTS-1,500 and Minimax-4 against each other. `python benchmark.py --games 80` gives tighter intervals. We report orderings of strength, not ratings.

**30. Why the alpha-beta stepper, if the real engine already prunes?**
On a 7-wide game tree the pruning happens thousands of times per move, too fast to follow. The stepper (`static/js/stepper.js`) runs the same fail-soft algorithm on a tree small enough to follow, the AIMA Fig. 5.2 tree (pruning as in Fig. 5.5), and records every event, so each caption describes what the algorithm actually did, not a script. It also makes the ordering argument concrete. On the presets, minimax evaluates 9, 27 and 27 leaves, and alpha-beta 7 (textbook), 11 (best case, the Knuth–Moore minimum 3² + 3 − 1) and 27 (worst case, nothing pruned).

**31. Did you find any bugs by measuring? Tell us about one.**
Yes: the horizon at odd depths. *Symptom:* depths 3 and 5 played no better than 2 and 4. In the old empty-board benchmark Greedy split 20–20 with Alpha-Beta at depths 1, 3 and 5 but lost 0–40 at depths 2 and 4; in the new design, against MCTS-1,000, Alpha-Beta scored 37% at depth 2 but 21% at depth 3, and 53% at depth 4 but 41% at depth 5. *Hypothesis:* our evaluation function is static: it doesn't know whose turn it is. At odd search depths the opponent moves next at the leaf, so a position where the opponent can win on the next move was scored as a mere "opponent three, −4", and the agent walked into one-move losses just beyond its horizon. *Measurement:* on 300 random positions, the pre-fix principal variation ended in a leaf where the opponent to move could win at once in 41 of 281 lines at depth 3, 48 of 274 at depth 5 and 37 of 267 at depth 7. *Three candidate fixes:* scoring leaves from the side to move's view, symmetric weights, and a leaf win check. Head-to-head against the original engine, the first two scored 46–52% at depths 2–7 (no measurable effect); the win check scored 72%, 60%, 60%, 56%, 56% at depths 1–5. *Chosen:* the one that is exactly correct: at the depth limit, if the side to move can win immediately, score the leaf as that proven win or loss, ±(1,000,000 − (ply + 1)) (`MinimaxAgent._leaf_value`, using the shift-and-AND `board.threat_cells`; no extra nodes, and Minimax and Alpha-Beta still agree). *Result,* 98 games per cell: depth 3 against Greedy went from 65% to 94% and against MCTS from 21% to 43%; depth 5 against MCTS from 41% to 52%. Strength now rises with depth (neighbouring depths are within the noise). The tournament barely changed because the presets use even depths. README "What we found and fixed" has the tables; slide 11 has the chart.

---

## Quick facts to remember

| Fact | Value |
|---|---|
| Agents (five agent programs, four decision rules) | Random, Greedy, Minimax (depth ≤ 6), Alpha-Beta (depth ≤ 8, preset 6), MCTS (50–20,000 iterations, preset 1,500) |
| Nodes at depth 6, empty board | Minimax 137,257 · alpha-beta 16,183 · ordered 1,493 (98.9% fewer than Minimax, about 92×) |
| Time at depth 6 | 239.0 ms → 41.3 ms → 3.4 ms in the benchmark run (machine-dependent) |
| Effective branching factor (AIMA b*) | 7.00 → 4.84 → 3.17; minimal tree 1,249 nodes (b* 3.07), so ordered = 1.2× minimum |
| Benchmark design | 40 games per pairing: 20 random 2-ply openings × both colours, seed 0, Wilson 95% intervals |
| Standings (score % [95% CI]) | Alpha-Beta-6 77 [70, 83] · MCTS-1,500 76 [69, 82] · Minimax-4 71 [64, 78] · Greedy 26 [19, 33] · Random 0 [0, 2]. Top two statistically tied |
| Odd-depth fix | Leaf win check for the side to move; depth 3 vs Greedy 65% → 94% |
| Heuristic | 69 windows; +2 / +5 own, −1 / −4 opponent, ±3 per centre disc |
| Win score | ±(1,000,000 − ply), draw 0 |
| UCB1 | w/n + √2 · √(ln N / n); draw = 0.5; most-visited child played |
| Tree trace | first 3 plies, at most 400 nodes |
| Review | depth 7, full-window exact values, consistency re-search ≤ 6 extra plies / 300,000 nodes; bands 0 / 4 / 10 / 25; "Best" is relative to that search |
| Tests | 114 in five suites, about 16 s |
| Solved result | First player wins with perfect play by starting in the centre (Allen, 1 Oct 1988; Allis independently, 15 days later) |
