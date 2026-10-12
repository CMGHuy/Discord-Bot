"""v152 D1: follower notifications -- claim, send, mention, retry.

Runs on the per-worker test Postgres (tests/conftest.py _store_database): the
plans, followers, prefs and claims are real rows. Discord is a fake channel.
"""
import asyncio
import datetime as dt
import logging

import pytest

from swingbot import config
from swingbot.commands import views
from swingbot.commands.scanning import follow_notify as fn
from swingbot.core.db.repositories.followers import followers_repo
from swingbot.core.db.repositories.notifications import MAX_ATTEMPTS, notifications_repo
from swingbot.core.db.repositories.notify_prefs import notify_prefs_repo
from swingbot.core.planning.plan_engine import PlanStatus
from swingbot.core.planning.plan_manager import PlanEvent
from swingbot.core.planning.plan_store import PlanStore
from tests.planning.test_plan_engine_model import _plan

PID = "0f8fad5b-d9cb-469f-a165-70867728950e"
PID2 = "7c9e6679-7425-40de-944b-e07fc1f90ae7"
MISSING = "16fd2706-8baf-433b-82eb-8c7fada847da"
NOTIFY_ID = 112233445566778899
FOLLOWER = 123456789012345678
WATCHER = 876543210987654321
TP1 = {"fraction": 0.5, "exit_price": 102.0, "r": 0.4, "reason": "tp1",
       "closed_at": "2026-10-12T15:00:00+00:00"}


class Chan:
    def __init__(self, fail: int = 0):
        self.sent: list[dict] = []
        self.fail = fail

    async def send(self, **kwargs):
        if self.fail:
            self.fail -= 1
            raise RuntimeError("discord down")
        self.sent.append(kwargs)
        return object()


class Bot:
    def __init__(self, chan):
        self.chan = chan

    def get_channel(self, channel_id):
        return self.chan if channel_id == NOTIFY_ID else None


@pytest.fixture(autouse=True)
def notify_on(monkeypatch):
    monkeypatch.setattr(config, "DISCORD_CHANNEL_NOTIFY_ID", str(NOTIFY_ID))
    monkeypatch.setattr(config, "ADMIN_PUBLIC_URL", "")
    monkeypatch.setattr(fn, "_CLAIMED", None)
    monkeypatch.setattr(fn, "_UNSETTLED", set())


def _store(status: str, plan_id: str = PID):
    partial = status == PlanStatus.PARTIAL
    plan = _plan(plan_id=plan_id, entry_type="stop_entry", trigger_price=100.0,
                 entry_price=100.0, status=status,
                 working_stop=101.33 if partial else None,
                 legs_realized=[dict(TP1)] if partial else [])
    PlanStore().add(plan)
    return plan


def _follow(user_id: int, kind: str, plan_id: str = PID) -> None:
    followers_repo().add(plan_id, user_id, kind, status_at_press="ACTIVE")


def _rows() -> dict:
    return {(r["plan_id"], r["event"]): r for r in notifications_repo().list_all()}


def _notify(bot, *events) -> int:
    return asyncio.run(fn.notify_followers(bot, list(events)))


def _sweep(bot, minutes: float = 2.0) -> int:
    now = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=minutes)
    return asyncio.run(fn.retry_pending_notifications(bot, now=now))


def _tp1_event(plan_id: str = PID) -> PlanEvent:
    return PlanEvent(plan_id, "tp1_partial", dict(TP1))


@pytest.mark.parametrize("raw", ["", "   ", "not-a-number"])
def test_no_usable_channel_key_sends_and_claims_nothing(monkeypatch, raw):
    monkeypatch.setattr(config, "DISCORD_CHANNEL_NOTIFY_ID", raw)
    _store(PlanStatus.PARTIAL)
    chan = Chan()
    assert _notify(Bot(chan), _tp1_event()) == 0
    assert _sweep(Bot(chan)) == 0
    assert chan.sent == [] and _rows() == {}


def test_a_channel_the_bot_cannot_see_sends_and_claims_nothing(monkeypatch):
    monkeypatch.setattr(config, "DISCORD_CHANNEL_NOTIFY_ID", "999999999999999999")
    _store(PlanStatus.PARTIAL)
    chan = Chan()
    assert _notify(Bot(chan), _tp1_event()) == 0
    assert chan.sent == [] and _rows() == {}


