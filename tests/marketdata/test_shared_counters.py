"""v171 D9: per-call counts by provider, kind, asker and outcome."""
import contextlib
import logging
from datetime import datetime, timezone

import pytest

from swingbot import config
from swingbot.core.marketdata.shared import counters
from swingbot.core.marketdata.shared.kinds import Asker, DataKind

HOUR = datetime(2026, 10, 16, 14, 0, tzinfo=timezone.utc)


class FakeRepo:
    def __init__(self, fail=False):
        self.rows, self.fail = [], fail

    def add_counts(self, rows, *, conn):
        if self.fail:
            raise RuntimeError("db down")
        self.rows.extend(rows)


@pytest.fixture
def repo(monkeypatch):
    fake = FakeRepo()
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "count")
    monkeypatch.setattr(counters, "market_shared_repo", lambda: fake)
    monkeypatch.setattr(counters, "side_connection", lambda: contextlib.nullcontext(None))
    monkeypatch.setattr(counters, "_now", lambda: HOUR.replace(minute=17))
    counters.reset()
    yield fake
    counters.reset()


def test_off_mode_counts_nothing(repo, monkeypatch):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "off")
    counters.count("alpaca", DataKind.QUOTE, Asker.SCAN, "fetched")
    assert counters.snapshot_and_clear() == []


def test_counts_aggregate_by_hour_and_key(repo):
    counters.count("alpaca", DataKind.QUOTE, Asker.SCAN, "hit", 3)
    counters.count("alpaca", DataKind.QUOTE, Asker.SCAN, "hit")
    counters.count("yfinance", DataKind.EARNINGS, Asker.ADMIN_PAGE, "failed")
    assert sorted(counters.snapshot_and_clear()) == [
        (HOUR.isoformat(), "alpaca", "quote", "scan", "hit", 4),
        (HOUR.isoformat(), "yfinance", "earnings", "admin_page", "failed", 1)]
    assert counters.snapshot_and_clear() == []


def test_an_unknown_outcome_is_rejected(repo):
    with pytest.raises(ValueError):
        counters.count("alpaca", DataKind.QUOTE, Asker.SCAN, "maybe")


def test_merge_adds_worker_rows(repo):
    counters.count("alpaca", DataKind.QUOTE, Asker.SCAN, "fetched")
    counters.merge([(HOUR.isoformat(), "alpaca", "quote", "scan", "fetched", 5)])
    assert counters.snapshot_and_clear() == [(HOUR.isoformat(), "alpaca", "quote", "scan", "fetched", 6)]


def test_flush_waits_sixty_seconds_unless_forced(repo, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(counters, "_monotonic", lambda: clock[0])
    counters.reset()                                  # _last_flush = 1000
    counters.count("alpaca", DataKind.QUOTE, Asker.SCAN, "hit")
    assert counters.flush() == 0 and repo.rows == []
    clock[0] = 1061.0
    assert counters.flush() == 1
    assert repo.rows == [(HOUR, "alpaca", "quote", "scan", "hit", 1)]   # hour back to datetime
    counters.count("alpaca", DataKind.QUOTE, Asker.SCAN, "hit")
    assert counters.flush(force=True) == 1


def test_a_failed_flush_keeps_the_rows_and_warns_once(repo, monkeypatch, caplog):
    repo.fail = True
    counters.count("alpaca", DataKind.QUOTE, Asker.SCAN, "hit")
    with caplog.at_level(logging.WARNING):
        assert counters.flush(force=True) == 0
        assert counters.flush(force=True) == 0
    assert len([r for r in caplog.records if "failed open" in r.message]) == 1
    assert counters.snapshot_and_clear() == [(HOUR.isoformat(), "alpaca", "quote", "scan", "hit", 1)]


def test_warn_fail_open_is_per_operation_and_error_class(caplog):
    counters.reset()
    with caplog.at_level(logging.WARNING):
        counters.warn_fail_open("read", TimeoutError("x"))
        counters.warn_fail_open("read", TimeoutError("y"))
        counters.warn_fail_open("read", OSError("z"))
        counters.warn_fail_open("lease", TimeoutError("x"))
    assert len(caplog.records) == 3
