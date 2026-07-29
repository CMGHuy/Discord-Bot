import datetime as dt
from zoneinfo import ZoneInfo

import numpy as np

from swingbot.core.gate.registry import CHECKS
from swingbot.core.gate.setup_quality import check_signal_confirmed
from tests.conftest import make_ohlcv
from tests.fixtures.gate import uptrend_daily
from tests.fixtures.gate.plans import make_plan

ET = ZoneInfo("America/New_York")


def test_closed_bar_passes():
    plan = make_plan(created_at="2026-07-13")            # yesterday's bar
    now = dt.datetime(2026, 7, 14, 15, 0, tzinfo=ET)     # mid-session today
    assert check_signal_confirmed(uptrend_daily(), plan, None, now=now).status == "pass"


def test_same_day_forming_bar_fails_hard():
    plan = make_plan(created_at="2026-07-14")
    now = dt.datetime(2026, 7, 14, 15, 0, tzinfo=ET)     # Tuesday, session open
    assert check_signal_confirmed(uptrend_daily(), plan, None, now=now).status == "fail"
    # after the close the same plan is fine
    evening = dt.datetime(2026, 7, 14, 17, 30, tzinfo=ET)
    assert check_signal_confirmed(uptrend_daily(), plan, None, now=evening).status == "pass"


def test_breakout_close_back_inside_fails():
    # market-entry breakout plan whose signal bar poked above the level
    # intrabar (high 100.5) but closed back inside (99.5)
    df = make_ohlcv(np.concatenate([np.full(59, 97.0), [99.5]]), spread_pct=2.0)
    plan = make_plan(strategy="Break & Retest", entry_type="market",
                     trigger_price=100.0, created_at="2026-07-13")
    now = dt.datetime(2026, 7, 14, 17, 30, tzinfo=ET)
    result = check_signal_confirmed(df, plan, None, now=now)
    assert result.status == "fail" and "inside" in result.detail


def test_registered_as_hard_block():
    assert CHECKS["signal_confirmed"].hard_block is True
