#!/usr/bin/env python3
"""v33 Task 7: what the adjacent-horizon gate actually costs and buys, per
horizon, plus the neutral-band test and the macro-anchor weight.

WHY NOT run_backtest_range.py (the brief's literal Step 1 command): that
script simulates trades through `swingbot.core.backtesting.backtest` /
`backtest_scenarios`, a replay harness that never calls
`swingbot.core.scanning.engine` and therefore never touches
`MTF_ADJACENT_GATE` (engine.py:925) or `factor_macro_alignment`
(scanning/factors.py). Running it would produce a baseline with no
relationship to either. This script instead SIMULATES the gate on the exact
per-scenario verdicts the gate keys on, over the same TRAIN population v33
Task 1 measured, by importing that task's committed instrumentation.

What it reports (v33 Task 7's four steps):
  1. Per horizon: scenarios and win rate with the gate OFF vs ON, Wilson
     95% on both. Comparator arm: the same simulation for the horizon's OWN
     trend, which Task 1 found better-powered (n_opp 419 vs 200).
  2. Per-horizon volume loss against the plan's ~30% aggregate budget, so a
     horizon that blows past it can be scoped out of the gate.
  3. Neutral band: scenarios where |ema_fast - ema_slow| / close < 0.5% on
     the ADJACENT horizon -- both the brief's literal coin-flip test and the
     sharper question the band exists to answer (does an "opposed" verdict
     inside the band still discriminate winners from losers?).
  4. The 6m macro anchor's lift, which sets `_MACRO_ALIGNMENT_POINTS`.

Win rate is wins / (wins + losses) throughout -- backtest.py's convention,
scratch and timeout excluded. "Scenarios" counts every row including
scratch/timeout, because the gate drops a scenario before its outcome is
known: that count, not the evaluated one, is the alert-volume cost.

TRAIN by default. `--validation` exists for v33 Task 8's ONE pre-registered
shot and for nothing else -- do not run it to "check" anything.

Prints one flushed line per ticker via collect() (CLAUDE.md).

Run: python scripts/backtest/measure_adjacent_gate_effect.py --train \
         --cache-dir ../../data/backtest_cache --json data/v33_train.json
"""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
# Task 1's instrument sits beside this file; import it rather than
# re-deriving the population, so both tasks measure the same rows.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from measure_trend_signal_overlap import (  # noqa: E402
    CACHE_DIR, HKEYS, TRAIN, _wins_and_evaluated, collect, signal_lift,
    verify_ema_precompute, wilson_interval,
)

VALIDATION = ("2024-01-01", "2025-12-31")  # verbatim run_backtest_range.py:67

# The brief's Step 3 threshold. The two neighbours are sensitivity only --
# a band chosen by scanning thresholds for the one that helps would be the
# data-dredging v32's discipline exists to prevent, so 0.005 is the
# pre-committed value and the others only say how sharp the edge is.
NEUTRAL_BAND = 0.005
BAND_SENSITIVITY = (0.0025, 0.005, 0.01)

# The plan's aggregate alert-volume ceiling for the gate.
VOLUME_BUDGET_PCT = 30.0
# A single horizon above this is a candidate for exclusion from the gate's
# scope rather than a reason to abandon the gate (brief Step 2).
PER_HORIZON_ALARM_PCT = 30.0


def _wr_block(rows: list) -> dict:
    wins, n_ev = _wins_and_evaluated(rows)
    lo, hi = wilson_interval(wins, n_ev)
    return {"scenarios": len(rows), "evaluated": n_ev, "wins": wins,
            "wr": wins / n_ev if n_ev else 0.0, "wilson": [lo, hi]}


def _kept(rows: list, key: str, band: float | None = None,
          margin_key: str = "adj_margin") -> list:
    """Rows the gate keeps: everything except a genuine `False` verdict.
    `None` is EXEMPT (no higher horizon, or too little history) and is
    always kept -- the plan's Global Constraints forbid conflating exempt
    with opposed. With `band`, an opposed verdict whose EMA pair is closer
    together than `band` is also kept (the neutral band)."""
    out = []
    for r in rows:
        if r[key] is not False:
            out.append(r)
            continue
        if band is not None:
            m = r.get(margin_key)
            if m is not None and m < band:
                out.append(r)
    return out


