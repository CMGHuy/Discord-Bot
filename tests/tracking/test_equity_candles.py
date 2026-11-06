"""v172 § 4: equity candles from raw samples and realized legs.

Berlin wall clock, weekdays 08:00-22:00. 2026 DST: CEST until Sun 25 October,
CET after.
"""
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from swingbot.core.tracking.equity import RealizedLeg
from swingbot.core.tracking.equity_candles import (
    TIMEFRAMES, add_change, bucket_label, bucket_start, mtm_candles, parse_bucket_label,
    fill_flat, realized_candles)

UTC = timezone.utc


def _utc(y, m, d, h, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=UTC)


def _label(at, tf):
    return bucket_label(bucket_start(at, tf), tf)


def _row(at, equity, *, kind="point", source="live", skipped=0, row_id=0):
    return {"id": row_id, "at": at, "equity": equity, "kind": kind, "source": source,
            "skipped_n": skipped}


def test_the_four_timeframes():
    assert TIMEFRAMES == ("1H", "4H", "1D", "1W")


def test_an_unknown_timeframe_is_refused():
    with pytest.raises(ValueError):
        bucket_start(_utc(2026, 10, 16, 14), "15m")


def test_the_day_turns_at_berlin_midnight_not_utc():
    assert _label(_utc(2026, 10, 15, 21, 59), "1D") == "2026-10-15"    # 23:59 Berlin
    assert _label(_utc(2026, 10, 15, 22, 1), "1D") == "2026-10-16"     # 00:01 Berlin


def test_hour_labels_carry_the_berlin_offset():
    assert _label(_utc(2026, 10, 16, 14, 35), "1H") == "2026-10-16T16:00:00+02:00"
    assert _label(_utc(2026, 10, 16, 14, 35), "4H") == "2026-10-16T16:00:00+02:00"
    assert _label(_utc(2026, 11, 2, 14, 35), "1H") == "2026-11-02T15:00:00+01:00"   # CET


def test_a_sample_outside_the_08_to_22_window_folds_into_its_own_day():
    assert _label(_utc(2026, 10, 16, 4, 30), "1H") == "2026-10-16T08:00:00+02:00"   # 06:30
    assert _label(_utc(2026, 10, 16, 21, 30), "1H") == "2026-10-16T21:00:00+02:00"  # 23:30
    assert _label(_utc(2026, 10, 16, 21, 30), "4H") == "2026-10-16T20:00:00+02:00"
    assert _label(_utc(2026, 10, 16, 4, 30), "1D") == "2026-10-16"


def test_a_weekend_sample_folds_into_monday_except_for_the_week_bucket():
    assert _label(_utc(2026, 10, 17, 10), "1H") == "2026-10-19T08:00:00+02:00"      # Saturday
    assert _label(_utc(2026, 10, 18, 10), "1D") == "2026-10-19"                      # Sunday
    assert _label(_utc(2026, 10, 18, 10), "1W") == "2026-10-12"                      # its own week


def test_the_week_starts_on_monday():
    assert _label(_utc(2026, 10, 18, 15), "1W") == "2026-10-12"        # Sunday
    assert _label(_utc(2026, 10, 19, 15), "1W") == "2026-10-19"        # Monday


# --- mark-to-market -----------------------------------------------------------

BACKFILL_DAY = [  # Thu 15 Oct: open 13:30Z, close 20:00Z
    _row(_utc(2026, 10, 15, 13, 30), 10000.0, source="backfill", row_id=1),
    _row(_utc(2026, 10, 15, 13, 30), 10300.0, kind="day_high", source="backfill", skipped=1, row_id=2),
    _row(_utc(2026, 10, 15, 13, 30), 9900.0, kind="day_low", source="backfill", row_id=3),
    _row(_utc(2026, 10, 15, 20, 0), 10100.0, source="backfill", row_id=4),
]
LIVE_DAY = [  # Fri 16 Oct
    _row(_utc(2026, 10, 16, 14, 0), 10150.0, row_id=5),
    _row(_utc(2026, 10, 16, 15, 0), 10250.0, row_id=6),
    _row(_utc(2026, 10, 16, 19, 55), 10200.0, row_id=7),
]
CANDLE_KEYS = ["t", "o", "h", "l", "c", "change", "change_pct", "samples", "skipped", "approx"]


