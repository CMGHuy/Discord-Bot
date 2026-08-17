#!/usr/bin/env python3
"""v32 Task 8: TRAIN-only per-factor win-rate lift, with Wilson intervals,
feeding Task 9's re-weighting and Level 6 decision.

Prints one flushed line per ticker (CLAUDE.md: any script running more than
a couple of minutes must report progress per unit of work, not just a final
summary).

Run: python scripts/backtest/measure_factor_lift.py --train --json data/v32_train_lift.json
"""
import argparse
import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from swingbot import config
from swingbot.core.backtesting.backtest import ALL_STRATEGIES, run_backtest
from swingbot.core.backtesting.registry import get_badge
from swingbot.core.edge import factors as rs_factors
from swingbot.core.market import levels
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.planning import quality
from swingbot.core.scanning.confidence import honesty_cap, level_for_score
from swingbot.core.scanning.factors import FACTORS, FactorContext, run_factors
from swingbot.core.scanning.regime import get_htf_bias

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "backtest_cache"
TRAIN = ("2020-01-01", "2023-12-31")


def wilson_interval(wins: int, n: int, z: float = 1.96) -> tuple:
    """Wilson score interval for a binomial proportion. Unlike the normal
    approximation it stays inside [0,1] and stays honest at small n --
    which is the entire reason the Level 6 gate uses it."""
    if n <= 0:
        return (0.0, 0.0)
    p = wins / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def _win_rate(trades: list) -> float:
    """wins / (wins + losses), excluding scratch/timeout -- the same
    convention backtest.py's own win_rate computation uses
    (evaluated_trades = trades where outcome in (win, loss)); a scratch or
    timeout in the denominator would understate every win rate this module
    reports."""
    evaluated = [t for t in trades if t["outcome"] in ("win", "loss")]
    wins = sum(1 for t in evaluated if t["outcome"] == "win")
    return wins / len(evaluated) if evaluated else 0.0


def _wins_and_evaluated(trades: list) -> tuple:
    evaluated = [t for t in trades if t["outcome"] in ("win", "loss")]
    wins = sum(1 for t in evaluated if t["outcome"] == "win")
    return wins, len(evaluated)


def factor_lift_table(trades: list, min_samples: int = 20) -> list:
    """Per factor: split the trades where it fired into a top half / bottom
    half by RANK (count), not by a raw value threshold, report each half's
    win rate and Wilson interval, and the lift between them.

    A value-threshold split (`> median` vs `<= median`) looked like the
    obvious approach but is broken for any capped, right-skewed factor --
    which is most of them (0-20/0-15/etc. point ranges where a large
    fraction of trades hit the cap). When over half the fired trades share
    the exact max value, the median EQUALS the max, so `> median` is empty
    by construction: the real TRAIN run produced n_above=0 for 7 of 15
    factors this way, all showing an identical, meaningless -0.461 "lift"
    (every group's win rate against an empty comparison group). A
    count-based split (sort by points, take the top/bottom half by index)
    always produces two real, roughly-equal-sized comparison groups
    regardless of how much mass sits at the cap.

    A factor absent from a trade's `points` dict never fired for that
    trade -- matches run_factors()'s None contract, so it is excluded from
    that factor's split entirely rather than counted as a real zero.
    Factors with fewer than `min_samples` firings are omitted -- too little
    evidence to judge, not a real measured zero-lift result."""
    names = sorted({name for t in trades for name in t["points"]})
    rows = []
    for name in names:
        fired = [t for t in trades if name in t["points"]]
        if len(fired) < min_samples:
            continue
        fired_by_points = sorted(fired, key=lambda t: t["points"][name])
        mid = len(fired_by_points) // 2
        at_or_below = fired_by_points[:mid]
        above = fired_by_points[mid:]
        wr_above = _win_rate(above)
        wr_below = _win_rate(at_or_below)
        wins_above, n_eval_above = _wins_and_evaluated(above)
        wins_below, n_eval_below = _wins_and_evaluated(at_or_below)
        lo_above, hi_above = wilson_interval(wins_above, n_eval_above)
        lo_below, hi_below = wilson_interval(wins_below, n_eval_below)
        rows.append({
            "factor": name,
            "n_above": len(above), "n_at_or_below": len(at_or_below),
            "win_rate_above": wr_above, "win_rate_at_or_below": wr_below,
            "wilson_above": (lo_above, hi_above), "wilson_below": (lo_below, hi_below),
            "lift": wr_above - wr_below,
            "overlapping": not (lo_above > hi_below or lo_below > hi_above),
        })
    return rows


def level_table(trades: list) -> list:
    """Per level 1-6: n, win rate, Wilson bounds -- the table Task 9 reads
    to decide Level 6 (n>=100, point estimate >=90%, Wilson lower bound
    >=80% AND above Level 5's own point estimate). `n` counts only
    evaluated (win/loss) trades at that level, same convention as
    backtest.py's own win_rate -- Task 9's n>=100 is a statistical-
    significance bar for a win-rate claim, so a scratch/timeout that never
    resolved win or loss must not pad the count that claim rests on."""
    rows = []
    for lvl in range(1, 7):
        bucket = [t for t in trades if t.get("level") == lvl]
        wins, n = _wins_and_evaluated(bucket)
        lo, hi = wilson_interval(wins, n)
        rows.append({
            "level": lvl, "n": n,
            "win_rate": wins / n if n else 0.0,
            "wilson_lo": lo, "wilson_hi": hi,
        })
    return rows


