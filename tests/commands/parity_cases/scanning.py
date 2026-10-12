"""Reply-parity cases for swingbot/commands/scanning/commands.py (v153 SP16)."""
import datetime as dt

from swingbot.bot_core import bot
from swingbot.commands.scanning import commands as commands_mod
from tests.commands.reply_harness import ParityCase

_FUNNEL = {"scenarios_found": 7, "failed_min_confluence": 3, "failed_min_confidence": 2,
           "conf_level_counts": {4: 1, 5: 1}}


def _trade(number: int, horizon: str = "4w") -> dict:
    return {"id": f"trade-{number}", "ticker": f"T{number:03d}", "opened_at": "2026-08-01T09:30:00+00:00",
            "horizon_key": horizon, "direction": "bullish" if number % 2 else "bearish", "status": "open",
            "entry": 100.0, "stop_loss": 95.0, "take_profit": 110.0, "confidence_level": 3,
            "strategy": "MACD"}


def stub_scan(alerts=(), *, funnel=None, stopped=False, on_scan=lambda: None):
    """run_scan returns `alerts`; every alert sender posts one line per alert
    to its destination, so the destination (the reply) is observable."""
    def stub(monkeypatch):
        async def run_scan(*, horizon_filter, require_confirmation, bot, progress, min_confluence):
            on_scan()
            progress.funnel = funnel
            progress.stopped = stopped
            return list(alerts)

        async def send_each(destination, alerts, **_kw):
            for alert in alerts:
                await destination.send(content=f"alert {alert}")

        async def no_short(destination, **_kw):
            return []
        monkeypatch.setattr(commands_mod.scan_engine, "run_scan", run_scan)
        monkeypatch.setattr(commands_mod, "_send_alerts", send_each)
        monkeypatch.setattr(commands_mod, "send_then_short", send_each)
        monkeypatch.setattr(commands_mod, "post_short_universe", no_short)
    return stub


def _stub_history(trades):
    def stub(monkeypatch):
        monkeypatch.setattr(commands_mod.trade_log, "get_trades", lambda **_kw: list(trades))
    return stub


def _stub_recap(monkeypatch):
    async def post(channel_id_override=None, today=None):
        return None
    monkeypatch.setattr(commands_mod.recap, "_post_retrospective", post)


def _recap_fails(monkeypatch):
    async def post(channel_id_override=None, today=None):
        raise RuntimeError("no trades table")
    monkeypatch.setattr(commands_mod.recap, "_post_retrospective", post)


def _stub_state(*, paused=False, running=False, active=True):
    def stub(monkeypatch):
        monkeypatch.setattr(commands_mod.runstate, "is_scan_paused", lambda: paused)
        monkeypatch.setattr(commands_mod.runstate, "set_scan_paused", lambda value: None)

        async def refresh():
            return None
        monkeypatch.setattr(commands_mod.presence, "_refresh_presence", refresh)
        monkeypatch.setattr(commands_mod.scan_engine, "is_scan_running", lambda: running)
        monkeypatch.setattr(commands_mod.scan_engine, "request_stop", lambda: None)
        monkeypatch.setattr(commands_mod, "in_session", lambda: active)
        monkeypatch.setattr("swingbot.bot_core.in_session", lambda: active)
        monkeypatch.setattr(commands_mod, "_session_now",
                            lambda: dt.datetime(2026, 10, 9, 15, 30, tzinfo=commands_mod.SESSION_TZ))
        monkeypatch.setattr(commands_mod, "load_watchlist", lambda: ["AAPL", "MSFT"])
        monkeypatch.setattr(commands_mod.trade_log, "get_stats", lambda: {"open": 2, "win": 5, "loss": 3})
        # bot.latency is NaN while the bot is not connected; round(NaN) raises.
        monkeypatch.setattr(type(bot), "latency", property(lambda self: 0.042))
    return stub


CASES = [
    ParityCase("scanning_recap_today", commands_mod.handle_recap, stub=_stub_recap, fail_stub=_recap_fails),
    ParityCase("scanning_recap_bad_date", commands_mod.handle_recap, args=("09/10/2026",), expect="error"),
    ParityCase("scanning_check_alerts", commands_mod.handle_check, args=("4w", 2),
               stub=stub_scan(["A", "B"], funnel=_FUNNEL), expect="edit"),
    ParityCase("scanning_check_no_alerts_funnel", commands_mod.handle_check,
               stub=stub_scan([], funnel=_FUNNEL), expect="edit"),
    ParityCase("scanning_check_no_alerts_plain", commands_mod.handle_check, stub=stub_scan([]), expect="edit"),
    ParityCase("scanning_check_stopped", commands_mod.handle_check,
               stub=stub_scan(["A"], stopped=True), expect="edit"),
    ParityCase("scanning_check_historical", commands_mod.handle_check, args=("4w",),
               kwargs={"date_from": "2026-08-01", "date_to": "2026-08-31"},
               stub=_stub_history([_trade(i) for i in range(30)] + [_trade(99, "2w")]), expect="multi_send"),
    ParityCase("scanning_check_historical_empty", commands_mod.handle_check,
               kwargs={"date_from": "2027-01-01"}, stub=_stub_history([_trade(1)])),
    ParityCase("scanning_session", commands_mod.handle_session, stub=_stub_state(paused=True)),
    ParityCase("scanning_status", commands_mod.handle_status, stub=_stub_state(active=False)),
    ParityCase("scanning_pause", commands_mod.handle_pause, stub=_stub_state(paused=False)),
    ParityCase("scanning_pause_already", commands_mod.handle_pause, stub=_stub_state(paused=True)),
    ParityCase("scanning_resume", commands_mod.handle_resume, stub=_stub_state(paused=True)),
    ParityCase("scanning_resume_already", commands_mod.handle_resume, stub=_stub_state(paused=False)),
    ParityCase("scanning_stop", commands_mod.handle_stop, stub=_stub_state(running=True)),
    ParityCase("scanning_stop_nothing_running", commands_mod.handle_stop, stub=_stub_state(running=False)),
]
