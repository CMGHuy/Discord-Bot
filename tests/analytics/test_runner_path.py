"""v142: compute_runner_path -- the runner's post-TP1 path, from daily bars."""
import logging

import pandas as pd
import pytest

from swingbot.core.analytics import runner_path as rp
from swingbot.core.planning.plan_engine import PlanStatus
from tests.planning.test_plan_engine_model import _plan

FILL = "2026-10-01T14:00:00+00:00"     # Thu
MON = "2026-10-05T15:00:00+00:00"      # TP1 session
WED = "2026-10-07T18:00:00+00:00"      # runner exit session


def _closed(reason, runner_price, *, direction="bullish", partial_at=MON, closed_at=WED,
            runner_leg=True):
    """A closed partial plan: entry 100, risk 5, TP1 filled at exactly 2.0R."""
    bull = direction == "bullish"
    sign = 1 if bull else -1
    stop, tp1, tp2 = (95.0, 110.0, 120.0) if bull else (105.0, 90.0, 80.0)
    legs = [{"fraction": 0.5, "exit_price": tp1, "r": 2.0, "reason": "tp1", "closed_at": partial_at}]
    if runner_leg:
        legs.append({"fraction": 0.5, "exit_price": runner_price,
                     "r": (runner_price - 100.0) * sign / 5.0, "reason": reason,
                     "closed_at": closed_at})
    return _plan(direction=direction, entry_price=100.0, stop_loss=stop, tp1=tp1, tp2=tp2,
                 status=PlanStatus.CLOSED, legs_realized=legs,
                 status_history=[{"status": "ACTIVE", "reason": "filled", "at": FILL},
                                 {"status": "PARTIAL", "reason": "tp1_partial", "at": partial_at},
                                 {"status": "CLOSED", "reason": reason, "at": closed_at}])


def _bars(rows):
    """rows: [(YYYY-MM-DD, high, low)] -> a daily OHLC frame."""
    index = pd.to_datetime([day for day, _, _ in rows])
    highs = [high for _, high, _ in rows]
    lows = [low for _, _, low in rows]
    return pd.DataFrame({"Open": lows, "High": highs, "Low": lows, "Close": highs}, index=index)


LONG_BARS = _bars([("2026-10-05", 112.0, 104.0), ("2026-10-06", 116.0, 108.0),
                   ("2026-10-07", 121.0, 115.0)])


def test_long_tp2_runner_path():
    path = rp.compute_runner_path(_closed("tp1_runner_tp2", 120.0), LONG_BARS)
    # MON's low (0.8R) may predate TP1, so it never reaches MAE; TUE's 1.6R does.
    assert path == {"mfe_r": 4.2, "mae_r": 1.6,
                    "ladder": {"1.5": "2026-10-05", "2.0": "2026-10-05", "2.5": "2026-10-06",
                               "3.0": "2026-10-06", "4.0": "2026-10-07"},
                    "sessions_after_tp1": 2, "source": "live"}


def test_short_runner_path_mirrors_the_long():
    bars = _bars([("2026-10-05", 96.0, 88.0), ("2026-10-06", 92.0, 84.0),
                  ("2026-10-07", 85.0, 79.0)])
    path = rp.compute_runner_path(_closed("tp1_runner_tp2", 80.0, direction="bearish"), bars)
    assert (path["mfe_r"], path["mae_r"]) == (4.2, 1.6)
    assert path["ladder"] == {"1.5": "2026-10-05", "2.0": "2026-10-05", "2.5": "2026-10-06",
                              "3.0": "2026-10-06", "4.0": "2026-10-07"}


def test_a_gap_through_a_level_counts_as_touched():
    # TUE gaps from 111 straight to 117: 2.5R (112.5) and 3.0R (115) never trade
    # inside a bar, but the gap went through both.
    bars = _bars([("2026-10-05", 111.0, 105.0), ("2026-10-06", 117.5, 116.5),
                  ("2026-10-07", 118.0, 113.0)])
    path = rp.compute_runner_path(_closed("tp1_runner_trail", 113.0), bars)
    assert path["ladder"]["2.5"] == "2026-10-06" and path["ladder"]["3.0"] == "2026-10-06"


def test_a_stop_exit_session_counts_only_the_exit_fill():
    # WED spikes to 125 (5R) but the trail exit at 113 is assumed to come first.
    bars = _bars([("2026-10-05", 111.0, 105.0), ("2026-10-06", 114.0, 112.0),
                  ("2026-10-07", 125.0, 112.5)])
    path = rp.compute_runner_path(_closed("tp1_runner_trail", 113.0), bars)
    assert path["mfe_r"] == 2.8                  # TUE's 114 -> 2.8R; WED's 125 ignored
    assert path["ladder"]["4.0"] is None and path["ladder"]["3.0"] is None
    assert path["mae_r"] == 2.0                  # TP1 fill; WED's low ignored, exit 2.6R


