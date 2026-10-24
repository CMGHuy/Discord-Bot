"""v184 V184-5: trade_monitor's per-ticker checks and its plan-manager tick,
extracted into helpers whose return values carry what the liveness stamp
(V184-7) needs -- which tickers' checks raised, and whether the manager
raised -- without changing a single close, skip or log line.

No pytest-asyncio in this repo -- coroutines are driven with asyncio.run().
"""
import asyncio
import logging

import pytest

from swingbot.commands.scanning import loops
from swingbot.core.planning import plan_manager


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def calls(monkeypatch):
    """Record every close-path call; each fake returns what `results` says,
    or raises when the value is an exception instance."""
    log = []
    results = {}

    def fake(name):
        def _call(ticker, live):
            log.append((name, ticker, live))
            out = results.get((name, ticker), [])
            if isinstance(out, Exception):
                raise out
            return out
        return _call

    monkeypatch.setattr(loops.trade_log, "close_if_live_price_hit", fake("close"))
    monkeypatch.setattr(loops.trade_log, "check_near_tp_timeout", fake("near_tp"))
    return log, results


def test_one_ticker_runs_close_then_near_tp_and_returns_both_closes(calls):
    log, results = calls
    results[("close", "AAPL")] = [{"id": "t1"}]
    results[("near_tp", "AAPL")] = [{"id": "t2"}]
    closed, errored = _run(loops._check_open_ticker("AAPL", 100.0))
    assert closed == [{"id": "t1"}, {"id": "t2"}]
    assert errored is False
    assert log == [("close", "AAPL", 100.0), ("near_tp", "AAPL", 100.0)]


def test_a_raising_close_skips_near_tp_and_reports_an_error(calls, caplog):
    log, results = calls
    results[("close", "AAPL")] = RuntimeError("db gone")
    with caplog.at_level(logging.WARNING, logger=loops.log.name):
        closed, errored = _run(loops._check_open_ticker("AAPL", 100.0))
    assert (closed, errored) == ([], True)
    assert log == [("close", "AAPL", 100.0)]
    assert any("close_if_live_price_hit failed for AAPL" in r.getMessage() for r in caplog.records)


def test_a_raising_near_tp_keeps_the_trades_the_close_already_closed(calls, caplog):
    log, results = calls
    results[("close", "AAPL")] = [{"id": "t1"}]
    results[("near_tp", "AAPL")] = RuntimeError("boom")
    with caplog.at_level(logging.WARNING, logger=loops.log.name):
        closed, errored = _run(loops._check_open_ticker("AAPL", 100.0))
    assert (closed, errored) == ([{"id": "t1"}], True)
    assert any("check_near_tp_timeout failed for AAPL" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("price", [None, 0, 0.0, -1.0])
def test_an_unpriced_ticker_is_skipped_before_any_call(calls, price):
    log, _ = calls
    prices = {} if price is None else {"AAPL": price}
    closed, errors = _run(loops._check_open_tickers(["AAPL"], prices))
    assert (closed, errors) == ([], [])
    assert log == []


def test_check_errors_list_the_raising_tickers_in_order_and_the_rest_still_run(calls):
    log, results = calls
    results[("close", "MSFT")] = RuntimeError("x")
    results[("near_tp", "NVDA")] = RuntimeError("y")
    results[("close", "AAPL")] = [{"id": "a"}]
    closed, errors = _run(loops._check_open_tickers(
        ["MSFT", "AAPL", "NVDA"], {"MSFT": 1.0, "AAPL": 2.0, "NVDA": 3.0}))
    assert closed == [{"id": "a"}]
    assert errors == ["MSFT", "NVDA"]
    assert [c[:2] for c in log] == [("close", "MSFT"), ("close", "AAPL"), ("near_tp", "AAPL"),
                                    ("close", "NVDA"), ("near_tp", "NVDA")]


def test_manager_tick_returns_its_events_and_no_error(monkeypatch):
    monkeypatch.setattr(plan_manager, "run_manager_tick", lambda: ["e1"])
    assert _run(loops._run_plan_manager_tick()) == (["e1"], False)


def test_a_raising_manager_tick_is_logged_and_reported(monkeypatch, caplog):
    def boom():
        raise RuntimeError("store locked")
    monkeypatch.setattr(plan_manager, "run_manager_tick", boom)
    with caplog.at_level(logging.WARNING, logger=loops.log.name):
        assert _run(loops._run_plan_manager_tick()) == ([], True)
    assert any("plan manager tick failed" in r.getMessage() for r in caplog.records)
