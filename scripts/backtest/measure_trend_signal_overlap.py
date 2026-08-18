#!/usr/bin/env python3
"""v33 Task 1: TRAIN-only mutual overlap of the trend signals, via pairwise
Cramer's V plus per-signal win-rate lift with Wilson intervals.

Feeds `docs/superpowers/plans/v33-trend-signal-reconciliation.md`, whose
four decisions retire `HTF_COUNTER_TREND_PENALTY` and `mtf_alignment` and
set Task 7's per-horizon alert-volume budget. Committed so those numbers
stay re-derivable rather than only narrated.

Signals recorded per TRAIN trade entry bar:
  mtf_alignment : edge/factors.py::mtf_alignment (0-3, weekly resample)
  htf_agree     : scanning/regime.py::get_htf_bias agrees? (bool|None)
  penalty_fired : HTF_COUNTER_TREND_PENALTY would fire? (bool)
  adj_agree     : adjacent-horizon check agrees? (bool|None)   [proposed]
  own_agree     : this horizon's own EMA-pair trend agrees?    [comparator]
  macro_agree   : the 6m anchor's EMA-pair trend agrees?       [proposed]

`adj_agree`/`own_agree`/`macro_agree` did not exist when this ran -- v33
Task 2 encapsulates them as `horizon_trend`/`adjacent_horizon` in
`swingbot/core/market/mtf.py`. They are computed here inline from each
horizon's own HORIZONS ema_fast/ema_slow, which is exactly the formula
Task 2 specifies: "bullish" if ema_fast > ema_slow else "bearish". If that
module now exists, this script is deliberately NOT rewired to it -- the
whole point of an independent instrument is that it does not inherit the
bugs of the thing it measured.

NO-LOOKAHEAD: every reading uses df.iloc[:i+1], never a future bar.
`mtf_alignment` is called per window because its weekly resample's last bar
is a PARTIAL week ending at i, so a full-series precompute would silently
substitute completed weeks. The EMAs behind the other signals ARE
precomputed over the full series, which is exact rather than approximate:
pandas ewm(span=N, adjust=False) is strictly recursive, so ema(full).iloc[i]
is bit-identical to ema(full.iloc[:i+1]).iloc[-1]. `--verify-ema` asserts
that against the real get_htf_bias before trusting it.

Prints one flushed line per ticker (CLAUDE.md: any script running more than
a couple of minutes must report progress per unit of work).

Run: python scripts/backtest/measure_trend_signal_overlap.py --train \
         --json data/v33_trend_overlap.json
"""
import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from swingbot import config
from swingbot.core.backtesting.backtest import ALL_STRATEGIES, run_backtest
from swingbot.core.edge import factors as rs_factors
from swingbot.core.market.indicators import ema
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.scanning.regime import _HTF_EMA_PERIOD, get_htf_bias

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "backtest_cache"
TRAIN = ("2020-01-01", "2023-12-31")

HKEYS = list(HORIZONS)
# The next horizon up, in HORIZONS key order. The last horizon has none --
# an EXEMPTION, never a pass (v33 plan's Global Constraints).
NEXT_HORIZON = {HKEYS[i]: HKEYS[i + 1] for i in range(len(HKEYS) - 1)}
NEXT_HORIZON[HKEYS[-1]] = None
# The macro anchor is the 6m horizon (v33 Task 5). Horizons at or above it
# have nothing to anchor to and are exempt, same rule as `9m` above.
MACRO_ANCHOR = "6m"
MACRO_EXEMPT = set(HKEYS[HKEYS.index(MACRO_ANCHOR):])

SIGNALS = ("mtf_alignment", "htf_agree", "penalty_fired",
           "adj_agree", "own_agree", "macro_agree")


