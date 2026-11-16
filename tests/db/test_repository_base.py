"""Unit-level contracts for the generic flat-dictionary repository."""
import pytest

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import journal_entries, trades


def test_repository_requires_an_actual_key_column():
    with pytest.raises(ValueError, match="not a table column"):
        Repository(trades, "not_a_column")


def test_repository_uses_the_schema_registry_for_promoted_fields():
    repository = Repository(trades, "trade_id")
    values = repository._values({
        "trade_id": "T1", "ticker": "AAPL", "strategy": "RSI", "confidence": 4,
    })
    assert values == {
        "trade_id": "T1", "ticker": "AAPL", "strategy": "RSI", "doc": {"confidence": 4},
    }
    assert repository._record(type("Row", (), {"_mapping": {
        "trade_id": "T1", "ticker": "AAPL", "strategy": "RSI", "doc": {"confidence": 4},
    }})()) == {"trade_id": "T1", "ticker": "AAPL", "strategy": "RSI", "confidence": 4}


def _journal_row(**doc):
    return {"trade_id": "J1", "strategy": "RSI", "outcome": "loss",
            "closed_at": "2026-11-12T15:31:00+00:00",
            "created_at": "2026-11-12T15:32:00+00:00", **doc}


def test_patch_where_that_matches_composes_the_doc(db_conn):
    repo = Repository(journal_entries, "trade_id")
    repo.upsert(_journal_row(note="keep", mfe_r=1.0), conn=db_conn)
    out = repo.patch("J1", {"mfe_r": 0.3}, conn=db_conn,
                     where=journal_entries.c.doc["note"].astext == "keep")
    assert out["mfe_r"] == 0.3 and out["note"] == "keep"


def test_patch_where_that_misses_returns_none_and_writes_nothing(db_conn):
    repo = Repository(journal_entries, "trade_id")
    repo.upsert(_journal_row(note="keep", mfe_r=1.0), conn=db_conn)
    assert repo.patch("J1", {"mfe_r": 0.3}, conn=db_conn,
                      where=journal_entries.c.doc["note"].astext == "other") is None
    assert repo.get("J1", conn=db_conn)["mfe_r"] == 1.0


def test_patch_without_where_keeps_todays_behaviour(db_conn):
    repo = Repository(journal_entries, "trade_id")
    assert repo.patch("missing", {"mfe_r": 0.3}, conn=db_conn) is None
    repo.upsert(_journal_row(mfe_r=1.0), conn=db_conn)
    assert repo.patch("J1", {"mfe_r": 0.3}, conn=db_conn)["mfe_r"] == 0.3
