"""The import verifier guards the one-shot migration of irreplaceable data."""
import datetime as dt

import pytest

from scripts.db.import_common import compare, record_checksum


def test_checksum_is_key_order_independent_but_type_sensitive():
    assert record_checksum({"a": 1, "b": 2}) == record_checksum({"b": 2, "a": 1})
    assert record_checksum({"a": 1}) != record_checksum({"a": "1"})
    assert record_checksum({"t": dt.datetime(2026, 1, 2)})


def test_compare_reports_clean_matching_rows():
    rows = [{"trade_id": "T1", "a": 1}, {"trade_id": "T2", "a": 2}]
    report = compare(rows, list(rows), key="trade_id")
    assert report.ok and report.source_count == report.imported_count == 2


def test_compare_names_missing_extra_and_changed_rows():
    report = compare([{"trade_id": "T1"}, {"trade_id": "T2", "a": 1}],
                     [{"trade_id": "T2", "a": 2}, {"trade_id": "T9"}], key="trade_id")
    assert report.missing == ["T1"]
    assert report.extra == ["T9"]
    assert report.mismatched == ["T2"]
    assert not report.ok
    assert all(value in report.render() for value in ("T1", "T2", "T9", "MISMATCH"))


def test_compare_rejects_duplicate_source_keys():
    with pytest.raises(ValueError, match="duplicate"):
        compare([{"trade_id": "T1"}, {"trade_id": "T1"}], [], key="trade_id")
