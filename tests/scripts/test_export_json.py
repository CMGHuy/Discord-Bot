"""export_json is the inverse of the import_*.py scripts (v67 rollback path).

No database: Repository.upsert/get/list_all are replaced with an in-memory
table that runs the real split_doc/merge_doc and turns TIMESTAMP columns into
aware datetimes, so the real importers' load_source/write_one run unchanged
and the export sees what a Postgres read would hand it.
"""
import datetime as dt
import json
import os

import pytest
import sqlalchemy as sa

from scripts.db import (export_json, import_account, import_common, import_journal,
                        import_plans, import_starred, import_state, import_trades,
                        import_watchlist)
from scripts.db.parity_report import STORES
from swingbot.core.db.codec import merge_doc, split_doc
from swingbot.core.db.repositories.base import Repository


@pytest.fixture
def fake_db(monkeypatch):
    """In-memory stand-in for every Repository table. Returns the tables dict."""
    tables: dict[str, dict] = {}

    def _timestamp(column, value):
        if isinstance(column.type, sa.TIMESTAMP) and isinstance(value, str):
            parsed = dt.datetime.fromisoformat(value)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)
        return value

    def upsert(self, record, *, conn=None):
        columns, document = split_doc(record, self.promoted)
        columns = {name: _timestamp(self.table.c[name], value) for name, value in columns.items()}
        row = {**columns, "doc": json.loads(json.dumps(document))}
        tables.setdefault(self.table.name, {})[row[self.key]] = row
        return merge_doc(row, self.promoted)

    def get(self, key_value, *, conn=None):
        row = tables.get(self.table.name, {}).get(key_value)
        return None if row is None else merge_doc(row, self.promoted)

    def list_all(self, *, conn=None, where=None, order_by=None, limit=None):
        # Reversed on purpose: the DB gives no order, so the exporter must sort.
        rows = list(tables.get(self.table.name, {}).values())[::-1]
        return [merge_doc(row, self.promoted) for row in rows]

    monkeypatch.setattr(Repository, "upsert", upsert)
    monkeypatch.setattr(Repository, "get", get)
    monkeypatch.setattr(Repository, "list_all", list_all)
    return tables


def _trade(trade_id, opened_at, **extra):
    return {"id": trade_id, "ticker": "AAPL", "strategy": "RSI", "horizon_key": "2w",
            "direction": "bullish", "status": "CLOSED", "opened_at": opened_at, "closed_at": "2026-02-01T00:00:00+00:00",
            "entry": 100.0, "stop_loss": 95.5, "r_multiple": 1.25, **extra}


TRADES = [_trade("T3", "2026-01-03T10:00:00+00:00"),
          _trade("T1", "2026-01-01T10:00:00+00:00", note="x", tp=[1.5, 2.0]),
          _trade("T2", "2026-01-01T10:00:00+00:00", r_multiple=-1.0)]
PLANS = [{"plan_id": "P2", "ticker": "MSFT", "strategy": "MACD", "horizon_key": "1w",
          "status": "PENDING", "created_at": "2026-01-05T15:30:00+00:00", "levels": {"tp1": 4.5}},
         {"plan_id": "P1", "ticker": "AAPL", "strategy": "RSI", "horizon_key": "2w",
          "status": "PENDING", "created_at": "2026-01-02T15:00:00+00:00"}]
JOURNAL = [{"trade_id": "T2", "strategy": "RSI", "outcome": "loss", "tags": ["late"],
            "closed_at": "2026-01-09T00:00:00+00:00", "created_at": "2026-01-10T00:00:00+00:00"},
           {"trade_id": "T1", "strategy": "RSI", "outcome": "win", "tags": [],
            "closed_at": "2026-01-08T00:00:00+00:00", "created_at": "2026-01-09T00:00:00+00:00"}]
