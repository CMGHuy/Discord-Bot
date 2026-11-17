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
import datetime as dt
from unittest.mock import patch

import pytest

from swingbot import config
from swingbot.commands import scanning as scanning_mod
from swingbot.commands.scanning import loops


def _run(coro):
    return asyncio.run(coro)


class _FakeReport:
    def __init__(self, text="excursion upgrade: read 3, upgraded 5min 2"):
        self.text = text

    def line(self):
        return self.text


@pytest.fixture(autouse=True)
def _stub_excursion_pass(monkeypatch):
    """Every test here starts with no pass run today and a fake pass."""
    calls = []

    def fake_upgrade(since, until=None, **kwargs):
        calls.append({"since": since, "until": until, **kwargs})
        return _FakeReport()

    monkeypatch.setattr(loops, "_EXCURSION_PASS_DATE", None)
    monkeypatch.setattr(
        "swingbot.core.analytics.excursion_upgrade.upgrade_excursions", fake_upgrade)
    return calls


def _fresh_refresh(symbols, timeframes, **_kwargs):
    return {"summary": {tf: {"full": 0, "incremental": 0, "fresh": 1,
                             "failed": 0, "added": 0} for tf in timeframes},
            "failures": [], "state": {}, "deadline_hit": False}


def _enable_refresh(monkeypatch, refresh=_fresh_refresh):
    monkeypatch.setattr(config, "MARKET_DATA_AUTO_REFRESH", True, raising=False)
    monkeypatch.setattr(config, "MARKET_DATA_TIMEFRAMES", "daily,5min", raising=False)
    monkeypatch.setattr(loops, "load_watchlist", lambda: ["AAPL"], raising=False)
    monkeypatch.setattr(loops, "_refresh_priority_tickers", lambda: [])
    monkeypatch.setattr("swingbot.core.marketdata.data_refresh.refresh_all", refresh)


def test_market_data_refresh_passes_its_configured_time_budget(monkeypatch):
    captured = {}

    def fake_refresh_all(symbols, timeframes, **kwargs):
        captured.update(kwargs)
        return {"summary": {tf: {"full": 0, "incremental": 0, "fresh": 1,
                                 "failed": 0, "added": 0} for tf in timeframes},
                "failures": [], "state": {}, "deadline_hit": False}

    monkeypatch.setattr(config, "MARKET_DATA_AUTO_REFRESH", True, raising=False)
    monkeypatch.setattr(config, "MARKET_DATA_REFRESH_BUDGET_SECONDS", 77, raising=False)
    monkeypatch.setattr("swingbot.commands.scanning.loops.load_watchlist", lambda: ["AAPL"])
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
    monkeypatch.setattr("swingbot.commands.scanning.loops.load_watchlist", lambda: ["AAPL"])
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
    monkeypatch.setattr("swingbot.commands.scanning.loops.load_watchlist", lambda: ["AAPL"])
    monkeypatch.setattr("swingbot.core.marketdata.data_refresh.refresh_all", fake_refresh_all)

    with caplog.at_level("WARNING"):
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


def test_sub_hourly_frames_refresh_after_hourly(monkeypatch):
    """v87: when the sweep's time budget binds, the frames it defers must be
    the archive-only ones (15min/5min), never hourly, which feeds live E29
    context."""
    from swingbot.commands.scanning import loops as loops_mod

    captured = {}

    def fake_refresh_all(symbols, timeframes, **_kwargs):
        captured["timeframes"] = timeframes
        return {"summary": {tf: {"full": 0, "incremental": 0, "fresh": 1,
                                  "failed": 0, "added": 0} for tf in timeframes},
                "failures": [], "state": {}, "deadline_hit": False}

    monkeypatch.setattr(config, "MARKET_DATA_AUTO_REFRESH", True, raising=False)
    monkeypatch.setattr(config, "MARKET_DATA_TIMEFRAMES", "5min,15min,hourly,daily",
                        raising=False)
    monkeypatch.setattr(loops_mod, "load_watchlist", lambda: ["AAPL"], raising=False)
    monkeypatch.setattr(loops_mod, "_refresh_priority_tickers", lambda: [])
    monkeypatch.setattr("swingbot.core.marketdata.data_refresh.refresh_all", fake_refresh_all)

    _run(scanning_mod.market_data_refresh.coro())

    order = captured["timeframes"]
    assert order.index("hourly") < order.index("15min")
    assert order.index("hourly") < order.index("5min")


def test_the_pass_constants_match_the_spec():
    assert loops.EXCURSION_PASS_DAYS == 7
    assert loops.EXCURSION_PASS_BUDGET_S == 60.0


