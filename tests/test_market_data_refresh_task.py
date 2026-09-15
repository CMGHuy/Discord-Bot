"""
commands/scanning.py's market_data_refresh background task.

Locks down two things a production incident (2026-08-24) showed were
missing: the sweep must be handed a time budget (MARKET_DATA_REFRESH_
BUDGET_SECONDS) rather than run unbounded, and hitting that budget must be
logged -- silent early exits are indistinguishable from "everything is
fine" in this codebase's convention (see CLAUDE.md, "background work must
be observable").

discord.py's @tasks.loop wraps the coroutine in a Loop object; `.coro` is
the underlying async function, callable directly without going through the
loop's own scheduling -- the documented way to unit-test a task body.
"""
import asyncio
from unittest.mock import patch

from swingbot import config
from swingbot.commands import scanning as scanning_mod


def _run(coro):
    return asyncio.run(coro)


def test_market_data_refresh_passes_its_configured_time_budget(monkeypatch):
    captured = {}

    def fake_refresh_all(symbols, timeframes, **kwargs):
        captured.update(kwargs)
        return {"summary": {tf: {"full": 0, "incremental": 0, "fresh": 1,
                                 "failed": 0, "added": 0} for tf in timeframes},
                "failures": [], "state": {}, "deadline_hit": False}

    monkeypatch.setattr(config, "MARKET_DATA_AUTO_REFRESH", True, raising=False)
    monkeypatch.setattr(config, "MARKET_DATA_REFRESH_BUDGET_SECONDS", 77, raising=False)
    monkeypatch.setattr(scanning_mod, "load_watchlist", lambda: ["AAPL"], raising=False)
    monkeypatch.setattr("swingbot.core.marketdata.data_refresh.refresh_all", fake_refresh_all)

    _run(scanning_mod.market_data_refresh.coro())

    assert captured.get("deadline_seconds") == 77


def test_market_data_refresh_logs_when_the_budget_is_hit(monkeypatch):
    def fake_refresh_all(symbols, timeframes, **kwargs):
        return {"summary": {tf: {"full": 1, "incremental": 0, "fresh": 0,
                                 "failed": 0, "added": 3} for tf in timeframes},
                "failures": [], "state": {}, "deadline_hit": True}

    monkeypatch.setattr(config, "MARKET_DATA_AUTO_REFRESH", True, raising=False)
    monkeypatch.setattr(config, "MARKET_DATA_REFRESH_BUDGET_SECONDS", 30, raising=False)
    monkeypatch.setattr(scanning_mod, "load_watchlist", lambda: ["AAPL"], raising=False)
    monkeypatch.setattr("swingbot.core.marketdata.data_refresh.refresh_all", fake_refresh_all)

    from swingbot.commands.scanning import loops
    with patch.object(loops.log, "warning") as warning:
        _run(scanning_mod.market_data_refresh.coro())

    assert "time budget" in str(warning.call_args)


def test_market_data_refresh_stays_quiet_when_the_budget_is_not_hit(monkeypatch, caplog):
    def fake_refresh_all(symbols, timeframes, **kwargs):
        return {"summary": {tf: {"full": 0, "incremental": 0, "fresh": 1,
                                 "failed": 0, "added": 0} for tf in timeframes},
                "failures": [], "state": {}, "deadline_hit": False}

    monkeypatch.setattr(config, "MARKET_DATA_AUTO_REFRESH", True, raising=False)
    monkeypatch.setattr(scanning_mod, "load_watchlist", lambda: ["AAPL"], raising=False)
    monkeypatch.setattr("swingbot.core.marketdata.data_refresh.refresh_all", fake_refresh_all)

    with caplog.at_level("WARNING", logger="swing-bot"):
        _run(scanning_mod.market_data_refresh.coro())

    assert not any("time budget" in r.message for r in caplog.records)


def test_market_data_refresh_prioritises_live_tickers_and_short_timeframes(monkeypatch):
    from swingbot.commands.scanning import loops as loops_mod

    captured = {}

    def fake_refresh_all(symbols, timeframes, **_kwargs):
        captured["symbols"] = symbols
        captured["timeframes"] = timeframes
        return {"summary": {tf: {"full": 0, "incremental": 0, "fresh": 1,
                                  "failed": 0, "added": 0} for tf in timeframes},
                "failures": [], "state": {}, "deadline_hit": False}

    monkeypatch.setattr(config, "MARKET_DATA_AUTO_REFRESH", True, raising=False)
    monkeypatch.setattr(config, "MARKET_DATA_TIMEFRAMES", "monthly,hourly,daily",
                        raising=False)
    monkeypatch.setattr(loops_mod, "load_watchlist", lambda: ["AAPL", "MSFT", "NVDA"],
                        raising=False)
    monkeypatch.setattr(loops_mod, "_refresh_priority_tickers", lambda: ["NVDA", "MSFT"])
    monkeypatch.setattr("swingbot.core.marketdata.data_refresh.refresh_all", fake_refresh_all)

    _run(scanning_mod.market_data_refresh.coro())

    assert captured["symbols"] == ["NVDA", "MSFT", "AAPL"]
    assert captured["timeframes"] == ["hourly", "daily", "monthly"]
