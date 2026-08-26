"""
commands/scanning.py's trade_monitor background task (60s interval).

Production incident (2026-08-24): open v2-plan trades breached their
stop-loss (confirmed against live quotes) and stayed "open" for hours.
Root cause: trade_monitor skipped its ENTIRE tick whenever a scan was
running, on the assumption "the full scan already handles SL/TP this
tick" -- but the full scan's own SL/TP check (TradeLog.update_open_trades)
explicitly excludes any trade with a plan_id, which is every trade now
that PLAN_ENGINE_V2 is on. Combined with scans now taking minutes,
trade_monitor's skip meant plan-linked trades' stops/targets went
unmonitored for most of the day.

No pytest-asyncio in this repo -- coroutines are driven with asyncio.run().
"""
import asyncio

from swingbot.commands import scanning as scanning_mod
from swingbot.core.scanning import engine as scan_engine
from swingbot.core.planning.plan_manager import PlanEvent


def _run(coro):
    return asyncio.run(coro)


def test_trade_monitor_still_checks_sl_tp_while_a_scan_is_running(monkeypatch):
    monkeypatch.setattr(scan_engine, "is_scan_running", lambda: True)

    calls = {"close": 0, "near_tp": 0, "manager_tick": 0}

    monkeypatch.setattr(
        scanning_mod.trade_log, "get_trades",
        lambda status=None, limit=None: [{"ticker": "AAPL", "id": "t1", "status": "open"}],
    )
    monkeypatch.setattr(scanning_mod, "get_current_price", lambda t: 100.0)

    def fake_close(ticker, live):
        calls["close"] += 1
        return []

    def fake_near_tp(ticker, live):
        calls["near_tp"] += 1
        return []

    def fake_tick():
        calls["manager_tick"] += 1
        return []

    monkeypatch.setattr(scanning_mod.trade_log, "close_if_live_price_hit", fake_close)
    monkeypatch.setattr(scanning_mod.trade_log, "check_near_tp_timeout", fake_near_tp)
    monkeypatch.setattr("swingbot.core.planning.plan_manager.run_manager_tick", fake_tick)

    _run(scanning_mod.trade_monitor.coro())

    assert calls["close"] == 1, "close_if_live_price_hit must run even mid-scan"
    assert calls["near_tp"] == 1, "check_near_tp_timeout must run even mid-scan"
    assert calls["manager_tick"] == 1, (
        "run_manager_tick is the ONLY code path that monitors plan_id-linked "
        "trades' SL/TP -- it must never be skipped just because a scan is running"
    )


def test_trade_monitor_skips_cleanly_when_there_are_no_open_trades(monkeypatch):
    """Unrelated to the scan-running bug: still a real early-exit worth
    keeping -- no work to do costs no work."""
    monkeypatch.setattr(scan_engine, "is_scan_running", lambda: False)
    monkeypatch.setattr(scanning_mod.trade_log, "get_trades",
                        lambda status=None, limit=None: [])

    calls = {"tick": 0}
    monkeypatch.setattr("swingbot.core.planning.plan_manager.run_manager_tick",
                        lambda: calls.__setitem__("tick", calls["tick"] + 1) or [])

    _run(scanning_mod.trade_monitor.coro())

    assert calls["tick"] == 0

def test_unknown_plan_event_transition_does_not_escape_monitor(monkeypatch):
    class Plan:
        plan_id = "p1"
        ticker = "AAPL"
        strategy = "RSI"
        horizon_key = "2w"
        direction = "bullish"
        badge = "VALIDATED"

    monkeypatch.setattr("swingbot.core.planning.plan_store.PlanStore", lambda: type("Store", (), {"get": lambda _, __: Plan()})())
    from swingbot.core.scanning.embeds import notify_plan_events
    _run(notify_plan_events(scanning_mod.bot, [PlanEvent("p1", "pyramid_add", {})]))
