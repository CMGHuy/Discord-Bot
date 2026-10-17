"""v172 § 4: equity candles from raw samples and realized legs.

New York wall clock throughout. 2026 DST: spring forward Sun 8 March (02:00
EST -> 03:00 EDT), fall back Sun 1 November (02:00 EDT -> 01:00 EST).
"""
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from swingbot.core.tracking.equity import RealizedLeg
from swingbot.core.tracking.equity_candles import (
    TIMEFRAMES, add_change, bucket_label, bucket_start, mtm_candles, realized_candles)

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


def test_the_day_turns_at_new_york_midnight_not_utc():
    assert _label(_utc(2026, 10, 17, 3, 59), "1D") == "2026-10-16"     # 23:59 New York
    assert _label(_utc(2026, 10, 17, 4, 1), "1D") == "2026-10-17"      # 00:01 New York


def test_hour_labels_carry_the_new_york_offset():
    assert _label(_utc(2026, 10, 16, 14, 35), "1H") == "2026-10-16T10:00:00-04:00"
    assert _label(_utc(2026, 10, 16, 14, 35), "4H") == "2026-10-16T08:00:00-04:00"


def test_the_week_starts_on_monday():
    assert _label(_utc(2026, 10, 18, 15), "1W") == "2026-10-12"        # Sunday
    assert _label(_utc(2026, 10, 19, 15), "1W") == "2026-10-19"        # Monday


def test_4h_bucket_is_three_real_hours_on_spring_forward_day():
    first = bucket_start(_utc(2026, 3, 8, 7, 30), "4H")                # 03:30 EDT
    assert first == bucket_start(_utc(2026, 3, 8, 5, 30), "4H")        # 00:30 EST, same bucket
    assert first.astimezone(UTC) == _utc(2026, 3, 8, 5)                # 00:00 EST
    second = bucket_start(_utc(2026, 3, 8, 8, 0), "4H")                # 04:00 EDT
    assert (second.astimezone(UTC) - first.astimezone(UTC)).total_seconds() == 3 * 3600   # same-zone subtraction is wall-clock


def test_4h_bucket_is_five_real_hours_on_fall_back_day():
    first = bucket_start(_utc(2026, 11, 1, 8, 30), "4H")               # 03:30 EST
    assert first.astimezone(UTC) == _utc(2026, 11, 1, 4)               # 00:00 EDT
    second = bucket_start(_utc(2026, 11, 1, 9, 0), "4H")               # 04:00 EST
    assert (second.astimezone(UTC) - first.astimezone(UTC)).total_seconds() == 5 * 3600   # same-zone subtraction is wall-clock


def test_the_repeated_hour_on_fall_back_day_is_two_1h_buckets():
    assert _label(_utc(2026, 11, 1, 5, 30), "1H") == "2026-11-01T01:00:00-04:00"
    assert _label(_utc(2026, 11, 1, 6, 30), "1H") == "2026-11-01T01:00:00-05:00"


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
    assert [c["t"] for c in candles] == ["2026-10-16T10:00:00-04:00", "2026-10-16T11:00:00-04:00",
                                         "2026-10-16T15:00:00-04:00"]
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