def gate_table(rows: list, key: str, band: float | None = None) -> dict:
    """Per horizon (plus ALL): before/after scenarios, win rates, Wilson,
    volume loss."""
    out = {}
    for hk in HKEYS + ["ALL"]:
        bucket = rows if hk == "ALL" else [r for r in rows if r["horizon"] == hk]
        before = _wr_block(bucket)
        after = _wr_block(_kept(bucket, key, band))
        dropped = before["scenarios"] - after["scenarios"]
        out[hk] = {
            "before": before, "after": after, "dropped": dropped,
            "volume_loss_pct": (100 * dropped / before["scenarios"]
                                if before["scenarios"] else 0.0),
            "wr_delta_pp": 100 * (after["wr"] - before["wr"]),
            # Does the gated population's win rate separate from the
            # ungated one? Overlapping intervals mean the gate did not
            # measurably move win rate on this horizon, however good the
            # point estimate looks. (Nested samples, so this is a
            # descriptive overlap check, not an independent-sample test --
            # it can only ever be conservative.)
            "separated": not (after["wilson"][0] <= before["wilson"][1]
                              and before["wilson"][0] <= after["wilson"][1]),
        }
    return out


def opposed_vs_aligned(rows: list, key: str) -> dict:
    """The discriminating power of the verdict itself on this subset.

    Adds `measurable`. signal_lift's `overlapping` is computed from
    wilson_interval, which returns (0.0, 0.0) for n=0 -- so an EMPTY oppose
    arm reports a huge lift with "separated" intervals, which is an
    artefact, not a finding. Anything with an empty arm is unmeasurable and
    the caller must not read `lift` from it. (This wraps rather than edits
    signal_lift: that function's output is published in Task 1's document.)"""
    out = signal_lift(rows, key, lambda r: r[key] is True,
                      lambda r: r[key] is False)
    out["measurable"] = out["n_agree"] > 0 and out["n_oppose"] > 0
    if not out["measurable"]:
        out["overlapping"] = True
    return out


def neutral_band_table(rows: list, key: str = "adj_agree",
                       margin_key: str = "adj_margin") -> dict:
    """Step 3. For each candidate band: what is inside it, whether the
    inside is a coin flip, and -- the question that actually decides it --
    whether an opposed verdict inside the band still tells winners from
    losers the way one outside it does."""
    have = [r for r in rows if r.get(margin_key) is not None]
    out = {"n_with_margin": len(have), "bands": {}}
    for band in BAND_SENSITIVITY:
        inside = [r for r in have if r[margin_key] < band]
        outside = [r for r in have if r[margin_key] >= band]
        blk = _wr_block(inside)
        opp_in = [r for r in inside if r[key] is False]
        out["bands"][f"{band}"] = {
            "n_inside": len(inside),
            "inside_share_pct": 100 * len(inside) / len(have) if have else 0.0,
            "inside_wr": blk,
            # The brief's literal test: is the band a coin flip?
            "spans_50pct": blk["wilson"][0] <= 0.5 <= blk["wilson"][1],
            # ... and the base rate it has to be read against, because a
            # population whose pooled WR is ~45% makes "spans 50%" easy to
            # satisfy by low power alone.
            "inside_vs_pooled_separated": not (
                blk["wilson"][0] <= _wr_block(have)["wilson"][1]
                and _wr_block(have)["wilson"][0] <= blk["wilson"][1]),
            "lift_inside": opposed_vs_aligned(inside, key),
            "lift_outside": opposed_vs_aligned(outside, key),
            # What exempting the band would hand back to alert volume.
            "opposed_inside": len(opp_in),
            "opposed_total": sum(1 for r in have if r[key] is False),
        }
    return out


