"""v208 V208-9: time-weighted exposure and Bot deployed return."""
from datetime import date, datetime, timezone
from decimal import Decimal
from itertools import count

import pytest

from swingbot.core.analytics import benchmark_series as bs
from swingbot.core.market.session import US_MARKET_TZ
from swingbot.core.tracking.equity import RealizedLeg

MON, TUE, WED = date(2026, 11, 2), date(2026, 11, 3), date(2026, 11, 4)
HALF_DAY = date(2026, 11, 27)
_ids = count(1)


def _at(day, hh, mm=0):
    return datetime(day.year, day.month, day.day, hh, mm, tzinfo=US_MARKET_TZ).astimezone(timezone.utc)


def _row(day, hh, mm, *, notional=None, equity=10_000.0, unrealized=0.0, realized=10_000.0,
         open_n=0, approx=None, kind="point", source="live"):
    row = {"id": next(_ids), "at": _at(day, hh, mm), "equity": equity, "realized_balance": realized,
           "unrealized_pnl": unrealized, "open_n": open_n, "skipped_n": 0, "source": source, "kind": kind}
    if notional is not None:
        row["open_notional"] = notional
    if approx is not None:
        row["open_notional_approx"] = approx
    return row


def test_rows_by_session_keeps_point_rows_in_time_order():
    late, early = _row(TUE, 15, 55), _row(TUE, 9, 35)
    rows = [late, _row(TUE, 9, 35, kind="day_high"), early, _row(date(2026, 11, 7), 16, 0)]
    assert bs.rows_by_session(rows, [MON, TUE]) == {TUE: [early, late]}


def test_exposure_is_time_weighted_to_the_close():
    by_day = {TUE: [_row(TUE, 9, 30, notional=0.0, open_n=0),
                    _row(TUE, 15, 0, notional=5_000.0, open_n=2)]}
    exp = bs.exposure_by_session(by_day)[TUE]
    assert exp.pct == pytest.approx(0.5 / 6.5)
    assert (exp.open_n, exp.approx) == (2, False)


@pytest.mark.parametrize("usable_approx", [False, True])
def test_exposure_uses_only_usable_rows_for_weights_and_approx(usable_approx):
    by_day = {TUE: [
        _row(TUE, 9, 30, approx=True, open_n=5),
        _row(TUE, 10, 0, notional=1_000.0, open_n=1),
        _row(TUE, 12, 0, notional=5_000.0, equity=0.0, approx=True, open_n=3),
        _row(TUE, 14, 0, notional=4_000.0, approx=usable_approx, open_n=2),
    ]}
    assert bs.exposure_by_session(by_day)[TUE] == bs.Exposure(pytest.approx(0.2), 5, usable_approx)


def test_a_half_day_weights_to_the_1300_close():
    by_day = {HALF_DAY: [_row(HALF_DAY, 9, 30, notional=0.0), _row(HALF_DAY, 12, 0, notional=5_000.0)]}
    assert bs.exposure_by_session(by_day)[HALF_DAY].pct == pytest.approx(0.5 / 3.5)


def test_a_lone_close_sample_falls_back_to_its_own_value():
    by_day = {TUE: [_row(TUE, 16, 0, notional=2_000.0, approx=True, source="backfill")]}
    assert bs.exposure_by_session(by_day)[TUE] == bs.Exposure(pytest.approx(0.2), 0, True)


def test_no_open_notional_means_no_exposure_value_not_zero():
    exp = bs.exposure_by_session({TUE: [_row(TUE, 10, 0, open_n=1), _row(TUE, 15, 55, open_n=3)]})[TUE]
    assert (exp.pct, exp.open_n, exp.approx) == (None, 3, False)


def _deployed(by_day, legs=()):
    return bs.deployed_returns(by_day, list(legs), [MON, TUE, WED])


def test_an_intraday_round_trip_is_divided_by_its_peak_notional():
    by_day = {MON: [_row(MON, 15, 55, notional=0.0)],
              TUE: [_row(TUE, 10, 0, notional=10_000.0, unrealized=50.0),
                    _row(TUE, 12, 0, notional=0.0), _row(TUE, 15, 55, notional=0.0)]}
    out = _deployed(by_day, [RealizedLeg(_at(TUE, 11, 30), Decimal("200"), "t1")])
    assert out[TUE] == bs.Deployed(pytest.approx(0.02), False, False, None)
    assert bs.exposure_by_session(by_day)[TUE].pct == pytest.approx(2 / 6)


def test_a_zero_exposure_day_is_not_chained():
    by_day = {MON: [_row(MON, 15, 55, notional=0.0)], TUE: [_row(TUE, 15, 55, notional=0.0)]}
    assert _deployed(by_day)[TUE] == bs.Deployed(None, False, False, "no_exposure")


@pytest.mark.parametrize("equity, notional, ret, reason", [
    (10_000.0, 499.0, None, "below_min"),
    (10_000.0, 500.0, pytest.approx(0.1), None),
    (8_000.60, 400.02, None, "below_min"),
    (8_000.60, 400.03, pytest.approx(0.1), None),
])
def test_the_five_percent_floor(equity, notional, ret, reason):
    by_day = {MON: [_row(MON, 15, 55, notional=notional)],
              TUE: [_row(TUE, 15, 55, notional=notional, equity=equity, unrealized=notional * 0.1)]}
    assert bs.DEPLOYED_MIN_SHARE == 0.05
    assert _deployed(by_day)[TUE] == bs.Deployed(ret, False, False, reason)


def test_a_short_gapping_past_minus_100_percent_is_clipped_and_flagged():
    by_day = {MON: [_row(MON, 15, 55, notional=1_000.0)],
              TUE: [_row(TUE, 15, 55, notional=0.0, realized=7_500.0, equity=7_500.0)]}
    out = _deployed(by_day, [RealizedLeg(_at(TUE, 9, 31), Decimal("-2500"), "short1")])
    assert out[TUE] == bs.Deployed(-1.0, True, False, None)


def test_a_base_balance_edit_never_enters_the_deployed_return():
    by_day = {MON: [_row(MON, 15, 55, notional=2_000.0, unrealized=40.0)],
              TUE: [_row(TUE, 15, 55, notional=2_000.0, unrealized=40.0, realized=10_500.0)]}
    assert _deployed(by_day)[TUE] == bs.Deployed(0.0, False, False, None)


def test_missing_inputs_are_missing_never_zero():
    no_notional = {MON: [_row(MON, 15, 55)], TUE: [_row(TUE, 15, 55, open_n=1)]}
    out = _deployed(no_notional)
    assert out[MON] == bs.Deployed(None, False, False, "missing")
    assert out[TUE] == bs.Deployed(None, False, False, "missing")
    assert out[WED] == bs.Deployed(None, False, False, "missing")


def test_a_gap_measures_from_the_last_session_with_rows_and_approx_is_carried():
    by_day = {MON: [_row(MON, 16, 0, notional=1_000.0, approx=True, source="backfill")],
              WED: [_row(WED, 15, 55, notional=1_000.0, unrealized=30.0)]}
    assert _deployed(by_day)[WED] == bs.Deployed(pytest.approx(0.03), False, True, None)
