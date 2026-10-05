import asyncio
import datetime as dt

from swingbot import config
from swingbot.commands import scanning as scanning_mod
from swingbot.commands.scanning import loops as loops_mod
from swingbot.core.db.repositories.scheduled import scheduled_repo


def test_daily_recap_does_not_refire_after_simulated_restart(monkeypatch):
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

    monkeypatch.setattr(config, "SESSION_END_HOUR", 23)
    monkeypatch.setattr(loops_mod.dt, "datetime", FixedDateTime)
    monkeypatch.setattr(loops_mod.recap, "_post_retrospective", post)
    monkeypatch.setattr(loops_mod, "_recap_fired_date", None)

    asyncio.run(scanning_mod.daily_recap.coro())
    monkeypatch.setattr(loops_mod, "_recap_fired_date", None)
    asyncio.run(scanning_mod.daily_recap.coro())

    assert calls == [True]
    assert scheduled_repo().fired_on("daily_recap") == "2026-08-24"


def test_weekly_earnings_refresh_runs_once_at_saturday_3am(monkeypatch):
    now = dt.datetime(2026, 8, 22, 3, 0)  # Saturday.

    class FixedDateTime:
        @classmethod
        def now(cls, tz=None):
            return now.replace(tzinfo=tz)

    calls = []
    monkeypatch.setattr(loops_mod.dt, "datetime", FixedDateTime)
    monkeypatch.setattr(loops_mod, "load_watchlist", lambda: ["AAPL"])
    monkeypatch.setattr(loops_mod, "_earnings_refresh_fired_date", None)
    monkeypatch.setattr(
        "swingbot.core.market.earnings_history.refresh_watchlist_earnings",
        lambda symbols: calls.append(symbols) or {"symbols": {"AAPL": {}}},
    )

    asyncio.run(scanning_mod.weekly_earnings_refresh.coro())
    asyncio.run(scanning_mod.weekly_earnings_refresh.coro())

    assert calls == [["AAPL"]]
    assert scheduled_repo().fired_on("weekly_earnings_refresh") == "2026-08-22"
