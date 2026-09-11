#!/usr/bin/env python3
"""Emit fold arms for ONE strategy under a config override, in the shape
validate_component.py --stage walkforward consumes.

Why this exists: wf_run.py's run_folds emits pooled expectancy deltas, not
per-trade rows, so gate_win_rate sees delta_win_rate_pp=None and fails every
fold. Stage 2 needs per-trade arms. This is the per-strategy instrument for
that, in the same spirit as measure_rs_gate_effect.py.

Run:
  python scripts/backtest/measure_strategy_arm.py \
      --strategy "RSI Divergence" \
      --component-json '{"RSI_DIV_MIN_CONSECUTIVE_TURN": 3}' \
      --out data/rsidiv_folds.json
"""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from swingbot.core.backtesting.backtest import run_backtest_daterange  # noqa: E402
from swingbot.core.backtesting.backtest_wf import (  # noqa: E402
    ANCHORED_FOLDS, _apply_overrides, _frame_for, _symbols_for_folds,
)
from swingbot.core.market.strategy_types import HORIZONS  # noqa: E402
from swingbot.core.marketdata.universe import liquidity_ok  # noqa: E402

DECIDED_OR_NOT = ("win", "loss", "scratch", "timeout")


def trade_to_arm(summary, trade) -> dict:
    """BacktestTrade -> the ArmTrade field set (acceptance.py:28-47).

    planned_rr is derived, not stored: BacktestTrade carries entry/stop/target
    but no ratio. Direction-adjusted so a short's reward and risk are both
    positive distances.
    """
    entry, stop, target = trade.entry, trade.stop_loss, trade.take_profit
    if str(trade.direction).lower().startswith("s"):
        reward, risk = entry - target, stop - entry
    else:
        reward, risk = target - entry, entry - stop
    planned_rr = (reward / risk) if risk else None
    return {
        "ticker": summary.ticker,
        "strategy": summary.strategy,
        "horizon_key": summary.horizon_key,
        "entry_date": trade.entry_date,
        "outcome": trade.outcome,
        "r_multiple": trade.r_multiple,
        "planned_rr": planned_rr,
    }


def _leg(strategy, symbols, horizons, start, end, overrides, frame_for, run_fn):
    """One arm of one fold. Config overrides are applied around the whole leg
    and restored afterwards, so a raising run never leaks config state."""
    old = _apply_overrides(overrides or {})
    try:
        rows = []
        for sym in symbols:
            df = frame_for(sym)
            if df is None:
                continue
            for hz in horizons:
                # tp2_mode MUST be passed explicitly: run_backtest_daterange
                # defaults to "none" while run_backtest_range.py's --tp2
                # defaults to "levels". Leaving it implicit would measure the
                # folds under different economics than the TRAIN grid -- the
                # same silent mismatch that corrupted round 2's Elliott Wave
                # grid (tune_strategy ran v1/no-scale-out while validation ran
                # v2/scale-out).
                s = run_fn(sym, df, strategy, hz, start, end,
                           exit_model="v2", scale_out=True, tp2_mode="levels")
                for t in s.trades:
                    if t.outcome in DECIDED_OR_NOT:
                        rows.append(trade_to_arm(s, t))
        return rows
    finally:
        _apply_overrides(old)


def build_fold_arms(strategy, overrides, symbols, horizons,
                    frame_for=None, run_fn=None) -> dict:
    frame_for = frame_for or _frame_for
    run_fn = run_fn or run_backtest_daterange
    folds = []
    for _tr_start, _tr_end, test_start, test_end in ANCHORED_FOLDS:
        folds.append({
            "test_year": test_start[:4],
            "baseline": _leg(strategy, symbols, horizons, test_start, test_end,
                             {}, frame_for, run_fn),
            "component": _leg(strategy, symbols, horizons, test_start, test_end,
                              overrides, frame_for, run_fn),
        })
        print(f"fold {test_start[:4]}: baseline={len(folds[-1]['baseline'])} "
              f"component={len(folds[-1]['component'])} trades", flush=True)
    return {"folds": folds}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strategy", required=True)
    ap.add_argument("--component-json", required=True,
                    help='config overrides for the component leg, e.g. '
                         '\'{"MA_RIBBON_CONFIRM_BARS": 2}\'')
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    overrides = json.loads(args.component_json)
    if not overrides:
        print("REFUSING: --component-json is empty; both arms would be "
              "identical and every fold delta would be 0.", file=sys.stderr)
        return 1

    symbols = [s for s in _symbols_for_folds()
               if (_frame_for(s) is not None and liquidity_ok(_frame_for(s)))]
    arms = build_fold_arms(args.strategy, overrides, symbols, list(HORIZONS))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(arms, indent=1), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
