import datetime as dt

import pandas as pd
import pytest

import swingbot.core.gate.backtest_ctx as bctx


@pytest.fixture
def env(monkeypatch):
    # cpi_yoy: April print (0.3) visible from May 12; May print (0.1) from Jun 10
    idx = pd.bdate_range("2020-05-01", "2020-06-30")
    frame = pd.DataFrame(index=idx)
    col = pd.Series(index=idx, dtype=float)
    col[pd.Timestamp("2020-05-12")] = 0.3
    col[pd.Timestamp("2020-06-10")] = 0.1
    frame["cpi_yoy"] = col.ffill()
    for key in ("core_cpi_yoy", "ppi_yoy", "pce_yoy", "core_pce_yoy", "fed_funds",
                "y2", "y10", "curve_10y2y", "curve_10y3m", "dollar_index", "wti"):
        frame[key] = 1.0
    monkeypatch.setattr(bctx, "_frame", lambda start="2018-01-01": frame)
    events = [{"date": "2020-06-10", "time_et": "08:30", "kind": "cpi",
               "label": "CPI release", "importance": 3}]
    monkeypatch.setattr(bctx.calendar_events, "load_events", lambda: events)
    monkeypatch.setattr(bctx, "_vix_percentile", lambda: {"2020-06-09": 71.0})


def test_day_before_cpi_sees_previous_print_and_pending_event(env):
    snap = bctx.historical_macro_snap(dt.date(2020, 6, 9))
    assert snap["inflation"]["cpi_yoy"]["value"] == 0.3      # PREVIOUS print
    assert snap["events"]["next_high_impact"]["date"] == "2020-06-10"  # pending
    assert snap["events"]["within_24h"]                       # inside 24h at the close
    assert snap["risk"]["vix"]["percentile_1y"] == 71.0
    assert snap["historical"] is True


def test_release_day_sees_new_print(env):
    snap = bctx.historical_macro_snap(dt.date(2020, 6, 10))
    assert snap["inflation"]["cpi_yoy"]["value"] == 0.1


def test_missing_history_degrades_to_unknowns(env, monkeypatch):
    monkeypatch.setattr(bctx, "_frame",
                        lambda start="2018-01-01": pd.DataFrame(
                            index=pd.bdate_range("2020-05-01", "2020-06-30")))
    snap = bctx.historical_macro_snap(dt.date(2020, 6, 9))
    assert snap["inflation"]["cpi_yoy"] is None
    assert snap["rates"]["curve_state"] == "unknown"
