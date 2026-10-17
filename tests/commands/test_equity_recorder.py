"""v172: trade_monitor records one live equity sample per 5 minutes, in session.

No pytest-asyncio in this repo -- coroutines are driven with asyncio.run().
The DB is the per-worker test Postgres (autouse `_store_database`)."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from swingbot.admin import dashboard as dash
from swingbot.commands import scanning as scanning_mod
from swingbot.commands.scanning import equity_recorder, loops
from swingbot.core.db.repositories.equity_samples import EquitySampleRepository
from swingbot.core.tracking import equity
from tests.store_seed import seed_store

# Wednesday 2026-10-14, 11:00 New York (EDT = UTC-4): inside the regular session.
IN_SESSION = datetime(2026, 10, 14, 15, 0, tzinfo=timezone.utc)
# The same day, 17:00 New York: after the close.
AFTER_CLOSE = datetime(2026, 10, 14, 21, 0, tzinfo=timezone.utc)
BASE = 10000.0


@pytest.fixture(autouse=True)
def _fresh_state():
    equity_recorder.reset_state()
    yield
    equity_recorder.reset_state()


@pytest.fixture
def repo():
    return EquitySampleRepository()


@pytest.fixture
def account():
    seed_store("account", {"base_balance": BASE, "balance": BASE, "risk_pct": 1.0,
                           "max_position_pct": 20.0, "sizing_mode": "risk_pct",
                           "balance_history": []})


def _trade(tid, ticker, *, shares=10.0, entry=100.0, status="open", **extra):
    return {"id": tid, "ticker": ticker, "direction": "bullish", "status": status,
            "entry": entry, "stop_loss": round(entry * 0.95, 2), "shares": shares,
            "opened_at": "2026-10-13T14:00:00+00:00", "ledger": "main", **extra}


def _patch_book(monkeypatch, trades):
    monkeypatch.setattr(equity_recorder, "load_trades", lambda: list(trades))
    monkeypatch.setattr(equity, "load_plans_by_id", lambda: {})


def _fake_price_batch_aapl_110(tickers, **kw):
    """Module-level so it pickles through loops._run_bounded's worker process."""
    return {"AAPL": 110.0}


def _patch_monitor(monkeypatch, *, tick=lambda: []):
    monkeypatch.setattr(loops.trade_log, "get_trades",
                        lambda status=None, limit=None: [{"ticker": "AAPL", "id": "t1",
                                                          "status": "open"}])
    monkeypatch.setattr(loops, "get_current_price_batch", _fake_price_batch_aapl_110)
    monkeypatch.setattr(loops.trade_log, "close_if_live_price_hit", lambda ticker, live: [])
    monkeypatch.setattr(loops.trade_log, "check_near_tp_timeout", lambda ticker, live: [])
    monkeypatch.setattr("swingbot.core.planning.plan_manager.run_manager_tick", tick)


def test_one_priced_one_unpriced_one_unsized_writes_one_row_with_two_skipped(
        monkeypatch, repo, account):
    _patch_book(monkeypatch, [_trade("t1", "AAPL"), _trade("t2", "MSFT"),
                              _trade("t3", "NVDA", shares=None)])
    assert equity_recorder.record_sample({"AAPL": 110.0, "NVDA": 50.0},
                                         now=IN_SESSION, repo=repo) is True
    (row,) = repo.list_rows()
    assert (row["source"], row["kind"], row["open_n"], row["skipped_n"]) == ("live", "point", 1, 2)
    assert row["unrealized_pnl"] == 100.0
    assert row["realized_balance"] == BASE
    assert row["equity"] == BASE + 100.0
    assert row["at"] == IN_SESSION
    assert row.get("backfill_run") is None  # merge_doc omits None columns on read


def test_a_zero_or_negative_price_is_unpriced_not_priced_at_zero(monkeypatch, repo, account):
    _patch_book(monkeypatch, [_trade("t1", "AAPL"), _trade("t2", "MSFT")])
    equity_recorder.record_sample({"AAPL": 0.0, "MSFT": -1.0}, now=IN_SESSION, repo=repo)
    (row,) = repo.list_rows()
    assert (row["open_n"], row["skipped_n"], row["unrealized_pnl"]) == (0, 2, 0.0)


def test_outside_the_regular_session_nothing_is_written(monkeypatch, repo, account):
    _patch_book(monkeypatch, [_trade("t1", "AAPL")])
    assert equity_recorder.record_sample({"AAPL": 110.0}, now=AFTER_CLOSE, repo=repo) is False
    assert repo.list_rows() == []