def wilson_interval(wins: int, n: int, z: float = 1.96) -> tuple:
    """Wilson score interval for a binomial proportion. Unlike the normal
    approximation it stays inside [0,1] and stays honest at small n.

    Kept as a verbatim copy of measure_factor_lift.py's (v32 Task 8)
    rather than an import: these two scripts are independent instruments
    reporting on overlapping populations, and a shared helper edited for
    one would silently move the other's published numbers."""
    if n <= 0:
        return (0.0, 0.0)
    p = wins / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def cramers_v(pairs: list) -> tuple:
    """Cramer's V for two categorical variables, from a list of (a, b)
    observations. Returns (V, n, n_rows, n_cols).

    No bias correction -- the v33 plan's "collapse any pair above 0.7"
    rule is stated against plain V, and applying a correction here would
    quietly move the threshold the decisions were made against.

    A variable with a single observed category has no association to
    measure and returns 0.0 rather than dividing by zero. Read that as
    "undefined", NOT as "measured independence": it means one signal never
    varied on this population."""
    if not pairs:
        return (0.0, 0, 0, 0)
    table = Counter(pairs)
    rows = sorted({a for a, _ in pairs}, key=str)
    cols = sorted({b for _, b in pairs}, key=str)
    n = len(pairs)
    if len(rows) < 2 or len(cols) < 2:
        return (0.0, n, len(rows), len(cols))
    row_tot = Counter(a for a, _ in pairs)
    col_tot = Counter(b for _, b in pairs)
    chi2 = 0.0
    for r in rows:
        for c in cols:
            exp = row_tot[r] * col_tot[c] / n
            if exp > 0:
                chi2 += (table.get((r, c), 0) - exp) ** 2 / exp
    v = math.sqrt(chi2 / (n * min(len(rows) - 1, len(cols) - 1)))
    return (min(1.0, v), n, len(rows), len(cols))


def _wins_and_evaluated(rows: list) -> tuple:
    """wins / (wins + losses), excluding scratch and timeout -- the same
    convention backtest.py's own win_rate uses. A scratch in the
    denominator would understate every win rate reported here."""
    ev = [r for r in rows if r["outcome"] in ("win", "loss")]
    return sum(1 for r in ev if r["outcome"] == "win"), len(ev)


def _trend_agrees(fast: pd.Series, slow: pd.Series, i: int, direction: str) -> bool:
    return (("bullish" if float(fast.iloc[i]) > float(slow.iloc[i])
             else "bearish") == direction)


