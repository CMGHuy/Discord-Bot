"""Dual-stage comparisons suppress representation noise, not real changes."""
import datetime as dt
import logging
from decimal import Decimal

from swingbot.core.db import dual


def test_identical_records_differ_in_nothing():
    record = {"trade_id": "T1", "entry": 1.5, "notes": {"a": 1}}
    assert dual.diff_records(record, dict(record)) == []


def test_decimal_and_float_are_the_same_number():
    assert dual.diff_records({"entry": 1.5}, {"entry": Decimal("1.50")}) == []


def test_datetime_and_iso_string_are_the_same_instant():
    when = dt.datetime(2026, 1, 2, 15, 0, tzinfo=dt.timezone.utc)
    assert dual.diff_records({"opened_at": when.isoformat()}, {"opened_at": when}) == []


def test_tuple_and_list_match_after_a_jsonb_round_trip():
    assert dual.diff_records({"legs": (1, 2)}, {"legs": [1, 2]}) == []


def test_real_and_missing_value_differences_are_reported():
    assert dual.diff_records({"entry": 1.5}, {"entry": 1.6}) == ["entry"]
    assert dual.diff_records({"a": 1, "b": 2}, {"a": 1}) == ["b"]
    assert dual.diff_records({"a": 1}, {"a": 1, "b": 2}) == ["b"]


def test_a_none_value_and_an_absent_key_are_the_same_unset_state():
    assert dual.diff_records({"closed_at": None}, {}) == []
    assert dual.diff_records({}, {"closed_at": None}) == []


def test_nested_differences_are_reported_by_top_level_field():
    assert dual.diff_records({"notes": {"a": 1}}, {"notes": {"a": 2}}) == ["notes"]


def test_float_comparison_tolerates_round_trip_precision():
    assert dual.diff_records({"entry": 0.1 + 0.2}, {"entry": 0.3}) == []
    assert dual.diff_records({"entry": 1.0}, {"entry": 1.000001}) == ["entry"]


def test_compare_and_log_reports_differences(caplog):
    with caplog.at_level(logging.WARNING):
        actual = dual.compare_and_log("trades", "T1", {"entry": 1.5}, {"entry": 1.6})
    assert actual == ["entry"]
    assert all(text in caplog.text for text in ("trades", "T1", "entry"))


def test_compare_and_log_is_quiet_for_a_match(caplog):
    with caplog.at_level(logging.WARNING):
        assert dual.compare_and_log("trades", "T1", {"a": 1}, {"a": 1}) == []
    assert caplog.text == ""


def test_missing_db_record_is_reported_not_raised(caplog):
    with caplog.at_level(logging.WARNING):
        actual = dual.compare_and_log("trades", "T1", {"a": 1}, None)
    assert actual == [dual.MISSING]
    assert "T1" in caplog.text


def test_comparison_never_raises_for_an_unusual_value(caplog):
    class Weird:
        def __eq__(self, other):
            raise RuntimeError("boom")

        def __hash__(self):
            return 0

    with caplog.at_level(logging.WARNING):
        actual = dual.compare_and_log("trades", "T1", {"x": Weird()}, {"x": 1})
    assert actual == ["x"]
