import datetime as dt

import numpy as np

from swingbot.core.gate.redflags import rf_fake_breakout
from tests.conftest import make_ohlcv
from tests.fixtures.gate import breakout_and_fail, uptrend_daily
from tests.fixtures.gate.plans import make_plan

BREAKOUT_PLAN = make_plan(strategy="Break & Retest", direction="bullish",
                          trigger_price=100.0)


def test_breakout_and_fail_fires():
    result = rf_fake_breakout(breakout_and_fail(level=100.0), BREAKOUT_PLAN, None)
    assert result.status == "fail"


def test_clean_high_volume_breakout_passes():
    vols = np.full(60, 1_000_000.0)
    vols[-1] = 2_500_000.0
    closes = np.concatenate([np.linspace(92, 99, 59), [102.0]])
    df = make_ohlcv(closes, volumes=vols)
    assert rf_fake_breakout(df, BREAKOUT_PLAN, None).status == "pass"


def test_serial_poker_fires():
    df = make_ohlcv(np.full(60, 97.0), spread_pct=1.0)
    for pos in (-5, -3):                       # two failed pokes through 100
        df.loc[df.index[pos], "High"] = 101.0
    df.loc[df.index[-1], "Close"] = 99.0
    assert rf_fake_breakout(df, BREAKOUT_PLAN, None).status == "fail"


def test_non_breakout_strategy_na_pass():
    result = rf_fake_breakout(breakout_and_fail(), make_plan(strategy="RSI"), None)
    assert result.status == "pass" and "n/a" in result.detail
