"""v171 Review Focus 1-2 on real Postgres: one statement per hit, a hung database
fails open inside the statement timeout, a dead holder never strands waiters."""
import threading
import time

import pytest
import sqlalchemy as sa

from swingbot import config
from swingbot.core.db import side_engine
from swingbot.core.marketdata.shared import counters, layer
from swingbot.core.marketdata.shared.kinds import Asker, DataKind

Q = DataKind.QUOTE


@pytest.fixture
def side_db(db_committed, db_engine, monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL", db_engine.url.render_as_string(hide_password=False))
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    monkeypatch.setattr(config, "MARKETDATA_PG_TIMEOUT_MS", 250)
    monkeypatch.setattr(counters, "flush", lambda force=False: 0)   # no count write in the statement tally
    side_engine.reset()
    yield db_committed
    side_engine.reset()


def test_a_cache_hit_is_one_statement(side_db):
    layer.get(Q, ["AAPL", "MSFT"], lambda s: {x: 1.0 for x in s}, asker=Asker.SCAN, provider="alpaca")
    statements = []
    sa.event.listen(side_engine._get(), "before_cursor_execute",
                    lambda *a, **k: statements.append(a[2]))
    got = layer.get(Q, ["AAPL", "MSFT"], lambda s: {}, asker=Asker.SCAN, provider="alpaca")
    assert {e.outcome for e in got.values()} == {"hit"} and len(statements) == 1


def test_hung_cache_read_fails_open_within_timeout(side_db, db_engine):
    blocker = db_engine.connect()
    tx = blocker.begin()
    blocker.execute(sa.text("LOCK TABLE market_cache IN ACCESS EXCLUSIVE MODE"))
    try:
        started = time.monotonic()
        got = layer.get(Q, ["AAPL"], lambda s: {"AAPL": 2.0}, asker=Asker.STOP_MONITOR,
                        provider="alpaca")
        assert got["AAPL"].value == 2.0 and time.monotonic() - started < 1.5
    finally:
        tx.rollback()
        blocker.close()


def test_a_dead_holder_never_strands_waiters(side_db):
    side_db.execute(sa.text(
        "insert into market_cache (key, kind, symbol, fetched_at, source, lease_holder, lease_until, doc)"
        " values ('quote:AAPL:', 'quote', 'AAPL', clock_timestamp() - interval '10 minutes', 'alpaca',"
        " 'dead', clock_timestamp() + interval '1 minute', '{\"value\": 1.0}')"))
    side_db.commit()
    stale = layer.get(Q, ["AAPL"], lambda s: {"AAPL": 2.0}, asker=Asker.ADMIN_PAGE,
                      provider="alpaca", deadline_s=0.3)
    assert stale["AAPL"].value == 1.0 and stale["AAPL"].age_s() > 500
    fresh = layer.get(Q, ["AAPL"], lambda s: {"AAPL": 2.0}, asker=Asker.STOP_MONITOR,
                      provider="alpaca", deadline_s=0.3)
    assert fresh["AAPL"].value == 2.0
    side_db.execute(sa.text("update market_cache set lease_holder='dead2', fetched_at=null,"
                            " lease_until=clock_timestamp() - interval '1 second'"))
    side_db.commit()
    again = layer.get(Q, ["AAPL"], lambda s: {"AAPL": 3.0}, asker=Asker.ADMIN_PAGE, provider="alpaca")
    assert again["AAPL"].value == 3.0 and again["AAPL"].outcome == "fetched"


def test_two_concurrent_askers_make_one_provider_call(side_db):
    calls = []

    def slow(symbols):
        calls.append(symbols)
        time.sleep(0.4)
        return {s: 5.0 for s in symbols}
    results = []
    threads = [threading.Thread(target=lambda: results.append(
        layer.get(Q, ["NVDA"], slow, asker=Asker.SCAN, provider="alpaca"))) for _ in range(2)]
    for t in threads:
        t.start()
        time.sleep(0.05)
    for t in threads:
        t.join()
    assert len(calls) == 1 and sorted(r["NVDA"].outcome for r in results) == ["fetched", "shared-wait"]
