"""AI Arena benchmark: round-robin tournament, depth sweep, minimax vs alpha-beta node counts.

Usage:
    python benchmark.py               # 40 games per pairing from 20 random 2-ply openings,
                                      # depth sweep over all 49 two-ply openings (98 games)
    python benchmark.py --quick       # 20 games per pairing, lighter MCTS / search settings
    python benchmark.py --games 80 --openings 3 --seed 1
    python benchmark.py --openings 0  # old design: every game starts from the empty board
    python benchmark.py --no-sweep    # skip the alpha-beta depth sweep
    python benchmark.py --sweep-games 40   # smaller depth sweep (default 98)
    python benchmark.py --jobs 4      # worker processes (default: all CPUs)

Experimental design.  Two deterministic agents always play the same game from
the same position, so starting every game from the empty board only ever
produces one or two distinct games per pairing.  Instead each game starts
from a random ``k``-ply opening (default k = 2, drawn without replacement
from a seeded RNG, the moves forced on both sides) and every opening is played
twice with colours swapped, which cancels any advantage the opening gives one
colour.  Scores count a draw as half a win and are reported with a Wilson 95%
confidence interval.

Prints markdown tables to stdout.  Results are deterministic for a given
seed and do not depend on ``--jobs`` (work is split into fixed-size chunks
of openings, each with its own derived seed, and run in parallel processes).
"""

import argparse
import itertools
import math
import os
import time
from concurrent.futures import ProcessPoolExecutor

from engine import api

#: openings per work unit (each opening = 2 games); fixed so results do not
#: depend on how many processes run them
CHUNK_OPENINGS = 2
SWEEP_DEPTHS = range(1, 8)
Z95 = 1.959964


def agent_configs(quick):
    cfgs = {}
    for key, preset in api.AGENT_PRESETS.items():
        cfg = {k: v for k, v in preset.items() if k not in ("label", "description")}
        if quick:
            if key == "mcts":
                cfg["iterations"] = 400
            if key == "alphabeta":
                cfg["depth"] = 5
        cfg["trace"] = False
        cfgs[key] = cfg
    return cfgs


def wilson(score, n, z=Z95):
    """Wilson score interval for a proportion ``score / n`` (draws count 0.5).

    Treating a draw as half a success is the usual approximation for game
    scores; with few draws (as here) it is very close to exact.
    """
    if n == 0:
        return 0.0, 1.0
    p = score / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def fmt_score(score, n):
    lo, hi = wilson(score, n)
    return f"{100.0 * score / n:.0f}% [{100 * lo:.0f}, {100 * hi:.0f}]"


# --------------------------------------------------------------------------
# parallel match runner
# --------------------------------------------------------------------------
def _run_chunk(job):
    cfg_a, cfg_b, openings, seed, games = job
    if openings is None:
        return api.run_match(cfg_a, cfg_b, games=games, seed=seed)
    return api.run_match(cfg_a, cfg_b, games=2 * len(openings), seed=seed, openings=openings)


