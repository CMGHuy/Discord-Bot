"""v173 V173-27: the daily override-verdict check, weekdays at SESSION_END_HOUR:50 Berlin."""
import asyncio
import datetime as dt
import logging
import threading

import pytest

from swingbot import config
from swingbot.commands.scanning import loops as loops_mod
from swingbot.core.analytics import override_io
from swingbot.core.db.repositories.scheduled import scheduled_repo

JOB = "override_verdict_check"
_DT = dt.datetime  # captured before _tick patches dt.datetime on the shared module
MONDAY = dt.date(2026, 10, 12)


@pytest.fixture
def calls(monkeypatch):
    seen = []

    def fake_check(now, **kwargs):
        seen.append((now, threading.current_thread() is threading.main_thread()))
        return "waiting"

    monkeypatch.setattr(override_io, "run_daily_check", fake_check)
    monkeypatch.setattr(config, "SESSION_END_HOUR", 23)
    monkeypatch.setattr(loops_mod, "_override_verdict_fired_date", None)
    return seen


def _tick(monkeypatch, now: _DT, *, restart: bool = False) -> None:
    class FixedDateTime:
        @classmethod
        def now(cls, tz=None):
            return now.replace(tzinfo=tz)

    monkeypatch.setattr(loops_mod.dt, "datetime", FixedDateTime)
    if restart:
        monkeypatch.setattr(loops_mod, "_override_verdict_fired_date", None)
    asyncio.run(loops_mod.override_verdict_check.coro())


def test_fires_once_at_the_2350_slot_off_the_event_loop(monkeypatch, calls):
    _tick(monkeypatch, _DT(2026, 10, 12, 23, 49))
    _tick(monkeypatch, _DT(2026, 10, 12, 23, 50))
    _tick(monkeypatch, _DT(2026, 10, 12, 23, 51))
    assert len(calls) == 1
    now, on_main_thread = calls[0]
    assert on_main_thread is False                    # asyncio.to_thread
    assert now == _DT(2026, 10, 12, 23, 50, tzinfo=loops_mod.SESSION_TZ)
    assert scheduled_repo().fired_on(JOB) == MONDAY.isoformat()


def test_not_at_2349_and_not_outside_the_end_hour(monkeypatch, calls):
    _tick(monkeypatch, _DT(2026, 10, 12, 23, 49))
    _tick(monkeypatch, _DT(2026, 10, 12, 22, 55))
    assert calls == []
    assert scheduled_repo().fired_on(JOB) is None


def test_a_restart_on_the_same_day_does_not_fire_again(monkeypatch, calls):
    _tick(monkeypatch, _DT(2026, 10, 12, 23, 50))
    _tick(monkeypatch, _DT(2026, 10, 12, 23, 55), restart=True)
    assert len(calls) == 1


def test_it_runs_again_the_next_weekday(monkeypatch, calls):
    _tick(monkeypatch, _DT(2026, 10, 12, 23, 50))
    _tick(monkeypatch, _DT(2026, 10, 13, 23, 50))
    assert [now.date() for now, _ in calls] == [MONDAY, dt.date(2026, 10, 13)]


@pytest.mark.parametrize("day", [17, 18])           # Saturday, Sunday
def test_never_fires_on_a_weekend(monkeypatch, calls, day):
    _tick(monkeypatch, _DT(2026, 10, day, 23, 50))
    assert calls == []


def test_a_failing_check_is_logged_never_raised(monkeypatch, calls, caplog):
    def boom(now, **kwargs):
        raise RuntimeError("database down")

    monkeypatch.setattr(override_io, "run_daily_check", boom)
    with caplog.at_level(logging.ERROR, logger=loops_mod.log.name):
        _tick(monkeypatch, _DT(2026, 10, 12, 23, 50))
    assert any(JOB in r.getMessage() for r in caplog.records)


def test_a_failing_marker_read_is_logged_never_raised(monkeypatch, calls, caplog):
    def down(job, today):
        raise RuntimeError("scheduled_jobs unreachable")

    monkeypatch.setattr(loops_mod, "_scheduled_job_already_fired", down)
    with caplog.at_level(logging.ERROR, logger=loops_mod.log.name):
        _tick(monkeypatch, _DT(2026, 10, 12, 23, 50))
    assert calls == []
    assert any(JOB in r.getMessage() for r in caplog.records)


def test_the_result_is_logged(monkeypatch, calls, caplog):
    with caplog.at_level(logging.INFO, logger=loops_mod.log.name):
        _tick(monkeypatch, _DT(2026, 10, 12, 23, 50))
    assert any(r.getMessage() == "override_verdict_check: waiting" for r in caplog.records)


def test_the_loop_starts_with_the_bot_last_in_order():
    loops = loops_mod._always_on_loops()
    assert loops[-1] is loops_mod.override_verdict_check
    assert loops_mod.gate_counterfactual_resolve in loops          # nothing else dropped
