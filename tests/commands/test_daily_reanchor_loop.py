"""v171 D4 backstop: the weekly full re-anchor, once per Sunday 04:00 Berlin."""
import asyncio
import datetime as dt

import pytest

from swingbot import config
from swingbot.commands.scanning import loops as loops_mod
from swingbot.core.db.repositories.scheduled import scheduled_repo
from swingbot.core.marketdata import daily_delta
from swingbot.core.marketdata.shared.kinds import Asker

JOB = "daily_reanchor"
SUNDAY = dt.date(2026, 10, 18)
_REAL = dt.datetime   # loops_mod.dt is the shared module: patching datetime would break later constructions


def _tick(monkeypatch, when):
    class FixedDateTime:
        @classmethod
        def now(cls, tz=None):
            return when.replace(tzinfo=tz)
    monkeypatch.setattr(loops_mod.dt, "datetime", FixedDateTime)
    asyncio.run(loops_mod.daily_reanchor.coro())


@pytest.fixture
def calls(monkeypatch):
    got = []
    monkeypatch.setattr(config, "DAILY_DELTA_FETCH", True)
    monkeypatch.setattr(config, "REANCHOR_WEEKDAY", 6)
    monkeypatch.setattr(config, "REANCHOR_HOUR", 4)
    monkeypatch.setattr(loops_mod, "_reanchor_fired_date", None)
    monkeypatch.setattr(loops_mod, "_REANCHOR_PAUSE_S", 0.0)
    monkeypatch.setattr(loops_mod, "load_watchlist", lambda: ["AAPL", "SAP.DE", "XAUUSD"])

    def refetch(tickers, *, asker):
        got.append((list(tickers), asker))
        return {t: None for t in tickers}
    monkeypatch.setattr(daily_delta, "full_refetch", refetch)
    return got


def test_fires_once_in_the_slot_with_spot_mapped_to_its_future(monkeypatch, calls):
    _tick(monkeypatch, _REAL(2026, 10, 18, 3, 59))
    assert calls == []
    _tick(monkeypatch, _REAL(2026, 10, 18, 4, 7))
    monkeypatch.setattr(loops_mod, "_reanchor_fired_date", None)      # simulated restart
    _tick(monkeypatch, _REAL(2026, 10, 18, 4, 30))
    assert len(calls) == 1
    symbols, asker = calls[0]
    assert sorted(symbols) == ["AAPL", "GC=F", "SAP.DE"] and asker is Asker.BACKGROUND
    assert scheduled_repo().fired_on(JOB) == SUNDAY.isoformat()


def test_other_days_and_the_flag_off_do_nothing(monkeypatch, calls):
    _tick(monkeypatch, _REAL(2026, 10, 17, 4, 0))                 # Saturday
    monkeypatch.setattr(config, "DAILY_DELTA_FETCH", False)
    _tick(monkeypatch, _REAL(2026, 10, 18, 4, 0))
    assert calls == []


def test_the_watchlist_is_re_anchored_in_chunks_of_thirty(monkeypatch, calls):
    monkeypatch.setattr(loops_mod, "load_watchlist", lambda: [f"T{i:02d}" for i in range(65)])
    _tick(monkeypatch, _REAL(2026, 10, 25, 4, 0))                 # its own Sunday: markers persist
    assert [len(c[0]) for c in calls] == [30, 30, 5]


def test_a_failing_chunk_does_not_stop_the_rest(monkeypatch, calls):
    monkeypatch.setattr(loops_mod, "load_watchlist", lambda: [f"T{i:02d}" for i in range(65)])
    seen = []

    def flaky(tickers, *, asker):
        seen.append(len(tickers))
        if len(seen) == 1:
            raise RuntimeError("provider down")
        return {}
    monkeypatch.setattr(daily_delta, "full_refetch", flaky)
    _tick(monkeypatch, _REAL(2026, 11, 1, 4, 0))
    assert seen == [30, 30, 5]


def test_registered_as_an_always_on_loop_before_the_tape_feed():
    loops = loops_mod._always_on_loops()
    assert loops.index(loops_mod.daily_reanchor) < loops.index(loops_mod.tape_feed)