def test_two_ticks_under_five_minutes_apart_write_one_row(monkeypatch, repo, account):
    _patch_book(monkeypatch, [_trade("t1", "AAPL")])
    record = equity_recorder.record_sample
    assert record({"AAPL": 110.0}, now=IN_SESSION, repo=repo) is True
    assert record({"AAPL": 111.0}, now=IN_SESSION + timedelta(minutes=4, seconds=59),
                  repo=repo) is False
    assert record({"AAPL": 112.0}, now=IN_SESSION + equity_recorder.SAMPLE_INTERVAL,
                  repo=repo) is True
    assert [r["unrealized_pnl"] for r in repo.list_rows()] == [100.0, 120.0]


def test_the_throttle_survives_a_restart_by_reading_the_last_live_row(
        monkeypatch, repo, account):
    _patch_book(monkeypatch, [_trade("t1", "AAPL")])
    repo.insert_sample({"at": IN_SESSION - timedelta(minutes=2),
                        "realized_balance": Decimal("10000"), "unrealized_pnl": Decimal("0"),
                        "equity": Decimal("10000"), "open_n": 0, "skipped_n": 0,
                        "source": "live", "kind": "point", "backfill_run": None})
    assert equity_recorder.record_sample({"AAPL": 110.0}, now=IN_SESSION, repo=repo) is False
    assert len(repo.list_rows()) == 1


def test_parity_with_the_trades_page_and_the_realized_walk(monkeypatch, repo, account):
    trades = [
        _trade("t1", "AAPL", shares=7.5, entry=101.2),
        _trade("t2", "MSFT", status="loss", exit_price=95.0, realized_pnl_amount=-50.0,
               closed_at="2026-10-14T14:00:00+00:00"),
        _trade("t3", "NVDA", ledger="weak"),          # weak ledger: never in a sample
    ]
    _patch_book(monkeypatch, trades)
    equity_recorder.record_sample({"AAPL": 103.5, "NVDA": 500.0}, now=IN_SESSION, repo=repo)
    (row,) = repo.list_rows()
    assert row["open_n"] == 1
    assert row["unrealized_pnl"] == dash.unrealized_pnl_amount(101.2, "bullish", 7.5, 103.5)
    walk = equity.realized_balance_at(equity.starting_balance(),
                                      equity.realized_legs(trades), IN_SESSION)
    assert row["realized_balance"] == float(walk.quantize(Decimal("0.01")))
    assert row["realized_balance"] == BASE - 50.0


def test_a_trade_closed_in_the_same_tick_is_realized_not_unrealized(monkeypatch, repo, account):
    book = {"trades": [_trade("t1", "AAPL")]}
    closed = _trade("t1", "AAPL", status="win", exit_price=110.0, realized_pnl_amount=100.0,
                    closed_at=(datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat())

    def tick_closes_the_trade():
        book["trades"] = [closed]
        return []

    monkeypatch.setattr(equity_recorder, "load_trades", lambda: list(book["trades"]))
    monkeypatch.setattr(equity, "load_plans_by_id", lambda: {})
    monkeypatch.setattr(equity_recorder, "is_regular_session", lambda now=None: True)
    _patch_monitor(monkeypatch, tick=tick_closes_the_trade)

    asyncio.run(scanning_mod.trade_monitor.coro())

    (row,) = repo.list_rows()
    assert (row["open_n"], row["unrealized_pnl"]) == (0, 0.0)
    assert row["realized_balance"] == BASE + 100.0


def test_a_recording_failure_is_logged_once_per_type_and_never_raises(
        monkeypatch, repo, account, caplog):
    caplog.set_level(logging.DEBUG, logger=equity_recorder.__name__)

    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(equity_recorder, "load_trades", boom)
    for minute in (0, 5, 10):
        assert equity_recorder.record_sample(
            {}, now=IN_SESSION + timedelta(minutes=minute), repo=repo) is False
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1 and "RuntimeError" in warnings[0].getMessage()

    def other():
        raise KeyError("plan")

    monkeypatch.setattr(equity_recorder, "load_trades", other)
    equity_recorder.record_sample({}, now=IN_SESSION + timedelta(minutes=15), repo=repo)
    assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 2
    assert repo.list_rows() == []


def test_the_monitor_tick_completes_when_recording_raises(monkeypatch):
    calls = {"tick": 0}

    def tick():
        calls["tick"] += 1
        return []

    def explode(live_prices, **kw):
        raise RuntimeError("recorder bug")

    _patch_monitor(monkeypatch, tick=tick)
    monkeypatch.setattr(equity_recorder, "record_sample", explode)
    asyncio.run(scanning_mod.trade_monitor.coro())     # must not raise
    assert calls["tick"] == 1


def test_the_monitor_hands_its_own_prices_to_the_recorder(monkeypatch):
    seen = []
    _patch_monitor(monkeypatch)
    monkeypatch.setattr(equity_recorder, "record_sample",
                        lambda live_prices, **kw: seen.append(dict(live_prices)) or False)
    asyncio.run(scanning_mod.trade_monitor.coro())
    assert seen == [{"AAPL": 110.0}]