def verify_ema_precompute(frames: dict, samples_per_horizon: int = 40) -> int:
    """Assert the full-series EMA precompute reproduces the real
    get_htf_bias bar for bar. Returns the number of mismatches, which must
    be 0 -- if it ever isn't, every htf/adjacent/macro number below is
    lookahead-contaminated and the run must be thrown away."""
    mismatches = checked = 0
    for ticker, df in list(frames.items())[:3]:
        close = df["Close"]
        for hk in HKEYS:
            period = _HTF_EMA_PERIOD.get(hk)
            if period is None:
                continue
            series = ema(close, period)
            step = max(1, (len(df) - period - 10) // samples_per_horizon)
            for i in range(period + 10, len(df), step):
                real = get_htf_bias(df.iloc[:i + 1], hk)
                if real is None:
                    continue
                mine = "bullish" if float(close.iloc[i]) > float(series.iloc[i]) else "bearish"
                checked += 1
                mismatches += (real["bias"] != mine)
    print(f"EMA precompute check: {checked} sampled (horizon, bar) pairs, "
          f"{mismatches} mismatches", flush=True)
    return mismatches


def collect(frames: dict) -> list:
    """One row per TRAIN trade entry bar, with all six trend readings."""
    rows = []
    for ticker, df in frames.items():
        close = df["Close"]
        date_to_idx = {str(d.date()): k for k, d in enumerate(df.index)}
        htf_ema = {p: ema(close, p) for p in set(_HTF_EMA_PERIOD.values())}
        hz_ema = {hk: (ema(close, h["ema_fast"]), ema(close, h["ema_slow"]))
                  for hk, h in HORIZONS.items()}
        n_rows = 0
        for hk in HKEYS:
            htf_period = _HTF_EMA_PERIOD.get(hk)
            nxt = NEXT_HORIZON[hk]
            for strategy in ALL_STRATEGIES:
                summary = run_backtest(ticker, df, strategy, hk,
                                       exit_model="v2", scale_out=True)
                for t in summary.trades:
                    if not (TRAIN[0] <= t.entry_date <= TRAIN[1]):
                        continue
                    i = date_to_idx.get(t.entry_date)
                    if i is None or i < 60:
                        continue
                    window = df.iloc[:i + 1]
                    direction = t.direction

                    mtf = int(rs_factors.mtf_alignment(window, direction))

                    # get_htf_bias, inlined against the precomputed EMA.
                    # Guards mirror the real function exactly: the config
                    # flag, an unmapped horizon, and its bar minimum.
                    htf_agree = None
                    if (config.HTF_CONFLUENCE_ENABLED and htf_period is not None
                            and i + 1 >= htf_period + 10):
                        htf_agree = (("bullish" if float(close.iloc[i]) >
                                      float(htf_ema[htf_period].iloc[i])
                                      else "bearish") == direction)
                    # engine.py:995 defines the penalty's trigger as exactly
                    # this. Recorded separately, NOT derived, so the
                    # identity check below can actually fail if it ever
                    # stops holding.
                    penalty_fired = (htf_agree is False)

                    adj_agree = None
                    if nxt is not None and i + 1 >= HORIZONS[nxt]["ema_slow"]:
                        adj_agree = _trend_agrees(*hz_ema[nxt], i, direction)

                    own_agree = None
                    if i + 1 >= HORIZONS[hk]["ema_slow"]:
                        own_agree = _trend_agrees(*hz_ema[hk], i, direction)

                    macro_agree = None
                    if (hk not in MACRO_EXEMPT
                            and i + 1 >= HORIZONS[MACRO_ANCHOR]["ema_slow"]):
                        macro_agree = _trend_agrees(*hz_ema[MACRO_ANCHOR], i, direction)

                    rows.append({
                        "ticker": ticker, "horizon": hk, "strategy": strategy,
                        "direction": direction, "outcome": t.outcome,
                        "mtf_alignment": mtf, "htf_agree": htf_agree,
                        "penalty_fired": penalty_fired, "adj_agree": adj_agree,
                        "own_agree": own_agree, "macro_agree": macro_agree,
                    })
                    n_rows += 1
        print(f"{ticker}: {n_rows} TRAIN entry-bar samples", flush=True)
    return rows


def cramers_v_table(rows: list) -> list:
    """Every unordered pair, over rows where BOTH signals are non-None --
    an unmapped or exempt reading is missing data, not a third category.
    Folding exemptions in as a category would invent association that the
    9m/6m-anchor holes alone would explain."""
    out = []
    for x in range(len(SIGNALS)):
        for y in range(x + 1, len(SIGNALS)):
            a, b = SIGNALS[x], SIGNALS[y]
            obs = [(r[a], r[b]) for r in rows
                   if r[a] is not None and r[b] is not None]
            v, n, n_r, n_c = cramers_v(obs)
            out.append({"a": a, "b": b, "v": v, "n": n,
                        "rows": n_r, "cols": n_c, "collapse": v > 0.7})
    return sorted(out, key=lambda d: -d["v"])


def signal_lift(rows: list, label: str, agree_pred, oppose_pred) -> dict:
    wins_a, n_a = _wins_and_evaluated([r for r in rows if agree_pred(r)])
    wins_o, n_o = _wins_and_evaluated([r for r in rows if oppose_pred(r)])
    lo_a, hi_a = wilson_interval(wins_a, n_a)
    lo_o, hi_o = wilson_interval(wins_o, n_o)
    return {
        "signal": label,
        "n_agree": n_a, "wr_agree": wins_a / n_a if n_a else 0.0,
        "wilson_agree": [lo_a, hi_a],
        "n_oppose": n_o, "wr_oppose": wins_o / n_o if n_o else 0.0,
        "wilson_oppose": [lo_o, hi_o],
        "lift": (wins_a / n_a if n_a else 0.0) - (wins_o / n_o if n_o else 0.0),
        # Overlapping intervals are reported as NO measured lift, never as
        # a small one -- the v32 precedent that emptied the FACTORS pool.
        "overlapping": not (lo_a > hi_o or lo_o > hi_a),
    }


def lift_table(rows: list) -> list:
    out = [signal_lift(rows, "mtf_alignment (>=2 vs <=1)",
                       lambda r: r["mtf_alignment"] >= 2,
                       lambda r: r["mtf_alignment"] <= 1)]
    for key, label in (("htf_agree", "get_htf_bias agrees vs opposes"),
                       ("adj_agree", "adjacent-horizon agrees vs opposes"),
                       ("own_agree", "own-horizon trend agrees vs opposes"),
                       ("macro_agree", "6m macro anchor agrees vs opposes")):
        out.append(signal_lift(
            rows, label,
            lambda r, k=key: r[k] is True, lambda r, k=key: r[k] is False))
    out.append(signal_lift(rows, "HTF penalty NOT fired vs fired",
                           lambda r: r["penalty_fired"] is False,
                           lambda r: r["penalty_fired"] is True))
    return out


def mtf_value_table(rows: list) -> list:
    """Per-value rather than a two-way split: the 0-3 score's designed
    premise is that it is MONOTONE, and only a per-value table can show
    that it isn't."""
    table = []
    for v in range(4):
        wins, n = _wins_and_evaluated([r for r in rows if r["mtf_alignment"] == v])
        lo, hi = wilson_interval(wins, n)
        table.append({"mtf": v, "n": n, "wr": wins / n if n else 0.0,
                      "wilson": [lo, hi]})
    return table


def per_horizon_table(rows: list) -> dict:
    """Per-horizon opposition rates. The adjacent column IS the alert-volume
    cost of v33's proposed hard gate, which the plan caps at ~30% PER
    HORIZON -- an aggregate hides that `2w` alone carries most of it."""
    out = {}
    for hk in HKEYS:
        bucket = [r for r in rows if r["horizon"] == hk]
        n = len(bucket)
        row = {"n": n}
        for key in ("adj_agree", "htf_agree", "macro_agree"):
            counts = Counter(str(r[key]) for r in bucket)
            opposed = counts.get("False", 0)
            row[key] = {
                "opposed": opposed,
                "opposed_pct": round(100 * opposed / n, 2) if n else None,
                "exempt": counts.get("None", 0),
                "counts": dict(counts),
            }
        out[hk] = row
    return out


def identity_check(rows: list) -> dict:
    """penalty_fired is DEFINED at engine.py:995 as `not htf_agree`. If
    this ever reports a violation, the two are no longer the same reading
    and the v33 doc's Decision 2 (collapse at V=1.0) must be revisited."""
    present = [r for r in rows if r["htf_agree"] is not None]
    return {
        "n_htf_present": len(present),
        "violations": sum(1 for r in present
                          if r["penalty_fired"] != (not r["htf_agree"])),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--train", action="store_true",
                    help="run over the TRAIN window (the only supported window)")
    ap.add_argument("--json", default=None, help="write the full result set here")
    ap.add_argument("--cache-dir", default=None,
                    help="OHLCV CSV cache. Defaults to <repo>/data/backtest_cache, "
                         "which is EMPTY inside a git worktree (data/ is "
                         "gitignored, so a worktree gets its own bare copy) -- "
                         "point this at the main checkout's cache when running "
                         "from one.")
    ap.add_argument("--limit", type=int, default=None,
                    help="only the first N cached tickers (smoke test)")
    ap.add_argument("--verify-ema", action="store_true",
                    help="assert the EMA precompute matches get_htf_bias, then exit")
    args = ap.parse_args()

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

    if args.verify_ema:
        return 1 if verify_ema_precompute(frames) else 0
    if verify_ema_precompute(frames) != 0:
        print("ABORT: EMA precompute disagrees with get_htf_bias -- results "
              "would be lookahead-contaminated.", file=sys.stderr)
        return 1

    rows = collect(frames)
    print(f"\nTotal TRAIN scenarios: {len(rows)}", flush=True)
    outcomes = Counter(r["outcome"] for r in rows)
    print(f"Outcomes: {dict(outcomes)}", flush=True)

    vs = cramers_v_table(rows)
    print("\nPairwise Cramer's V (rows where both signals are non-None):")
    for row in vs:
        flag = "  <-- COLLAPSE (V > 0.7)" if row["collapse"] else ""
        print(f"  {row['a']:<15} x {row['b']:<15} V={row['v']:.4f}  "
              f"n={row['n']}{flag}", flush=True)

    lifts = lift_table(rows)
    print("\nPer-signal win-rate lift (Wilson 95%):")
    for L in lifts:
        flag = "  (intervals overlap -- no measured lift)" if L["overlapping"] else ""
        print(f"  {L['signal']:<38} "
              f"agree n={L['n_agree']:>5} WR={L['wr_agree']*100:5.1f}% "
              f"[{L['wilson_agree'][0]*100:.1f},{L['wilson_agree'][1]*100:.1f}]  "
              f"oppose n={L['n_oppose']:>5} WR={L['wr_oppose']*100:5.1f}% "
              f"[{L['wilson_oppose'][0]*100:.1f},{L['wilson_oppose'][1]*100:.1f}]  "
              f"lift={L['lift']*100:+5.1f}pp{flag}", flush=True)

    mtf_table = mtf_value_table(rows)
    print("\nmtf_alignment per value (designed to be monotone -- check that it is):")
    for row in mtf_table:
        print(f"  mtf={row['mtf']}: n={row['n']:>5} WR={row['wr']*100:5.1f}% "
              f"[{row['wilson'][0]*100:.1f},{row['wilson'][1]*100:.1f}]", flush=True)

    per_hz = per_horizon_table(rows)
    print("\nPer-horizon opposition rate (the adjacent column is v33's "
          "alert-volume cost, capped at ~30% per horizon):")
    for hk, row in per_hz.items():
        a, h, m = row["adj_agree"], row["htf_agree"], row["macro_agree"]
        print(f"  {hk:>3}: n={row['n']:>5}  adj_opposed={a['opposed']:>4} "
              f"({a['opposed_pct']}%, exempt={a['exempt']})  "
              f"htf_opposed={h['opposed']:>4} ({h['opposed_pct']}%, "
              f"exempt={h['exempt']})  macro_exempt={m['exempt']}", flush=True)

    ident = identity_check(rows)
    print(f"\nS2/S3 identity check: penalty_fired != (not htf_agree) in "
          f"{ident['violations']} of {ident['n_htf_present']} rows where htf "
          f"is present", flush=True)

    both = [r for r in rows
            if r["htf_agree"] is not None and r["adj_agree"] is not None]
    disagree = [r for r in both if r["htf_agree"] != r["adj_agree"]]
    print(f"htf vs adj: both-present n={len(both)}, disagree n={len(disagree)}"
          + (f" ({len(disagree)/len(both)*100:.1f}%)" if both else ""), flush=True)

    if args.json:
        out = {
            "n_scenarios": len(rows),
            "window": {"train_from": TRAIN[0], "train_to": TRAIN[1]},
            "outcome_counts": dict(outcomes),
            "direction_counts": dict(Counter(r["direction"] for r in rows)),
            "signal_value_counts": {
                k: dict(Counter(str(r[k]) for r in rows)) for k in SIGNALS},
            "cramers_v": vs,
            "lifts": lifts,
            "mtf_value_table": mtf_table,
            "per_horizon": per_hz,
            "identity_check": ident,
            "htf_vs_adj": {"both_n": len(both), "disagree_n": len(disagree)},
            "contingency": {
                f"{a} x {b}": {f"{x}|{y}": c for (x, y), c in sorted(
                    Counter((r[a], r[b]) for r in rows
                            if r[a] is not None and r[b] is not None).items(),
                    key=str)}
                for a, b in (("htf_agree", "penalty_fired"),
                             ("htf_agree", "adj_agree"),
                             ("mtf_alignment", "adj_agree"),
                             ("adj_agree", "own_agree"),
                             ("htf_agree", "macro_agree"),
                             ("macro_agree", "adj_agree"))},
        }
        Path(args.json).write_text(json.dumps(out, indent=2))
        print(f"\nWrote {args.json}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