STATE = {"AAPL|RSI|2w": {"last_alert": "2026-01-02", "count": 2}, "MSFT|MACD|1w": {"count": 1}}
WATCHLIST = ["AAPL", "MSFT", "NVDA"]
STARRED = ["P1", "P2"]
ACCOUNT = {"starting_balance": 10000.0, "risk_pct": 1.0,
           "balance_history": [{"ts": "2026-01-01T00:00:00+00:00", "balance": 10000.0},
                               {"ts": "2026-01-02T00:00:00+00:00", "balance": 10125.5},
                               {"ts": "2026-01-03T00:00:00+00:00", "balance": 10050.0}]}

SOURCES = {"trades": TRADES, "plans": PLANS, "journal": JOURNAL, "state": STATE,
           "watchlist": WATCHLIST, "starred_plans": STARRED, "account": ACCOUNT}
IMPORTERS = {"trades": import_trades, "plans": import_plans, "journal": import_journal,
             "state": import_state, "watchlist": import_watchlist,
             "starred_plans": import_starred}


def _write(path, obj):
    path.write_text(json.dumps(obj), encoding="utf-8")
    return str(path)


def _import_store(name, source_path):
    """Run the real importer's load_source/write_one (or account's save)."""
    from swingbot.core.db.repositories.account import AccountRepository
    if name == "account":
        AccountRepository().save(json.loads(open(source_path, encoding="utf-8").read()))
        return
    module = IMPORTERS[name]
    repo = STORES[name].repo_factory()
    for record in module.load_source(source_path):
        module.write_one(repo, record)


@pytest.fixture
def imported(fake_db, tmp_path):
    """Every store imported from SOURCES; returns the source dir."""
    src = tmp_path / "src"
    src.mkdir()
    for name, data in SOURCES.items():
        _import_store(name, _write(src / STORES[name].filename, data))
    return src


def _read(path):
    return json.loads(open(path, encoding="utf-8").read())


def _semantic_rows(name, data):
    spec = STORES[name]
    rows = spec.loader(data) if spec.loader else data
    rows = list(rows.values()) if isinstance(rows, dict) else rows
    return [{k: v for k, v in row.items() if k not in spec.ignore_fields} for row in rows]


@pytest.mark.parametrize("name", ["trades", "plans", "journal", "state", "watchlist", "starred_plans"])
def test_export_round_trips_source_semantically(name, imported, tmp_path):
    out = tmp_path / "out"
    results = export_json.run_export([name], str(out), dry_run=False, force=False)
    exported = _read(out / STORES[name].filename)
    report = import_common.compare(_semantic_rows(name, _read(imported / STORES[name].filename)),
                                   _semantic_rows(name, exported), key=STORES[name].key)
    assert report.ok, report.render()
    assert results[0].count == len(_semantic_rows(name, exported))


def test_export_account_is_config_plus_balance_history(imported, tmp_path):
    out = tmp_path / "out"
    export_json.run_export(["account"], str(out), dry_run=False, force=False)
    assert _read(out / "account.json") == ACCOUNT


def test_shapes_match_the_on_disk_json_types(imported, tmp_path):
    out = tmp_path / "out"
    export_json.run_export(["all"], str(out), dry_run=False, force=False)
    assert isinstance(_read(out / "trades.json"), list)
    assert isinstance(_read(out / "plans.json"), list)
    assert isinstance(_read(out / "journal.json"), list)
    assert isinstance(_read(out / "state.json"), dict)
    assert _read(out / "state.json") == STATE
    assert _read(out / "watchlist.json") == WATCHLIST
    assert _read(out / "starred_plans.json") == STARRED


def test_rows_are_sorted_because_the_db_returns_no_order(imported, tmp_path):
    out = tmp_path / "out"
    export_json.run_export(["all"], str(out), dry_run=False, force=False)
    assert [t["id"] for t in _read(out / "trades.json")] == ["T1", "T2", "T3"]
    assert [p["plan_id"] for p in _read(out / "plans.json")] == ["P1", "P2"]
    assert [j["trade_id"] for j in _read(out / "journal.json")] == ["T1", "T2"]
    assert [h["balance"] for h in _read(out / "account.json")["balance_history"]] == [
        10000.0, 10125.5, 10050.0]