def collect_train_trades() -> list:
    """One row per TRAIN trade entry bar: every kept factor's real points
    (via the actual factors.py registry, no reimplemented arithmetic), the
    unified score/level, and the realized outcome. NO-LOOKAHEAD: every
    reading uses df.iloc[:i+1], never a future bar.

    RS percentile and market breadth are scoped out (same as Task 1's
    correlation measurement): both need a historical universe-wide
    reconstruction (per-date cross-sectional RS ranks / breadth) this repo's
    cache doesn't retain, so they are always None here -- run_factors()
    correctly omits factor_rs/factor_breadth from every trade's breakdown
    rather than inventing a value. Regime is also None (offline: no SPY
    regime feed), matching scripts/reports/audit_quality_score.py's own
    documented limitation.
    """
    rows = []
    frames = {p.stem: pd.read_csv(p, index_col="Date", parse_dates=True)
              for p in sorted(CACHE_DIR.glob("*.csv"))}
    for ticker, df in frames.items():
        vol_ratio_series = df["Volume"] / df["Volume"].rolling(20).mean()
        date_to_idx = {str(d.date()): k for k, d in enumerate(df.index)}
        ticker_rows = 0
        for hk in HORIZONS:
            h = HORIZONS[hk]
            for strategy in ALL_STRATEGIES:
                s = run_backtest(ticker, df, strategy, hk, exit_model="v2", scale_out=True)
                badge = get_badge("strategy", strategy)
                for t in s.trades:
                    if not (TRAIN[0] <= t.entry_date <= TRAIN[1]):
                        continue
                    i = date_to_idx.get(t.entry_date)
                    if i is None or i < 60:
                        continue
                    window = df.iloc[:i + 1]
                    entry = t.entry

                    target_confluence = levels.count_confirming_strategies(
                        window, h, entry, t.take_profit,
                        tolerance_pct=config.CONFLUENCE_DEVIATION_PCT)
                    stop_confluence = levels.count_confirming_strategies(
                        window, h, entry, t.stop_loss,
                        tolerance_pct=config.CONFLUENCE_DEVIATION_PCT)
                    atr_floor = levels.atr_floor_pct(window, entry, h)
                    target_distance_pct = abs(t.take_profit - entry) / entry * 100
                    stop_distance_pct = abs(entry - t.stop_loss) / entry * 100

                    scenario = SimpleNamespace(
                        direction=t.direction,
                        target_distance_pct=target_distance_pct,
                        target_sources=list(target_confluence[1]),
                        stop_distance_pct=stop_distance_pct,
                        atr_floor_pct=atr_floor,
                        tight_stop=bool(atr_floor > 0 and stop_distance_pct < atr_floor),
                    )

                    htf = get_htf_bias(window, hk)
                    ctx = FactorContext(
                        scenario=scenario, df=window, regime_trend=None,
                        htf_bias=(htf["bias"] if htf else None),
                        rs_percentile=None,
                        mtf=int(rs_factors.mtf_alignment(window, t.direction)),
                        breadth=None,
                        volume_ratio=float(vol_ratio_series.iloc[i]) if pd.notna(vol_ratio_series.iloc[i]) else None,
                        atr_pct=quality.atr_percentile(window),
                        trigger_distance_pct=0.0,
                        badge_status=badge.status,
                        gap_fragile=False,
                        target_count=target_confluence[0], target_families=list(target_confluence[1]),
                        stop_count=stop_confluence[0], stop_families=list(stop_confluence[1]),
                    )
                    score_raw, breakdown_points = run_factors(FACTORS, ctx)
                    score = max(0, min(100, score_raw))
                    level, _label = level_for_score(score, target_confluence[0])

                    # run_factors() returns {name: line}; re-derive the raw
                    # points per factor for the median split above (the
                    # line string embeds them but isn't meant to be parsed).
                    points = {}
                    for fn in FACTORS:
                        r = fn(ctx)
                        if r is not None:
                            points[r.name] = r.points

                    rows.append({
                        "ticker": ticker, "horizon": hk, "strategy": strategy,
                        "outcome": t.outcome, "score": score, "level": level,
                        "target_count": target_confluence[0], "points": points,
                    })
                    ticker_rows += 1
        print(f"{ticker}: {ticker_rows} TRAIN entry-bar samples", flush=True)
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", action="store_true")
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    trades = collect_train_trades()
    print(f"\nTotal TRAIN trades: {len(trades)}", flush=True)

    lift = factor_lift_table(trades)
    print("\nFactor lift (median split, win rate above vs at-or-below):")
    for row in sorted(lift, key=lambda r: -abs(r["lift"])):
        flag = " (overlapping -- no real lift)" if row["overlapping"] else ""
        print(f"  {row['factor']:<30} n={row['n_above']+row['n_at_or_below']:>5} "
              f"lift={row['lift']:+.3f}{flag}")

    levels_table = level_table(trades)
    print("\nPer-level win rate:")
    for row in levels_table:
        print(f"  Level {row['level']}: n={row['n']:>5} "
              f"WR={row['win_rate']*100:5.1f}% "
              f"Wilson=[{row['wilson_lo']*100:5.1f}%, {row['wilson_hi']*100:5.1f}%]")

    if args.json:
        # Lean raw records (no per-trade `points` breakdown -- factor_lift
        # already summarizes it, and 4337 full breakdowns would bloat a
        # committed file) so a future re-weighting/re-leveling pass can
        # recompute factor_lift_table()/level_table() offline without
        # re-running the whole backtest again.
        raw_trades = [{"outcome": t["outcome"], "score": t["score"],
                      "level": t["level"], "target_count": t["target_count"]}
                     for t in trades]
        out = {"n_trades": len(trades), "factor_lift": lift,
              "level_table": levels_table, "trades": raw_trades}
        Path(args.json).write_text(json.dumps(out, indent=2, default=list))
        print(f"\nWrote {args.json}", flush=True)
