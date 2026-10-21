"""AI Arena benchmark: round-robin tournament + minimax vs alpha-beta node counts.

Usage:
    python benchmark.py               # presets, 6 games per pairing
    python benchmark.py --games 10 --seed 1
    python benchmark.py --quick       # lighter MCTS / search settings

Prints markdown tables to stdout.
"""

import argparse
import itertools
import time

from engine import api


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


def tournament(cfgs, games, seed):
    keys = list(cfgs)
    standings = {k: {"w": 0, "l": 0, "d": 0, "ms": 0.0, "nodes": 0.0, "n": 0} for k in keys}
    rows = []
    for i, (ka, kb) in enumerate(itertools.combinations(keys, 2)):
        t0 = time.perf_counter()
        r = api.run_match(cfgs[ka], cfgs[kb], games=games, seed=seed + i)
        wall = time.perf_counter() - t0
        rows.append((ka, kb, r, wall))
        for side, k, w, lose in (("a", ka, r["a_wins"], r["b_wins"]),
                                 ("b", kb, r["b_wins"], r["a_wins"])):
            s = standings[k]
            s["w"] += w
            s["l"] += lose
            s["d"] += r["draws"]
            s["ms"] += r[side]["avg_time_ms"]
            s["nodes"] += r[side]["avg_nodes"]
            s["n"] += 1
    return rows, standings


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--games", type=int, default=6, help="games per pairing (default 6)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--quick", action="store_true", help="lighter settings for a fast run")
    ap.add_argument("--max-depth", type=int, default=6, help="deepest row of the node table")
    args = ap.parse_args()

    t_start = time.perf_counter()
    cfgs = agent_configs(args.quick)
    labels = {k: api.agent_label(api.normalize_config(c)) for k, c in cfgs.items()}

    print(f"# AI Arena benchmark\n\n{args.games} games per pairing, colours alternate, "
          f"seed {args.seed}.\n")
    rows, standings = tournament(cfgs, args.games, args.seed)

    print("## Head-to-head\n")
    print("| Agent A | Agent B | A wins | B wins | Draws | A ms/move | B ms/move | Wall s |")
    print("|---|---|---:|---:|---:|---:|---:|---:|")
    for ka, kb, r, wall in rows:
        print(f"| {labels[ka]} | {labels[kb]} | {r['a_wins']} | {r['b_wins']} | {r['draws']} | "
              f"{r['a']['avg_time_ms']:.1f} | {r['b']['avg_time_ms']:.1f} | {wall:.1f} |")

    print("\n## Standings\n")
    print("| Agent | W | L | D | Score % | avg ms/move | avg nodes/move |")
    print("|---|---:|---:|---:|---:|---:|---:|")
    order = sorted(standings, key=lambda k: (standings[k]["w"] + 0.5 * standings[k]["d"]),
                   reverse=True)
    for k in order:
        s = standings[k]
        total = s["w"] + s["l"] + s["d"]
        pct = 100.0 * (s["w"] + 0.5 * s["d"]) / max(total, 1)
        print(f"| {labels[k]} | {s['w']} | {s['l']} | {s['d']} | {pct:.0f} | "
              f"{s['ms'] / s['n']:.1f} | {s['nodes'] / s['n']:,.0f} |")

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

    print(f"\n_Total runtime: {time.perf_counter() - t_start:.1f} s_")


if __name__ == "__main__":
    main()