def test_a_non_stop_exit_session_counts_its_bar():
    bars = _bars([("2026-10-05", 111.0, 105.0), ("2026-10-06", 114.0, 112.0),
                  ("2026-10-07", 125.0, 112.5)])
    path = rp.compute_runner_path(_closed("tp1_runner_progress_stall", 113.0), bars)
    assert path["mfe_r"] == 5.0 and path["ladder"]["4.0"] == "2026-10-07"


def test_tp1_and_exit_on_the_same_session():
    plan = _closed("tp1_runner_be", 106.66666666666667, closed_at="2026-10-05T19:00:00+00:00")
    path = rp.compute_runner_path(plan, _bars([("2026-10-05", 130.0, 90.0)]))
    assert path["sessions_after_tp1"] == 0
    assert path["mfe_r"] == 2.0                  # floored at the TP1 R; the bar is a stop-exit bar
    assert path["mae_r"] == pytest.approx(1.3333, abs=1e-4)
    assert path["ladder"] == {"1.5": "2026-10-05", "2.0": "2026-10-05", "2.5": None,
                              "3.0": None, "4.0": None}


def test_the_tp1_session_counts_a_level_beyond_tp1_its_bar_reached():
    bars = _bars([("2026-10-05", 113.0, 96.0), ("2026-10-06", 112.0, 108.0),
                  ("2026-10-07", 112.0, 108.0)])
    path = rp.compute_runner_path(_closed("tp1_runner_trail", 108.0), bars)
    assert path["ladder"]["2.5"] == "2026-10-05"
    assert path["mae_r"] == 1.6                  # MON's 96 low is not counted


def test_a_missing_session_bar_returns_none():
    bars = _bars([("2026-10-05", 112.0, 104.0), ("2026-10-07", 121.0, 115.0)])  # no TUE
    assert rp.compute_runner_path(_closed("tp1_runner_tp2", 120.0), bars) is None
    assert rp.compute_runner_path(_closed("tp1_runner_tp2", 120.0), None) is None


def test_a_still_forming_exit_session_bar_is_optional():
    bars = _bars([("2026-10-05", 112.0, 104.0), ("2026-10-06", 116.0, 108.0)])  # no WED yet
    path = rp.compute_runner_path(_closed("tp1_runner_tp2", 120.0), bars)
    assert path["mfe_r"] == 4.0                  # the TP2 fill itself
    assert path["ladder"]["4.0"] == "2026-10-07"


def test_a_manual_close_without_a_runner_leg_uses_the_exit_bar():
    plan = _closed("manual", 0.0, runner_leg=False)
    path = rp.compute_runner_path(plan, LONG_BARS)
    assert path["mfe_r"] == 4.2 and path["mae_r"] == 1.6


def test_a_plan_without_a_partial_transition_has_no_path():
    plan = _closed("tp1_runner_tp2", 120.0)
    plan.status_history = [h for h in plan.status_history if h["status"] != "PARTIAL"]
    assert rp.compute_runner_path(plan, LONG_BARS) is None


def test_source_is_recorded():
    path = rp.compute_runner_path(_closed("tp1_runner_tp2", 120.0), LONG_BARS, source="backfill")
    assert path["source"] == "backfill"


def test_stamp_sets_the_field_and_logs_a_miss(caplog):
    plan = _closed("tp1_runner_tp2", 120.0)
    assert rp.stamp_runner_path(plan, lambda ticker: LONG_BARS)["mfe_r"] == 4.2
    assert plan.runner_path["source"] == "live"
    with caplog.at_level(logging.INFO, logger=rp.log.name):
        assert rp.stamp_runner_path(plan, lambda ticker: None) is None
    assert plan.runner_path is None
    assert [r.getMessage() for r in caplog.records if r.name == rp.log.name] == [
        "runner_path: no stamp for p1 (AAPL) -- bars do not cover the runner window"]


def test_stamp_never_raises():
    plan = _closed("tp1_runner_tp2", 120.0)

    def boom(ticker):
        raise OSError("disk gone")

    assert rp.stamp_runner_path(plan, boom) is None
    assert plan.runner_path is None


def test_cached_daily_bars_reads_the_disk_cache_only(monkeypatch):
    from swingbot.core.marketdata import data_store
    calls = []
    monkeypatch.setattr(data_store, "load_normalized",
                        lambda ticker, interval: calls.append((ticker, interval)) or "frame")
    assert rp.cached_daily_bars("AAPL") == "frame"
    assert calls == [("AAPL", "daily")]
