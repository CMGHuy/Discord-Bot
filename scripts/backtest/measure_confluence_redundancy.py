"""v49 Task 3: measure inter-family co-occurrence, emit the frozen 12x12 matrix.

Run: python scripts/backtest/measure_confluence_redundancy.py [n_tickers]

WHAT THIS MEASURES, AND WHY IT NEEDS ITS OWN INSTRUMENT
-------------------------------------------------------
`levels.count_confirming_strategies` counts FAMILIES that land within
`CONFLUENCE_DEVIATION_PCT` of a target. Several of those families are
derivations of the same underlying series -- EMA/VWAP/AVWAP/Bollinger/Donchian/
Rolling S/R all slide a window over the same closes; Fibonacci/Zigzag Pivot/
Floor Pivot all derive from the same swing extremes -- so a count of 5 can be
two observations wearing five hats.

This sweeps TRAIN (2020-01-01..2023-12-31), and for every candidate price at
every sampled bar records which families landed on it. That gives a tally:

    C[i][i] = number of candidate prices family i landed on
    C[i][j] = number of those on which family j ALSO landed

and the symmetrised conditional

    R[i][j] = (C[i][j]/C[i][i] + C[j][i]/C[j][j]) / 2

which is what `edge/confluence.py` divides by. Same instrument shape as
`measure_avwap_confluence.py` (v35 Task 4), and for the same reason:
`run_backtest_range.py`'s named-strategy path never calls
count_confirming_strategies at all, so this question is invisible to the
standard harness.

PROGRESS OUTPUT IS MANDATORY (repo rule): one flushed line per ticker-horizon,
so a backgrounded run is monitorable rather than a silent multi-minute hang.
"""
from __future__ import annotations

import os
import sys
import warnings
from collections import defaultdict

warnings.filterwarnings("ignore")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts", "data"))

TRAIN_FROM, TRAIN_TO = "2020-01-01", "2023-12-31"
HORIZ = ["4w", "2m", "3m", "4m", "6m"]
SAMPLE_EVERY = 20


def tally_to_matrix(tally: dict, n: int) -> list[list[float]]:
    """Co-occurrence tally -> symmetric redundancy matrix with a unit diagonal.

    `tally` is {(i, j): count}; the diagonal (i, i) is how often family i
    landed at all. A family that never landed contributes nothing: its
    conditional is undefined, and the honest encoding of "no evidence" is a
    zero off-diagonal, not an implicit 1.0 that would discount every count it
    appears in. Its own diagonal stays 1.0 so the matrix shape holds.
    """
    m = [[0.0] * n for _ in range(n)]
    for i in range(n):
        m[i][i] = 1.0
    for i in range(n):
        ci = tally.get((i, i), 0)
        for j in range(i + 1, n):
            cj = tally.get((j, j), 0)
            if ci <= 0 or cj <= 0:
                continue
            v = (tally.get((i, j), 0) / ci + tally.get((j, i), 0) / cj) / 2.0
            v = min(1.0, max(0.0, v))
            m[i][j] = m[j][i] = v
    return m


def main() -> int:
    from fetch_backtest_data import load_cached, load_watchlist
    from swingbot import config
    from swingbot.core.market import levels
    from swingbot.core.market.strategy_types import HORIZONS, MIN_BARS

    families = list(levels.ALL_STRATEGY_FAMILIES)
    index = {name: i for i, name in enumerate(families)}
    n = len(families)
    tol = float(config.CONFLUENCE_DEVIATION_PCT)

    tickers = sorted(load_watchlist())
    if len(sys.argv) > 1:
        tickers = tickers[:int(sys.argv[1])]

    tally: dict = defaultdict(int)
    total_units = len(tickers) * len(HORIZ)
    unit = 0
    n_prices = 0
    skipped = 0

    print(f"measuring redundancy: {len(tickers)} tickers x {len(HORIZ)} horizons, "
          f"TRAIN {TRAIN_FROM}..{TRAIN_TO}, tol={tol}%", flush=True)

    for tkr in tickers:
        df = load_cached(tkr)
        if df is None:
            skipped += 1
            unit += len(HORIZ)
            print(f"[{unit}/{total_units}] {tkr} -- no cached data, skipped", flush=True)
            continue
        for hk in HORIZ:
            unit += 1
            h = HORIZONS[hk]
            warm = MIN_BARS[hk]
            pairs_here = 0
            for i in range(warm, len(df), SAMPLE_EVERY):
                ts = str(df.index[i].date())
                if not (TRAIN_FROM <= ts <= TRAIN_TO):
                    continue
                window = df.iloc[:i + 1]
                price = float(window["Close"].iloc[-1])
                try:
                    candidates = levels.collect_candidate_levels(window, h, price)
                except Exception:
                    continue

                # One tally entry per CANDIDATE PRICE: which families land on it.
                for target, _label in candidates:
                    if not target or target <= 0:
                        continue
                    present = set()
                    for cp, clabel in candidates:
                        if not cp or cp <= 0:
                            continue
                        if abs(cp - target) / target * 100.0 <= tol:
                            fam = levels.strategy_family(clabel)
                            if fam in index:
                                present.add(index[fam])
                    if not present:
                        continue
                    n_prices += 1
                    pairs_here += len(present) * len(present)
                    for a in present:
                        for b in present:
                            tally[(a, b)] += 1
            print(f"[{unit}/{total_units}] {tkr} {hk} pairs={pairs_here}", flush=True)

    matrix = tally_to_matrix(tally, n)

    print(f"\nprices tallied: {n_prices}   tickers skipped: {skipped}", flush=True)
    print("\nper-family landing counts (the N behind each row):", flush=True)
    for i, name in enumerate(families):
        print(f"  {name:18s} {tally.get((i, i), 0)}", flush=True)

    print("\n# --- paste into swingbot/core/edge/confluence.py ---", flush=True)
    print("REDUNDANCY = [", flush=True)
    for i, row in enumerate(matrix):
        cells = ", ".join(f"{v:.4f}" for v in row)
        print(f"    [{cells}],   # {families[i]}", flush=True)
    print("]", flush=True)

    off = [matrix[i][j] for i in range(n) for j in range(n) if i != j]
    strongest = max(off) if off else 0.0
    print(f"\nmax off-diagonal: {strongest:.4f}", flush=True)
    if strongest < 0.15:
        print("NEAR-IDENTITY: every off-diagonal < 0.15. The premise is false -- "
              "the families are already independent and there is nothing to "
              "discount. Record this and STOP (Task 4 Step 5).", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
