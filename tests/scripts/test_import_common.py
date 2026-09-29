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


def test_every_run_import_name_is_a_parity_store():
    """run_import delegates verification by name, so the names must match."""
    import importlib
    from scripts.db.parity_report import STORES
    for module_name, expected in [
        ("import_watchlist", "watchlist"), ("import_state", "state"),
        ("import_plans", "plans"), ("import_starred", "starred_plans"),
        ("import_trades", "trades"), ("import_journal", "journal"),
    ]:
        importlib.import_module(f"scripts.db.{module_name}")
        assert expected in STORES, f"{module_name} verifies against a missing store"


def test_parity_accepts_a_source_override():
    """run_import --source must verify against the file it actually imported."""
    import inspect

    from scripts.db.parity_report import parity
    assert "source_path" in inspect.signature(parity).parameters


def test_run_import_verdict_comes_from_parity(monkeypatch):
    """A store whose parity is OK must not be reported FAILED by run_import."""
    import scripts.db.import_common as mod
    from scripts.db.import_common import ImportReport

    monkeypatch.setattr(mod, "parity",
                        lambda name, source_path=None: ImportReport(
                            source_count=3, imported_count=3))

    class FakeRepo:
        def count(self):
            return 0

    rc = mod.run_import([], load_source=lambda p: [{"k": 1}, {"k": 2}, {"k": 3}],
                        write_one=lambda repo, rec: None, repo=FakeRepo(),
                        key="k", name="watchlist")
    assert rc == 0


def test_run_import_fails_when_parity_fails(monkeypatch):
    import scripts.db.import_common as mod
    from scripts.db.import_common import ImportReport

    monkeypatch.setattr(mod, "parity",
                        lambda name, source_path=None: ImportReport(
                            source_count=3, imported_count=2, missing=["c"]))

    class FakeRepo:
        def count(self):
            return 0

    rc = mod.run_import([], load_source=lambda p: [{"k": 1}],
                        write_one=lambda repo, rec: None, repo=FakeRepo(),
                        key="k", name="watchlist")
    assert rc == 1
