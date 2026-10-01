"""export_json for the five ephemeral ops stores (v116). Proven by reading
each exported file back through the store's own JSON-stage reader."""
import json

from swingbot import config
from scripts.db import export_json
from swingbot.commands.scanning import runstate
from swingbot.core.db.repositories.flags import flags_repo
from swingbot.core.db.repositories.heartbeat import heartbeat_repo
from swingbot.core.db.repositories.market_data_state import market_data_state_repo
from swingbot.core.db.repositories.notify_queue import NotifyQueueRepository
from swingbot.core.db.repositories.scan_progress import scan_progress_repo
from swingbot.core.marketdata import data_refresh
from swingbot.core.scanning import progress_store

STATE = {"AAPL|daily": {"last_status": "failed", "fail_count": 1, "last_error": "x"}}
PROGRESS = {"at": "2026-10-01T10:00:00+00:00", "pct": 50, "stage": "analyzing"}


def _seed():
    flags_repo().set("scan_paused")
    heartbeat_repo().beat({"session_active": True, "consecutive_failures": 2})
    queue = NotifyQueueRepository()
    queue.enqueue({"trade_id": "T1"})
    queue.enqueue({"trade_id": "T2"})
    scan_progress_repo().publish(PROGRESS)
    market_data_state_repo().save(STATE)


def test_every_ops_store_exports_and_reads_back_at_the_json_stage(store_db, tmp_path, monkeypatch):
    _seed()
    (tmp_path / "trigger_check.flag").write_text("stale")
    names = ["flags", "heartbeat", "notify_queue", "scan_progress", "market_data_state"]
    results = export_json.run_export(names, str(tmp_path), dry_run=False, force=False)
    assert {r.name: r.status for r in results} == {name: "written" for name in names}

    monkeypatch.setattr(config, "DB_STORES", "")
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(runstate, "_PAUSE_FILE", str(tmp_path / "scan_paused.flag"))
    monkeypatch.setattr(runstate, "_TRIGGER_FILE", str(tmp_path / "trigger_check.flag"))
    monkeypatch.setattr(runstate, "_HEARTBEAT_FILE", str(tmp_path / "bot_heartbeat.json"))
    monkeypatch.setattr(data_refresh, "STATE_FILE", str(tmp_path / "market_data_state.json"))
    assert runstate.is_scan_paused() is True
    assert runstate.is_trigger_requested() is False        # the stale flag was removed
    assert runstate._read_heartbeat()["consecutive_failures"] == 2
    queued = json.loads((tmp_path / "manual_close_notify.json").read_text())
    assert [r["trade_id"] for r in queued] == ["T1", "T2"]
    assert all("queued_at" not in r for r in queued)
    assert progress_store.read() == PROGRESS
    assert data_refresh.load_state() == STATE


def test_exporting_the_queue_does_not_drain_it(store_db, tmp_path):
    _seed()
    export_json.run_export(["notify_queue"], str(tmp_path), dry_run=False, force=False)
    assert NotifyQueueRepository().pending() == 2


def test_no_scan_in_progress_removes_the_progress_file(store_db, tmp_path):
    (tmp_path / "scan_progress.json").write_text(json.dumps(PROGRESS))
    export_json.run_export(["scan_progress"], str(tmp_path), dry_run=False, force=False)
    assert not (tmp_path / "scan_progress.json").exists()


def test_the_ops_stores_are_exportable_names():
    assert {"flags", "heartbeat", "notify_queue", "scan_progress",
            "market_data_state"} <= set(export_json.exportable_names())
