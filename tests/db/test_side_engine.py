"""v171 D1: the layer's own tiny pool, autocommit, a hard statement timeout, fast fail-open."""
import multiprocessing
import time

import pytest
import sqlalchemy as sa

from swingbot import config
from swingbot.core.db import side_engine
from swingbot.core.db.engine import DatabaseUnavailable


@pytest.fixture
def side_db(db_committed, db_engine, monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL", db_engine.url.render_as_string(hide_password=False))
    monkeypatch.setattr(config, "MARKETDATA_PG_TIMEOUT_MS", 250)
    side_engine.reset()
    yield db_committed
    side_engine.reset()


def test_pool_is_one_plus_one_in_the_parent_and_one_in_a_worker(monkeypatch):
    assert side_engine.pool_limits() == (1, 1)
    monkeypatch.setattr(multiprocessing, "parent_process", lambda: object())
    assert side_engine.pool_limits() == (1, 0)


def test_statement_timeout_follows_the_knob(side_db, monkeypatch):
    with side_engine.side_connection() as conn:
        assert conn.execute(sa.text("show statement_timeout")).scalar_one() == "250ms"
    monkeypatch.setattr(config, "MARKETDATA_PG_TIMEOUT_MS", 300)
    with side_engine.side_connection() as conn:
        assert conn.execute(sa.text("show statement_timeout")).scalar_one() == "300ms"


def test_a_hung_statement_is_cancelled_at_the_timeout(side_db):
    started = time.monotonic()
    with pytest.raises(sa.exc.OperationalError):
        with side_engine.side_connection() as conn:
            conn.execute(sa.text("select pg_sleep(3)"))
    assert time.monotonic() - started < 1.0


def test_writes_are_autocommitted(side_db):
    with side_engine.side_connection() as conn:
        conn.execute(sa.text("insert into market_cache (key, kind, symbol) values ('k', 'quote', 'X')"))
    assert side_db.execute(sa.text("select count(*) from market_cache where key='k'")).scalar_one() == 1


def test_a_down_database_fails_fast_after_the_first_refusal(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL",
                        "postgresql+psycopg://u:p@127.0.0.1:1/none")
    side_engine.reset()
    with pytest.raises(Exception):
        with side_engine.side_connection():
            pass
    started = time.monotonic()
    with pytest.raises(DatabaseUnavailable):
        with side_engine.side_connection():
            pass
    assert time.monotonic() - started < 0.05
    side_engine.reset()


def test_no_url_is_database_unavailable(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL", "")
    side_engine.reset()
    with pytest.raises(DatabaseUnavailable):
        with side_engine.side_connection():
            pass
