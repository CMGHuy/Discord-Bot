"""The audit log: append-only, newest first, never lossy."""
import os

import pytest

from swingbot import config
from swingbot.admin import helpers
from swingbot.core.db.repositories.settings_audit import SettingsAuditRepository


@pytest.fixture(params=["", "settings_audit:dual", "settings_audit:db"])
def any_stage(request, tmp_path, monkeypatch, db_committed):
    from swingbot.core.db.engine import reset_engine
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_STORES", request.param)
    monkeypatch.setattr(
        config, "DATABASE_URL",
        db_committed.engine.url.render_as_string(hide_password=False))
    reset_engine()
    yield request.param
    reset_engine()


DIFF = [{"key": "MIN_ALERT_CONFIDENCE_LEVEL", "old": "3", "new": "4"}]


def test_an_empty_diff_writes_nothing(any_stage):
    helpers.append_settings_audit([])
    assert helpers.read_settings_audit() == []


def test_append_then_read(any_stage):
    helpers.append_settings_audit(DIFF)
    rows = helpers.read_settings_audit()
    assert len(rows) == 1
    assert rows[0]["changes"][0]["key"] == "MIN_ALERT_CONFIDENCE_LEVEL"


def test_entries_are_newest_first(any_stage):
    helpers.append_settings_audit([{"key": "A", "old": "1", "new": "2"}])
    helpers.append_settings_audit([{"key": "B", "old": "1", "new": "2"}])
    rows = helpers.read_settings_audit()
    assert [r["changes"][0]["key"] for r in rows] == ["B", "A"]


def test_n_limits_the_tail(any_stage):
    for i in range(5):
        helpers.append_settings_audit([{"key": f"K{i}", "old": "1", "new": "2"}])
    assert len(helpers.read_settings_audit(n=2)) == 2


def test_two_identical_changes_are_two_entries(any_stage):
    helpers.append_settings_audit(DIFF)
    helpers.append_settings_audit(DIFF)
    assert len(helpers.read_settings_audit()) == 2


def test_no_jsonl_at_the_db_stage(any_stage, tmp_path):
    if any_stage != "settings_audit:db":
        pytest.skip("file absence is only asserted at the db stage")
    helpers.append_settings_audit(DIFF)
    assert not os.path.exists(os.path.join(tmp_path, "settings_audit.jsonl"))
