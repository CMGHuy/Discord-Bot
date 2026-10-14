"""v147 V147-12: the nightly gate-counterfactual resolver loop."""
import asyncio
import datetime as dt
import logging
import threading

import pytest

from swingbot import config
from swingbot.commands.scanning import loops as loops_mod
from swingbot.core.backtesting import gate_resolver
from swingbot.core.db.repositories.scheduled import scheduled_repo

JOB = "gate_counterfactual_resolve"
_DT = dt.datetime  # captured before _tick patches dt.datetime on the shared module
MONDAY = dt.date(2026, 10, 12)


@pytest.fixture
def calls(monkeypatch):
    seen = []

    def fake_resolve(today, **kwargs):
        seen.append((today, threading.current_thread() is threading.main_thread()))
        return {"filled": 1}

    monkeypatch.setattr(gate_resolver, "resolve_due", fake_resolve)
    monkeypatch.setattr(config, "SESSION_END_HOUR", 22)
    monkeypatch.setattr(loops_mod, "_gate_resolve_fired_date", None)
    return seen


def _tick(monkeypatch, now: _DT, *, restart: bool = False) -> None:
    class FixedDateTime:
        @classmethod
        def now(cls, tz=None):
            return now.replace(tzinfo=tz)

    monkeypatch.setattr(loops_mod.dt, "datetime", FixedDateTime)
    if restart:
        monkeypatch.setattr(loops_mod, "_gate_resolve_fired_date", None)
    asyncio.run(loops_mod.gate_counterfactual_resolve.coro())


def test_fires_once_at_the_slot_off_the_event_loop(monkeypatch, calls):
    _tick(monkeypatch, _DT(2026, 10, 12, 22, 44))
    _tick(monkeypatch, _DT(2026, 10, 12, 22, 45))
    _tick(monkeypatch, _DT(2026, 10, 12, 22, 46))
    assert calls == [("2026-10-12", False)]           # the ET session date, on a worker thread
    assert scheduled_repo().fired_on(JOB) == MONDAY.isoformat()


def test_a_restart_on_the_same_day_does_not_fire_again(monkeypatch, calls):
    _tick(monkeypatch, _DT(2026, 10, 12, 22, 45))
    _tick(monkeypatch, _DT(2026, 10, 12, 22, 50), restart=True)
    assert len(calls) == 1


@pytest.mark.parametrize("day", [10, 11])           # Saturday, Sunday
def test_never_fires_on_a_weekend(monkeypatch, calls, day):
    _tick(monkeypatch, _DT(2026, 10, day, 22, 45))
    assert calls == []


def test_a_failing_resolver_is_logged_never_raised(monkeypatch, calls, caplog):
    def boom(today, **kwargs):
        raise RuntimeError("database down")

    monkeypatch.setattr(gate_resolver, "resolve_due", boom)
    with caplog.at_level(logging.ERROR, logger=loops_mod.log.name):
        _tick(monkeypatch, _DT(2026, 10, 12, 22, 45))
    assert any("gate_counterfactual_resolve" in r.getMessage() for r in caplog.records)


def test_the_loop_starts_with_the_bot():
    assert loops_mod.gate_counterfactual_resolve in loops_mod._always_on_loops()
