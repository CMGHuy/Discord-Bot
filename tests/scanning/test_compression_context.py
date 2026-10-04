import datetime as dt
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd

from swingbot.core.scanning.compression_context import compression_mode
from tests.helpers import make_ohlcv

ET = ZoneInfo("America/New_York")
ASOF = dt.datetime(2026, 9, 17, 17, tzinfo=ET)  # after close: last bar is complete
BEAR = SimpleNamespace(trend="bearish")
BULL = SimpleNamespace(trend="bullish")


def _series(step, n=100, end="2026-09-17"):
    start = (pd.Timestamp(end) - pd.tseries.offsets.BDay(n - 1)).date().isoformat()
    return make_ohlcv([200 + step * i for i in range(n)], start=start)


WEAK, STRONG = _series(0.1), _series(2.0)
SECTOR, FALLING_SPY, RISING_SPY = _series(1.0), _series(-0.5), _series(0.5)


def test_broad_arm_on_bearish_spy_needs_no_sector():
    assert compression_mode(WEAK, FALLING_SPY, None, now=ASOF, spy_regime=BEAR) == ("broad", None)


def test_isolated_arm_on_nonbearish_spy_with_sector_laggard():
    assert compression_mode(WEAK, RISING_SPY, SECTOR, now=ASOF, spy_regime=BULL) == ("isolated", None)


def test_stronger_stock_is_not_a_sector_laggard():
    assert compression_mode(STRONG, RISING_SPY, SECTOR, now=ASOF, spy_regime=BULL) == (None, "not_sector_laggard")


def test_missing_inputs_fail_closed():
    assert compression_mode(WEAK, None, SECTOR, now=ASOF, spy_regime=BULL) == (None, "missing_spy")
    assert compression_mode(WEAK, RISING_SPY, None, now=ASOF, spy_regime=BULL) == (None, "missing_sector")


def test_stale_frames_are_unaligned():
    stale_spy = RISING_SPY.iloc[:-1]
    assert compression_mode(WEAK, stale_spy, SECTOR, now=ASOF, spy_regime=BULL) == (None, "unaligned_spy")
    assert compression_mode(WEAK, RISING_SPY, SECTOR.iloc[:-2], now=ASOF,
                            spy_regime=BULL) == (None, "unaligned_sector")


def test_arms_are_mutually_exclusive():
    for stock in (WEAK, STRONG):
        broad = compression_mode(stock, FALLING_SPY, SECTOR, now=ASOF, spy_regime=BEAR)[0]
        other = compression_mode(stock, RISING_SPY, SECTOR, now=ASOF, spy_regime=BULL)[0]
        assert broad == "broad"
        assert other in ("isolated", None) and other != broad
    assert compression_mode(WEAK, RISING_SPY, SECTOR, now=ASOF, spy_regime=BULL)[0] == "isolated"
    assert compression_mode(STRONG, RISING_SPY, SECTOR, now=ASOF, spy_regime=BULL)[0] is None


def test_tomorrows_sector_bar_cannot_change_todays_mode():
    future = SECTOR.iloc[[-1]].copy()
    future.index = future.index + pd.Timedelta(days=1)
    future[["Open", "High", "Low", "Close"]] = 1.0  # crash tomorrow
    extended = pd.concat([SECTOR, future])
    base = compression_mode(WEAK, RISING_SPY, SECTOR, now=ASOF, spy_regime=BULL)
    assert compression_mode(WEAK, RISING_SPY, extended, now=ASOF, spy_regime=BULL) == base


def test_short_history_fails_closed():
    assert compression_mode(WEAK.iloc[-30:], RISING_SPY, SECTOR, now=ASOF,
                            spy_regime=BULL) == (None, "short_history")
