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


def test_checksum_treats_nan_as_null():
    """Source holds NaN; the database holds null. Parity must call that equal."""
    assert record_checksum({"k": "a", "v": float("nan")}) ==            record_checksum({"k": "a", "v": None})


def test_negative_zero_and_zero_have_the_same_checksum():
    """JSONB returns 0.0 for a stored -0.0; parity must not call that a loss."""
    from scripts.db.import_common import record_checksum
    source = {"id": "a", "r": -0.0, "legs": [{"r": -0.0}], "gate": {"x": [-0.0]}}
    stored = {"id": "a", "r": 0.0, "legs": [{"r": 0.0}], "gate": {"x": [0.0]}}
    assert record_checksum(source) == record_checksum(stored)


def test_a_real_difference_still_changes_the_checksum():
    from scripts.db.import_common import record_checksum
    assert record_checksum({"r": 0.0}) != record_checksum({"r": 0.1})
    assert record_checksum({"r": 0}) != record_checksum({"r": None})


def test_watchlist_prune_removes_only_tickers_the_source_dropped():
    """An upsert never deletes, so GC=F would outlive the XAUUSD rename."""
    from scripts.db.import_watchlist import prune

    class FakeRepo:
        def __init__(self):
            self.rows = ["AAPL", "GC=F", "SI=F", "XAUUSD"]

        def tickers(self):
            return sorted(self.rows)

        def remove(self, ticker):
            self.rows.remove(ticker)

    repo = FakeRepo()
    n = prune(repo, [{"ticker": "AAPL"}, {"ticker": "XAUUSD"}])
    assert n == 2 and repo.rows == ["AAPL", "XAUUSD"]


def test_run_import_calls_prune_after_writes_but_not_on_dry_run(monkeypatch):
    import scripts.db.import_common as mod
    from scripts.db.import_common import ImportReport

    monkeypatch.setattr(mod, "parity", lambda name, source_path=None: ImportReport(
        source_count=1, imported_count=1))
    calls = []

    class FakeRepo:
        def count(self):
            return 0

    kw = dict(load_source=lambda p: [{"k": 1}], write_one=lambda r, rec: calls.append("w"),
              repo=FakeRepo(), key="k", name="watchlist",
              prune=lambda r, s: calls.append("p") or 0)
    assert mod.run_import(["--dry-run"], **kw) == 0 and calls == []
    assert mod.run_import([], **kw) == 0 and calls == ["w", "p"]
