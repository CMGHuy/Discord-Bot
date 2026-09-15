"""The flat-record codec used by the staged PostgreSQL migration."""
import pytest

from swingbot.core.db.codec import ReservedKeyError, merge_doc, split_doc


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
