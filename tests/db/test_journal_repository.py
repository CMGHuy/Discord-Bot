"""JournalRepository filters match JournalStore.entries."""
import pytest

from swingbot.core.db.repositories.journal import JournalRepository


@pytest.fixture
def repo():
    return JournalRepository()


def _entry(trade_id, **overrides):
    entry = dict(trade_id=trade_id, strategy="RSI", outcome="win",
                 closed_at="2026-01-09T15:00:00+00:00",
                 created_at="2026-01-09T16:00:00+00:00",
                 tags=["clean-entry"], note="", lesson="held to TP1")
    entry.update(overrides)
    return entry


def test_entries_are_newest_first_by_closed_at(repo, db_conn):
    repo.upsert(_entry("OLD", closed_at="2026-01-01T00:00:00+00:00"), conn=db_conn)
    repo.upsert(_entry("NEW", closed_at="2026-01-09T00:00:00+00:00"), conn=db_conn)
    assert [entry["trade_id"] for entry in repo.entries(conn=db_conn)] == ["NEW", "OLD"]


def test_filter_by_strategy_and_outcome(repo, db_conn):
    repo.upsert(_entry("T1", strategy="RSI", outcome="win"), conn=db_conn)
    repo.upsert(_entry("T2", strategy="MACD", outcome="loss"), conn=db_conn)
    assert [entry["trade_id"] for entry in repo.entries(strategy="MACD", conn=db_conn)] == ["T2"]
    assert [entry["trade_id"] for entry in repo.entries(outcome="loss", conn=db_conn)] == ["T2"]


def test_filter_by_tag_uses_jsonb_containment(repo, db_conn):
    repo.upsert(_entry("T1", tags=["clean-entry", "runner"]), conn=db_conn)
    repo.upsert(_entry("T2", tags=["chased"]), conn=db_conn)
    assert [entry["trade_id"] for entry in repo.entries(tag="runner", conn=db_conn)] == ["T1"]


def test_filter_by_since_is_inclusive(repo, db_conn):
    repo.upsert(_entry("T1", closed_at="2026-01-01T00:00:00+00:00"), conn=db_conn)
    repo.upsert(_entry("T2", closed_at="2026-01-09T00:00:00+00:00"), conn=db_conn)
    assert [entry["trade_id"] for entry in repo.entries(
        since="2026-01-09T00:00:00+00:00", conn=db_conn)] == ["T2"]


def test_filter_by_has_note_trims_whitespace(repo, db_conn):
    repo.upsert(_entry("T1", note="  "), conn=db_conn)
    repo.upsert(_entry("T2", note="real note"), conn=db_conn)
    assert [entry["trade_id"] for entry in repo.entries(has_note=True, conn=db_conn)] == ["T2"]
    assert [entry["trade_id"] for entry in repo.entries(has_note=False, conn=db_conn)] == ["T1"]


def test_filters_are_and_combined_and_upserts_replace(repo, db_conn):
    repo.upsert(_entry("T1", strategy="RSI", outcome="win", lesson="first"), conn=db_conn)
    repo.upsert(_entry("T2", strategy="RSI", outcome="loss"), conn=db_conn)
    repo.upsert(_entry("T1", strategy="RSI", outcome="win", lesson="second"), conn=db_conn)
    assert [entry["trade_id"] for entry in repo.entries(
        strategy="RSI", outcome="loss", conn=db_conn)] == ["T2"]
    assert repo.count(conn=db_conn) == 2
    assert repo.get("T1", conn=db_conn)["lesson"] == "second"
