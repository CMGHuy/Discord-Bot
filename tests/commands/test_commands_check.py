"""Regression coverage for bounded historical !check output."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

from swingbot.commands.scanning import commands as commands_mod
from swingbot.commands.reply import CtxReply


def _trade(number: int) -> dict:
    return {
        "id": f"trade-{number}",
        "ticker": f"T{number:03d}",
        "opened_at": "2026-08-01T09:30:00+00:00",
        "horizon_key": "swing",
        "direction": "bullish",
        "status": "open",
        "entry": 100.0,
        "stop_loss": 95.0,
        "take_profit": 110.0,
        "confidence_level": 3,
        "strategy": "breakout",
    }


def test_historical_check_batches_and_caps_large_result_sets(monkeypatch):
    """A broad date range must not turn hundreds of records into 429 pressure."""
    ctx = MagicMock()
    ctx.send = AsyncMock()
    monkeypatch.setattr(
        commands_mod.trade_log, "get_trades", lambda **_kwargs: [_trade(i) for i in range(300)]
    )

    asyncio.run(commands_mod._check_historical(CtxReply(ctx), "all", "2026-08-01", "2026-08-31"))

    assert ctx.send.await_count <= 10
    messages = [call.args[0] for call in ctx.send.await_args_list]
    assert all(len(message) <= 1900 for message in messages)
    assert any("showing the first" in message.lower() for message in messages)



# --- v153 SP16: handlers, edit semantics, the stale token, tips and twins -------

import datetime as dt
import inspect

from swingbot.bot_core import bot
from swingbot.commands import reply as reply_mod
from swingbot.commands.reply import TOKEN_LIFETIME_S, InteractionReply
from tests.commands.parity_cases.scanning import _FUNNEL, stub_scan
from tests.commands.reply_harness import FakeContext, FakeInteraction, run_both


def _tip_window_open(monkeypatch):
    monkeypatch.setattr(reply_mod, "_today", lambda: reply_mod.PREFIX_TIP_UNTIL - dt.timedelta(days=1))


def _edits(events):
    return [event[1] for event in events if event[0] == "edit"]


def test_check_edits_the_progress_handle_identically_on_both_surfaces(monkeypatch):
    stub_scan(["A", "B"], funnel=_FUNNEL)(monkeypatch)

    run = run_both(lambda reply: commands_mod.handle_check(reply, "4w", 2), monkeypatch)

    assert _edits(run.ctx_events) == _edits(run.inter_events) == [
        "🔬 Scan complete — building results…",
        "✅ **2 qualifying trade(s)** (min Lv{lv}, min strategies: 2)  •  confidence breakdown: Lv4:1  Lv5:1".format(
            lv=commands_mod.config.MIN_ALERT_CONFIDENCE_LEVEL),
    ]
    sends = [event[1] for event in run.ctx_events if event[0] == "send"]
    assert sends[0].startswith("🔬 Scanning `4w` · min confidence Lv")
    assert sends[1:] == ["alert A", "alert B"]


def test_stale_check_posts_its_summary_and_alerts_as_fresh_channel_messages(monkeypatch):
    now = [0.0]

    def outlive_the_token():
        now[0] = TOKEN_LIFETIME_S + 1.0

    stub_scan(["A"], funnel=_FUNNEL, on_scan=outlive_the_token)(monkeypatch)
    events: list = []
    interaction = FakeInteraction(events)
    reply = InteractionReply(interaction, clock=lambda: now[0])

    asyncio.run(commands_mod.handle_check(reply))

    summary = [event for event in events if (event[1] or "").startswith("✅")]
    assert [event[0] for event in summary] == ["send"]
    assert not any(event[0] == "edit" for event in events)
    assert interaction.calls[-2:] == ["channel.send", "channel.send"]
    assert events[-1][1] == "alert A"


def test_prefix_check_parses_tokens_into_the_handler(monkeypatch):
    seen = {}

    async def fake(reply, *args):
        seen["args"] = args
    monkeypatch.setattr(commands_mod, "handle_check", fake)

    asyncio.run(commands_mod.check_cmd.callback(FakeContext([]), "4W", "3", "from:2026-08-01", "junk"))

    assert seen["args"] == ("4w", 3, "2026-08-01", None)


def test_check_prefix_answer_ends_with_the_tip(monkeypatch):
    _tip_window_open(monkeypatch)
    stub_scan([])(monkeypatch)
    events: list = []

    asyncio.run(commands_mod.check_cmd.callback(FakeContext(events, qualified_name="check")))

    assert events[-1][1] == "Tip: this is now /check"


def test_recap_posts_to_the_invoking_channel_on_both_surfaces(monkeypatch):
    channels = []

    async def post(channel_id_override=None, today=None):
        channels.append(channel_id_override)
    monkeypatch.setattr(commands_mod.recap, "_post_retrospective", post)

    run_both(lambda reply: commands_mod.handle_recap(reply, "2026-10-09"), monkeypatch)

    assert channels == [10, 10]  # FakeContext / FakeInteraction default channel_id


def test_bad_recap_date_answers_once_without_a_tip(monkeypatch):
    _tip_window_open(monkeypatch)
    events: list = []

    asyncio.run(commands_mod.recap_cmd.callback(FakeContext(events, qualified_name="recap"), "tomorrow"))

    assert [event[1] for event in events] == ["⚠️ Unrecognised date `tomorrow`. Use YYYY-MM-DD."]


def test_stop_logs_the_invoking_user_on_both_surfaces(monkeypatch, caplog):
    import logging
    monkeypatch.setattr(commands_mod.scan_engine, "is_scan_running", lambda: True)
    monkeypatch.setattr(commands_mod.scan_engine, "request_stop", lambda: None)

    with caplog.at_level(logging.INFO, logger=commands_mod.log.name):
        run_both(commands_mod.handle_stop, monkeypatch)

    assert [r.getMessage() for r in caplog.records if "Stop requested" in r.getMessage()] == [
        "Stop requested via !stop (by user1).", "Stop requested via !stop (by user1)."]


def test_scanning_twins_live_in_commands_py_and_slash_py_holds_none():
    from swingbot.commands import slash
    from swingbot.commands.scanning import commands as module

    assert "@bot.tree.command" not in inspect.getsource(slash)
    for name in ("check", "stop", "recap", "session", "status", "pause", "resume"):
        assert bot.tree.get_command(name) is getattr(module, f"slash_{name}")
    assert slash.HORIZON_CHOICES  # tests/market/test_v113_horizon_vocab.py reads it


def test_no_context_bridge_is_left_in_the_commands_package():
    import pathlib
    root = pathlib.Path(commands_mod.__file__).resolve().parents[1]
    offenders = [str(p) for p in root.rglob("*.py") if "from_interaction" in p.read_text(encoding="utf-8")]
    assert offenders == []


def test_moved_check_and_stop_keep_their_payload():
    check = commands_mod.slash_check
    assert check.description == "Live scan or historical review of recorded trade plans"
    assert [p.name for p in check.parameters] == ["horizon", "min_strategies", "from_date", "to_date"]
    assert commands_mod.slash_stop.description == "Stop whatever scan is currently running"
    assert commands_mod.slash_stop.parameters == []


def test_slash_check_passes_typed_options_and_drops_a_negative_minimum(monkeypatch):
    from discord import app_commands
    seen = {}

    async def fake(reply, *args):
        seen["args"] = args
    monkeypatch.setattr(commands_mod, "handle_check", fake)

    asyncio.run(commands_mod.slash_check.callback(
        FakeInteraction([]), horizon=app_commands.Choice(name="4w", value="4w"),
        min_strategies=-1, from_date=None, to_date="2026-08-31"))

    assert seen["args"] == ("4w", None, None, "2026-08-31")
