"""History-frame tests.

The plan's goldens use cpi_yoy/y10. Those series were cut with G13-G20, but
the goldens are about the *publication-lag semantics*, which are the whole
point of this module — so they are kept and driven through as_of_frame's
injectable series_keys rather than through the shipped registry.
"""
import os

import pandas as pd
import pytest

import swingbot.core.macro.history as hist
from swingbot.core.jsonio import atomic_write_json

KEYS = ("cpi_yoy", "y10")


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(hist, "HISTORY_DIR", str(tmp_path))
    events = [
        {"date": "2020-05-12", "time_et": "08:30", "kind": "cpi", "label": "CPI", "importance": 3},
        {"date": "2020-06-10", "time_et": "08:30", "kind": "cpi", "label": "CPI", "importance": 3},
    ]
    monkeypatch.setattr(hist.calendar_events, "load_events", lambda: events)
    return tmp_path


def test_publication_lag_golden(env):
    # April CPI (ref 2020-04-01) released May 12; May CPI released Jun 10.
    atomic_write_json(os.path.join(str(env), "cpi_yoy.json"),
                      [["2020-04-01", 0.3], ["2020-05-01", 0.1]])
    frame = hist.as_of_frame(start="2020-05-01", end="2020-06-30", series_keys=KEYS)
    assert frame.loc["2020-05-29", "cpi_yoy"] == 0.3   # May 29: only April's print is out
    assert frame.loc["2020-06-09", "cpi_yoy"] == 0.3   # still April's the day before release
    assert frame.loc["2020-06-10", "cpi_yoy"] == 0.1   # May's print appears ON release day
    assert pd.isna(frame.loc["2020-05-01", "cpi_yoy"])  # nothing published yet in-window


def test_ffill_and_missing_series(env):
    atomic_write_json(os.path.join(str(env), "cpi_yoy.json"), [["2020-04-01", 0.3]])
    frame = hist.as_of_frame(start="2020-05-01", end="2020-06-30", series_keys=KEYS)
    assert (frame.loc["2020-05-12":, "cpi_yoy"] == 0.3).all()   # forward-filled
    assert frame["y10"].isna().all()                # missing file -> NaN column, no error


def test_daily_series_have_no_lag(env):
    """VIX and breadth are same-day prints: the value must be visible on its
    own observation date, not deferred to any release calendar."""
    atomic_write_json(os.path.join(str(env), "vix.json"),
                      [["2020-05-04", 37.2], ["2020-05-05", 33.6]])
    frame = hist.as_of_frame(start="2020-05-01", end="2020-05-08",
                             series_keys=("vix",))
    assert frame.loc["2020-05-04", "vix"] == 37.2
    assert frame.loc["2020-05-05", "vix"] == 33.6
    assert frame.loc["2020-05-06", "vix"] == 33.6      # ffilled, not re-dated


def test_default_registry_is_the_surviving_series(env):
    frame = hist.as_of_frame(start="2020-05-01", end="2020-05-08")
    assert list(frame.columns) == list(hist.SERIES_KEYS)
    assert "cpi_yoy" not in frame.columns              # cut with G13-G20
