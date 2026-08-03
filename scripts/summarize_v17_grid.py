#!/usr/bin/env python3
"""Turn the per-strategy V17 grid JSONs into the results tables (plan v8 V17
Step 3). Reads only what `tune_sizing.py` wrote -- it re-ranks nothing and
re-decides nothing, so the tables cannot disagree with the run.

Usage: python scripts/summarize_v17_grid.py docs/superpowers/results/v17
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from tune_sizing import qualifies  # noqa: E402  (the same predicate, not a copy)


def _f(v, spec, dash="n/a"):
    return format(v, spec) if v is not None else dash


def _cap_contrast(outdir, payloads):
    """The three strategies whose chunks ran before V51's 1.75% cap landed
    mid-sweep were re-run under it. Both arms are kept, so the cost of the cap
    is a measurement here rather than an inference. See v17/uncapped/README."""
    unc_dir = outdir / "uncapped"
    if not unc_dir.is_dir():
        return
    capped = {d["strategy"]: d for d in payloads}
    print("\n## What the 1.75% loss cap cost — same grid, same window, both arms\n")
    print("| Strategy | arm | best WR | Wilson LB | ExpR | dead | distinct WR of 108 |")
    print("|---|---|---|---|---|---|---|")
    for p in sorted(unc_dir.glob("*.json")):
        u = json.loads(p.read_text())
        c = capped.get(u["strategy"])
        if not c:
            continue
        for label, d in (("uncapped", u), ("**capped**", c)):
            b = d.get("best")
            n_wr = len({round(r["win_rate"], 6) for r in d["rows"]
                        if r["win_rate"] is not None})
            if not b:
                print(f"| {d['strategy']} | {label} | **none qualifies** | — | — | — | {n_wr} |")
                continue
            print(f"| {d['strategy']} | {label} | {b['win_rate']:.1f}% | "
                  f"{b['wilson_lb']:.1f}% | {_f(b['expectancy_r'], '+.3f')} | "
                  f"{b['excluded_share'] * 100:.0f}% | {n_wr} |")


def main():
    outdir = Path(sys.argv[1] if len(sys.argv) > 1
                  else "docs/superpowers/results/v17")
    files = sorted(outdir.glob("*.json"))
    if not files:
        sys.exit(f"no grid JSONs in {outdir}")

    payloads = [json.loads(p.read_text()) for p in files]
    print(f"Chunks found: {len(payloads)} / 11\n")

    print("## Winners, one per strategy\n")
    print("| Strategy | floor | rr | stop | trail | N | N ind | WR | Wilson LB | ExpR | dead |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for d in sorted(payloads, key=lambda d: d["strategy"]):
        best = d.get("best")
        if not best:
            print(f"| {d['strategy']} | — | — | — | — | — | — | **no config qualifies** | — | — | — |")
            continue
        p = best["params"]
        print(f"| {d['strategy']} | {p['min_target_pct']} | {p['rr']} | "
              f"{p['atr_stop_multiple']} | {p['trail_atr_mult']} | "
              f"{best['n_eval']} | {best['n_independent']} | "
              f"{_f(best['win_rate'], '.1f')}% | {best['wilson_lb']:.1f}% | "
              f"{_f(best['expectancy_r'], '+.3f')} | "
              f"{best['excluded_share'] * 100:.0f}% |")

    print("\n## Qualification and the horizon-reuse correction\n")
    print("| Strategy | configs | qualify | qualify if N were the summed N | max reuse ratio |")
    print("|---|---|---|---|---|")
    for d in sorted(payloads, key=lambda d: d["strategy"]):
        rows = d["rows"]
        q = sum(1 for r in rows if qualifies(r))
        q_naive = sum(1 for r in rows
                      if r["n_eval"] >= 30 and (r["expectancy_r"] or 0) > 0
                      and r["excluded_share"] <= 0.5)
        ratio = max((r["horizon_overcount"] for r in rows), default=1.0)
        flag = " **<-**" if q_naive > q else ""
        print(f"| {d['strategy']} | {len(rows)} | {q} | {q_naive}{flag} | {ratio:.1f}x |")

    print("\n## Best row per axis value (win rate of the best qualifying config)\n")
    for axis in ("min_target_pct", "rr", "atr_stop_multiple", "trail_atr_mult"):
        print(f"\n### {axis}\n")
        values = sorted({r["params"][axis] for d in payloads for r in d["rows"]})
        print("| Strategy | " + " | ".join(str(v) for v in values) + " |")
        print("|---" * (len(values) + 1) + "|")
        for d in sorted(payloads, key=lambda d: d["strategy"]):
            cells = []
            for v in values:
                cand = [r for r in d["rows"]
                        if r["params"][axis] == v and qualifies(r)]
                best = max(cand, key=lambda r: r["win_rate"] or -9, default=None)
                cells.append(f"{best['win_rate']:.1f}" if best else "—")
            print(f"| {d['strategy']} | " + " | ".join(cells) + " |")

    _cap_contrast(outdir, payloads)

    print("\n## Stretch goal (V6 Step 3: WR >= 90%)\n")
    hits = [(d["strategy"], r) for d in payloads for r in d["rows"]
            if qualifies(r) and (r["win_rate"] or 0) >= 90]
    if not hits:
        best = max(((d["strategy"], r) for d in payloads for r in d["rows"]
                    if qualifies(r)), key=lambda x: x[1]["win_rate"] or -9,
                   default=None)
        if best:
            s, r = best
            print(f"Not reached. Best qualifying win rate anywhere in the grid: "
                  f"**{r['win_rate']:.1f}%** ({s}, Wilson LB {r['wilson_lb']:.1f}%, "
                  f"independent N={r['n_independent']}).")
        else:
            print("Not reached — and no config anywhere in the grid qualifies at all.")
    else:
        print(f"{len(hits)} qualifying configs at WR >= 90%:")
        for s, r in sorted(hits, key=lambda x: -x[1]["win_rate"]):
            print(f"- {s}: WR {r['win_rate']:.1f}%, Wilson LB {r['wilson_lb']:.1f}%, "
                  f"independent N={r['n_independent']} "
                  f"({'PROVISIONAL, N<59' if r['n_independent'] < 59 else 'N>=59'})"
                  f" — {r['params']}")


if __name__ == "__main__":
    main()
