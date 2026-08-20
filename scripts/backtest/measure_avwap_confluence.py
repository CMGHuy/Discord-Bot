"""v35 Task 4: confluence-count distribution + AVWAP anti-inflation check.

Run: python scripts/backtest/measure_avwap_confluence.py [n_tickers]

Purpose-built instrument, in the same spirit as the measurement behind
LEVEL_LIFECYCLE_STOPS_ENABLED's "on by default, not a demonstrated edge"
precedent (docs/superpowers/results/2026-08-08-level-lifecycle-stops-validation.md):
run_backtest_range.py's named-strategy path never calls
levels.count_confirming_strategies at all (that lives only in
backtest_scenarios.replay_scenarios), so the confluence question this
measures is invisible to the standard harness. Result of the 2026-08-20 run:
docs/superpowers/plans/implemented/v35-avwap-preregistration.md section 5.1.


The plan's Global Constraint is "method count must not inflate with anchor
count". AVWAP now emits ONE labelled candidate PER ANCHOR ("Anchored VWAP
(52w high)", "Anchored VWAP (swing low)", ...), and levels.strategy_family is
supposed to fold every one of them back to the single "AVWAP" family. If that
guard leaks, a target's method count rises by MORE THAN ONE purely because the
ticker happened to have several anchors.

Two measurements, deliberately separated:

(A) FIXED-TARGET family delta -- the clean guard test. Hold the target price
    still and recount confirming families with the flag off and on. Any delta
    is purely the family-addition effect. A correct guard gives delta in
    {0, +1}, never more, and the added family set must be exactly {"AVWAP"}
    whenever it is +1.

(B) MOVING-MAP effect -- the honest end-to-end. Rebuild the clustered level
    map with the flag on and compare target prices against the off arm. This
    picks up the second-order effect (AVWAP candidates shift _cluster_levels
    bucket means, moving the target price itself). This is the "level map
    moved more than intended" check and where TP1 drift is measured.

PERFORMANCE: collect_candidate_levels is the expensive call, so it is made
exactly TWICE per sampled bar (once per arm) and the resulting candidate list
is reused for every target price evaluated at that bar. The family-counting
below is an inlined copy of levels.count_confirming_strategies' body -- same
tolerance rule, same strategy_family folding -- kept identical on purpose so
the amortization changes cost, not semantics.
"""
import os
import sys
import warnings
from collections import Counter

warnings.filterwarnings("ignore")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts", "data"))

from fetch_backtest_data import load_cached, load_watchlist
from swingbot import config
from swingbot.core.market import levels
from swingbot.core.market.strategy_types import HORIZONS, MIN_BARS

HORIZ = ["4w", "2m", "3m", "4m", "6m"]
SAMPLE_EVERY = 20
TOL = 5.0                       # replay_scenarios' tolerance_pct
TRAIN_FROM, TRAIN_TO = "2020-01-01", "2023-12-31"


def families_at(candidates, target, tol=TOL):
    """Inlined levels.count_confirming_strategies body (see module docstring)."""
    fams = set()
    for price, label in candidates:
        if not price or price <= 0:
            continue
        if abs(price - target) / target * 100 <= tol:
            fams.add(levels.strategy_family(label))
    return fams


