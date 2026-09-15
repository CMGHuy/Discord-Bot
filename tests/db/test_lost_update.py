"""Characterise the JSON lost-update race and prove the DB replacement fixes it."""
from __future__ import annotations

import os
import threading

import pytest

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import trades
from swingbot.core.infra.jsonio import atomic_write_json, read_json


RECORD = {
    "trade_id": "RACE-1",
    "ticker": "AAPL",
    "strategy": "RSI",
    "horizon": "2w",
    "direction": "LONG",
    "status": "open",
    "opened_at": "2026-01-02T15:00:00+00:00",
    "confidence": 4,
    "notes": "original",
}


def test_the_file_store_loses_one_of_two_concurrent_updates(tmp_path):
    """Whole-file rewrites lose an earlier writer's unrelated change."""
    path = os.path.join(tmp_path, "trades.json")
    atomic_write_json(path, [dict(RECORD)])

    # Both processes read the same old snapshot. A process-local lock cannot
    # bridge the bot and admin containers sharing this file.
    snapshot_a = read_json(path, [])
    snapshot_b = read_json(path, [])

    snapshot_a[0]["status"] = "closed"
    atomic_write_json(path, snapshot_a)
    snapshot_b[0]["confidence"] = 5
    atomic_write_json(path, snapshot_b)

    final = read_json(path, [])[0]
    assert final["confidence"] == 5
    assert final["status"] == "open", (
        "the JSON path unexpectedly kept both changes; update this "
        "characterisation if its write model has changed"
    )


def test_the_repository_keeps_two_partial_updates(db_conn):
    """Database-side document patches compose instead of rewriting a snapshot."""
    repository = Repository(trades, key="trade_id")
    repository.insert(dict(RECORD), conn=db_conn)

    repository.patch("RACE-1", {"status": "closed"}, conn=db_conn)
    repository.patch("RACE-1", {"confidence": 5}, conn=db_conn)

    final = repository.get("RACE-1", conn=db_conn)
    assert final["status"] == "closed"
    assert final["confidence"] == 5
    assert final["notes"] == "original"


@pytest.mark.slow
def test_two_real_connections_do_not_lose_an_update(db_engine, db_committed):
    """Independent bot/admin-style transactions retain both partial writes."""
    repository = Repository(trades, key="trade_id")
    with db_committed.begin():
        repository.insert(dict(RECORD), conn=db_committed)

    barrier = threading.Barrier(2, timeout=10)
    errors: list[BaseException] = []

    def writer(changes: dict) -> None:
        try:
            with db_engine.begin() as connection:
                barrier.wait()
                Repository(trades, key="trade_id").patch(
                    "RACE-1", changes, conn=connection
                )
        except BaseException as exc:  # noqa: BLE001 - test reports worker errors
            errors.append(exc)

    threads = [
        threading.Thread(target=writer, args=({"status": "closed"},)),
        threading.Thread(target=writer, args=({"confidence": 5},)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)

    assert not errors, f"a writer raised: {errors}"
    assert all(not thread.is_alive() for thread in threads)
    final = repository.get("RACE-1", conn=db_committed)
    assert final["status"] == "closed"
    assert final["confidence"] == 5
