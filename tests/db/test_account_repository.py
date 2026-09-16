"""Account config is one row; history is separate chronological rows."""
import pytest

from swingbot.core.db.repositories.account import AccountRepository


@pytest.fixture
def repo():
    return AccountRepository()


def test_load_save_and_replace_config(repo, db_conn):
    assert repo.load(conn=db_conn) == {}
    repo.save({"balance": 1.0, "gone": True}, conn=db_conn)
    repo.save({"balance": 2.0}, conn=db_conn)
    assert repo.count(conn=db_conn) == 1
    assert repo.load(conn=db_conn) == {"balance": 2.0}


def test_history_splits_from_config_and_is_chronological(repo, db_conn):
    repo.save({"balance": 1.0, "balance_history": [{"ts": "2026-01-02T00:00:00+00:00", "balance": 1.0}]}, conn=db_conn)
    repo.append_history({"ts": "2026-01-01T00:00:00+00:00", "balance": 0.0, "reason": "seed"}, conn=db_conn)
    assert "balance_history" not in repo.load(conn=db_conn)
    assert [row["balance"] for row in repo.history(conn=db_conn)] == [0.0, 1.0]


def test_history_upserts_an_existing_timestamp(repo, db_conn):
    entry = {"ts": "2026-01-01T00:00:00+00:00", "balance": 1.0}
    repo.append_history(entry, conn=db_conn)
    repo.append_history({**entry, "balance": 2.0}, conn=db_conn)
    assert [row["balance"] for row in repo.history(conn=db_conn)] == [2.0]


def test_history_limit_returns_most_recent_rows_in_chronological_order(repo, db_conn):
    for day in range(1, 6):
        repo.append_history({"ts": f"2026-01-0{day}T00:00:00+00:00", "balance": float(day)}, conn=db_conn)
    assert [row["balance"] for row in repo.history(limit=2, conn=db_conn)] == [4.0, 5.0]