def test_sparse_open_trade_gains_null_keys_only(fake_db, tmp_path):
    sparse = {"id": "T9", "ticker": "AAPL", "strategy": "RSI", "horizon_key": "2w",
              "status": "OPEN", "opened_at": "2026-01-01T10:00:00+00:00"}
    import_trades.write_one(STORES["trades"].repo_factory(), import_trades._db_record(sparse))
    export_json.run_export(["trades"], str(tmp_path), dry_run=False, force=False)
    [row] = _read(tmp_path / "trades.json")
    assert row == {**sparse, "closed_at": None, "entry": None, "stop_loss": None}


def test_nan_is_exported_as_null(fake_db, tmp_path):
    import_trades.write_one(STORES["trades"].repo_factory(),
                            import_trades._db_record(_trade("T1", "2026-01-01T10:00:00+00:00",
                                                            r_multiple=float("nan"))))
    export_json.run_export(["trades"], str(tmp_path), dry_run=False, force=False)
    assert _read(tmp_path / "trades.json")[0]["r_multiple"] is None


def test_dry_run_writes_nothing_but_reports_counts(imported, tmp_path):
    out = tmp_path / "out"
    results = export_json.run_export(["watchlist"], str(out), dry_run=True, force=False)
    assert not out.exists() or not list(out.iterdir())
    assert results[0].count == 3 and results[0].status == "dry-run"
    assert len(results[0].checksum) == 64


def test_identical_existing_file_is_left_alone(imported, tmp_path):
    export_json.run_export(["watchlist"], str(tmp_path), dry_run=False, force=False)
    results = export_json.run_export(["watchlist"], str(tmp_path), dry_run=False, force=False)
    assert results[0].status == "unchanged"
    assert not (tmp_path / "watchlist.exported.json").exists()


def test_differing_existing_file_is_refused_and_sidecar_written(imported, tmp_path):
    target = tmp_path / "watchlist.json"
    target.write_text('["ZZZZ"]', encoding="utf-8")
    results = export_json.run_export(["watchlist"], str(tmp_path), dry_run=False, force=False)
    assert results[0].status == "refused"
    assert _read(target) == ["ZZZZ"]
    assert _read(tmp_path / "watchlist.exported.json") == WATCHLIST


def test_force_overwrites_a_differing_file(imported, tmp_path):
    target = tmp_path / "watchlist.json"
    target.write_text('["ZZZZ"]', encoding="utf-8")
    results = export_json.run_export(["watchlist"], str(tmp_path), dry_run=False, force=True)
    assert results[0].status == "written"
    assert _read(target) == WATCHLIST


def test_main_prints_counts_checksum_and_restart_warning(imported, tmp_path, capsys):
    code = export_json.main(["--store", "watchlist", "--out-dir", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert "watchlist" in out and "3 record" in out
    assert "RESTART" in out


def test_main_exits_nonzero_when_a_store_was_refused(imported, tmp_path):
    (tmp_path / "watchlist.json").write_text("[]", encoding="utf-8")
    assert export_json.main(["--store", "watchlist", "--out-dir", str(tmp_path)]) == 1


def test_main_rejects_unknown_store(tmp_path):
    with pytest.raises(SystemExit):
        export_json.main(["--store", "nope", "--out-dir", str(tmp_path)])


def test_default_out_dir_is_config_data_dir(imported, tmp_path, monkeypatch):
    monkeypatch.setattr(export_json.config, "DATA_DIR", str(tmp_path))
    export_json.main(["--store", "starred_plans"])
    assert os.path.exists(tmp_path / "starred_plans.json")
