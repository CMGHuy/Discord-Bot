"""v170 §3 / A4 / A10: the execution feed's buttons.

feed_view holds Chart, Breakdown, Watch and the new P&L now; P&L now lives
in FEED_BUTTONS, never in PLAN_BUTTONS, so the full-alert panel cannot grow
it. Every reply is ephemeral. No pytest-asyncio: coroutines run through
asyncio.run.
"""
import asyncio
import datetime as dt
import inspect
import logging
import types
from unittest.mock import AsyncMock, MagicMock

import pytest

from swingbot import config
from swingbot.commands import pnl_now, views
from swingbot.commands.views import (
    FEED_BUTTONS,
    PLAN_BUTTONS,
    BreakdownButton,
    ChartButton,
    PlanActionView,
    PnlNowButton,
    WatchButton,
    custom_id_for,
    feed_view,
)
from swingbot.core.planning.account import compute_unrealized_pnl
from swingbot.core.planning.plan_types import PlanStatus
from tests.planning.test_plan_engine_model import _plan

PID = "0f8fad5b-d9cb-469f-a165-70867728950e"
OTHER = 876543210987654321
FEED_ORDER = [ChartButton, BreakdownButton, WatchButton, PnlNowButton]


def _interaction(user_id: int = OTHER) -> MagicMock:
    interaction = MagicMock()
    interaction.user.id = user_id
    interaction.response = AsyncMock()
    interaction.followup = AsyncMock()
    return interaction


def _press(view) -> MagicMock:
    interaction = _interaction()
    button = next(item for item in view.children if isinstance(item, PnlNowButton))
    asyncio.run(button.callback(interaction))
    return interaction


def _reply_text(interaction) -> str:
    interaction.followup.send.assert_awaited_once()
    args, kwargs = interaction.followup.send.call_args
    assert kwargs == {"ephemeral": True}
    return args[0]


def test_feed_buttons_hold_only_pnl_now():
    assert FEED_BUTTONS == (PnlNowButton,)
    assert (PnlNowButton.ACTION, PnlNowButton.LABEL) == ("pnl", "💵 P&L now")


def test_pnl_now_custom_id_round_trips_after_a_restart():
    custom_id = custom_id_for("pnl", PID, None)
    assert custom_id == f"plan:pnl:{PID}"
    match = PnlNowButton.__discord_ui_compiled_template__.fullmatch(custom_id)
    item = asyncio.run(PnlNowButton.from_custom_id(_interaction(), MagicMock(), match))
    assert isinstance(item, PnlNowButton)
    assert (item.plan_id, item.author_id, item.custom_id) == (PID, None, custom_id)


def test_pnl_now_and_the_plan_buttons_never_claim_each_others_ids():
    pnl_id = custom_id_for("pnl", PID, None)
    assert all(cls.__discord_ui_compiled_template__.fullmatch(pnl_id) is None
               for cls in PLAN_BUTTONS)
    for cls in PLAN_BUTTONS:
        other = custom_id_for(cls.ACTION, PID, None)
        assert PnlNowButton.__discord_ui_compiled_template__.fullmatch(other) is None


def test_feed_view_is_persistent_and_holds_chart_breakdown_watch_and_pnl_now():
    view = feed_view(PID)
    assert view.timeout is None and view.is_persistent()
    assert [type(item) for item in view.children] == FEED_ORDER
    assert [item.custom_id for item in view.children] == [
        custom_id_for(cls.ACTION, PID, None) for cls in FEED_ORDER]


def test_feed_view_never_carries_dismiss_or_following():
    actions = {item.custom_id.split(":")[1] for item in feed_view(PID).children}
    assert actions == {"chart", "breakdown", "watch", "pnl"}


def test_feed_view_for_a_malformed_plan_id_is_empty_and_warns(caplog):
    with caplog.at_level(logging.WARNING, logger="swingbot.commands.views"):
        view = feed_view("not-a-uuid")
    assert view.children == []
    assert "persistent custom_id" in caplog.text


def test_the_full_alert_panel_never_grows_pnl_now():
    assert PnlNowButton not in PLAN_BUTTONS
    view = PlanActionView(PID, author_id=None)
    assert [type(item) for item in view.children] == list(PLAN_BUTTONS)


def test_pnl_now_replies_ephemerally_and_never_posts_in_the_channel(monkeypatch):
    monkeypatch.setattr(pnl_now, "reply_for", lambda plan_id, now=None: f"reply for {plan_id}")
    interaction = _press(feed_view(PID))
    interaction.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
    assert _reply_text(interaction) == f"reply for {PID}"
    interaction.response.send_message.assert_not_awaited()
    assert not interaction.channel.send.called


def test_pnl_now_reads_off_the_event_loop():
    source = inspect.getsource(PnlNowButton.callback)
    assert "to_thread(pnl_now.reply_for" in source


def _seams(monkeypatch, plan, trade, quote, *, market_open=True):
    monkeypatch.setattr(config, "CURRENCY_SYMBOL", "$")
    monkeypatch.setattr(pnl_now, "_load_plan", lambda plan_id: plan)
    monkeypatch.setattr(pnl_now, "_linked_trade", lambda plan_id: trade)
    pnl = (compute_unrealized_pnl(entry=100.0, stop_loss=95.0, take_profit=110.0,
                                  direction="bullish", current_price=quote.price)
           if quote is not None and quote.price is not None else None)
    monkeypatch.setattr(pnl_now, "_quote", lambda p, t: (quote, pnl))
    monkeypatch.setattr(pnl_now, "is_regular_session", lambda now=None: market_open)


TRADE = {"plan_id": PID, "ticker": "AAPL", "direction": "bullish", "entry": 100.0,
         "stop_loss": 95.0, "take_profit": 110.0, "shares": 20.5, "status": "open",
         "realized_pnl_amount": None, "exit_price": None}
LEGS = [{"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1"},
        {"fraction": 0.5, "exit_price": 120.0, "r": 4.0, "reason": "tp1_runner_tp2"}]


@pytest.mark.parametrize("status, legs, trade, price, market_open, expected", [
    ("open", [], TRADE, 104.0, True, "🧾 total +$82.00 · +0.8R (paper, gross)"),
    ("closed", LEGS, {**TRADE, "status": "win", "realized_pnl_amount": 307.5},
     None, True, "🧾 +$307.50 · +3.0R (paper, gross)"),
    ("price unavailable", [], TRADE, None, True, "price unavailable"),
    ("market closed", [], TRADE, 104.0, False, "· market closed"),
])
def test_a_press_answers_each_plan_state_ephemerally(monkeypatch, status, legs, trade,
                                                     price, market_open, expected):
    plan_status = PlanStatus.CLOSED if status == "closed" else PlanStatus.ACTIVE
    plan = _plan(plan_id=PID, status=plan_status, entry_type="stop_entry", trigger_price=100.0,
                 entry_price=100.0, stop_loss=95.0, tp1=110.0, tp2=120.0, legs_realized=legs)
    quote = types.SimpleNamespace(price=price, daily_close=None) if status != "closed" else None
    _seams(monkeypatch, plan, trade, quote, market_open=market_open)
    assert expected in _reply_text(_press(feed_view(PID)))
