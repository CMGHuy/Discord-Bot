"""plan_manager._bars_since must accept the timestamps plans actually carry.

Plans store tz-aware ISO strings ("2026-10-08T14:03:11+00:00"); the daily bar
index is tz-naive session dates. The comparison used to raise TypeError for
every live plan, so pending expiry and the stall/time exits never ran."""
import pandas as pd
import pytest

import swingbot.core.marketdata.data as data
from swingbot.core.planning import plan_manager as pm


def _bars(index_tz=None):
    index = pd.date_range("2026-10-05", periods=6, freq="B", tz=index_tz)   # Mon 5th .. Mon 12th
    return pd.DataFrame({"Close": range(len(index))}, index=index)


@pytest.fixture
def daily(monkeypatch):
    def install(index_tz=None):
        df = _bars(index_tz)
        monkeypatch.setattr(data, "get_daily_data", lambda ticker: df)
    return install


def test_a_tz_aware_utc_timestamp_counts_sessions_after_its_new_york_day(daily):
    daily()
    # 14:03 UTC on Wed 7th is 10:03 ET on Wed 7th: Thu 8th, Fri 9th, Mon 12th follow.
    assert pm._bars_since("AAPL", "2026-10-07T14:03:11+00:00") == 3


def test_an_evening_new_york_fill_is_still_that_new_york_day(daily):
    daily()
    # 01:30 UTC on Thu 8th is 21:30 ET on Wed 7th, so Thu is the first bar after it.
    assert pm._bars_since("AAPL", "2026-10-08T01:30:00+00:00") == 3


def test_a_naive_timestamp_is_unchanged(daily):
    daily()
    assert pm._bars_since("AAPL", "2026-10-07T10:00:00") == 3


def test_a_tz_aware_index_gives_the_same_count(daily):
    daily("America/New_York")
    assert pm._bars_since("AAPL", "2026-10-07T14:03:11+00:00") == 3


def test_a_timestamp_after_the_last_bar_counts_zero(daily):
    daily()
    assert pm._bars_since("AAPL", "2026-10-12T15:00:00+00:00") == 0