def test_a_following_follower_is_mentioned_and_the_claim_is_marked_sent():
    _store(PlanStatus.PARTIAL)
    _follow(FOLLOWER, "taken")
    chan = Chan()
    assert _notify(Bot(chan), _tp1_event()) == 1
    [kwargs] = chan.sent
    assert kwargs["content"].endswith(f"<@{FOLLOWER}>")
    assert kwargs["content"].startswith("Paper plan update: AAPL long reached TP1 at 102.00.")
    mentions = kwargs["allowed_mentions"]
    assert [user.id for user in mentions.users] == [FOLLOWER]
    assert mentions.roles is False and mentions.everyone is False
    assert not kwargs.get("silent")
    assert _rows()[(PID, "tp1")]["state"] == "sent"


def test_the_message_carries_only_the_persistent_chart_button():
    _store(PlanStatus.PARTIAL)
    chan = Chan()
    _notify(Bot(chan), _tp1_event())
    view = chan.sent[0]["view"]
    assert view.timeout is None
    assert [type(item) for item in view.children] == [views.ChartButton]


def test_no_follower_posts_silently_without_a_mention():
    _store(PlanStatus.PARTIAL)
    chan = Chan()
    assert _notify(Bot(chan), _tp1_event()) == 1
    [kwargs] = chan.sent
    assert kwargs["silent"] is True
    assert kwargs["allowed_mentions"].users is False
    assert "<@" not in kwargs["content"]


def test_a_second_identical_event_posts_nothing_even_after_a_restart(monkeypatch):
    _store(PlanStatus.PARTIAL)
    chan = Chan()
    assert _notify(Bot(chan), _tp1_event()) == 1
    assert _notify(Bot(chan), _tp1_event()) == 0
    monkeypatch.setattr(fn, "_CLAIMED", None)          # a restart: the cache reseeds from the table
    assert _notify(Bot(chan), _tp1_event()) == 0
    assert len(chan.sent) == 1


def test_a_cached_claim_costs_no_database_call(monkeypatch):
    _store(PlanStatus.PARTIAL)
    chan = Chan()
    _notify(Bot(chan), _tp1_event())
    calls = []
    monkeypatch.setattr(fn, "_load_plan", lambda plan_id: calls.append(("plan", plan_id)))
    monkeypatch.setattr(fn, "_claim", lambda *a: calls.append(("claim", a)) or True)
    assert _notify(Bot(chan), _tp1_event()) == 0
    assert calls == []


def test_closed_other_needs_a_following_follower_and_mentions_only_them(monkeypatch):
    _store(PlanStatus.CLOSED)
    _follow(WATCHER, "watch")
    event = PlanEvent(PID, "closed", {"reason": "stall_exit", "exit_price": 101.0,
                                      "leg": {"fraction": 1.0, "exit_price": 101.0,
                                              "r": 0.2, "reason": "stall_exit"},
                                      "_terminal_persisted": True})
    chan = Chan()
    assert _notify(Bot(chan), event) == 0
    assert chan.sent == [] and _rows() == {}            # not posted, not claimed
    _follow(FOLLOWER, "taken")
    assert _notify(Bot(chan), event) == 1
    [kwargs] = chan.sent
    assert f"<@{FOLLOWER}>" in kwargs["content"] and f"<@{WATCHER}>" not in kwargs["content"]
    assert [user.id for user in kwargs["allowed_mentions"].users] == [FOLLOWER]
    assert "_terminal_persisted" not in _rows()[(PID, "closed_other")]["detail"]


def test_watch_only_near_stop_is_off_by_default_and_a_toggle_turns_it_on():
    _store(PlanStatus.ACTIVE)
    _store(PlanStatus.ACTIVE, plan_id=PID2)
    _follow(WATCHER, "watch")
    _follow(WATCHER, "watch", plan_id=PID2)
    near = {"stop": 95.0, "price": 96.05, "r_dist": 0.21}
    chan = Chan()
    assert _notify(Bot(chan), PlanEvent(PID, "near_stop", dict(near))) == 1
    assert chan.sent[0]["silent"] is True                 # posts, mentions nobody
    notify_prefs_repo().set_pref(WATCHER, "near_stop", True)
    assert _notify(Bot(chan), PlanEvent(PID2, "near_stop", dict(near))) == 1
    assert chan.sent[1]["content"].endswith(f"<@{WATCHER}>")