def macro_table(rows: list) -> dict:
    """Step 4. Overall and per-horizon lift of the 6m macro anchor -- the
    only evidence `_MACRO_ALIGNMENT_POINTS` may be set from."""
    overall = opposed_vs_aligned(rows, "macro_agree")
    per_hz = {}
    for hk in HKEYS:
        bucket = [r for r in rows if r["horizon"] == hk
                  and r["macro_agree"] is not None]
        if not bucket:
            continue
        per_hz[hk] = opposed_vs_aligned(bucket, "macro_agree")
    return {"overall": overall, "per_horizon": per_hz}


def _fmt_wr(b: dict) -> str:
    return (f"n={b['scenarios']:>5} ev={b['evaluated']:>5} "
            f"WR={b['wr']*100:5.1f}% [{b['wilson'][0]*100:4.1f},"
            f"{b['wilson'][1]*100:4.1f}]")


def print_gate_table(title: str, table: dict) -> None:
    print(f"\n{title}")
    print(f"  {'hz':>3}  {'BEFORE (gate off)':<38}  {'AFTER (gate on)':<38}  "
          f"{'cut':>7}  {'dWR':>7}  sep")
    for hk, row in table.items():
        flag = "yes" if row["separated"] else "no"
        print(f"  {hk:>3}  {_fmt_wr(row['before']):<38}  "
              f"{_fmt_wr(row['after']):<38}  "
              f"{row['volume_loss_pct']:6.2f}%  {row['wr_delta_pp']:+6.2f}pp  "
              f"{flag}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--train", action="store_true", help="the TRAIN window")
    g.add_argument("--validation", action="store_true",
                   help="the VALIDATION window -- v33 Task 8's ONE shot only")
    ap.add_argument("--json", default=None, help="write the full result set here")
    ap.add_argument("--cache-dir", default=None,
                    help="OHLCV CSV cache. Defaults to <repo>/data/backtest_cache, "
                         "which is EMPTY inside a git worktree -- point this at "
                         "the main checkout's cache when running from one.")
    ap.add_argument("--limit", type=int, default=None,
                    help="only the first N cached tickers (smoke test)")
    args = ap.parse_args()

    window = VALIDATION if args.validation else TRAIN
    label = "VALIDATION" if args.validation else "TRAIN"

    cache = Path(args.cache_dir) if args.cache_dir else CACHE_DIR
    paths = sorted(cache.glob("*.csv"))
    if args.limit:
        paths = paths[:args.limit]
    if not paths:
        print(f"No CSVs in {cache} -- run scripts/data/fetch_backtest_data.py "
              f"first, or pass --cache-dir.", file=sys.stderr)
        return 1
    frames = {p.stem: pd.read_csv(p, index_col="Date", parse_dates=True)
              for p in paths}

    if verify_ema_precompute(frames) != 0:
        print("ABORT: EMA precompute disagrees with get_htf_bias -- results "
              "would be lookahead-contaminated.", file=sys.stderr)
        return 1

    print(f"Window: {label} {window[0]}..{window[1]} over {len(frames)} tickers",
          flush=True)
    rows = collect(frames, window)
    print(f"\nTotal {label} scenarios: {len(rows)}", flush=True)

    adj = gate_table(rows, "adj_agree")
    print_gate_table("STEP 1 -- adjacent-horizon gate (MTF_ADJACENT_GATE), "
                     "per horizon:", adj)

    own = gate_table(rows, "own_agree")
    print_gate_table("COMPARATOR -- same simulation on the horizon's OWN "
                     "trend (not proposed, Task 1 asked for the arm):", own)

    banded = gate_table(rows, "adj_agree", band=NEUTRAL_BAND)
    print_gate_table(f"STEP 3 -- adjacent gate WITH a {NEUTRAL_BAND*100:.2f}% "
                     f"neutral band (opposed-but-near-flat kept):", banded)

    over = [hk for hk in HKEYS
            if adj[hk]["volume_loss_pct"] > PER_HORIZON_ALARM_PCT]
    print(f"\nSTEP 2 -- aggregate volume loss "
          f"{adj['ALL']['volume_loss_pct']:.2f}% against the "
          f"{VOLUME_BUDGET_PCT:.0f}% budget; horizons over "
          f"{PER_HORIZON_ALARM_PCT:.0f}%: {over or 'none'}", flush=True)

    band = neutral_band_table(rows)
    print(f"\nSTEP 3 -- neutral band on the adjacent horizon's EMA pair "
          f"({band['n_with_margin']} rows carry a margin):")
    def _verdict(x: dict) -> str:
        if not x["measurable"]:
            return "  (unmeasurable -- an arm is empty)"
        return "  (overlap)" if x["overlapping"] else "  (SEPARATED)"

    for b, d in band["bands"].items():
        li, lo = d["lift_inside"], d["lift_outside"]
        print(f"  band <{float(b)*100:.2f}%: n={d['n_inside']} "
              f"({d['inside_share_pct']:.1f}% of rows)  "
              f"WR={d['inside_wr']['wr']*100:.1f}% "
              f"[{d['inside_wr']['wilson'][0]*100:.1f},"
              f"{d['inside_wr']['wilson'][1]*100:.1f}]  "
              f"spans50={d['spans_50pct']}  "
              f"opposed_inside={d['opposed_inside']}/{d['opposed_total']}",
              flush=True)
        print(f"      inside : agree n={li['n_agree']:>4} "
              f"WR={li['wr_agree']*100:5.1f}%  oppose n={li['n_oppose']:>4} "
              f"WR={li['wr_oppose']*100:5.1f}%  lift={li['lift']*100:+5.1f}pp"
              f"{_verdict(li)}", flush=True)
        print(f"      outside: agree n={lo['n_agree']:>4} "
              f"WR={lo['wr_agree']*100:5.1f}%  oppose n={lo['n_oppose']:>4} "
              f"WR={lo['wr_oppose']*100:5.1f}%  lift={lo['lift']*100:+5.1f}pp"
              f"{_verdict(lo)}", flush=True)

    macro = macro_table(rows)
    m = macro["overall"]
    print(f"\nSTEP 4 -- 6m macro anchor: agree n={m['n_agree']} "
          f"WR={m['wr_agree']*100:.1f}% "
          f"[{m['wilson_agree'][0]*100:.1f},{m['wilson_agree'][1]*100:.1f}]  "
          f"oppose n={m['n_oppose']} WR={m['wr_oppose']*100:.1f}% "
          f"[{m['wilson_oppose'][0]*100:.1f},{m['wilson_oppose'][1]*100:.1f}]  "
          f"lift={m['lift']*100:+.1f}pp  "
          f"{'UNMEASURABLE -- an arm is empty' if not m['measurable'] else ('OVERLAPPING -- no measured lift' if m['overlapping'] else 'SEPARATED')}",
          flush=True)
    for hk, d in macro["per_horizon"].items():
        print(f"    {hk:>3}: agree n={d['n_agree']:>4} WR={d['wr_agree']*100:5.1f}%  "
              f"oppose n={d['n_oppose']:>3} WR={d['wr_oppose']*100:5.1f}%  "
              f"lift={d['lift']*100:+5.1f}pp"
              f"{'  (unmeasurable -- an arm is empty)' if not d['measurable'] else ('  (overlap)' if d['overlapping'] else '  (SEPARATED)')}",
              flush=True)

    if args.json:
        out = {
            "window": {"label": label, "from": window[0], "to": window[1]},
            "n_tickers": len(frames),
            "n_scenarios": len(rows),
            "neutral_band_pre_committed": NEUTRAL_BAND,
            "volume_budget_pct": VOLUME_BUDGET_PCT,
            "adjacent_gate": adj,
            "own_horizon_comparator": own,
            "adjacent_gate_with_neutral_band": banded,
            "horizons_over_budget": over,
            "neutral_band": band,
            "macro_anchor": macro,
        }
        Path(args.json).write_text(json.dumps(out, indent=2))
        print(f"\nWrote {args.json}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
