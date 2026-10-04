"""v119 Task 8: resting-order and MOC instructions, one wording in every channel.

The compression short is a resting SELL STOP at the broker, then (at most) a
buy-to-cover market-on-close order ten sessions after the fill. The bot has no
broker API, so every message tells the reader to cancel or verify; none ever
claims an order was cancelled for them.
"""
import asyncio
import dataclasses
import datetime as dt
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from swingbot import config
from swingbot.core.infra import notifier
from swingbot.core.market.strategy_types import STRATEGY_GATES
from swingbot.core.planning.plan_manager import Delivery, PlanEvent, PlanManager, ack_notified
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.presentation import short_notice
from swingbot.core.presentation.instructions import instruction_for
from swingbot.core.scanning import execution_embeds, lifecycle_embeds
from swingbot.core.scanning.alert_embeds import build_embed, build_simple_alert
from tests.planning.test_compression_time_exit import _short
from tests.scanning.test_embeds_v3 import (PERF_STATS_EMPTY, make_item, make_plan_v2,
                                           _isolated_scan_snapshots)  # noqa: F401

STAMP = {"compression_mode": "isolated", "compression_bar_date": "2026-10-01"}


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(execution_embeds, "_sizing_snapshot", lambda entry, plan: None)


def _pending_plan():
    return dataclasses.replace(
        make_plan_v2(direction="bearish", entry_type="stop_entry", trigger_price=99.8),
        strategy=_short().strategy, created_at="2026-10-01", expiry_bars=1,
        stop_loss=101.05, tp1=92.4, tp1_fraction=1.0, tp2=None, entry_context=dict(STAMP))


def _item():
    item = make_item(plan_v2=_pending_plan())
    return item


def _text(embed):
    return "\n".join([embed.description or "", *(f.name + "\n" + f.value for f in embed.fields)])


def _surfaces():
    item = _item()
    return {"discord": _text(build_embed(item, "x", PERF_STATS_EMPTY, None, None)),
            "simple": _text(build_simple_alert(item)),
            "email/push": notifier._build_alert_texts(item, item.plan, item.conf)[1]}


# -- the initial alert, in every channel -------------------------------------------

def test_pending_alert_carries_the_same_trade_numbers_and_borrow_check_everywhere():
    for name, text in _surfaces().items():
        assert "CHECK BORROW AVAILABILITY" in text, name
        for needle in ("99.80", "101.05", "92.40", "2026-10-02", "2026-10-01", "isolated"):
            assert needle in text, (name, needle)
        assert "SELL STOP" in text and "whole position" in text.lower(), name


def test_pending_notice_text_is_identical_across_channels():
    block = short_notice.compression_pending_notice(_pending_plan(), currency=config.CURRENCY_SYMBOL)
    for name, text in _surfaces().items():
        assert block in text, name


def test_pending_notice_names_expiry_session_and_the_cancel_instruction():
    text = short_notice.compression_pending_notice(_pending_plan(), currency="$")
    assert "expires" in text.lower() and "2026-10-02" in text
    assert "cancel" in text.lower() and "sell stop" in text.lower()
    assert "not a verified locate" in text.lower()


def test_other_strategies_get_no_compression_notice():
    plan = make_plan_v2(direction="bearish")
    item = make_item(plan_v2=plan)
    assert "BORROW" not in build_simple_alert(item).description
    assert "BORROW" not in notifier._build_alert_texts(item, item.plan, item.conf)[1]


# -- lifecycle instructions ----------------------------------------------------------

def _words(instruction):
    return " ".join([instruction.headline, *instruction.lines])


def test_expiry_says_cancel_the_resting_sell_stop_and_never_claims_it_was_cancelled():
    plan = _short(status="CANCELLED", entry_price=None)
    event = PlanEvent("p1", "cancelled_expired", {"bars_waited": 1, "cancel_resting_order": True})
    text = _words(instruction_for(plan, event))
    assert "cancel" in text.lower() and "resting sell stop" in text.lower()
    assert "cannot cancel" in text.lower()
    assert "automatically" not in text.lower() and "was cancelled" not in text.lower()


def test_risk_cap_says_cancel_the_resting_sell_stop():
    plan = _short(status="CANCELLED", entry_price=None)
    event = PlanEvent("p1", "cancelled_risk_cap", {
        "entry_price": 99.0, "stop_loss": 101.0, "planned_loss_pct": 2.02,
        "max_planned_loss_pct": 2.0})
    text = _words(instruction_for(plan, event))
    assert "cancel" in text.lower() and "resting sell stop" in text.lower()
    assert "automatically" not in text.lower()


def test_other_strategy_expiry_wording_is_unchanged():
    plan = make_plan_v2(direction="bearish", entry_type="stop_entry")
    event = PlanEvent("plan-1", "cancelled_expired", {"bars_waited": 5})
    instruction = instruction_for(plan, event)
    assert instruction.lines == ("not triggered within 5 sessions",)


def test_due_notice_says_buy_to_cover_by_the_stated_closing_auction_with_shares():
    event = PlanEvent("p1", "time_exit_due", {
        "cover_fraction": 1.0, "auction_time": "2026-12-01T16:00:00-05:00", "late": False,
        "notice_id": "p1:time_exit_due:2026-12-01"})
    text = _words(instruction_for(_short(), event, sizing={"shares": 12.6}))
    assert "buy to cover" in text.lower() and "12 sh" in text and "16:00" in text
    assert "MOC" in text and "broker" in text.lower()