def test_daily_mtm_reads_o_and_c_from_points_and_h_l_from_every_row():
    first, second = mtm_candles(BACKFILL_DAY + LIVE_DAY, "1D")
    assert list(first) == CANDLE_KEYS
    assert first == {"t": "2026-10-15", "o": 10000.0, "h": 10300.0, "l": 9900.0, "c": 10100.0,
                     "change": 100.0, "change_pct": 1.0, "samples": 4, "skipped": 1, "approx": True}
    assert second == {"t": "2026-10-16", "o": 10150.0, "h": 10250.0, "l": 10150.0, "c": 10200.0,
                      "change": 100.0, "change_pct": 0.99, "samples": 3, "skipped": 0,
                      "approx": False}


def test_rows_arrive_in_any_order():
    assert mtm_candles(list(reversed(BACKFILL_DAY + LIVE_DAY)), "1D") == mtm_candles(
        BACKFILL_DAY + LIVE_DAY, "1D")


def test_empty_buckets_are_omitted():
    monday = [_row(_utc(2026, 10, 19, 14), 10300.0, row_id=8)]
    candles = mtm_candles(LIVE_DAY + monday, "1D")
    assert [c["t"] for c in candles] == ["2026-10-16", "2026-10-19"]
    assert candles[1]["change"] == 100.0                               # vs Friday's close


def test_intraday_mtm_never_reads_backfill_rows():
    candles = mtm_candles(BACKFILL_DAY + LIVE_DAY, "1H")
    assert [c["t"] for c in candles] == ["2026-10-16T16:00:00+02:00", "2026-10-16T17:00:00+02:00",
                                         "2026-10-16T21:00:00+02:00"]
    assert not any(c["approx"] for c in candles)
    assert candles[0]["change"] == 0.0                                 # first: c - its own o


def test_the_week_aggregates_both_days():
    (week,) = mtm_candles(BACKFILL_DAY + LIVE_DAY, "1W")
    assert (week["t"], week["o"], week["h"], week["l"], week["c"]) == (
        "2026-10-12", 10000.0, 10300.0, 9900.0, 10200.0)
    assert (week["samples"], week["skipped"], week["approx"]) == (7, 1, True)


def test_no_rows_no_candles():
    assert mtm_candles([], "1D") == []


# --- change -------------------------------------------------------------------

def test_change_pct_is_null_when_the_base_is_zero():
    (candle,) = add_change([{"t": "2026-10-16", "o": 0, "h": 5, "l": 0, "c": 5,
                             "samples": 1, "skipped": 0, "approx": False}])
    assert (candle["change"], candle["change_pct"]) == (5.0, None)


def test_change_is_measured_from_the_previous_close():
    candles = add_change([
        {"t": "a", "o": 100, "h": 110, "l": 95, "c": 105, "samples": 1, "skipped": 0, "approx": False},
        {"t": "b", "o": 108, "h": 108, "l": 101.333, "c": 101.333, "samples": 1, "skipped": 0,
         "approx": False}])
    assert [(c["change"], c["change_pct"]) for c in candles] == [(5.0, 5.0), (-3.67, -3.49)]
    assert candles[1]["l"] == 101.33


# --- realized basis -----------------------------------------------------------

def _leg(at, amount):
    return RealizedLeg(at=at, amount=Decimal(str(amount)), trade_id="t")


