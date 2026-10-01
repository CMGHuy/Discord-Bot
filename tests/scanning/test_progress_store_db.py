"""progress_store is a table (v116). The record stays a display artefact:
nothing may raise into the scan or the admin."""
import pytest

from swingbot import config
from swingbot.core.db.repositories.scan_progress import ScanProgressRepository
from swingbot.core.scanning import progress_store
from swingbot.core.scanning.scan_run import ScanProgress


def _progress() -> ScanProgress:
    progress = ScanProgress()
    progress.stage, progress.total, progress.done = "analyzing", 10, 5
    return progress


def test_publish_read_and_clear_use_the_row(store_db):
    progress_store.publish(_progress())
    assert ScanProgressRepository().read(conn=store_db)["pct"] == 66
    assert progress_store.read()["stage"] == "analyzing"
    progress_store.clear()
    assert ScanProgressRepository().read(conn=store_db) is None
    assert progress_store.read() is None


@pytest.mark.real_engine
def test_an_unreachable_database_never_raises(monkeypatch):
    from swingbot.core.db.engine import reset_engine
    monkeypatch.setattr(config, "DATABASE_URL", "postgresql+psycopg://x:y@127.0.0.1:1/none")
    reset_engine()
    try:
        progress_store.publish(_progress())
        assert progress_store.read() is None
        progress_store.clear()
    finally:
        reset_engine()
