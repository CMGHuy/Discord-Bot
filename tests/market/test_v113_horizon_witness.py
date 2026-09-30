"""v113 §1: adding the 1w horizon changes nothing on the ten existing horizons.

The golden (tests/fixtures/v113/horizon_witness.json) was written by this
module's __main__ BEFORE any v113 code landed (Task V113-1). Every later v113
task must leave it byte-identical: entries, backtest sizing (_trade_plan_at),
live sizing (build_strategy_plan) and the v2 exit, for every legacy strategy x
horizon x direction on the frozen TSLA fixture.

Regenerate ONLY on the pre-v113 tree:
    python -m tests.market.test_v113_horizon_witness
"""
from __future__ import annotations

import contextlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

TESTS = Path(__file__).resolve().parents[1]
GOLDEN = TESTS / "fixtures" / "v113" / "horizon_witness.json"
OHLCV = TESTS / "fixtures" / "ohlcv" / "TSLA.csv"
# Spelled out, NOT read from strategy_types: the witness must not move when HORIZONS does.
LEGACY = ("2w", "4w", "2m", "3m", "4m", "5m", "6m", "7m", "8m", "9m")
PER_CELL = 3
# Every flag that can move a plan independently of v113, pinned so the golden
# measures v113's change only (and never today's date via opex, or the journal).
PINS = {
    "LEVEL_LIFECYCLE_STOPS_ENABLED": False,
    "DATA_DRIVEN_STOPS_ENABLED": False,
    "STALL_EXIT_ENABLED": False,
    "REGIME_GATES_ENABLED": False,
    "STRUCTURAL_STOP_SCOPE": "",
    "OPEX_STOP_WIDEN_PCT": 0.0,
    "FIB_SR_CONFLUENCE_ATR": 0.0,
    "FIB_LEVEL_STOP_ATR": 0.0,
    "MIN_RISK_REWARD_RATIO": 1.5,
    "MAX_RISK_REWARD_RATIO": 2.5,
}
_MISSING = object()


@contextlib.contextmanager
def pinned_config():
    from swingbot import config

    saved = {key: getattr(config, key, _MISSING) for key in PINS}
    try:
        for key, value in PINS.items():
            setattr(config, key, value)
        yield
    finally:
        for key, value in saved.items():
            if value is _MISSING:
                delattr(config, key)
            else:
                setattr(config, key, value)


def _r(value):
    return None if value is None else round(float(value), 6)


def _bt(df, i, direction, strategy, horizon, series) -> list:
    from swingbot.core.backtesting.backtest import _trade_plan_at

    picked = _trade_plan_at(df, i, direction, strategy, horizon, *series)
    return [None, None, None] if picked is None else [_r(value) for value in picked]


def _live(df, i, direction, strategy, horizon) -> list:
    from swingbot.core.planning.builders import build_strategy_plan
    from swingbot.core.planning.exit_sim import simulate_exit

    plan = build_strategy_plan(df, i, ticker="TSLA", strategy=strategy,
                               horizon_key=horizon, direction=direction)
    if plan is None:
        return [None] * 11
    res = simulate_exit(df, i, plan, scale_out=True)
    return [plan.entry_type, _r(plan.trigger_price), _r(plan.stop_loss), _r(plan.tp1),
            _r(plan.tp2), _r(plan.tp1_fraction), plan.expiry_bars,
            _r(plan.breakeven_trigger_fraction), res.outcome, res.exit_index, _r(res.r_total)]


def witness_rows() -> list:
    from swingbot.core.backtesting.backtest import ALL_STRATEGIES, _plan_series
    from swingbot.core.market.entry_filters import entries_for

    df = pd.read_csv(OHLCV, index_col=0, parse_dates=True)
    rows = []
    with pinned_config():
        for strategy in ALL_STRATEGIES:
            for horizon in LEGACY:
                bull, bear = entries_for(strategy, df, horizon)
                series = _plan_series(df, strategy, horizon)
                for direction, mask in (("bullish", bull), ("bearish", bear)):
                    idx = [int(i) for i in np.flatnonzero(mask.to_numpy(dtype=bool))]
                    rows.append([strategy, horizon, direction, "entries", len(idx), sum(idx)])
                    for i in idx[-PER_CELL:]:
                        rows.append([strategy, horizon, direction, i,
                                     *_bt(df, i, direction, strategy, horizon, series),
                                     *_live(df, i, direction, strategy, horizon)])
    return rows


@pytest.mark.slow
def test_legacy_horizons_are_byte_identical_to_the_pre_v113_golden():
    assert witness_rows() == json.loads(GOLDEN.read_text(encoding="utf-8"))


if __name__ == "__main__":
    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN.write_text(json.dumps(witness_rows(), indent=0) + "\n", encoding="utf-8")
    print(f"wrote {GOLDEN}")
