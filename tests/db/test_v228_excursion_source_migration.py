"""v228_001: stamp excursion_source = "daily" on every journal entry that has
an mfe_r and no source, once. The downgrade is a deliberate no-op: stripping
the field would also strip intraday sources written after the upgrade."""
from __future__ import annotations

import importlib.util
import logging
import pathlib
import sys

import pytest
import sqlalchemy as sa
from alembic.command import downgrade, upgrade
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

from swingbot.core.db.repositories.journal import JournalRepository

REPO = pathlib.Path(__file__).resolve().parents[2]
REVISION_FILE = (REPO / "swingbot" / "core" / "db" / "migrations" / "versions"
                 / "v228_001_excursion_source.py")
PREVIOUS_HEAD = "v208_001"   # `python -m alembic heads` when V228-7 ran

sys.path.insert(0, str(REPO / "scripts" / "ops"))
import rollback_migrations as rm  # noqa: E402


def _load_revision():
    spec = importlib.util.spec_from_file_location("v228_001_excursion_source", REVISION_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MIG = _load_revision()


@pytest.fixture
def journal_conn(db_conn):
    db_conn.execute(sa.text("DELETE FROM journal_entries"))   # rolled back with the fixture
    return db_conn


def _entry(conn, trade_id, **doc):
    record = {"trade_id": trade_id, "strategy": "S/R Confluence", "outcome": "loss",
              "closed_at": "2026-10-14T15:00:00+00:00",
              "created_at": "2026-10-14T15:00:01+00:00",
              "mfe_r": 1.24, "mae_r": 1.0, "exit_efficiency": -0.8065,
              "tags": ["near-miss-tp"], "note": "", "holding_days": 0.2}
    record.update(doc)
    JournalRepository().upsert(record, conn=conn)


def _drop_key(conn, trade_id, key):
    conn.execute(sa.text("UPDATE journal_entries SET doc = doc - :key WHERE trade_id = :tid"),
                 {"key": key, "tid": trade_id})


def _row(conn, trade_id):
    return JournalRepository().get(trade_id, conn=conn)



def test_a_row_with_mfe_and_no_source_is_stamped_daily(journal_conn):
    _entry(journal_conn, "T1")
    assert MIG.stamp(journal_conn) == 1
    assert _row(journal_conn, "T1")["excursion_source"] == "daily"


def test_an_explicit_null_mfe_stays_unlabelled(journal_conn):
    """No bars at close: build_entry wrote mfe_r = null. A later upgrade can
    still give it an intraday source, so the revision must not call it daily."""
    _entry(journal_conn, "T-null", mfe_r=None, mae_r=None, exit_efficiency=None)
    assert MIG.stamp(journal_conn) == 0
    assert "excursion_source" not in _row(journal_conn, "T-null")


def test_a_row_without_an_mfe_key_stays_unlabelled(journal_conn):
    _entry(journal_conn, "T-nokey")
    _drop_key(journal_conn, "T-nokey", "mfe_r")
    assert MIG.stamp(journal_conn) == 0
    assert "excursion_source" not in _row(journal_conn, "T-nokey")


@pytest.mark.parametrize("source", ["5min", "15min", "hourly", "daily"])
def test_a_row_that_already_names_its_source_is_left_alone(journal_conn, source):
    _entry(journal_conn, "T-src", excursion_source=source)
    assert MIG.stamp(journal_conn) == 0
    assert _row(journal_conn, "T-src")["excursion_source"] == source


def test_the_stamp_touches_no_other_field(journal_conn):
    _entry(journal_conn, "T1", note="Should have trailed further.")
    before = _row(journal_conn, "T1")
    MIG.stamp(journal_conn)
    after = _row(journal_conn, "T1")
    changed = {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
    assert changed <= {"excursion_source", "updated_at"}
    assert after["note"] == "Should have trailed further."
    assert after["mfe_r"] == 1.24 and after["tags"] == ["near-miss-tp"]


def test_the_stamp_is_idempotent(journal_conn):
    _entry(journal_conn, "T1")
    _entry(journal_conn, "T2")
    assert MIG.stamp(journal_conn) == 2
    assert MIG.stamp(journal_conn) == 0


def test_an_empty_journal_stamps_nothing(journal_conn):
    assert MIG.stamp(journal_conn) == 0



def test_upgrade_logs_the_count_and_downgrade_leaves_stamped_rows(journal_conn, caplog):
    _entry(journal_conn, "T1")
    _entry(journal_conn, "T2", mfe_r=None)
    with Operations.context(MigrationContext.configure(journal_conn)):
        with caplog.at_level(logging.INFO, logger="alembic.runtime.migration"):
            MIG.upgrade()
        assert _row(journal_conn, "T1")["excursion_source"] == "daily"
        MIG.downgrade()
    assert _row(journal_conn, "T1")["excursion_source"] == "daily"
    assert "excursion_source" not in _row(journal_conn, "T2")
    assert "v228_001: stamped 1 journal entry row(s) excursion_source=daily" in caplog.text


def test_downgrade_keeps_an_intraday_source_written_after_the_upgrade(journal_conn):
    """The reason the downgrade is a no-op: a later pass wrote 5min."""
    _entry(journal_conn, "T1")
    with Operations.context(MigrationContext.configure(journal_conn)):
        MIG.upgrade()
        JournalRepository().patch("T1", {"excursion_source": "5min", "mfe_r": 0.31},
                                  conn=journal_conn)
        MIG.downgrade()
    row = _row(journal_conn, "T1")
    assert row["excursion_source"] == "5min" and row["mfe_r"] == 0.31



def test_the_revision_is_rollback_safe_by_its_stated_reason():
    verdict = rm.scan_upgrade(REVISION_FILE.read_text(encoding="utf-8"),
                              revision="v228_001", path=str(REVISION_FILE))
    assert verdict.safe is True
    assert verdict.override is not None and "excursion_source" in verdict.override
    assert "reviewed" not in verdict.override.lower()


def test_v228_001_sits_on_the_previous_head_and_keeps_one_head():
    scripts = ScriptDirectory.from_config(Config(str(REPO / "alembic.ini")))
    assert MIG.revision == "v228_001"
    assert scripts.get_revision("v228_001").down_revision == PREVIOUS_HEAD
    heads = scripts.get_heads()
    assert len(heads) == 1
    assert "v228_001" in {r.revision for r in scripts.iterate_revisions(heads[0], "base")}


def test_the_revision_runs_up_down_and_up_again(db_engine_empty):
    cfg = Config(str(REPO / "alembic.ini"))
    with db_engine_empty.begin() as connection:
        cfg.attributes["connection"] = connection
        upgrade(cfg, "head")
        downgrade(cfg, MIG.down_revision)
        upgrade(cfg, "head")
