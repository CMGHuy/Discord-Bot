"""v164 D3: the instant, latched ops-channel flag of the live loss watch.

Latches use the real scheduled_repo() (autouse _store_database fixture,
tests/conftest.py); the watch itself is faked so no bootstrap runs here.
"""
import asyncio
import datetime as dt
import types

from swingbot import config
from swingbot.commands import scanning as scanning_mod
from swingbot.commands.scanning import loops as loops_mod
from swingbot.commands.scanning import notices, recap
from swingbot.core.analytics import calibration
from swingbot.core.db.repositories.scheduled import scheduled_repo
from swingbot.core.tracking import live_loss_watch as lw

DAY = dt.date(2026, 10, 20)          # a Tuesday


class _Chan:
    def __init__(self, *, fail=False):
        self.sent, self.fail = [], fail

    async def send(self, *args, **kwargs):
        if self.fail:
            raise RuntimeError("discord down")
        self.sent.append(kwargs)
        return types.SimpleNamespace(id=len(self.sent))     # a discord.Message stand-in


def _row(horizon="4w", *, alert=True, bound=-0.08):
    return {"source": "confluence", "strategy": "ALL", "horizon": horizon, "live_n": 31,
            "live_wr": 38.7, "live_expr": -0.27, "bound_upper": bound, "alert": alert,
            "registry_status": "WEAK", "registry_window_kind": "TRAIN",
            "registry_run_date": "2026-09-01", "registry_expr": -0.03}


def _wire(monkeypatch, rows, chan):
    monkeypatch.setattr(lw, "load_watch", lambda **kwargs: {"rows": rows, "counts": {}})
    monkeypatch.setattr(loops_mod, "_ops_channel", lambda: chan)


def _flag(day=DAY):
    return asyncio.run(loops_mod._post_live_loss_flags(day))


def test_flag_embed_names_the_row_and_states_the_meaning():
    embed = notices.live_loss_flag_embed(_row())
    assert embed.title == "📜 RETROSPECTIVE · live loss watch"
    assert "confluence / ALL / 4w" in embed.description
    assert calibration.LIVE_LOSS_MEANING in embed.description
    assert calibration.REGISTRY_CONTEXT_LABEL in embed.description
    assert "-0.08R" in embed.description and "-0.27R" in embed.description
    pooled = notices.live_loss_flag_embed(_row(None))
    assert "confluence / ALL / pooled" in pooled.description


def test_flag_embed_tolerates_missing_figures():
    row = dict(_row(), live_wr=None, registry_expr=None, registry_window_kind=None,
               registry_status=None, registry_run_date=None)
    assert "—" in notices.live_loss_flag_embed(row).description


def test_posts_once_per_alert_row_and_latches_it(monkeypatch):
    rows = [_row("4w"), _row("2w", alert=False, bound=0.1), _row(None, bound=-0.02)]
    chan = _Chan()
    _wire(monkeypatch, rows, chan)

    assert _flag() == 2
    assert len(chan.sent) == 2
    assert lw.is_latched(rows[0]) and lw.is_latched(rows[2])
    assert not lw.is_latched(rows[1])
    assert scheduled_repo().fired_on(lw.latch_job(rows[0])) == "2026-10-20"


def test_rerun_the_same_day_is_silent(monkeypatch):
    chan = _Chan()
    _wire(monkeypatch, [_row()], chan)
    assert _flag() == 1
    assert _flag() == 0
    assert len(chan.sent) == 1


def test_silent_while_latched_on_later_days(monkeypatch):
    chan = _Chan()
    _wire(monkeypatch, [_row()], chan)
    _flag()
    assert _flag(DAY + dt.timedelta(days=1)) == 0
    assert _flag(DAY + dt.timedelta(days=6)) == 0
    assert len(chan.sent) == 1


def test_re_arms_only_after_a_sunday_clear(monkeypatch):
    chan = _Chan()
    row = _row()
    _wire(monkeypatch, [row], chan)
    _flag()
    lw.clear_latches([dict(row, bound_upper=0.05, alert=False)])   # what Part 11 does
    assert _flag(DAY + dt.timedelta(days=7)) == 1
    assert len(chan.sent) == 2
    assert scheduled_repo().fired_on(lw.latch_job(row)) == "2026-10-27"


def test_a_failed_send_does_not_latch_and_retries_next_time(monkeypatch):
    row = _row()
    _wire(monkeypatch, [row], _Chan(fail=True))
    assert _flag() == 0
    assert not lw.is_latched(row)

    chan = _Chan()
    _wire(monkeypatch, [row], chan)
    assert _flag(DAY + dt.timedelta(days=1)) == 1
    assert lw.is_latched(row)


def test_no_ops_channel_posts_and_latches_nothing(monkeypatch):
    row = _row()
    _wire(monkeypatch, [row], None)
    assert _flag() == 0
    assert not lw.is_latched(row)


def test_a_raising_watch_never_escapes(monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("bootstrap exploded")

    monkeypatch.setattr(lw, "load_watch", boom)
    monkeypatch.setattr(loops_mod, "_ops_channel", lambda: _Chan())
    assert _flag() == 0


def _fixed_now(monkeypatch, now):
    class FixedDateTime:
        @classmethod
        def now(cls, tz=None):
            return now.replace(tzinfo=tz)

        @classmethod
        def utcnow(cls):
            return now

    monkeypatch.setattr(loops_mod.dt, "datetime", FixedDateTime)


def test_daily_recap_flags_after_the_retrospective_even_when_it_fails(monkeypatch):
    order = []

    async def post():
        order.append("retro")
        raise RuntimeError("retrospective exploded")

    async def flags(today):
        order.append(("flags", today))
        return 0

    async def prune():
        return None

    _fixed_now(monkeypatch, dt.datetime(2026, 10, 20, 23, 15))
    monkeypatch.setattr(config, "SESSION_END_HOUR", 23)
    monkeypatch.setattr(loops_mod.recap, "_post_retrospective", post)
    monkeypatch.setattr(loops_mod, "_post_live_loss_flags", flags)
    monkeypatch.setattr(loops_mod, "_prune_alert_posts", prune)
    monkeypatch.setattr(loops_mod, "_recap_fired_date", None)

    asyncio.run(scanning_mod.daily_recap.coro())

    assert order == ["retro", ("flags", DAY)]


def test_recap_command_path_never_flags(monkeypatch):
    """!recap / !recap <date> go through recap._post_retrospective with a
    channel override; only the scheduled daily_recap posts flags."""
    from swingbot.core.tracking import retrospective

    calls = []

    async def flags(today):
        calls.append(today)
        return 0

    async def resolve(*args, **kwargs):
        return _Chan()

    monkeypatch.setattr(loops_mod, "_post_live_loss_flags", flags)
    monkeypatch.setattr(retrospective, "build_daily_retrospective",
                        lambda trades, today=None: ["recap body"])
    monkeypatch.setattr(recap, "trade_log", types.SimpleNamespace(get_trades=lambda **kw: []))
    monkeypatch.setattr(recap, "_resolve_retrospective_channel", resolve)

    asyncio.run(recap._post_retrospective(channel_id_override=1, today=dt.date(2026, 10, 18)))
    asyncio.run(recap._post_retrospective(channel_id_override=1))

    assert calls == []
    assert not hasattr(recap, "loops")