def test_the_pass_runs_after_the_refresh_with_its_window_and_budget(
        monkeypatch, _stub_excursion_pass):
    order = []

    def refresh(symbols, timeframes, **kwargs):
        order.append("refresh")
        return _fresh_refresh(symbols, timeframes, **kwargs)

    def fake_upgrade(since, until=None, **kwargs):
        order.append("pass")
        _stub_excursion_pass.append({"since": since, "until": until, **kwargs})
        return _FakeReport()

    monkeypatch.setattr(
        "swingbot.core.analytics.excursion_upgrade.upgrade_excursions", fake_upgrade)
    _enable_refresh(monkeypatch, refresh)

    _run(scanning_mod.market_data_refresh.coro())

    assert order == ["refresh", "pass"]
    call = _stub_excursion_pass[0]
    today = dt.datetime.now(dt.timezone.utc).date()
    expected = dt.datetime.combine(today - dt.timedelta(days=7), dt.time(),
                                   tzinfo=dt.timezone.utc).isoformat()
    assert call["since"] == expected
    assert call["until"] is None
    assert call["budget_seconds"] == 60.0


def test_the_pass_runs_at_most_once_per_utc_date(_stub_excursion_pass):
    day = dt.date(2026, 11, 14)
    _run(loops._run_excursion_pass(day))
    _run(loops._run_excursion_pass(day))
    assert len(_stub_excursion_pass) == 1
    assert loops._EXCURSION_PASS_DATE == day


def test_a_new_utc_date_runs_the_pass_again(_stub_excursion_pass):
    _run(loops._run_excursion_pass(dt.date(2026, 11, 14)))
    _run(loops._run_excursion_pass(dt.date(2026, 11, 15)))
    assert [c["since"] for c in _stub_excursion_pass] == [
        "2026-11-07T00:00:00+00:00", "2026-11-08T00:00:00+00:00"]


def test_the_pass_runs_in_a_worker_thread(monkeypatch):
    seen = []
    real = asyncio.to_thread

    async def spy(fn, *args, **kwargs):
        seen.append(getattr(fn, "__name__", repr(fn)))
        return await real(fn, *args, **kwargs)

    monkeypatch.setattr(loops.asyncio, "to_thread", spy)
    _run(loops._run_excursion_pass(dt.date(2026, 11, 14)))
    assert seen == ["fake_upgrade"]


def test_the_pass_logs_one_info_line_with_the_report():
    with patch.object(loops.log, "info") as info:
        _run(loops._run_excursion_pass(dt.date(2026, 11, 14)))
    assert info.call_count == 1
    assert info.call_args.args[0] == "market_data_refresh: %s"
    assert info.call_args.args[1].startswith("excursion upgrade:")


def test_a_failing_pass_is_logged_never_raised_and_not_retried_that_day(monkeypatch):
    calls = []

    def boom(since, until=None, **kwargs):
        calls.append(since)
        raise RuntimeError("journal unreachable")

    monkeypatch.setattr("swingbot.core.analytics.excursion_upgrade.upgrade_excursions", boom)
    day = dt.date(2026, 11, 14)
    with patch.object(loops.log, "exception") as exception:
        _run(loops._run_excursion_pass(day))
        _run(loops._run_excursion_pass(day))
    assert len(calls) == 1
    assert "excursion upgrade failed" in str(exception.call_args)


def test_a_failing_pass_never_fails_the_refresh(monkeypatch):
    def boom(since, until=None, **kwargs):
        raise RuntimeError("journal unreachable")

    monkeypatch.setattr("swingbot.core.analytics.excursion_upgrade.upgrade_excursions", boom)
    _enable_refresh(monkeypatch)
    with patch.object(loops.log, "exception") as exception:
        _run(scanning_mod.market_data_refresh.coro())   # must not raise
    assert "excursion upgrade failed" in str(exception.call_args)


def test_a_failed_refresh_skips_the_pass_and_leaves_the_date_unstamped(
        monkeypatch, _stub_excursion_pass):
    def refresh(symbols, timeframes, **kwargs):
        raise RuntimeError("provider down")

    _enable_refresh(monkeypatch, refresh)
    _run(scanning_mod.market_data_refresh.coro())
    assert _stub_excursion_pass == []
    assert loops._EXCURSION_PASS_DATE is None


def test_auto_refresh_off_runs_no_pass(monkeypatch, _stub_excursion_pass):
    monkeypatch.setattr(config, "MARKET_DATA_AUTO_REFRESH", False, raising=False)
    _run(scanning_mod.market_data_refresh.coro())
    assert _stub_excursion_pass == []


def test_a_budget_hit_refresh_still_runs_the_pass(monkeypatch, _stub_excursion_pass):
    def refresh(symbols, timeframes, **kwargs):
        result = _fresh_refresh(symbols, timeframes)
        result["deadline_hit"] = True
        return result

    _enable_refresh(monkeypatch, refresh)
    _run(scanning_mod.market_data_refresh.coro())
    assert len(_stub_excursion_pass) == 1
