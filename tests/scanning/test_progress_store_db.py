"""progress_store at each stage (v116 Phase 1). The record stays a display
artefact: no stage may raise into the scan or the admin."""
import os

import pytest

from swingbot import config
from swingbot.core.db.repositories.scan_progress import ScanProgressRepository
from swingbot.core.scanning import progress_store
from swingbot.core.scanning.scan_run import ScanProgress


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    return tmp_path


def _progress() -> ScanProgress:
    progress = ScanProgress()
    progress.stage, progress.total, progress.done = "analyzing", 10, 5
    return progress


def test_json_stage_writes_only_the_file(data_dir, monkeypatch):
    monkeypatch.setattr(config, "DB_STORES", "")
    progress_store.publish(_progress())
    assert os.path.exists(data_dir / "scan_progress.json")
    assert progress_store.read()["pct"] == 66


def test_dual_writes_both_and_reads_the_file(data_dir, store_db, monkeypatch):
    monkeypatch.setattr(config, "DB_STORES", "scan_progress:dual")
    progress_store.publish(_progress())
    assert os.path.exists(data_dir / "scan_progress.json")
    assert ScanProgressRepository().read(conn=store_db)["pct"] == 66
    progress_store.clear()
    assert ScanProgressRepository().read(conn=store_db) is None
    assert not os.path.exists(data_dir / "scan_progress.json")


def test_db_stage_writes_and_reads_only_the_row(data_dir, store_db, monkeypatch):
    monkeypatch.setattr(config, "DB_STORES", "scan_progress:db")
    progress_store.publish(_progress())
    assert not os.path.exists(data_dir / "scan_progress.json")
    assert progress_store.read()["stage"] == "analyzing"
    progress_store.clear()
    assert progress_store.read() is None


def test_an_unreachable_database_never_raises(data_dir, monkeypatch):
    from swingbot.core.db.engine import reset_engine
    monkeypatch.setattr(config, "DB_STORES", "scan_progress:db")
    monkeypatch.setattr(config, "DATABASE_URL", "postgresql+psycopg://x:y@127.0.0.1:1/none")
    reset_engine()
    try:
        progress_store.publish(_progress())
        assert progress_store.read() is None
        progress_store.clear()
    finally:
        reset_engine()