def test_watch_mode_silent_drops_the_watch_mention_but_still_posts():
    _store(PlanStatus.PARTIAL)
    _follow(WATCHER, "watch")
    notify_prefs_repo().set_pref(WATCHER, "watch_mode", "silent")
    chan = Chan()
    assert _notify(Bot(chan), _tp1_event()) == 1
    assert chan.sent[0]["silent"] is True


def test_a_failed_send_stays_pending_and_the_sweep_retries_it():
    _store(PlanStatus.PARTIAL)
    chan = Chan(fail=1)
    assert _notify(Bot(chan), _tp1_event()) == 0
    row = _rows()[(PID, "tp1")]
    assert row["state"] == "pending" and row["attempts"] == 1
    assert _sweep(Bot(chan), minutes=0) == 0              # younger than a minute: left alone
    assert _sweep(Bot(chan)) == 1
    assert _rows()[(PID, "tp1")]["state"] == "sent"
    assert chan.sent[0]["content"].startswith("Paper plan update: AAPL long reached TP1")


def test_five_failed_attempts_mark_the_row_failed_with_a_warning(caplog):
    _store(PlanStatus.PARTIAL)
    chan = Chan(fail=MAX_ATTEMPTS)
    _notify(Bot(chan), _tp1_event())
    with caplog.at_level(logging.WARNING, logger=fn.__name__):
        for attempt in range(2, MAX_ATTEMPTS + 1):
            assert _sweep(Bot(chan), minutes=2 * attempt) == 0
    assert _rows()[(PID, "tp1")]["state"] == "failed"
    assert any("giving up" in r.getMessage() for r in caplog.records)
    assert _sweep(Bot(chan), minutes=60) == 0             # failed rows are never retried
    assert chan.sent == []


def test_a_lost_sent_write_settles_without_resending(monkeypatch):
    _store(PlanStatus.PARTIAL)
    chan = Chan()

    def broken(plan_id, notify_event):
        raise RuntimeError("db blip")

    with monkeypatch.context() as failed_write:
        failed_write.setattr(fn, "_mark_sent", broken)
        assert _notify(Bot(chan), _tp1_event()) == 1
        assert _rows()[(PID, "tp1")]["state"] == "pending"
    assert _sweep(Bot(chan)) == 0
    assert _sweep(Bot(chan), minutes=10) == 0
    assert len(chan.sent) == 1
    assert _rows()[(PID, "tp1")]["state"] == "sent"


def test_unmapped_events_and_unknown_plans_send_nothing_and_do_not_stop_the_batch():
    _store(PlanStatus.PARTIAL)
    chan = Chan()
    events = [PlanEvent(PID, "be_moved", {"working_stop": 100.0, "live_price": 101.0}),
              PlanEvent(MISSING, "tp1_partial", dict(TP1)),
              _tp1_event()]
    assert _notify(Bot(chan), *events) == 1
    assert set(_rows()) == {(PID, "tp1")}


@pytest.mark.parametrize("raw", ["", "bad", "999999999999999999"])
def test_unusable_channel_never_reads_the_database(monkeypatch, raw):
    monkeypatch.setattr(config, "DISCORD_CHANNEL_NOTIFY_ID", raw)

    async def no_thread(*args, **kwargs):
        pytest.fail("disabled notifier touched the database")

    monkeypatch.setattr(fn.asyncio, "to_thread", no_thread)
    assert _notify(Bot(Chan()), _tp1_event()) == 0
    assert _sweep(Bot(Chan())) == 0


def test_simultaneous_notifications_claim_before_send_and_send_only_once():
    _store(PlanStatus.PARTIAL)

    class ClaimedChannel(Chan):
        async def send(self, **kwargs):
            rows = await asyncio.to_thread(_rows)
            assert rows[(PID, "tp1")]["state"] == "pending"
            await super().send(**kwargs)

    chan = ClaimedChannel()

    async def concurrently():
        return await asyncio.gather(
            fn.notify_followers(Bot(chan), [_tp1_event()]),
            fn.notify_followers(Bot(chan), [_tp1_event()]),
        )

    assert sum(asyncio.run(concurrently())) == 1
    assert len(chan.sent) == 1
    assert _rows()[(PID, "tp1")]["state"] == "sent"


