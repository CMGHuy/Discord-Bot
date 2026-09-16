"""Signal state: one row per ticker|strategy|horizon."""
import pytest

from swingbot.core.db.repositories.signal_state import SignalStateRepository


@pytest.fixture
def repo():
    return SignalStateRepository()


def test_entry_for_an_unknown_key_is_an_empty_dict(repo, db_conn):
    assert repo.entry("AAPL|RSI|2w", conn=db_conn) == {}


def test_put_then_entry_round_trips(repo, db_conn):
    repo.put("AAPL|RSI|2w", {"trend": "bullish", "pending_value": None,
                              "pending_count": 0}, conn=db_conn)
    assert repo.entry("AAPL|RSI|2w", conn=db_conn)["trend"] == "bullish"


def test_put_replaces_the_whole_entry(repo, db_conn):
    repo.put("K", {"trend": "bullish", "pending_count": 3}, conn=db_conn)
    repo.put("K", {"trend": "bearish"}, conn=db_conn)
    assert repo.entry("K", conn=db_conn) == {"trend": "bearish"}


def test_two_keys_do_not_interfere(repo, db_conn):
    repo.put("A|RSI|2w", {"trend": "bullish"}, conn=db_conn)
    repo.put("B|RSI|2w", {"trend": "bearish"}, conn=db_conn)
    assert repo.entry("A|RSI|2w", conn=db_conn)["trend"] == "bullish"
    assert repo.entry("B|RSI|2w", conn=db_conn)["trend"] == "bearish"


def test_all_entries_is_keyed_by_key(repo, db_conn):
    repo.put("A|RSI|2w", {"trend": "bullish"}, conn=db_conn)
    repo.put("B|RSI|2w", {"trend": "bearish"}, conn=db_conn)
    out = repo.all_entries(conn=db_conn)
    assert set(out) == {"A|RSI|2w", "B|RSI|2w"}
    assert "key" not in out["A|RSI|2w"]


def test_a_none_valued_field_survives(repo, db_conn):
    repo.put("K", {"trend": "bullish", "pending_value": None}, conn=db_conn)
    assert repo.entry("K", conn=db_conn)["pending_value"] is None
