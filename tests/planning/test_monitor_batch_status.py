"""v184: the per-tick fetch-failed flag. A failed or timed-out bounded quote batch
(_run_bounded returned None, or the call raised) marks the tick; an empty but
successful batch does not. Return values are unchanged."""
import asyncio

import pytest

from swingbot import config
from swingbot.commands.scanning import loops
from swingbot.core.marketdata.shared.kinds import QuoteDetail
from swingbot.core.planning import plan_manager as pm
from swingbot.core.scanning import fetch


@pytest.fixture(autouse=True)
def _clear_flag():
    pm.reset_monitor_batch_status()
    yield
    pm.reset_monitor_batch_status()


def _quiet_counters(monkeypatch):
    from swingbot.core.marketdata.shared import counters
    monkeypatch.setattr(counters, "merge", lambda rows: None)
    monkeypatch.setattr(counters, "flush", lambda **k: 0)


def _q(price=190.0):
    return QuoteDetail(symbol="AAPL", price=price, trade_at=None, bid=None, ask=None,
                       quote_at=None, source="alpaca-iex")


# -- the flag itself ---------------------------------------------------------

def test_flag_is_clear_after_reset_and_sticky_until_the_next_reset():
    assert pm.monitor_batch_failed() is False
    pm.mark_monitor_batch_failed()
    assert pm.monitor_batch_failed() is True
    pm.mark_monitor_batch_failed()
    assert pm.monitor_batch_failed() is True
    pm.reset_monitor_batch_status()
    assert pm.monitor_batch_failed() is False


# -- plan_manager.monitor_quotes (layer on/count) ----------------------------

def test_monitor_quotes_marks_failed_when_the_bounded_batch_returns_none(monkeypatch):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    monkeypatch.setattr(fetch, "_run_bounded", lambda *a, **k: None)
    assert pm.monitor_quotes(["AAPL"]) == {}
    assert pm.monitor_batch_failed() is True


def test_monitor_quotes_empty_success_is_not_a_failure(monkeypatch):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    _quiet_counters(monkeypatch)
    monkeypatch.setattr(fetch, "_run_bounded", lambda *a, **k: ({}, []))
    assert pm.monitor_quotes(["AAPL"]) == {}
    assert pm.monitor_batch_failed() is False


def test_monitor_quotes_success_is_not_a_failure(monkeypatch):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    _quiet_counters(monkeypatch)
    q = _q()
    monkeypatch.setattr(fetch, "_run_bounded", lambda *a, **k: ({"AAPL": q.to_doc()}, []))
    assert pm.monitor_quotes(["AAPL"])["AAPL"].price == 190.0
    assert pm.monitor_batch_failed() is False


def test_monitor_quotes_with_no_tickers_never_marks(monkeypatch):
    monkeypatch.setattr(fetch, "_run_bounded", lambda *a, **k: pytest.fail("no fetch"))
    assert pm.monitor_quotes([]) == {}
    assert pm.monitor_batch_failed() is False


# -- plan_manager._legacy_price_batch (layer off) ----------------------------

def test_legacy_price_batch_marks_failed_on_none(monkeypatch):
    monkeypatch.setattr(fetch, "_run_bounded", lambda *a, **k: None)
    assert pm._legacy_price_batch(["AAPL"]) == {}
    assert pm.monitor_batch_failed() is True


def test_legacy_price_batch_empty_success_is_not_a_failure(monkeypatch):
    monkeypatch.setattr(fetch, "_run_bounded", lambda *a, **k: {})
    assert pm._legacy_price_batch(["AAPL"]) == {}
    assert pm.monitor_batch_failed() is False


def test_off_mode_monitor_quotes_marks_through_the_legacy_batch(monkeypatch):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "off")
    monkeypatch.setattr(fetch, "_run_bounded", lambda *a, **k: None)
    assert pm.monitor_quotes(["AAPL"]) == {}
    assert pm.monitor_batch_failed() is True


# -- loops._live_price_batch / _legacy_live_price_batch ----------------------

def test_live_price_batch_marks_failed_when_monitor_quotes_raises(monkeypatch):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")

    def boom(tickers):
        raise TimeoutError("hung")
    monkeypatch.setattr(pm, "monitor_quotes", boom)
    assert asyncio.run(loops._live_price_batch(["AAPL"])) == {}
    assert pm.monitor_batch_failed() is True


def test_live_price_batch_empty_quotes_is_not_a_failure(monkeypatch):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    monkeypatch.setattr(pm, "monitor_quotes", lambda tickers: {})
    assert asyncio.run(loops._live_price_batch(["AAPL"])) == {}
    assert pm.monitor_batch_failed() is False


def test_legacy_live_price_batch_marks_failed_on_none(monkeypatch):
    monkeypatch.setattr(loops, "_run_bounded", lambda fn, args, timeout, label: None)
    assert asyncio.run(loops._legacy_live_price_batch(["AAPL"])) == {}
    assert pm.monitor_batch_failed() is True


def test_legacy_live_price_batch_marks_failed_when_it_raises(monkeypatch):
    def boom(fn, args, timeout, label):
        raise RuntimeError("spawn failed")
    monkeypatch.setattr(loops, "_run_bounded", boom)
    assert asyncio.run(loops._legacy_live_price_batch(["AAPL"])) == {}
    assert pm.monitor_batch_failed() is True


def test_legacy_live_price_batch_success_is_not_a_failure(monkeypatch):
    monkeypatch.setattr(loops, "_run_bounded", lambda fn, args, timeout, label: {"AAPL": 1.0})
    assert asyncio.run(loops._legacy_live_price_batch(["AAPL"])) == {"AAPL": 1.0}
    assert pm.monitor_batch_failed() is False


def test_legacy_live_price_batch_with_no_tickers_never_marks(monkeypatch):
    monkeypatch.setattr(loops, "_run_bounded", lambda *a: pytest.fail("no fetch"))
    assert asyncio.run(loops._legacy_live_price_batch([])) == {}
    assert pm.monitor_batch_failed() is False
