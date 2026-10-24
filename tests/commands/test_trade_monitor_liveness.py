"""v184 V184-7: every trade_monitor tick ends by stamping the `monitor` key.

The stamp sits in a `finally`: a raised tick is still stamped (as `raised`,
with unknown positions), a raised plan manager reads as unknown rather than
checked, and a failing stamp never touches the closes. Order and arguments
of everything the tick did before v184 stay the same.

No pytest-asyncio in this repo -- coroutines are driven with asyncio.run().
"""
import asyncio
import datetime as dt

import pytest

from swingbot import config
from swingbot.commands import scanning as scanning_mod
from swingbot.commands.scanning import loops, monitor_liveness
from swingbot.core.planning import plan_manager
from swingbot.core.planning.plan_manager import PollDemand

REAL_LIVE_PRICE_BATCH = loops._live_price_batch
START = dt.datetime(2026, 10, 21, 13, 0, tzinfo=dt.timezone.utc)


def _run_tick():
    return asyncio.run(scanning_mod.trade_monitor.coro())


@pytest.fixture
def env(monkeypatch):
    """A stubbed tick: two open trades (AAPL, MSFT), both priced; closes
    return nothing; the manager returns no events and demanded nothing.
    `env["seq"]` records the order of every step, the stamp write last."""
    state = {"prices": {"AAPL": 100.0, "MSFT": 200.0}, "demand": None,
             "plan_errors": (), "events": [],
             "closed": {}, "seq": [], "writes": []}
    seq = state["seq"]
    monkeypatch.setattr(monitor_liveness, "_STATE", monitor_liveness.MonitorLiveness(started_at=START))

    def write(doc):
        seq.append("stamp")
        state["writes"].append(doc)
    monkeypatch.setattr(monitor_liveness, "_write", write)
    monkeypatch.setattr(loops.trade_log, "get_trades", lambda status=None, limit=None: [
        {"ticker": "AAPL", "id": "t1", "status": "open"},
        {"ticker": "MSFT", "id": "t2", "status": "open"}])

    async def prices(tickers):
        seq.append("prices")
        return {t: p for t, p in state["prices"].items() if t in tickers}
    monkeypatch.setattr(loops, "_live_price_batch", prices)

    def close(ticker, live):
        seq.append(f"close:{ticker}")
        return state["closed"].get(ticker, [])

    def near_tp(ticker, live):
        seq.append(f"near_tp:{ticker}")
        return []
    monkeypatch.setattr(loops.trade_log, "close_if_live_price_hit", close)
    monkeypatch.setattr(loops.trade_log, "check_near_tp_timeout", near_tp)

    def tick():
        seq.append("manager")
        return state["events"]
    monkeypatch.setattr(plan_manager, "run_manager_tick", tick)
    monkeypatch.setattr(plan_manager, "last_poll_demand", lambda: state["demand"])
    monkeypatch.setattr(plan_manager, "last_poll_check_errors",
                        lambda: state["plan_errors"], raising=False)

    async def post_events(events):
        seq.append("plan_events")

    async def equity(live_prices):
        seq.append("equity")

    async def retry():
        seq.append("retry")
    monkeypatch.setattr(loops, "_post_plan_events", post_events)
    monkeypatch.setattr(loops, "_record_equity_sample", equity)
    monkeypatch.setattr(loops, "_retry_notifications", retry)

    async def notify(bot, closed):
        seq.append("notify")

    async def presence():
        seq.append("presence")
    monkeypatch.setattr("swingbot.core.scanning.embeds.notify_closed_trades", notify)
    monkeypatch.setattr(loops.presence, "_refresh_presence", presence)
    return state


def _doc(env):
    assert len(env["writes"]) == 1, env["writes"]
    return env["writes"][0]


def _assert_tick_order(seq, suffix):
    assert seq[0] == "prices"
    assert seq[1:5] in (
        ["close:AAPL", "near_tp:AAPL", "close:MSFT", "near_tp:MSFT"],
        ["close:MSFT", "near_tp:MSFT", "close:AAPL", "near_tp:AAPL"],
    )
    assert seq[5:] == suffix


def test_a_clean_tick_stamps_ok_with_positions_and_advances_priced_at(env):
    _run_tick()
    doc = _doc(env)
    assert doc["outcome"] == "ok"
    assert doc["positions"] == ["AAPL", "MSFT"]
    assert doc["unquoted"] == [] and doc["unquoted_count"] == 0
    assert doc["check_errors"] == [] and doc["fetch_failed"] is False
    assert doc["priced_at"] is not None and doc["priced_at"] == doc["tick_at"]
    assert doc["started_at"] == "2026-10-21T13:00:00+00:00"


def test_the_stamp_is_the_last_step_and_nothing_else_moved(env):
    env["closed"]["AAPL"] = [{"id": "t1"}]
    env["events"] = ["ev"]
    _run_tick()
    _assert_tick_order(env["seq"], ["manager", "plan_events", "equity", "retry",
                                    "notify", "presence", "stamp"])


