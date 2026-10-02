"""JournalStore.set_note patches the journal repository (no Postgres needed)."""
import pytest

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
def repo(monkeypatch):
    repo = FakeRepo({"DBONLY": {"trade_id": "DBONLY", "note": ""}})
    monkeypatch.setattr(journal_repo_mod, "journal_repo", lambda: repo)
    return repo


def test_annotates_a_row(repo):
    assert JournalStore().set_note("DBONLY", "hi") is True
    assert repo.rows["DBONLY"]["note"] == "hi"


def test_unknown_trade_returns_false(repo):
    assert JournalStore().set_note("NOPE", "hi") is False
