"""v175 § 1: the close-day series and the current state (run, window drawdown).

Trades are built with entry 100, stop 99 (1 point of risk), bullish, so a
trade's R is exactly ``exit_price - 100``.
"""
from datetime import date, timedelta

import pytest

from swingbot.core.analytics import variance_band as vb
from swingbot.core.analytics.variance_band import CloseDay


def _trade(r, closed_at, **extra):
    return {"entry": 100.0, "stop_loss": 99.0, "direction": "bullish",
            "exit_price": 100.0 + r, "closed_at": closed_at,
            "status": "loss" if r < 0 else "win", **extra}


def _days(*rs, start=date(2026, 1, 5)):
    """CloseDay list, one per consecutive calendar day, kinds from day_kind."""
    return [CloseDay(start + timedelta(days=i), r, vb.day_kind(r))
            for i, r in enumerate(rs)]


def test_frozen_constants():
    assert (vb.MIN_DAYS, vb.MIN_WEEKS, vb.HORIZONS, vb.WINDOW) == (100, 20, (20, 50), 50)
    assert vb.WINDOW == vb.HORIZONS[-1]
    assert (vb.PATHS, vb.SEED, vb.SCRATCH_R) == (10_000, 42, 0.05)
    assert (vb.ROUGH_PCT, vb.OUTSIDE_PCT) == (80, 95)
    assert (vb.OUTER_RESAMPLES, vb.OUTER_PATHS, vb.CI_PCT) == (200, 1_000, (10, 90))
    assert (vb.EXPR_RESAMPLES, vb.EXPR_CI_PCT) == (10_000, (2.5, 97.5))
    assert vb.ZONES == ("normal", "rough", "outside")
    assert vb.CAVEAT == ("This book's past results are not positive. "
                         "A run within their range is still a losing run.")
    assert "edge" not in vb.CAVEAT.lower()


@pytest.mark.parametrize("closed_at, expected", [
    ("2026-03-10T19:59:00+00:00", date(2026, 3, 10)),   # 15:59 EDT, in session
    ("2026-03-11T01:30:00+00:00", date(2026, 3, 10)),   # 21:30 EDT: after hours, same NYSE day
    ("2026-03-11T01:30:00", date(2026, 3, 10)),         # naive is read as UTC
    ("2026-01-06T03:00:00Z", date(2026, 1, 5)),         # 22:00 EST the day before
    ("2026-01-06T14:30:00+00:00", date(2026, 1, 6)),    # 09:30 EST
])
def test_et_close_date_puts_an_after_hours_close_on_its_session(closed_at, expected):
    assert vb.et_close_date(closed_at) == expected


@pytest.mark.parametrize("r, kind", [
    (-1.0, "loss"), (-0.0501, "loss"), (-0.05, "scratch"), (0.0, "scratch"),
    (0.05, "scratch"), (0.0501, "win"), (2.0, "win"),
])
def test_day_kind_scratch_band_is_inclusive(r, kind):
    assert vb.day_kind(r) == kind


def test_five_losses_on_one_date_are_one_loss_day():
    trades = [_trade(-1.0, f"2026-03-10T1{i}:00:00+00:00") for i in range(5)]
    assert vb.close_days(trades) == [CloseDay(date(2026, 3, 10), -5.0, "loss")]


def test_mixed_r_on_one_date_nets_out():
    trades = [_trade(-1.0, "2026-03-10T15:00:00+00:00"),
              _trade(1.03, "2026-03-10T18:00:00+00:00"),     # net +0.03: scratch
              _trade(-1.0, "2026-03-12T15:00:00+00:00"),
              _trade(0.5, "2026-03-12T18:00:00+00:00")]      # net -0.5: loss
    assert vb.close_days(trades) == [
        CloseDay(date(2026, 3, 10), 0.03, "scratch"),
        CloseDay(date(2026, 3, 12), -0.5, "loss"),
    ]