def main():
    tickers = sorted(load_watchlist())
    if len(sys.argv) > 1:
        tickers = tickers[:int(sys.argv[1])]

    dist_off, dist_on = Counter(), Counter()
    delta_fixed = Counter()
    added_family_sets = Counter()
    leaks = []
    avwap_only_gain = 0
    n_targets = 0

    tp_same = tp_diff = 0
    tp_drift_pcts = []
    n_lv_off = n_lv_on = 0
    n_bars = 0

    for ti, tkr in enumerate(tickers, 1):
        df = load_cached(tkr)
        if df is None:
            continue
        for hk in HORIZ:
            h = HORIZONS[hk]
            warm = MIN_BARS[hk]
            for i in range(warm, len(df), SAMPLE_EVERY):
                ts = str(df.index[i].date())
                if not (TRAIN_FROM <= ts <= TRAIN_TO):
                    continue
                window = df.iloc[:i + 1]
                price = float(window["Close"].iloc[-1])

                config.AVWAP_LEVELS_ENABLED = False
                try:
                    cand_off = levels.collect_candidate_levels(window, h, price)
                except Exception:
                    continue
                config.AVWAP_LEVELS_ENABLED = True
                try:
                    cand_on = levels.collect_candidate_levels(window, h, price)
                except Exception:
                    continue
                n_bars += 1

                # ---- (A) fixed target: the OFF map's clustered levels ----
                clustered_off = levels._cluster_levels(cand_off)
                clustered_on = levels._cluster_levels(cand_on)
                n_lv_off += len(clustered_off)
                n_lv_on += len(clustered_on)

                for lv in clustered_off:
                    t = lv.price
                    if not t or t <= 0:
                        continue
                    n_targets += 1
                    f_off = families_at(cand_off, t)
                    f_on = families_at(cand_on, t)
                    c_off, c_on = len(f_off), len(f_on)
                    dist_off[c_off] += 1
                    dist_on[c_on] += 1
                    d = c_on - c_off
                    delta_fixed[d] += 1
                    added = tuple(sorted(f_on - f_off))
                    added_family_sets[added] += 1
                    if d == 1 and added == ("AVWAP",):
                        avwap_only_gain += 1
                    if d > 1:
                        leaks.append(("delta>1", tkr, hk, ts, c_off, c_on, added))
                    for f in f_on:
                        if "VWAP" in f and f not in ("VWAP", "AVWAP"):
                            leaks.append(("unfolded", tkr, hk, ts, f, added))

                # ---- (B) moving map: did the level PRICES move? ----
                off_prices = sorted(lv.price for lv in clustered_off)
                on_prices = sorted(lv.price for lv in clustered_on)
                for p in off_prices:
                    nearest = min(on_prices, key=lambda q: abs(q - p)) if on_prices else None
                    if nearest is None:
                        tp_diff += 1
                        continue
                    if abs(nearest - p) < 1e-9:
                        tp_same += 1
                    else:
                        tp_diff += 1
                        tp_drift_pcts.append(abs(nearest - p) / p * 100)

        print(f"[{ti}/{len(tickers)}] {tkr} bars={n_bars} targets={n_targets} "
              f"leaks={len(leaks)}", flush=True)

    # No reset here: this process exits right after, and the per-bar loop
    # above always leaves config.AVWAP_LEVELS_ENABLED True as its last write
    # (line ~111) -- which now matches the judged default (v35), not a
    # stale pre-v35 False this used to force back on exit.

    def mean(c):
        tot = sum(c.values())
        return sum(k * v for k, v in c.items()) / tot if tot else 0.0

    print("\n" + "=" * 64)
    print("(A) FIXED-TARGET (level map held still) -- the anti-inflation guard")
    print("=" * 64)
    print(f"bars sampled: {n_bars}   targets evaluated: {n_targets}")
    print(f"  mean confluence OFF: {mean(dist_off):.4f}")
    print(f"  mean confluence ON : {mean(dist_on):.4f}")
    print(f"  MEAN DELTA         : {mean(dist_on) - mean(dist_off):+.4f}  "
          f"(pre-registered guard: < +0.5)")
    print("  distribution OFF:", dict(sorted(dist_off.items())))
    print("  distribution ON :", dict(sorted(dist_on.items())))
    print("  count-delta histogram:", dict(sorted(delta_fixed.items())))
    print(f"  delta==+1 with added exactly {{AVWAP}}: {avwap_only_gain}")
    print("  added-family sets (top 8):")
    for fams, n in added_family_sets.most_common(8):
        print(f"    {fams or '(none)'}: {n}")
    print(f"  LEAKS (delta>1, or an unfolded 'Anchored VWAP (...)' family): {len(leaks)}")
    for L in leaks[:10]:
        print("   ", L)

    print("\n" + "=" * 64)
    print("(B) MOVING MAP -- level-price drift")
    print("=" * 64)
    tot = tp_same + tp_diff
    if tot:
        print(f"  level prices compared: {tot}")
        print(f"    unchanged: {tp_same} ({tp_same / tot * 100:.2f}%)")
        print(f"    moved    : {tp_diff} ({tp_diff / tot * 100:.2f}%)")
    if tp_drift_pcts:
        srt = sorted(tp_drift_pcts)
        print(f"    drift among moved: mean {sum(srt)/len(srt):.4f}%  "
              f"median {srt[len(srt)//2]:.4f}%  "
              f"p90 {srt[int(len(srt)*0.9)]:.4f}%  max {srt[-1]:.4f}%")
    print(f"  clustered levels in map: OFF {n_lv_off}  ON {n_lv_on}  "
          f"({(n_lv_on - n_lv_off) / n_lv_off * 100:+.2f}%)" if n_lv_off else "")


if __name__ == "__main__":
    main()
