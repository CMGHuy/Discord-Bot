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


def _fixed(now):
    class FixedDateTime:
        @classmethod
        def now(cls, tz=None):
            return now.replace(tzinfo=tz)
    return FixedDateTime


def _short_interest_stubs(monkeypatch, calls):
    from swingbot.core.market import short_interest
    monkeypatch.setattr(short_interest, "refresh_symbols", lambda: ["GME", "TSLA"])
    monkeypatch.setattr(short_interest, "refresh_short_interest",
                        lambda symbols: calls.append(symbols) or {"updated": 2, "failed": []})
    monkeypatch.setattr(loops_mod, "_short_interest_refresh_fired_date", None)


def test_daily_short_interest_refresh_runs_once_after_the_close(monkeypatch):
    calls = []
    monkeypatch.setattr(config, "SHORT_RISK_NOTICE", True)
    monkeypatch.setattr(loops_mod.dt, "datetime", _fixed(dt.datetime(2026, 10, 21, 23, 40)))  # Wednesday
    _short_interest_stubs(monkeypatch, calls)

    asyncio.run(scanning_mod.daily_short_interest_refresh.coro())
    monkeypatch.setattr(loops_mod, "_short_interest_refresh_fired_date", None)   # simulated restart
    asyncio.run(scanning_mod.daily_short_interest_refresh.coro())

    assert calls == [["GME", "TSLA"]]
    assert scheduled_repo().fired_on("daily_short_interest_refresh") == "2026-10-21"


def test_daily_short_interest_refresh_skips_weekends_and_other_minutes(monkeypatch):
    calls = []
    monkeypatch.setattr(config, "SHORT_RISK_NOTICE", True)
    _short_interest_stubs(monkeypatch, calls)
    for now in (dt.datetime(2026, 10, 24, 23, 40),      # Saturday
                dt.datetime(2026, 10, 21, 23, 39),
                dt.datetime(2026, 10, 21, 22, 40)):
        monkeypatch.setattr(loops_mod.dt, "datetime", _fixed(now))
        asyncio.run(scanning_mod.daily_short_interest_refresh.coro())
    assert calls == []


def test_daily_short_interest_refresh_fetches_nothing_while_the_notice_is_off(monkeypatch):
    calls = []
    monkeypatch.setattr(config, "SHORT_RISK_NOTICE", False)
    monkeypatch.setattr(loops_mod.dt, "datetime", _fixed(dt.datetime(2026, 10, 22, 23, 40)))
    _short_interest_stubs(monkeypatch, calls)
    asyncio.run(scanning_mod.daily_short_interest_refresh.coro())
    assert calls == []


def test_a_failed_short_interest_refresh_is_logged_not_raised(monkeypatch, caplog):
    from swingbot.core.market import short_interest
    monkeypatch.setattr(config, "SHORT_RISK_NOTICE", True)
    monkeypatch.setattr(loops_mod.dt, "datetime", _fixed(dt.datetime(2026, 10, 23, 23, 40)))
    monkeypatch.setattr(loops_mod, "_short_interest_refresh_fired_date", None)
    monkeypatch.setattr(short_interest, "refresh_symbols", lambda: ["GME"])

    def boom(symbols):
        raise RuntimeError("yahoo down")

    monkeypatch.setattr(short_interest, "refresh_short_interest", boom)
    asyncio.run(scanning_mod.daily_short_interest_refresh.coro())      # no exception
    assert "daily_short_interest_refresh: refresh failed" in caplog.text


def test_daily_short_interest_refresh_is_always_on_and_tape_feed_stays_last():
    loops = loops_mod._always_on_loops()
    assert loops.index(loops_mod.daily_short_interest_refresh) == loops.index(loops_mod.weekly_earnings_refresh) + 1
    assert loops[-1] is loops_mod.tape_feed
