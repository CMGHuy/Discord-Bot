#!/usr/bin/env python3
"""v32 Task 10: the one-shot VALIDATION run.

Plan gap found before running: the plan's literal Step 2 command
(`run_backtest_range.py --validation`) measures raw per-(strategy,horizon)
win rates via `run_backtest()`, entirely independent of
`score_confidence()`/`MIN_ALERT_CONFIDENCE_LEVEL` gating -- it cannot test
what the pre-registration gate actually describes ("win rate improves vs.
the legacy scorer on the same VALIDATION window, AND alert volume falls by
no more than 30%" -- a comparison of two GATED populations). This script
builds that comparison directly: for every VALIDATION-window
(2024-01-01..2025-12-31) trade, scores it with BOTH the legacy and the
unified score_confidence() path (toggling config.UNIFIED_CONFIDENCE), gates
each at MIN_ALERT_CONFIDENCE_LEVEL, and compares the two gated populations'
win rate and volume.

NO-LOOKAHEAD: every reading uses df.iloc[:i+1], never a future bar. Prints
one flushed line per ticker.

Run: python scripts/backtest/v32_validation.py --json data/v32_validation.json
"""
import argparse
import json
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
from swingbot.core.scanning.confidence import score_confidence
from swingbot.core.scanning.regime import get_htf_bias

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "backtest_cache"
VALIDATION = ("2024-01-01", "2025-12-31")


def _win_rate(trades: list) -> tuple:
    """Returns (win_rate, n_evaluated), excluding scratch/timeout -- same
    convention as measure_factor_lift.py / backtest.py's own win_rate."""
    evaluated = [t for t in trades if t["outcome"] in ("win", "loss")]
    wins = sum(1 for t in evaluated if t["outcome"] == "win")
    return (wins / len(evaluated) if evaluated else 0.0), len(evaluated)


def collect_validation_trades() -> list:
    """One row per VALIDATION trade entry bar: both the legacy and unified
    score_confidence() level for the SAME scenario, so gating comparisons
    are apples-to-apples. Same construction as
    measure_factor_lift.py's collect_train_trades() (RS/breadth scoped out,
    regime offline) -- see that script for the full rationale."""
    rows = []
    frames = {p.stem: pd.read_csv(p, index_col="Date", parse_dates=True)
              for p in sorted(CACHE_DIR.glob("*.csv"))}
    for ticker, df in frames.items():
        date_to_idx = {str(d.date()): k for k, d in enumerate(df.index)}
        ticker_rows = 0
        for hk in HORIZONS:
            h = HORIZONS[hk]
            for strategy in ALL_STRATEGIES:
                s = run_backtest(ticker, df, strategy, hk, exit_model="v2", scale_out=True)
                badge = get_badge("strategy", strategy)
                for t in s.trades:
                    if not (VALIDATION[0] <= t.entry_date <= VALIDATION[1]):
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
                        stop_sources=list(stop_confluence[1]),
                        stop_distance_pct=stop_distance_pct,
                        atr_floor_pct=atr_floor,
                        tight_stop=bool(atr_floor > 0 and stop_distance_pct < atr_floor),
                        take_profit=t.take_profit,
                        risk_reward_ratio=(abs(t.take_profit - entry) / abs(entry - t.stop_loss)
                                          if entry != t.stop_loss else 0.0),
                    )

                    htf = get_htf_bias(window, hk)
                    kwargs = dict(
                        target_confluence=target_confluence, stop_confluence=stop_confluence,
                        htf_bias=(htf["bias"] if htf else None), rs_percentile=None,
                        mtf=int(rs_factors.mtf_alignment(window, t.direction)), breadth=None,
                        badge_status=badge.status,
                    )

                    prior_flag = config.UNIFIED_CONFIDENCE
                    try:
                        config.UNIFIED_CONFIDENCE = False
                        legacy = score_confidence(scenario, regime_trend=None, df=window, **kwargs)
                        config.UNIFIED_CONFIDENCE = True
                        unified = score_confidence(scenario, regime_trend=None, df=window, **kwargs)
                    finally:
                        config.UNIFIED_CONFIDENCE = prior_flag

                    rows.append({
                        "ticker": ticker, "horizon": hk, "strategy": strategy,
                        "outcome": t.outcome,
                        "legacy_level": legacy.level, "unified_level": unified.level,
                    })
                    ticker_rows += 1
        print(f"{ticker}: {ticker_rows} VALIDATION entry-bar samples", flush=True)
    return rows


def compare_gated_populations(trades: list, min_level: int) -> dict:
    legacy_gated = [t for t in trades if t["legacy_level"] >= min_level]
    unified_gated = [t for t in trades if t["unified_level"] >= min_level]
    legacy_wr, legacy_n = _win_rate(legacy_gated)
    unified_wr, unified_n = _win_rate(unified_gated)
    volume_delta_pct = (
        (len(unified_gated) - len(legacy_gated)) / len(legacy_gated) * 100
        if legacy_gated else 0.0
    )
    win_rate_delta = unified_wr - legacy_wr
    verdict = "PASS" if (win_rate_delta > 0 and volume_delta_pct >= -30.0) else "FAIL"
    return {
        "min_level": min_level,
        "legacy_alert_count": len(legacy_gated), "legacy_evaluated": legacy_n, "legacy_win_rate": legacy_wr,
        "unified_alert_count": len(unified_gated), "unified_evaluated": unified_n, "unified_win_rate": unified_wr,
        "volume_delta_pct": volume_delta_pct, "win_rate_delta": win_rate_delta,
        "verdict": verdict,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    trades = collect_validation_trades()
    print(f"\nTotal VALIDATION trades: {len(trades)}", flush=True)

    result = compare_gated_populations(trades, config.MIN_ALERT_CONFIDENCE_LEVEL)
    print(f"\nGate: MIN_ALERT_CONFIDENCE_LEVEL={result['min_level']}")
    print(f"  Legacy:  {result['legacy_alert_count']:>5} alerts "
          f"({result['legacy_evaluated']} evaluated), "
          f"WR={result['legacy_win_rate']*100:.1f}%")
    print(f"  Unified: {result['unified_alert_count']:>5} alerts "
          f"({result['unified_evaluated']} evaluated), "
          f"WR={result['unified_win_rate']*100:.1f}%")
    print(f"  Volume delta: {result['volume_delta_pct']:+.1f}%  "
          f"Win-rate delta: {result['win_rate_delta']*100:+.1f}pp")
    print(f"  VERDICT: {result['verdict']}")

    if args.json:
        out = {"n_trades": len(trades), "result": result}
        Path(args.json).write_text(json.dumps(out, indent=2))
        print(f"\nWrote {args.json}", flush=True)
