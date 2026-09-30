"""JournalStore.set_note honours the per-store stage (no Postgres needed)."""
import json
import os

import pytest

from swingbot import config
from swingbot.core.analytics.journal import JournalStore
from swingbot.core.db.repositories import journal as journal_repo_mod


class FakeRepo:
    def __init__(self, rows=None):
        self.rows = dict(rows or {})
        self.patches = []

    def patch(self, trade_id, changes):
        self.patches.append((trade_id, changes))
        if trade_id not in self.rows:
            return None
        self.rows[trade_id] = {**self.rows[trade_id], **changes}
        return self.rows[trade_id]


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    repo = FakeRepo({"DBONLY": {"trade_id": "DBONLY", "note": ""},
                     "T1": {"trade_id": "T1", "note": ""}})
    monkeypatch.setattr(journal_repo_mod, "journal_repo", lambda: repo)
    with open(os.path.join(tmp_path, "journal.json"), "w") as fh:
        json.dump([{"trade_id": "T1", "note": ""}], fh)
    return tmp_path, repo


def _json_note(tmp_path):
    with open(os.path.join(tmp_path, "journal.json")) as fh:
        return json.load(fh)[0]["note"]


def test_json_stage_never_touches_db(env, monkeypatch):
    tmp_path, repo = env
    monkeypatch.setattr(config, "DB_STORES", "")
    assert JournalStore().set_note("T1", "hi") is True
    assert _json_note(tmp_path) == "hi"
    assert repo.patches == []


def test_dual_stage_writes_json_and_db(env, monkeypatch):
    tmp_path, repo = env
    monkeypatch.setattr(config, "DB_STORES", "journal:dual")
    assert JournalStore().set_note("T1", "hi") is True
    assert _json_note(tmp_path) == "hi"
    assert repo.rows["T1"]["note"] == "hi"


def test_db_stage_annotates_db_only_entry(env, monkeypatch):
    tmp_path, repo = env
    monkeypatch.setattr(config, "DB_STORES", "journal:db")
    assert JournalStore().set_note("DBONLY", "hi") is True
    assert repo.rows["DBONLY"]["note"] == "hi"
    assert _json_note(tmp_path) == ""


def test_db_stage_unknown_trade_returns_false(env, monkeypatch):
    monkeypatch.setattr(config, "DB_STORES", "journal:db")
    assert JournalStore().set_note("NOPE", "hi") is False
