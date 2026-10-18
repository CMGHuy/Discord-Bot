"""v171 D8: trade_monitor and the plan manager land as ONE provider call per
tick in `on` mode; a dead Postgres never stops the stop monitor's quote."""
import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

import pytest

from swingbot import config
from swingbot.commands.scanning import loops
from swingbot.core.marketdata.providers import router
from swingbot.core.marketdata.shared.kinds import Asker, QuoteDetail
from swingbot.core.planning import plan_manager
from swingbot.core.scanning import fetch


class CountingProvider:
    def __init__(self):
        self.calls, self.askers = 0, []

    def latest_quotes(self, tickers, max_age):
        self.calls += 1
        self.askers.append(router.current_asker())
        at = datetime.now(timezone.utc) - timedelta(seconds=2)
        return {t: QuoteDetail(symbol=t, price=190.0, trade_at=at, bid=None, ask=None,
                               quote_at=None, source="alpaca-iex") for t in tickers}


@pytest.fixture
def layer_on(monkeypatch):
    for key, value in {"MARKETDATA_LAYER": "on", "ALPACA_ENABLED": True,
                       "ALPACA_API_KEY_ID": "k", "ALPACA_API_SECRET_KEY": "s",
                       "QUOTE_MAX_AGE_MONITOR_S": 15}.items():
        monkeypatch.setattr(config, key, value)
    prov = CountingProvider()
    monkeypatch.setattr(router, "_provider_factory", lambda *a: prov)
    monkeypatch.setattr(fetch, "_run_bounded", lambda fn, args, timeout, label: fn(*args))
    monkeypatch.setattr("swingbot.core.marketdata.data._yf_quote_details",
                        lambda tickers: pytest.fail("yfinance fallback"))
    router.reset()
    yield prov
    router.reset()


@pytest.fixture
def shared_db(monkeypatch, db_committed):
    from swingbot.core.db import side_engine
    from swingbot.core.db.engine import reset_engine
    monkeypatch.setattr(config, "DATABASE_URL",
                        db_committed.engine.url.render_as_string(hide_password=False))
    reset_engine(); side_engine.reset()
    yield
    side_engine.reset(); reset_engine()


def _tick(monkeypatch, manager_saw):
    monkeypatch.setattr(loops.trade_log, "get_trades", lambda status=None, limit=None: [
        {"ticker": "AAPL", "id": "t1", "status": "open"}])
    monkeypatch.setattr(loops.trade_log, "close_if_live_price_hit", lambda t, live: [])
    monkeypatch.setattr(loops.trade_log, "check_near_tp_timeout", lambda t, live: [])
    monkeypatch.setattr(plan_manager, "run_manager_tick",
                        lambda: manager_saw.append(plan_manager._price_batch_fn(["AAPL"])) or [])
    asyncio.run(loops.trade_monitor.coro())


def test_monitor_and_manager_share_one_provider_call_per_tick(layer_on, shared_db, monkeypatch):
    saw = []
    _tick(monkeypatch, saw)
    assert layer_on.calls == 1
    assert saw == [{"AAPL": 190.0}] and saw[0].details["AAPL"].trade_at is not None
    assert layer_on.askers == [Asker.STOP_MONITOR]


def test_count_mode_still_makes_one_call_each_as_today(layer_on, shared_db, monkeypatch):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "count")
    saw = []
    _tick(monkeypatch, saw)
    assert layer_on.calls == 2 and saw == [{"AAPL": 190.0}]


def test_monitor_gets_its_quote_when_postgres_is_down(layer_on, monkeypatch):
    from swingbot.core.db import side_engine
    monkeypatch.setattr(config, "DATABASE_URL", "postgresql+psycopg://x:x@127.0.0.1:1/none")
    side_engine.reset()
    started = time.monotonic()
    try:
        assert asyncio.run(loops._live_price_batch(["AAPL"])) == {"AAPL": 190.0}
    finally:
        side_engine.reset()
    assert time.monotonic() - started < 10 and layer_on.calls == 1


def test_off_mode_keeps_the_legacy_monitor_path(monkeypatch):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "off")
    monkeypatch.setattr(plan_manager, "monitor_quotes", lambda t: pytest.fail("layer path"))
    seen = []
    monkeypatch.setattr(loops, "_run_bounded",
                        lambda fn, args, timeout, label: seen.append(fn.keywords) or {"AAPL": 1.0})
    assert asyncio.run(loops._live_price_batch(["AAPL"])) == {"AAPL": 1.0}
    assert seen == [{"allow_stale": False}]


def test_on_mode_monitor_failure_is_a_warning_and_empty(monkeypatch, caplog):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")

    def boom(tickers):
        raise TimeoutError("hung")
    monkeypatch.setattr(plan_manager, "monitor_quotes", boom)
    with caplog.at_level(logging.DEBUG, logger=loops.log.name):
        assert asyncio.run(loops._live_price_batch(["AAPL"])) == {}
    assert [r.levelno for r in caplog.records if r.name == loops.log.name] == [logging.WARNING]