def test_realized_steps_through_each_leg_of_the_day():
    legs = [_leg(_utc(2026, 10, 14, 15), 50.0),      # TP1
            _leg(_utc(2026, 10, 14, 19), -80.0),
            _leg(_utc(2026, 10, 14, 19, 30), 20.0),
            _leg(_utc(2026, 10, 16, 18), 100.0)]
    first, second = realized_candles(legs, Decimal("10000"), "1D")
    assert first == {"t": "2026-10-14", "o": 10000.0, "h": 10050.0, "l": 9970.0, "c": 9990.0,
                     "change": -10.0, "change_pct": -0.1, "samples": 3, "skipped": 0,
                     "approx": False}
    assert second == {"t": "2026-10-16", "o": 9990.0, "h": 10090.0, "l": 9990.0, "c": 10090.0,
                      "change": 100.0, "change_pct": 1.0, "samples": 1, "skipped": 0,
                      "approx": False}


def test_a_day_with_no_leg_has_no_realized_candle():
    assert realized_candles([], Decimal("10000"), "1D") == []


# --- parse_bucket_label (v181: the /equity/candles paging cursor) -------------

ROUND_TRIP_INSTANTS = [
    _utc(2026, 10, 16, 14, 35),            # ordinary EDT session hour
    _utc(2026, 3, 8, 6, 30),               # 01:30 EST, the hour before spring forward
    _utc(2026, 3, 8, 7, 30),               # 03:30 EDT, the hour after the skipped one
    _utc(2026, 11, 1, 5, 30),              # 01:30 EDT, first pass of the repeated hour
    _utc(2026, 11, 1, 6, 30),              # 01:30 EST, second pass of the repeated hour
    _utc(2027, 1, 1, 4, 59),               # 23:59 New York on 31 Dec
]


@pytest.mark.parametrize("tf", TIMEFRAMES)
@pytest.mark.parametrize("at", ROUND_TRIP_INSTANTS)
def test_a_bucket_label_parses_back_to_its_bucket_start(at, tf):
    start = bucket_start(at, tf)
    label = bucket_label(start, tf)
    parsed = parse_bucket_label(label, tf)
    assert parsed.tzinfo is not None
    assert parsed.timestamp() == start.timestamp()     # instants, so `fold` counts
    assert bucket_label(parsed, tf) == label


def test_the_two_repeated_fall_back_hours_parse_to_different_instants():
    first = parse_bucket_label("2026-11-01T01:00:00-04:00", "1H")
    second = parse_bucket_label("2026-11-01T01:00:00-05:00", "1H")
    assert second.timestamp() - first.timestamp() == 3600


def test_a_daily_label_is_the_berlin_midnight_instant():
    parsed = parse_bucket_label("2026-10-16", "1D")
    assert parsed.astimezone(UTC) == _utc(2026, 10, 15, 22)   # 00:00 CEST


@pytest.mark.parametrize("label, tf", [
    ("2026-10-16", "1H"),                          # a date where a datetime is emitted
    ("2026-10-16T10:00:00-04:00", "1D"),           # a datetime where a date is emitted
    ("2026-10-16T10:00:00", "1H"),                 # naive
    ("2026-10-16T10:00:00Z", "4H"),                # Z is not the emitted offset form
    ("2026-10-16T10:00-04:00", "1H"),              # no seconds
    ("20261016", "1D"),                            # compact date
    ("2026-13-01", "1W"),                          # not a date
    ("", "1D"),
    ("abc", "1H"),
])
def test_any_other_label_shape_is_refused(label, tf):
    with pytest.raises(ValueError):
        parse_bucket_label(label, tf)


def test_parse_refuses_an_unknown_timeframe():
    with pytest.raises(ValueError):
        parse_bucket_label("2026-10-16", "15m")


# --- fill_flat: no holes between the first candle and now -----------------------

def _live(at, equity, row_id=0):
    return _row(at, equity, row_id=row_id)


