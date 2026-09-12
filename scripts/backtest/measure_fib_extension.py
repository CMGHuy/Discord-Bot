#!/usr/bin/env python3
"""Arms-measurement harness for the Fibonacci 1.0 extension flag
(config.FIB_TARGET_1_0_EXTENSION), emitting the ArmTrade JSON shapes
validate_component.py consumes: {"baseline","component"} for --stage mde,
{"folds":[...]} for --stage walkforward.

Reuses Task R15's shared per-strategy leg logic (measure_strategy_arm.py)
directly -- a config-Field arm (baseline vs {"FIB_TARGET_1_0_EXTENSION":
True}) is exactly what that harness's _leg() already does; this script only
adds the flat single-TRAIN-window "mde" shape (R15 only ever folds) and a
--tickers filter for fast/dev runs. See the v84 index plan's "Known
reconciliation item" note.

--stage mde has no caller in this plan today -- R33/R35 measure Fibonacci's
TRAIN/VALIDATION numbers directly via run_backtest_range.py against the
badge threshold (Tier 3's change is not eligible for the six-clause funnel).
Only R34 (Stage 2 walkforward) calls this script, with --stage walkforward.
Built per this task's own spec/test regardless.

Run:
  python scripts/backtest/measure_fib_extension.py --stage mde \
      --tickers AAPL,TSLA,NVDA --out /tmp/fib_mde.json
  python scripts/backtest/measure_fib_extension.py --stage walkforward \
      --out data/v84_fib_folds.json
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from measure_strategy_arm import _leg  # noqa: E402  (sibling script, same dir)
from swingbot.core.backtesting.backtest import run_backtest_daterange  # noqa: E402
from swingbot.core.backtesting.backtest_wf import (  # noqa: E402
    ANCHORED_FOLDS, _frame_for, _symbols_for_folds,
)
from swingbot.core.market.strategy_types import HORIZONS  # noqa: E402
from swingbot.core.marketdata.universe import liquidity_ok  # noqa: E402

STRATEGY = "Fibonacci"
COMPONENT_OVERRIDES = {"FIB_TARGET_1_0_EXTENSION": True}
TRAIN = ("2020-01-01", "2023-12-31")  # verbatim run_backtest_range.py


def _symbols(tickers_arg):
    if tickers_arg:
        return [t.strip() for t in tickers_arg.split(",") if t.strip()]
    return [s for s in _symbols_for_folds()
            if (_frame_for(s) is not None and liquidity_ok(_frame_for(s)))]


def _leg_with_progress(strategy, symbols, horizons, start, end, overrides):
    """Per-ticker flushed progress, reusing R15's _leg at single-ticker
    granularity so the override-apply/restore and ArmTrade conversion logic
    is never duplicated -- only the progress printing is new here."""
    rows = []
    n = len(symbols)
    for i, sym in enumerate(symbols, 1):
        print(f"[{i}/{n}] {sym}", flush=True)
        rows.extend(_leg(strategy, [sym], horizons, start, end, overrides,
                          _frame_for, run_backtest_daterange))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stage", required=True, choices=("mde", "walkforward"))
    ap.add_argument("--tickers", default=None,
                    help="comma-separated ticker filter, for fast/dev runs; "
                         "default: full universe")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    symbols = _symbols(args.tickers)
    horizons = list(HORIZONS)

    if args.stage == "mde":
        baseline = _leg_with_progress(STRATEGY, symbols, horizons, *TRAIN, {})
        component = _leg_with_progress(STRATEGY, symbols, horizons, *TRAIN,
                                       COMPONENT_OVERRIDES)
        payload = {"baseline": baseline, "component": component}
    else:
        folds = []
        for _tr_start, _tr_end, test_start, test_end in ANCHORED_FOLDS:
            folds.append({
                "test_year": test_start[:4],
                "baseline": _leg_with_progress(STRATEGY, symbols, horizons,
                                               test_start, test_end, {}),
                "component": _leg_with_progress(STRATEGY, symbols, horizons,
                                                test_start, test_end,
                                                COMPONENT_OVERRIDES),
            })
            print(f"fold {test_start[:4]}: baseline={len(folds[-1]['baseline'])} "
                  f"component={len(folds[-1]['component'])} trades", flush=True)
        payload = {"folds": folds}

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
