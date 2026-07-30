import math

import numpy as np

from swingbot.core.gate.registry import CHECKS
from swingbot.core.gate.timing import check_trigger_objective, check_not_chasing
from tests.conftest import make_ohlcv
from tests.fixtures.gate import uptrend_daily
from tests.fixtures.gate.plans import make_plan


def test_well_formed_plan_passes():
    assert check_trigger_objective(uptrend_daily(), make_plan(), None).status == "pass"


def test_priceless_plan_fails_hard():
    broken = make_plan(trigger_price=None)
    result = check_trigger_objective(uptrend_daily(), broken, None)
    assert result.status == "fail"
    assert CHECKS["trigger_objective"].hard_block is True


def test_unknown_entry_type_fails():
    weird = make_plan(entry_type="vibes")
    assert check_trigger_objective(uptrend_daily(), weird, None).status == "fail"


def test_nan_trigger_price_fails():
    broken = make_plan(trigger_price=float('nan'))
    result = check_trigger_objective(uptrend_daily(), broken, None)
    assert result.status == "fail"
    assert CHECKS["trigger_objective"].hard_block is True


def _df_at(price):
    return make_ohlcv(np.concatenate([np.full(59, price * 0.97), [price]]),
                      spread_pct=2.0)


def test_fresh_entry_passes():
    # price at 100.2, trigger 100, ATR ~2 -> 0.1 ATR past: fresh
    plan = make_plan(direction="bullish", trigger_price=100.0)
    assert check_not_chasing(_df_at(100.2), plan, None).status == "pass"


def test_late_entry_fails():
    # price at 103.5 with ATR ~2 -> ~1.75 ATR past the trigger
    plan = make_plan(direction="bullish", trigger_price=100.0)
    result = check_not_chasing(_df_at(103.5), plan, None)
    assert result.status == "fail"
    assert result.evidence["dist_atr"] > 1.0


def test_not_yet_triggered_passes():
    plan = make_plan(direction="bullish", trigger_price=100.0)
    assert check_not_chasing(_df_at(99.0), plan, None).status == "pass"