def test_failed_claim_does_not_send_or_prevent_later_event(monkeypatch):
    _store(PlanStatus.PARTIAL)
    _store(PlanStatus.PARTIAL, PID2)
    claim = fn._claim

    def first_claim_fails(plan_id, event, doc):
        if plan_id == PID:
            raise RuntimeError("claim unavailable")
        return claim(plan_id, event, doc)

    monkeypatch.setattr(fn, "_claim", first_claim_fails)
    chan = Chan()
    assert _notify(Bot(chan), _tp1_event(), _tp1_event(PID2)) == 1
    assert set(_rows()) == {(PID2, "tp1")}
    assert (PID, "tp1") not in fn._CLAIMED
    monkeypatch.setattr(fn, "_claim", claim)
    assert _notify(Bot(chan), _tp1_event()) == 1


def test_retry_uses_stored_event_with_current_stop_and_preferences():
    plan = _store(PlanStatus.PARTIAL)
    _follow(FOLLOWER, "taken")
    chan = Chan(fail=1)
    assert _notify(Bot(chan), _tp1_event()) == 0
    plan.working_stop = 101.75
    PlanStore().update(plan)
    notify_prefs_repo().set_pref(FOLLOWER, "tp1", False)
    assert _sweep(Bot(chan)) == 1
    [message] = chan.sent
    assert "reached TP1 at 102.00" in message["content"]
    assert "Stop now at 101.75" in message["content"]
    assert message["silent"] is True
    assert "<@" not in message["content"]


def test_delivery_and_retry_database_calls_run_off_event_loop(monkeypatch):
    import threading

    _store(PlanStatus.PARTIAL)
    loop_thread = threading.get_ident()
    calls = set()

    def guard(name, call):
        def checked(*args, **kwargs):
            assert threading.get_ident() != loop_thread, name
            calls.add(name)
            return call(*args, **kwargs)
        return checked

    helpers = ("_claimed_keys", "_load_plan", "_audience", "_claim",
               "_record_failure", "_pending_rows", "_mark_sent")
    for name in helpers:
        monkeypatch.setattr(fn, name, guard(name, getattr(fn, name)))
    chan = Chan(fail=1)
    assert _notify(Bot(chan), _tp1_event()) == 0
    assert _sweep(Bot(chan)) == 1
    assert calls == set(helpers)
    assert _rows()[(PID, "tp1")]["state"] == "sent"


@pytest.mark.parametrize("initial_send_fails", [False, True])
def test_repeated_sent_write_failures_retry_settlement_without_resending(
        monkeypatch, initial_send_fails):
    _store(PlanStatus.PARTIAL)
    chan = Chan(fail=int(initial_send_fails))

    def broken(plan_id, notify_event):
        raise RuntimeError("settlement unavailable")

    with monkeypatch.context() as failed_write:
        failed_write.setattr(fn, "_mark_sent", broken)
        _notify(Bot(chan), _tp1_event())
        _sweep(Bot(chan))
        _sweep(Bot(chan), minutes=4)
        assert len(chan.sent) == 1
        row = _rows()[(PID, "tp1")]
        assert row["state"] == "pending"
        assert row["attempts"] == int(initial_send_fails)
    assert _sweep(Bot(chan), minutes=6) == 0
    assert len(chan.sent) == 1
    assert _rows()[(PID, "tp1")]["state"] == "sent"
    assert (PID, "tp1") not in fn._UNSETTLED


def test_restart_recovers_a_successful_send_without_durable_settlement(monkeypatch):
    _store(PlanStatus.PARTIAL)
    chan = Chan()

    def broken(plan_id, notify_event):
        raise RuntimeError("settlement unavailable")

    with monkeypatch.context() as failed_write:
        failed_write.setattr(fn, "_mark_sent", broken)
        assert _notify(Bot(chan), _tp1_event()) == 1
    # A new process cannot distinguish a lost settlement from an unsent claim.
    monkeypatch.setattr(fn, "_CLAIMED", None)
    monkeypatch.setattr(fn, "_UNSETTLED", set())
    assert _sweep(Bot(chan)) == 1
    assert _sweep(Bot(chan), minutes=4) == 0
    assert len(chan.sent) == 2
    assert _rows()[(PID, "tp1")]["state"] == "sent"