def plan_match(cfg_a, cfg_b, games, plies, seed):
    """Split one pairing into independent, deterministic chunks of work."""
    if plies == 0:
        return [(cfg_a, cfg_b, None, seed, games)]
    openings = api.random_openings((games + 1) // 2, plies, seed)
    jobs = []
    for i in range(0, len(openings), CHUNK_OPENINGS):
        jobs.append((cfg_a, cfg_b, openings[i:i + CHUNK_OPENINGS], seed * 1009 + i, None))
    return jobs


def _decisions(game, side):
    """Moves ``side`` chose itself in one game (opening moves are forced)."""
    red = game["first"] == side            # Red plays the even move indices
    k = len(game.get("opening", []))
    return sum(1 for i in range(k, game["length"]) if (i % 2 == 0) == red)


def merge(parts):
    """Combine run_match results of several chunks of the same pairing."""
    out = {"games": 0, "a_wins": 0, "b_wins": 0, "draws": 0, "results": []}
    sums = {"a": [0.0, 0.0, 0], "b": [0.0, 0.0, 0]}
    for r in parts:
        for k in ("games", "a_wins", "b_wins", "draws"):
            out[k] += r[k]
        out["results"] += r["results"]
        for side in ("a", "b"):
            # weight per-chunk averages by the number of decisions in the chunk
            n = sum(_decisions(g, side) for g in r["results"])
            sums[side][0] += r[side]["avg_time_ms"] * n
            sums[side][1] += r[side]["avg_nodes"] * n
            sums[side][2] += n
            out.setdefault(side, {})["label"] = r[side]["label"]
    for side in ("a", "b"):
        n = max(sums[side][2], 1)
        out[side]["avg_time_ms"] = sums[side][0] / n
        out[side]["avg_nodes"] = sums[side][1] / n
    return out


def run_all(pool, matches, plies):
    """``matches``: list of (key, cfg_a, cfg_b, seed, games) -> {key: (result, cpu_s)}."""
    futures = []
    for key, cfg_a, cfg_b, seed, games in matches:
        for job in plan_match(cfg_a, cfg_b, games, plies, seed):
            futures.append((key, pool.submit(_timed_chunk, job)))
    parts, cpu = {}, {}
    for key, fut in futures:
        r, secs = fut.result()
        parts.setdefault(key, []).append(r)
        cpu[key] = cpu.get(key, 0.0) + secs
    return {k: (merge(v), cpu[k]) for k, v in parts.items()}


def _timed_chunk(job):
    t0 = time.perf_counter()
    r = _run_chunk(job)
    return r, time.perf_counter() - t0


def score_of(r, side):
    w = r["a_wins"] if side == "a" else r["b_wins"]
    return w + 0.5 * r["draws"]


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--games", type=int, default=None,
                    help="games per pairing (default 40, --quick 20)")
    ap.add_argument("--openings", type=int, default=2,
                    help="random opening plies per game, 0-6 (default 2; 0 = empty board)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--quick", action="store_true",
                    help="20 games per pairing, MCTS 400 iterations, Alpha-Beta depth 5")
    ap.add_argument("--no-sweep", action="store_true", help="skip the alpha-beta depth sweep")
    ap.add_argument("--sweep-games", type=int, default=None,
                    help="games per depth and opponent in the sweep (default 98 = all 49 "
                         "two-ply openings x 2 colours; --quick: same as --games)")
    ap.add_argument("--max-depth", type=int, default=6, help="deepest row of the node table")
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 1,
                    help="worker processes (default: all CPUs); results do not depend on it")
    args = ap.parse_args()
    games = args.games or (20 if args.quick else 40)
    sweep_games = args.sweep_games or (games if args.quick else 98)
    plies = max(0, min(6, args.openings))

    t_start = time.perf_counter()
    cfgs = agent_configs(args.quick)
    labels = {k: api.agent_label(api.normalize_config(c)) for k, c in cfgs.items()}
    pairs = list(itertools.combinations(cfgs, 2))

    sweep_ref_iters = 400 if args.quick else 1000
    sweep_refs = {"greedy": {"type": "greedy", "trace": False},
                  "mcts": {"type": "mcts", "iterations": sweep_ref_iters, "trace": False}}
    matches = [(("t", ka, kb), cfgs[ka], cfgs[kb], args.seed + i, games)
               for i, (ka, kb) in enumerate(pairs)]
    if not args.no_sweep:
        for j, (ref, rc) in enumerate(sweep_refs.items()):
            for d in SWEEP_DEPTHS:
                matches.append((("s", ref, d), {"type": "alphabeta", "depth": d, "trace": False},
                                rc, args.seed + 100 + 10 * j + d, sweep_games))

    with ProcessPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        res = run_all(pool, matches, plies)

    if plies:
        design = (f"{games} games per pairing: {(games + 1) // 2} distinct random {plies}-ply "
                  "openings, each played twice with colours swapped")
    else:
        design = f"{games} games per pairing from the empty board, colours alternate"
    print(f"# AI Arena benchmark\n\n{design}, seed {args.seed}. Score counts a draw as "
          "half a win; brackets are Wilson 95% confidence intervals.\n")
    if not plies:
        print("_Warning: without random openings two deterministic agents replay the same "
              "one or two games, so those games are not independent and their intervals "
              "are not meaningful._\n")

    print("## Head-to-head\n")
    print("| Agent A | Agent B | A wins | B wins | Draws | A score [95% CI] | "
          "A ms/move | B ms/move | CPU s |")
    print("|---|---|---:|---:|---:|---:|---:|---:|---:|")
    standings = {k: {"w": 0, "l": 0, "d": 0, "ms": 0.0, "nodes": 0.0, "n": 0} for k in cfgs}
    for ka, kb in pairs:
        r, cpu = res[("t", ka, kb)]
        print(f"| {labels[ka]} | {labels[kb]} | {r['a_wins']} | {r['b_wins']} | {r['draws']} | "
              f"{fmt_score(score_of(r, 'a'), r['games'])} | "
              f"{r['a']['avg_time_ms']:.1f} | {r['b']['avg_time_ms']:.1f} | {cpu:.1f} |")
        for side, k, w, lose in (("a", ka, r["a_wins"], r["b_wins"]),
                                 ("b", kb, r["b_wins"], r["a_wins"])):
            s = standings[k]
            s["w"] += w
            s["l"] += lose
            s["d"] += r["draws"]
            s["ms"] += r[side]["avg_time_ms"]
            s["nodes"] += r[side]["avg_nodes"]
            s["n"] += 1

    print("\n## Standings\n")
    print("| Agent | W | L | D | Score [95% CI] | avg ms/move | avg nodes/move |")
    print("|---|---:|---:|---:|---:|---:|---:|")
    order = sorted(standings, key=lambda k: (standings[k]["w"] + 0.5 * standings[k]["d"]),
                   reverse=True)
    for k in order:
        s = standings[k]
        total = s["w"] + s["l"] + s["d"]
        print(f"| {labels[k]} | {s['w']} | {s['l']} | {s['d']} | "
              f"{fmt_score(s['w'] + 0.5 * s['d'], total)} | "
              f"{s['ms'] / s['n']:.1f} | {s['nodes'] / s['n']:,.0f} |")

    if not args.no_sweep:
        print("\n## Alpha-beta depth sweep\n")
        print(f"Alpha-Beta (center-first ordering) at each depth against two fixed opponents, "
              f"same design as above ({sweep_games} games per depth and opponent). "
              "Score is Alpha-Beta's.\n")
        print(f"| Depth | vs Greedy: W-L-D | Score [95% CI] | vs MCTS ({sweep_ref_iters:,} it.): "
              "W-L-D | Score [95% CI] | AB ms/move |")
        print("|---:|---:|---:|---:|---:|---:|")
        for d in SWEEP_DEPTHS:
            rg, _ = res[("s", "greedy", d)]
            rm, _ = res[("s", "mcts", d)]
            ms = (rg["a"]["avg_time_ms"] + rm["a"]["avg_time_ms"]) / 2
            print(f"| {d} | {rg['a_wins']}-{rg['b_wins']}-{rg['draws']} | "
                  f"{fmt_score(score_of(rg, 'a'), rg['games'])} | "
                  f"{rm['a_wins']}-{rm['b_wins']}-{rm['draws']} | "
                  f"{fmt_score(score_of(rm, 'a'), rm['games'])} | {ms:.1f} |")

    print("\n## Minimax vs alpha-beta: nodes searched from the empty board\n")
    print("| Depth | Minimax nodes | Alpha-beta nodes | Alpha-beta + ordering | "
          "Minimax ms | Alpha-beta ms | Ordered ms | Saving (ordered) |")
    print("|---:|---:|---:|---:|---:|---:|---:|---:|")
    for r in api.compare_depth(depths=range(1, args.max_depth + 1)):
        mm = r["minimax_nodes"]
        saving = f"{100.0 * (1 - r['alphabeta_ordered_nodes'] / mm):.1f}%" if mm else "-"
        mm_s = f"{mm:,}" if mm else "-"
        mm_ms = f"{r['minimax_ms']:.1f}" if r["minimax_ms"] is not None else "-"
        print(f"| {r['depth']} | {mm_s} | {r['alphabeta_nodes']:,} | "
              f"{r['alphabeta_ordered_nodes']:,} | {mm_ms} | {r['alphabeta_ms']:.1f} | "
              f"{r['alphabeta_ordered_ms']:.1f} | {saving} |")

    cpu_total = sum(c for _, c in res.values())
    print(f"\n_Total runtime: {time.perf_counter() - t_start:.1f} s wall, "
          f"{cpu_total:.0f} s of match CPU time on {max(1, args.jobs)} worker processes_")


if __name__ == "__main__":
    main()
