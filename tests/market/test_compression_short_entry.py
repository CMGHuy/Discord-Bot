"""V119-2: First Bearish Compression Release -- bar-level frame, masked live admission."""
import datetime as dt
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from swingbot.core.market import short_entries as se
from swingbot.core.market.entry_filters import entries_for
from swingbot.core.market.strategy_types import SHORT_STRATEGIES, STRATEGY_GATES
from swingbot.core.scanning.strategy_pass import completed_frame
from tests.market.test_squeeze_release_series import _frame

NAME = se.COMPRESSION_SHORT
ET = ZoneInfo("America/New_York")


@pytest.fixture
def release():
    return _frame([96])


def test_name_registered_and_masked():
    assert NAME == "First Bearish Compression Release"
    assert NAME in SHORT_STRATEGIES
    assert STRATEGY_GATES[NAME] == {"directions": ()}


def test_first_release_fires_bearish_on_2w_only(release):
    assert bool(se.compression_short_frame(release, "2w")["signal"].iloc[-1])
    for hk in ("1w", "4w", "2m"):
        assert not se.compression_short_frame(release, hk)["signal"].any()


def test_bullish_release_never_fires(release):
    assert not se.compression_short_frame(_frame([104]), "2w")["signal"].iloc[-1]


def test_second_outside_bar_does_not_fire():
    assert not se.compression_short_frame(_frame([96, 94]), "2w")["signal"].iloc[-1]


def test_live_admission_stays_masked(release):
    for hk in ("2w", "1w"):
        bull, bear = entries_for(NAME, release, hk)
        assert not bull.any() and not bear.any()


def test_frame_carries_level_and_stop_above_high(release):
    row = se.compression_short_frame(release, "2w").iloc[-1]
    assert row["level"] == release["Close"].iloc[-1]
    assert row["stop"] > release["High"].iloc[-1]


def test_truncated_frame_row_equals_full_frame_row(release):
    full = se.compression_short_frame(release, "2w")
    for i in range(len(release) - 6, len(release)):
        part = se.compression_short_frame(release.iloc[:i + 1], "2w").iloc[-1]
        pd.testing.assert_series_equal(part, full.iloc[i], check_names=False)


def test_forming_rth_bar_excluded_by_completed_frame(release):
    day = release.index[-1].date()
    during = completed_frame(release, dt.datetime(day.year, day.month, day.day, 11, tzinfo=ET))
    assert len(during) == len(release) - 1
    assert not se.compression_short_frame(during, "2w")["signal"].iloc[-1]
    after = completed_frame(release, dt.datetime(day.year, day.month, day.day, 16, 5, tzinfo=ET))
    assert bool(se.compression_short_frame(after, "2w")["signal"].iloc[-1])
