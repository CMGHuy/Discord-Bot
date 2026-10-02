"""The flat-record codec used by the staged PostgreSQL migration."""
import pytest

import datetime as dt
from decimal import Decimal

from swingbot.core.db.codec import ReservedKeyError, merge_doc, normalise, split_doc


PROMOTED = ("trade_id", "ticker", "status", "closed_at")


def test_split_sends_promoted_fields_to_columns_and_the_rest_to_doc():
    columns, doc = split_doc(
        {"trade_id": "T1", "ticker": "AAPL", "status": "open",
         "confidence": 4, "notes": {"why": "breakout"}},
        PROMOTED,
    )
    assert columns == {"trade_id": "T1", "ticker": "AAPL", "status": "open"}
    assert doc == {"confidence": 4, "notes": {"why": "breakout"}}


def test_split_leaves_missing_promoted_fields_absent():
    columns, doc = split_doc({"trade_id": "T1"}, PROMOTED)
    assert columns == {"trade_id": "T1"}
    assert doc == {}


@pytest.mark.parametrize("key", ["id", "doc", "updated_at"])
def test_split_rejects_reserved_infrastructure_keys(key):
    with pytest.raises(ReservedKeyError, match=key):
        split_doc({"trade_id": "T1", key: "x"}, PROMOTED)


def test_merge_rebuilds_the_flat_contract_and_omits_null_columns():
    row = {"id": 7, "trade_id": "T1", "ticker": "AAPL", "status": "open",
           "closed_at": None, "doc": {"confidence": 4}, "updated_at": "2026-01-01"}
    assert merge_doc(row, PROMOTED) == {
        "trade_id": "T1", "ticker": "AAPL", "status": "open", "confidence": 4,
    }


def test_merge_tolerates_a_null_doc_and_a_column_wins_over_a_stale_doc_copy():
    assert merge_doc({"trade_id": "T1", "doc": None}, PROMOTED) == {"trade_id": "T1"}
    row = {"trade_id": "T1", "status": "closed", "doc": {"status": "open"}}
    assert merge_doc(row, PROMOTED)["status"] == "closed"


@pytest.mark.parametrize("record", [
    {"trade_id": "T1", "ticker": "AAPL", "confidence": 4, "legs": [1, 2]},
    {"trade_id": "T2", "nested": {"a": {"b": [1, {"c": None}]}}},
    {"trade_id": "T3"},
])
def test_round_trip_is_lossless(record):
    columns, doc = split_doc(record, PROMOTED)
    row = {**columns, "id": 1, "doc": doc, "updated_at": "2026-01-01"}
    assert merge_doc(row, PROMOTED) == record


def test_nan_in_a_document_field_becomes_none():
    """Bare NaN is not valid JSON and JSONB rejects it outright."""
    _, doc = split_doc({"trade_id": "t1", "mfe_r": float("nan")}, ["trade_id"])
    assert doc["mfe_r"] is None


def test_infinity_in_a_document_field_becomes_none():
    _, doc = split_doc({"trade_id": "t1", "r": float("inf")}, ["trade_id"])
    assert doc["r"] is None


def test_nan_nested_in_a_list_of_dicts_becomes_none():
    """legs_realized and status_history are lists of dicts; NaN hides in there."""
    _, doc = split_doc(
        {"trade_id": "t1", "legs": [{"r": float("nan"), "fraction": 0.5}]},
        ["trade_id"])
    assert doc["legs"][0]["r"] is None
    assert doc["legs"][0]["fraction"] == 0.5


def test_nan_in_a_promoted_column_becomes_none():
    columns, _ = split_doc({"trade_id": "t1", "entry": float("nan")},
                           ["trade_id", "entry"])
    assert columns["entry"] is None


def test_finite_values_are_untouched():
    columns, doc = split_doc(
        {"trade_id": "t1", "entry": 152.36, "n": 0, "flag": False, "s": "x"},
        ["trade_id", "entry"])
    assert columns["entry"] == 152.36
    assert doc == {"n": 0, "flag": False, "s": "x"}


def test_sanitise_leaves_bools_and_ints_alone():
    """bool is a subclass of int, not float -- it must not be coerced."""
    from swingbot.core.db.codec import sanitise_non_finite
    assert sanitise_non_finite({"a": True, "b": 3}) == {"a": True, "b": 3}


def test_normalise_turns_a_decimal_into_a_float():
    assert normalise(Decimal("1.5")) == 1.5
    assert isinstance(normalise(Decimal("1.5")), float)


def test_normalise_turns_a_datetime_into_its_isoformat():
    when = dt.datetime(2026, 1, 2, 15, 0, tzinfo=dt.timezone.utc)
    assert normalise(when) == when.isoformat()


def test_normalise_recurses_through_dicts_and_lists():
    when = dt.datetime(2026, 1, 2, 15, 0, tzinfo=dt.timezone.utc)
    value = {"legs": [{"r": Decimal("2.5"), "at": when}], "t": (Decimal("1"), 3)}
    assert normalise(value) == {"legs": [{"r": 2.5, "at": when.isoformat()}], "t": [1.0, 3]}