def test_close_days_are_in_date_order_and_after_hours_joins_its_session():
    trades = [_trade(2.0, "2026-03-12T15:00:00+00:00"),
              _trade(-1.0, "2026-03-11T01:30:00+00:00"),     # 2026-03-10 ET
              _trade(-1.0, "2026-03-10T15:00:00+00:00")]
    assert vb.close_days(trades) == [
        CloseDay(date(2026, 3, 10), -2.0, "loss"),
        CloseDay(date(2026, 3, 12), 2.0, "win"),
    ]


def test_trade_without_r_or_close_is_skipped():
    no_exit = {**_trade(-1.0, "2026-03-10T15:00:00+00:00"), "exit_price": None}
    no_close = _trade(-1.0, None)
    bad_direction = {**_trade(-1.0, "2026-03-10T15:00:00+00:00"), "direction": "flat"}
    kept = _trade(2.0, "2026-03-11T15:00:00+00:00")
    assert vb.close_days([no_exit, no_close, bad_direction, kept]) == [
        CloseDay(date(2026, 3, 11), 2.0, "win")]


def test_close_days_of_an_empty_book():
    assert vb.close_days([]) == []


def test_current_run_counts_loss_days_and_scratch_neither_breaks_nor_extends():
    days = _days(2.0, -1.0, -1.0, 0.0, -1.0, 0.01)
    assert vb.current_run(days) == (3, days[1].day)


def test_a_win_day_ends_the_run():
    days = _days(-1.0, -1.0, 2.0, -1.0, -1.0)
    assert vb.current_run(days) == (2, days[3].day)


@pytest.mark.parametrize("rs", [(), (2.0,), (-1.0, 2.0), (0.0, 0.01)])
def test_no_run_in_progress(rs):
    assert vb.current_run(_days(*rs)) == (0, None)


def test_window_drawdown_is_peak_to_now_inside_the_window():
    # 10 losing days (an all-time drawdown of 10R), then 40 wins, then 10 x -0.5:
    # the last 50 days climb to +40R and give back 5R.
    days = _days(*([-1.0] * 10 + [1.0] * 40 + [-0.5] * 10))
    assert vb.window_drawdown(days) == (5.0, days[49].day)


def test_older_deeper_drawdown_outside_the_window_does_not_count():
    days = _days(*([-1.0] * 30 + [1.0] * 50))
    assert vb.window_drawdown(days) == (0.0, None)


def test_window_drawdown_from_the_zero_baseline_peaks_on_the_first_window_day():
    days = _days(*([2.0] * 60 + [-1.0] * 3))
    assert vb.window_drawdown(days, window=3) == (3.0, days[60].day)


def test_window_drawdown_takes_the_latest_equal_peak():
    days = _days(1.0, -1.0, 1.0, -0.5)
    assert vb.window_drawdown(days) == (0.5, days[2].day)


def test_window_drawdown_of_no_days():
    assert vb.window_drawdown([]) == (0.0, None)


@pytest.mark.parametrize("value, p80, p95, zone", [
    (3, 4, 6, "normal"), (4, 4, 6, "normal"), (5, 4, 6, "rough"),
    (6, 4, 6, "rough"), (7, 4, 6, "outside"),
    (4, 4, 4, "normal"), (5, 4, 4, "outside"),           # tie: rough is empty
    (2.5, 2.5, 4.1, "normal"), (4.1, 2.5, 4.1, "rough"), (4.11, 2.5, 4.1, "outside"),
])
def test_zone_boundaries_exactly_at_p80_and_p95(value, p80, p95, zone):
    assert vb.zone_of(value, p80, p95) == zone


@pytest.mark.parametrize("a, b, worse", [
    ("normal", "normal", "normal"), ("normal", "rough", "rough"),
    ("outside", "rough", "outside"), ("rough", "normal", "rough"),
])
def test_worse_zone_follows_zones_order(a, b, worse):
    assert vb.worse_zone(a, b) == worse