def test_stop_after_due_says_cancel_verify_staged_moc_even_on_a_closed_plan():
    plan = _short(time_exit_due_date="2026-12-01", time_exit_notified_date="2026-12-01", status="CLOSED")
    event = PlanEvent("p1", "closed", {"reason": "loss", "exit_price": 101.0, "session": "regular"})
    assert "cancel/verify staged moc" in _words(instruction_for(plan, event)).lower()
    target = PlanEvent("p1", "closed", {"reason": "win", "exit_price": 95.0, "session": "regular"})
    assert "cancel/verify staged moc" in _words(instruction_for(plan, target)).lower()


def test_a_due_session_handled_without_a_sent_notice_gets_no_staged_moc_line():
    plan = _short(time_exit_due_date="2026-12-01", status="CLOSED")       # the notice was never sent
    event = PlanEvent("p1", "closed", {"reason": "loss", "exit_price": 101.0, "session": "regular"})
    assert "staged moc" not in _words(instruction_for(plan, event)).lower()


def test_no_moc_line_without_a_staged_moc():
    event = PlanEvent("p1", "closed", {"reason": "loss", "exit_price": 101.0, "session": "regular"})
    assert "staged moc" not in _words(instruction_for(_short(), event)).lower()


def test_every_compression_message_names_ticker_and_direction():
    plan = _short(time_exit_due_date="2026-12-01")
    for event in (PlanEvent("p1", "cancelled_expired", {"bars_waited": 1}),
                  PlanEvent("p1", "closed", {"reason": "loss", "exit_price": 101.0})):
        instruction = instruction_for(plan, event)
        assert instruction.ticker == "AAPL" and instruction.direction == "bearish"


def test_live_trade_instruction_emission_stays_masked():
    gate = STRATEGY_GATES.get(_short().strategy) or {}
    assert not gate.get("directions") and not gate.get("cells")


# -- delivery: durable, retried, acknowledged once ----------------------------------

class _Chan:
    def __init__(self, fail=0):
        self.sent, self.fail = [], fail

    async def send(self, *args, **kwargs):
        if self.fail:
            self.fail -= 1
            raise RuntimeError("discord down")
        self.sent.append(kwargs)


def _bot(feed, history=None):
    channels = {"7": feed, "8": history}
    return SimpleNamespace(get_channel=lambda cid: channels.get(str(cid)))


@pytest.fixture
def channels(monkeypatch):
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_SIMPLE_ID", "7")
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_HISTORY_ID", "")


def _notice(notice_id, transition="time_exit_due"):
    return {"id": notice_id, "transition": transition, "acked": False,
            "at": "2026-12-01T19:30:00+00:00",
            "detail": {"cover_fraction": 1.0, "auction_time": "2026-12-01T16:00:00-05:00",
                       "due_session": "2026-12-01", "late": False,
                       "reason": "official closing-auction price unavailable"}}


def test_failed_send_keeps_the_terminal_close_owed_then_one_ack_ends_it(channels):
    store = PlanStore()
    plan = _short(status="CLOSED", time_exit_due_date="2026-12-01")
    plan.pending_notice = {"transition": "closed", "at": PlanManager(store, None)._now(),
                           "detail": {"reason": "loss", "exit_price": 101.0, "session": "regular"}}
    store.add(plan)
    feed = _Chan(fail=1)
    events = PlanManager(store, None).resend_notices()
    assert asyncio.run(lifecycle_embeds.notify_plan_events(_bot(feed), events)) == []
    events = PlanManager(PlanStore(), None).resend_notices()      # next sweep still owes it
    deliveries = asyncio.run(lifecycle_embeds.notify_plan_events(_bot(feed), events))
    assert deliveries == [Delivery("p1", "notice", "closed")] and len(feed.sent) == 1
    ack_notified(deliveries)
    assert PlanManager(PlanStore(), None).resend_notices() == []
    assert len(feed.sent) == 1                                    # no duplicate terminal close


def test_two_outstanding_time_notices_survive_a_restart_and_ack_independently(channels):
    store = PlanStore()
    plan = _short()
    plan.pending_time_notices = [_notice("p1:time_exit_due:2026-12-01"),
                                 _notice("p1:time_exit_unresolved:2026-12-01",
                                         "time_exit_unresolved")]
    store.add(plan)
    before_close = dt.datetime(2026, 12, 1, 15, 40, tzinfo=ZoneInfo("America/New_York"))
    events = PlanManager(PlanStore(), None).resend_notices(now=before_close)      # a fresh process
    assert {e.detail["notice_id"] for e in events} == {
        "p1:time_exit_due:2026-12-01", "p1:time_exit_unresolved:2026-12-01"}
    feed = _Chan()
    deliveries = asyncio.run(lifecycle_embeds.notify_plan_events(_bot(feed), events))
    assert len(deliveries) == 2
    ack_notified([d for d in deliveries if d.value.endswith("due:2026-12-01")])
    left = PlanManager(PlanStore(), None).resend_notices(now=before_close)
    assert [e.detail["notice_id"] for e in left] == ["p1:time_exit_unresolved:2026-12-01"]
