"""The test database fixture must isolate each test with a rollback."""
import sqlalchemy as sa

from swingbot.core.db.schema import trades

ROW = {
    "trade_id": "HARNESS-1", "ticker": "AAPL", "strategy": "RSI", "horizon": "2w",
    "direction": "LONG", "status": "open", "opened_at": "2026-01-02T15:00:00+00:00",
}


def test_a_write_is_visible_inside_its_own_test(db_conn):
    db_conn.execute(sa.insert(trades).values(**ROW))
    assert db_conn.execute(sa.select(trades.c.ticker).where(
        trades.c.trade_id == "HARNESS-1"
    )).scalar_one() == "AAPL"


def test_previous_writes_are_rolled_back(db_conn):
    count = db_conn.execute(sa.select(sa.func.count()).select_from(trades).where(
        trades.c.trade_id == "HARNESS-1"
    )).scalar_one()
    assert count == 0


def test_doc_defaults_to_an_empty_object(db_conn):
    db_conn.execute(sa.insert(trades).values(**ROW))
    assert db_conn.execute(sa.select(trades.c.doc).where(
        trades.c.trade_id == "HARNESS-1"
    )).scalar_one() == {}
