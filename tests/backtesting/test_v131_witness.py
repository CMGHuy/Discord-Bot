"""v131 byte-identity witness: with no `limit_price` plan-shape key, every
existing strategy builds the plans and backtest trades it built before v131.

tests/fixtures/v131/witness.json was written by write_golden() on main BEFORE
any v131 code change (plan task V131-01). Never regenerate it to make this
test pass -- a diff here is a behaviour change v131 promised not to make.
"""
import dataclasses
import json
from pathlib import Path

import pytest

from swingbot.core.backtesting.backtest import ALL_STRATEGIES, run_backtest
from swingbot.core.market.entry_filters import entries_for, gate_override
from swingbot.core.market.strategy_types import FADE_STRATEGY, V104_SHORTS
from swingbot.core.planning.builders import build_strategy_plan
from swingbot.core.planning.plan_types import plan_to_dict
from tests.backtesting.test_v74_fixture import load_v74_fixture
from tests.market.test_fib_sr_confluence import _trending_frame

pytestmark = pytest.mark.slow

GOLDEN = Path(__file__).resolve().parent.parent / "fixtures" / "v131" / "witness.json"
STRATEGIES = ALL_STRATEGIES + V104_SHORTS + (FADE_STRATEGY,)
HORIZONS_UNDER_TEST = ("1w", "2w", "4w", "2m")
# Every strategy unmasked in both directions, 1w admitted too, so masked
# strategies (the v104 shorts, the v113 fade) are witnessed as well.
OPEN_GATES = {"cells": frozenset({("bullish", "1w"), ("bearish", "1w")})}
# The plan fields that decide how a plan trades. plan_id is random and the
# badge fields follow the registry, so neither belongs in a behaviour witness.
PLAN_KEYS = ("created_at", "direction", "entry_type", "trigger_price", "entry_price",
             "expiry_bars", "stop_loss", "tp1", "tp1_fraction", "tp2",
             "breakeven_trigger_fraction", "trail_atr_mult", "hold_cap_bars", "status",
             "stop_mult_applied", "tp2_r_applied", "time_stop_days", "stall_exit_day")


def _frames():
    frames = dict(load_v74_fixture())
    frames["UP"] = _trending_frame(400, 0.06, seed=2)
    frames["DN"] = _trending_frame(400, -0.06, seed=11)
    return frames


def _plan_rows(symbol, frame, strategy, horizon):
    rows = []
    bullish, bearish = entries_for(strategy, frame, horizon)
    for direction, mask in (("bullish", bullish), ("bearish", bearish)):
        for index in [int(i) for i in mask.to_numpy().nonzero()[0]]:
            plan = build_strategy_plan(frame, index, ticker=symbol, strategy=strategy,
                                       horizon_key=horizon, direction=direction)
            if plan is None:
                rows.append([symbol, strategy, horizon, direction, index, None])
                continue
            record = plan_to_dict(plan)
            rows.append([symbol, strategy, horizon, direction, index,
                         [record[key] for key in PLAN_KEYS]])
    return rows


def _trade_rows(symbol, frame, strategy, horizon):
    summary = run_backtest(symbol, frame, strategy, horizon, exit_model="v2",
                           scale_out=True, tp2_mode="levels")
    # context is entry_context's feature snapshot -- v131 does not touch it, and
    # it is most of the bytes; every priced and scored field is kept.
    return [[symbol, strategy, horizon,
             {k: v for k, v in dataclasses.asdict(trade).items() if k != "context"}]
            for trade in summary.trades]


def snapshot() -> dict:
    plans, trades = [], []
    for symbol, frame in _frames().items():
        for strategy in STRATEGIES:
            with gate_override(strategy, OPEN_GATES):
                for horizon in HORIZONS_UNDER_TEST:
                    plans.extend(_plan_rows(symbol, frame, strategy, horizon))
                    trades.extend(_trade_rows(symbol, frame, strategy, horizon))
    # One JSON round trip so the comparison sees exactly what the file stores.
    return json.loads(json.dumps({"plans": plans, "trades": trades}, default=str))


def write_golden() -> None:
    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN.write_text(json.dumps(snapshot(), separators=(",", ":"), default=str), encoding="utf-8")


def _same(current, before):
    """Equal, except that a float may differ in its last bits. The golden was
    written on Windows and CI runs Linux: libm gives 91.3788433158948 and
    91.37884331589481 for the same plan. A behaviour change moves a price by
    far more than 1e-9 relative, which is what this still catches."""
    if isinstance(current, float) and isinstance(before, float):
        return current == pytest.approx(before, rel=1e-9, abs=0)
    if isinstance(current, (list, tuple)) and isinstance(before, (list, tuple)):
        return len(current) == len(before) and all(
            _same(c, b) for c, b in zip(current, before))
    if isinstance(current, dict) and isinstance(before, dict):
        return current.keys() == before.keys() and all(
            _same(current[k], before[k]) for k in current)
    return current == before


def test_golden_is_not_vacuous():
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert len(golden["trades"]) >= 200
    assert sum(1 for row in golden["plans"] if row[5] is not None) >= 200


def test_existing_strategies_build_the_pre_v131_plans_and_trades():
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    now = snapshot()
    assert _same(now["trades"], golden["trades"])
    assert len(now["plans"]) == len(golden["plans"])
    for current, before in zip(now["plans"], golden["plans"]):
        assert _same(current, before), current[:5]
