"""V189-5: per-path lock timeouts on owned transactions, and a FOR UPDATE read.

Two real connections to this worker's test database: one holds a row lock,
the other asks for it under a short lock_timeout and must get LockTimeout
quickly instead of waiting forever."""
from __future__ import annotations

import time

import pytest
import sqlalchemy as sa
from sqlalchemy import exc as sa_exc

from swingbot.core.db import engine as engine_module
from swingbot.core.db.engine import (ADMIN_LOCK_TIMEOUT_MS, BOT_LOCK_TIMEOUT_MS,
                                     LockTimeout, transaction)
from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import trades

RECORD = {
    "trade_id": "LOCK-1",
    "ticker": "AAPL",
    "strategy": "RSI",
    "horizon": "2w",
    "direction": "bullish",
    "status": "open",
    "opened_at": "2026-01-02T15:00:00+00:00",
    "confidence": 4,
}


def _repo() -> Repository:
    return Repository(trades, key="trade_id")


@pytest.fixture
def seeded():
    _repo().insert(dict(RECORD))          # own transaction, committed
    return "LOCK-1"


def _shown_lock_timeout(conn) -> str:
    return conn.execute(sa.text("SHOW lock_timeout")).scalar_one()


def test_path_timeouts_are_one_and_five_seconds():
    assert (BOT_LOCK_TIMEOUT_MS, ADMIN_LOCK_TIMEOUT_MS) == (1000, 5000)


def test_owned_transaction_sets_the_lock_timeout_locally():
    with transaction(lock_timeout_ms=1234) as conn:
        assert _shown_lock_timeout(conn) == "1234ms"


def test_without_a_timeout_the_server_default_stands():
    with transaction() as conn:
        assert _shown_lock_timeout(conn) == "0"


def test_the_setting_does_not_leak_into_the_next_transaction():
    with transaction(lock_timeout_ms=1234):
        pass
    with transaction() as conn:
        assert _shown_lock_timeout(conn) == "0"


def test_a_passthrough_connection_is_yielded_unchanged():
    outer = engine_module.get_engine().connect()
    try:
        with outer.begin():
            with transaction(outer, lock_timeout_ms=50) as inner:
                assert inner is outer
                assert _shown_lock_timeout(inner) == "0"
    finally:
        outer.close()


@pytest.mark.parametrize("bad", [0, -5])
def test_a_non_positive_timeout_is_refused(bad):
    with pytest.raises(ValueError):
        with transaction(lock_timeout_ms=bad):
            pass


def test_get_for_update_returns_the_row(seeded):
    with transaction() as conn:
        row = _repo().get_for_update(seeded, conn=conn)
    assert row["trade_id"] == "LOCK-1" and row["status"] == "open"


def test_get_for_update_of_a_missing_key_is_none():
    with transaction() as conn:
        assert _repo().get_for_update("NOPE", conn=conn) is None


def test_get_for_update_requires_the_callers_connection():
    with pytest.raises(TypeError):
        _repo().get_for_update("LOCK-1")            # no conn keyword at all
    with pytest.raises(ValueError):
        _repo().get_for_update("LOCK-1", conn=None)


def test_a_held_row_lock_times_out_as_lock_timeout(seeded):
    holder = engine_module.get_engine().connect()
    try:
        holder.begin()
        assert _repo().get_for_update(seeded, conn=holder) is not None
        started = time.monotonic()
        with pytest.raises(LockTimeout) as caught:
            with transaction(lock_timeout_ms=200) as conn:
                _repo().get_for_update(seeded, conn=conn)
        assert time.monotonic() - started < 3.0
        assert isinstance(caught.value.__cause__, sa_exc.DBAPIError)
    finally:
        holder.rollback()
        holder.close()
    # Released at rollback: the same request now succeeds at once.
    with transaction(lock_timeout_ms=200) as conn:
        assert _repo().get_for_update(seeded, conn=conn) is not None


def test_other_database_errors_are_not_translated():
    with pytest.raises(sa_exc.DBAPIError) as caught:
        with transaction(lock_timeout_ms=200) as conn:
            conn.execute(sa.text("SELECT 1 / 0"))
    assert not isinstance(caught.value, LockTimeout)
