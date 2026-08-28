import asyncio
import datetime as dt

from swingbot import config
from swingbot.commands import scanning as scanning_mod
from swingbot.commands.scanning import loops as loops_mod
from swingbot.core.infra.jsonio import read_json


def test_daily_recap_does_not_refire_after_simulated_restart(monkeypatch, tmp_path):
    now = dt.datetime(2026, 8, 24, 23, 15)  # Monday, at the recap trigger.

    class FixedDateTime:
        @classmethod
        def now(cls, tz=None):
            return now.replace(tzinfo=tz)

        @classmethod
        def utcnow(cls):
            return now

    calls = []

    async def post():
        calls.append(True)

    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "SESSION_END_HOUR", 23)
    monkeypatch.setattr(loops_mod.dt, "datetime", FixedDateTime)
    monkeypatch.setattr(loops_mod.recap, "_post_retrospective", post)
    monkeypatch.setattr(loops_mod, "_recap_fired_date", None)

    asyncio.run(scanning_mod.daily_recap.coro())
    monkeypatch.setattr(loops_mod, "_recap_fired_date", None)
    asyncio.run(scanning_mod.daily_recap.coro())

    assert calls == [True]
    assert read_json(str(tmp_path / "scheduled_jobs.json"), {}) == {
        "daily_recap": "2026-08-24"
    }