def test_a_quiet_hour_gets_a_flat_candle_at_the_previous_close():
    rows = [_live(_utc(2026, 10, 16, 6, 10), 10000.0, 1), _live(_utc(2026, 10, 16, 9, 5), 10100.0, 2)]
    candles = fill_flat(mtm_candles(rows, "1H"), "1H", _utc(2026, 10, 16, 9, 30))
    assert [c["t"][11:16] for c in candles] == ["08:00", "09:00", "10:00", "11:00"]
    flat = candles[1]
    assert (flat["o"], flat["h"], flat["l"], flat["c"], flat["change"]) == (10000.0,) * 4 + (0.0,)
    assert flat["change_pct"] == 0.0 and flat["samples"] == 0 and not flat["approx"]
    assert candles[3]["change"] == 100.0                                # real candle vs the same close


def test_the_series_runs_on_flat_to_the_slot_holding_now_but_never_beyond():
    rows = [_live(_utc(2026, 10, 16, 6, 10), 10000.0, 1)]
    candles = fill_flat(mtm_candles(rows, "1H"), "1H", _utc(2026, 10, 16, 10, 30))   # 12:30 Berlin
    assert candles[-1]["t"] == "2026-10-16T12:00:00+02:00"


def test_nights_and_weekends_have_no_candles_for_any_timeframe():
    rows = [_live(_utc(2026, 10, 16, 19, 0), 10000.0, 1)]                  # Fri 21:00 Berlin
    hourly = fill_flat(mtm_candles(rows, "1H"), "1H", _utc(2026, 10, 19, 6, 30))  # Mon 08:30
    assert [c["t"] for c in hourly] == ["2026-10-16T21:00:00+02:00", "2026-10-19T08:00:00+02:00"]
    four = fill_flat(mtm_candles(rows, "4H"), "4H", _utc(2026, 10, 19, 11))
    assert [c["t"][5:16] for c in four] == ["10-16T20:00", "10-19T08:00", "10-19T12:00"]
    daily = fill_flat(mtm_candles(rows, "1D"), "1D", _utc(2026, 10, 21, 12))
    assert [c["t"] for c in daily] == ["2026-10-16", "2026-10-19", "2026-10-20", "2026-10-21"]
    weekly = fill_flat(mtm_candles(rows, "1W"), "1W", _utc(2026, 10, 28, 12))
    assert [c["t"] for c in weekly] == ["2026-10-12", "2026-10-19", "2026-10-26"]


def test_now_on_a_weekend_or_at_night_adds_no_future_slot():
    rows = [_live(_utc(2026, 10, 16, 10, 0), 10000.0, 1)]                  # Fri 12:00 Berlin
    sat = fill_flat(mtm_candles(rows, "1H"), "1H", _utc(2026, 10, 17, 12))
    assert sat[-1]["t"] == "2026-10-16T21:00:00+02:00"
    daily = fill_flat(mtm_candles(rows, "1D"), "1D", _utc(2026, 10, 17, 12))
    assert [c["t"] for c in daily] == ["2026-10-16"]


def test_fill_flat_of_nothing_is_nothing_and_realized_candles_fill_too():
    assert fill_flat([], "1D", _utc(2026, 10, 16, 10)) == []
    legs = [RealizedLeg(at=_utc(2026, 10, 14, 10), amount=Decimal("50"), trade_id="1")]
    daily = fill_flat(realized_candles(legs, Decimal("10000"), "1D"), "1D", _utc(2026, 10, 16, 10))
    assert [(c["t"], c["c"], c["change"]) for c in daily] == [
        ("2026-10-14", 10050.0, 50.0), ("2026-10-15", 10050.0, 0.0), ("2026-10-16", 10050.0, 0.0)]


def test_a_zero_balance_flat_candle_has_no_percentage():
    assert fill_flat([{"t": "2026-10-14", "o": 0.0, "h": 0.0, "l": 0.0, "c": 0.0, "change": 0.0,
                       "change_pct": None, "samples": 1, "skipped": 0, "approx": False}],
                     "1D", _utc(2026, 10, 15, 10))[1]["change_pct"] is None