def test_an_unquoted_trade_ticker_is_still_skipped_and_now_reported(env):
    env["prices"] = {"AAPL": 100.0}
    _run_tick()
    doc = _doc(env)
    assert "close:MSFT" not in env["seq"]
    assert doc["unquoted"] == ["MSFT"] and doc["unquoted_count"] == 1
    assert doc["priced_at"] is None


def test_plan_tickers_poll_demanded_join_positions_and_unpriced_ones_are_unquoted(env):
    env["demand"] = PollDemand(demanded=("NVDA", "AAPL"), priced=frozenset({"AAPL"}))
    _run_tick()
    doc = _doc(env)
    assert doc["positions"] == ["AAPL", "MSFT", "NVDA"]
    assert doc["unquoted"] == ["NVDA"]
    assert doc["priced_at"] is None


def test_a_raising_close_call_is_a_check_error(env, monkeypatch):
    def close(ticker, live):
        env["seq"].append(f"close:{ticker}")
        if ticker == "AAPL":
            raise RuntimeError("store locked")
        return []
    monkeypatch.setattr(loops.trade_log, "close_if_live_price_hit", close)
    _run_tick()
    doc = _doc(env)
    assert doc["check_errors"] == ["AAPL"]
    assert "near_tp:AAPL" not in env["seq"] and "near_tp:MSFT" in env["seq"]
    assert doc["outcome"] == "ok" and doc["priced_at"] is None


def test_a_swallowed_plan_step_failure_does_not_refresh_priced_at(env, monkeypatch):
    monkeypatch.setattr(loops.trade_log, "get_trades",
                        lambda status=None, limit=None: [])
    env["demand"] = PollDemand(demanded=("NVDA",), priced=frozenset({"NVDA"}))
    env["plan_errors"] = ("NVDA",)
    _run_tick()
    doc = _doc(env)
    assert doc["positions"] == ["NVDA"]
    assert doc["unquoted"] == []
    assert doc["check_errors"] == ["NVDA"]
    assert doc["priced_at"] is None


def test_a_raising_manager_reads_as_unknown_not_checked(env, monkeypatch):
    def boom():
        env["seq"].append("manager")
        raise RuntimeError("plan store down")
    monkeypatch.setattr(plan_manager, "run_manager_tick", boom)
    _run_tick()
    doc = _doc(env)
    assert doc["positions"] is None
    assert doc["check_errors"] == [monitor_liveness.PLAN_MANAGER_ERROR]
    assert doc["priced_at"] is None
    assert "equity" in env["seq"] and "retry" in env["seq"]


def test_a_raised_tick_is_still_stamped_as_raised_and_the_error_escapes(env, monkeypatch):
    def broken(status=None, limit=None):
        raise RuntimeError("trades table gone")
    monkeypatch.setattr(loops.trade_log, "get_trades", broken)
    with pytest.raises(RuntimeError, match="trades table gone"):
        _run_tick()
    doc = _doc(env)
    assert doc["outcome"] == "raised"
    assert doc["positions"] is None and doc["priced_at"] is None
    assert env["seq"] == ["stamp"]


def test_a_restart_forgets_priced_at(env, monkeypatch):
    _run_tick()
    assert env["writes"][0]["priced_at"] is not None
    monkeypatch.setattr(monitor_liveness, "_STATE", monitor_liveness.MonitorLiveness(started_at=START))
    monkeypatch.setattr(plan_manager, "run_manager_tick",
                        lambda: (_ for _ in ()).throw(RuntimeError("x")))
    env["writes"].clear()
    _run_tick()
    assert _doc(env)["priced_at"] is None


def test_a_failed_bounded_fetch_sets_fetch_failed(env, monkeypatch):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "off")
    monkeypatch.setattr(loops, "_live_price_batch", REAL_LIVE_PRICE_BATCH)
    monkeypatch.setattr(loops, "_run_bounded", lambda fn, args, timeout, label: None)
    _run_tick()
    doc = _doc(env)
    assert doc["fetch_failed"] is True
    assert doc["unquoted"] == ["AAPL", "MSFT"]
    assert not any(step.startswith("close:") for step in env["seq"])


def test_the_fetch_failed_flag_is_reset_at_the_start_of_each_tick(env):
    plan_manager.mark_monitor_batch_failed()
    _run_tick()
    assert _doc(env)["fetch_failed"] is False


def test_a_raising_stamp_write_leaves_the_tick_untouched(env, monkeypatch):
    def boom(doc):
        raise RuntimeError("db down")
    monkeypatch.setattr(monitor_liveness, "_write", boom)
    env["closed"]["AAPL"] = [{"id": "t1"}]
    assert _run_tick() is None
    _assert_tick_order(env["seq"], ["manager", "equity", "retry", "notify", "presence"])
