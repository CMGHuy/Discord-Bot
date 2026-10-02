"""scan_progress and market_data_state: the last files that drive live
updates, as tables (v116 Phase 1). Ephemeral: at `db` they start empty."""
from swingbot.core.db import events, schema
from swingbot.core.db.repositories.market_data_state import MarketDataStateRepository
from swingbot.core.db.repositories.scan_progress import ScanProgressRepository


def test_both_tables_promote_only_a_unique_key():
    for name in ("scan_progress", "market_data_state"):
        table = schema.METADATA.tables[name]
        assert table.c.key.unique is True and table.c.key.nullable is False
        assert schema.promoted_for(name) == ("key",)


def test_both_raise_the_concern_whose_screen_shows_them():
    assert events.TABLE_CHANNELS["scan_progress"] == "scan"
    assert events.TABLE_CHANNELS["market_data_state"] == "watchlist"


def test_scan_progress_is_one_row_published_read_and_cleared(db_conn):
    repo = ScanProgressRepository()
    assert repo.read(conn=db_conn) is None
    repo.publish({"pct": 10, "stage": "crawling data"}, conn=db_conn)
    repo.publish({"pct": 55, "stage": "analyzing"}, conn=db_conn)
    assert repo.read(conn=db_conn) == {"pct": 55, "stage": "analyzing"}
    assert repo.count(conn=db_conn) == 1
    repo.clear(conn=db_conn)
    assert repo.read(conn=db_conn) is None


def test_market_data_state_save_replaces_the_whole_map(db_conn):
    repo = MarketDataStateRepository()
    repo.save({"AAPL|daily": {"last_status": "fresh", "fail_count": 0},
               "MSFT|daily": {"last_status": "failed", "fail_count": 2, "last_error": "x"}},
              conn=db_conn)
    repo.save({"AAPL|daily": {"last_status": "incremental", "fail_count": 0}}, conn=db_conn)
    assert repo.load(conn=db_conn) == {
        "AAPL|daily": {"last_status": "incremental", "fail_count": 0}}


def test_saving_an_empty_map_empties_the_table(db_conn):
    repo = MarketDataStateRepository()
    repo.save({"AAPL|daily": {"last_status": "fresh"}}, conn=db_conn)
    repo.save({}, conn=db_conn)
    assert repo.load(conn=db_conn) == {}


def test_store_db_points_the_app_engine_at_the_test_database(store_db):
    from swingbot.core.db.engine import get_engine
    with get_engine().connect() as conn:
        assert conn.exec_driver_sql("select 1").scalar() == 1
