"""Compare two run_backtest_range.py --json outputs (e.g. a component off vs on).

Usage: python scripts/backtest/compare_backtest_json.py <off.json> <on.json> [label]

Written for v35 Task 4 (AVWAP off vs on) but strategy-agnostic: any two
--json dumps from the same window can be pooled and diffed here.

Pooled win rate is sum(wins)/sum(n_eval) over all strategies -- n_eval is
already win+loss only (see run_backtest_range.pool), so this matches the
repo's "win_rate over win+loss only" convention. Wilson 95% intervals are
printed so the reading rule can say whether the two overlap.
"""
import json
import math
import sys


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - m) / d * 100, (c + m) / d * 100)


def pooled(d):
    wins = sum(v["wins"] for v in d.values())
    n = sum(v["n_eval"] for v in d.values())
    closed = sum(v["closed"] for v in d.values())
    exp_vals = [(v["expectancy_r"], v["closed"]) for v in d.values()
                if v["expectancy_r"] is not None and v["closed"]]
    exp = (sum(e * c for e, c in exp_vals) / sum(c for _, c in exp_vals)
           if exp_vals else None)
    return wins, n, closed, exp


def main():
    off = json.load(open(sys.argv[1]))
    on = json.load(open(sys.argv[2]))
    label = sys.argv[3] if len(sys.argv) > 3 else ""

    wo, no, co, eo = pooled(off)
    wn, nn, cn, en = pooled(on)
    ro = wo / no * 100 if no else 0.0
    rn = wn / nn * 100 if nn else 0.0
    lo_o, hi_o = wilson(wo, no)
    lo_n, hi_n = wilson(wn, nn)

    print(f"=== v35 AVWAP comparison {label} ===\n")
    print(f"{'':6s} {'wins':>7s} {'n_eval':>8s} {'closed':>8s} {'win%':>8s} "
          f"{'Wilson95':>18s} {'expR':>9s}")
    print(f"{'OFF':6s} {wo:7d} {no:8d} {co:8d} {ro:8.2f} "
          f"  [{lo_o:6.2f},{hi_o:6.2f}] {eo:+9.4f}")
    print(f"{'ON':6s} {wn:7d} {nn:8d} {cn:8d} {rn:8.2f} "
          f"  [{lo_n:6.2f},{hi_n:6.2f}] {en:+9.4f}")
    print()
    print(f"win-rate delta : {rn - ro:+.3f} pp")
    print(f"expectancy delta: {en - eo:+.5f} R")
    print(f"trade-count delta (closed): {cn - co:+d} "
          f"({(cn - co) / co * 100:+.2f}%)" if co else "")
    overlap = not (hi_o < lo_n or hi_n < lo_o)
    print(f"Wilson intervals overlap: {overlap}")
    print()
    print("-- per strategy --")
    print(f"{'strategy':22s} {'n_off':>6s} {'n_on':>6s} {'wr_off':>7s} "
          f"{'wr_on':>7s} {'delta':>7s}")
    for s in sorted(set(off) | set(on)):
        a, b = off.get(s, {}), on.get(s, {})
        wra, wrb = a.get("win_rate"), b.get("win_rate")
        d = (wrb - wra) if (wra is not None and wrb is not None) else None
        print(f"{s:22s} {a.get('n_eval', 0):6d} {b.get('n_eval', 0):6d} "
              f"{(f'{wra:.2f}' if wra is not None else 'n/a'):>7s} "
              f"{(f'{wrb:.2f}' if wrb is not None else 'n/a'):>7s} "
              f"{(f'{d:+.2f}' if d is not None else 'n/a'):>7s}")


if __name__ == "__main__":
    main()
