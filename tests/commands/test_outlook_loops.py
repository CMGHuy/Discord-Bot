"""v144: the outlook loops fire once per slot, never into a running session,
and the wrap-up waits for every plan of D to be terminal."""
import asyncio
import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from swingbot import config
from swingbot.commands.scanning import loops as loops_mod
from swingbot.commands.scanning import outlook as outlook_cmd
from swingbot.core.db.repositories.scheduled import scheduled_repo
from swingbot.core.planning.plan_engine import PlanStatus, record_transition
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.scanning.outlook_types import OutlookLine, OutlookResult
from tests.planning.test_plan_engine_model import _plan

BERLIN, ET = ZoneInfo("Europe/Berlin"), ZoneInfo("America/New_York")
SUNDAY, MONDAY = dt.date(2026, 10, 11), dt.date(2026, 10, 12)


class FakeChannel:
    def __init__(self):
        self.sent = []

    async def send(self, **kwargs):
        self.sent.append(kwargs)


@pytest.fixture
def scan(monkeypatch):
    calls = []

    async def run(run_date):
        calls.append(run_date)

    monkeypatch.setattr(config, "NEXT_SESSION_SCAN_ENABLED", True)
    monkeypatch.setattr(config, "NEXT_SESSION_SCAN_TIME", "23:30")
    monkeypatch.setattr(loops_mod, "_next_session_fired_date", None)
    monkeypatch.setattr(loops_mod.outlook, "run_next_session_outlook", run)

    def tick(now):
        monkeypatch.setattr(loops_mod, "_outlook_now", lambda: now)
        monkeypatch.setattr(loops_mod, "_next_session_fired_date", None)   # as after a restart
        asyncio.run(loops_mod.next_session_scan.coro())
    return calls, tick


def test_fires_once_at_the_sunday_slot(scan):
    calls, tick = scan
    tick(dt.datetime(2026, 10, 11, 23, 29, tzinfo=BERLIN))
    tick(dt.datetime(2026, 10, 11, 23, 30, tzinfo=BERLIN))
    tick(dt.datetime(2026, 10, 11, 23, 31, tzinfo=BERLIN))
    # 23:29: Thursday's slot is the latest, but Friday's RTH open has passed, so it
    # is marked and skipped, never run. 23:30 runs Sunday's; 23:31 sees it fired.
    assert calls == [SUNDAY]
    assert scheduled_repo().fired_on("next_session_scan") == "2026-10-11"


def test_never_runs_disabled(scan, monkeypatch):
    calls, tick = scan
    monkeypatch.setattr(config, "NEXT_SESSION_SCAN_ENABLED", False)
    tick(dt.datetime(2026, 10, 11, 23, 30, tzinfo=BERLIN))
    assert calls == []


def test_a_late_fire_before_the_rth_open_still_runs(scan):
    calls, tick = scan
    scheduled_repo().mark("next_session_scan", "2026-10-08")       # Thursday's ran
    tick(dt.datetime(2026, 10, 12, 8, 0, tzinfo=BERLIN))           # Monday morning: Sunday's was missed
    assert calls == [SUNDAY]


def test_a_late_fire_after_the_rth_open_is_skipped_and_marked(scan):
    calls, tick = scan
    scheduled_repo().mark("next_session_scan", "2026-10-08")
    tick(dt.datetime(2026, 10, 12, 15, 45, tzinfo=BERLIN))         # 09:45 ET Monday
    assert calls == []
    assert scheduled_repo().fired_on("next_session_scan") == "2026-10-11"


def test_friday_and_saturday_evenings_never_fire(scan):
    calls, tick = scan
    scheduled_repo().mark("next_session_scan", "2026-10-08")
    tick(dt.datetime(2026, 10, 9, 23, 30, tzinfo=BERLIN))
    tick(dt.datetime(2026, 10, 10, 23, 30, tzinfo=BERLIN))
    assert calls == []


# --- the wrap-up loop ---------------------------------------------------------------

@pytest.fixture
def wrap(monkeypatch):
    answers, asked = {}, []

    async def post(day):
        asked.append(day)
        return answers.get(day, True)

    monkeypatch.setattr(loops_mod.outlook, "post_wrapup_when_terminal", post)

    def tick(now):
        monkeypatch.setattr(loops_mod, "_outlook_now", lambda: now)
        asyncio.run(loops_mod.next_session_wrapup.coro())
    return answers, asked, tick


def test_the_wrapup_waits_for_the_close_plus_15(wrap):
    answers, asked, tick = wrap
    scheduled_repo().mark("next_session_wrapup", "2026-10-09")
    tick(dt.datetime(2026, 10, 12, 16, 10, tzinfo=ET))
    assert asked == []
    tick(dt.datetime(2026, 10, 12, 16, 15, tzinfo=ET))
    assert asked == [MONDAY]
    assert scheduled_repo().fired_on("next_session_wrapup") == "2026-10-12"


def test_a_pending_plan_keeps_the_wrapup_open(wrap):
    answers, asked, tick = wrap
    scheduled_repo().mark("next_session_wrapup", "2026-10-09")
    answers[MONDAY] = False
    tick(dt.datetime(2026, 10, 12, 16, 20, tzinfo=ET))
    tick(dt.datetime(2026, 10, 12, 16, 21, tzinfo=ET))
    assert asked == [MONDAY, MONDAY]
    assert scheduled_repo().fired_on("next_session_wrapup") == "2026-10-09"


# --- posting --------------------------------------------------------------------------

def _outlook(plan_id, **kw):
    return _plan(plan_id=plan_id, entry_type="stop_entry", origin="next_session",
                 valid_session=MONDAY.isoformat(), **kw)


def test_post_wrapup_waits_then_posts_once_terminal(monkeypatch):
    channel = FakeChannel()
    monkeypatch.setattr(outlook_cmd, "_alerts_channel", lambda: channel)
    store = PlanStore()
    pending = _outlook("o1")
    store.add(pending)
    assert asyncio.run(outlook_cmd.post_wrapup_when_terminal(MONDAY)) is False
    assert channel.sent == []
    record_transition(pending, PlanStatus.CANCELLED, reason="never_triggered", at="t")
    pending.cancel_reason_message = "High 101.40 stopped 0.6% short of the 102.00 trigger"
    store.update(pending)
    assert asyncio.run(outlook_cmd.post_wrapup_when_terminal(MONDAY)) is True
    (message,) = channel.sent
    assert "1 issued · 0 filled · 1 cancelled (never_triggered ×1)" in message["embed"].description


def test_a_session_without_outlook_plans_is_done_silently(monkeypatch):
    channel = FakeChannel()
    monkeypatch.setattr(outlook_cmd, "_alerts_channel", lambda: channel)
    assert asyncio.run(outlook_cmd.post_wrapup_when_terminal(MONDAY)) is True
    assert channel.sent == []


def test_run_posts_the_digest_then_the_cards(monkeypatch):
    channel, sent_alerts = FakeChannel(), []
    result = OutlookResult(run_date=SUNDAY, target=MONDAY, plans=[OutlookLine(
        "AAPL", "bullish", "Break & Retest", 102.0, 100.5, 106.0, risk_dollars=120.0)],
        alerts=[("embed", None, None, None)])

    async def send_alerts(destination, alerts, route_by_confidence=False):
        sent_alerts.append((destination, alerts))

    monkeypatch.setattr(outlook_cmd, "_alerts_channel", lambda: channel)
    monkeypatch.setattr(outlook_cmd.outlook_run, "run_outlook", lambda run_date: result)
    monkeypatch.setattr(outlook_cmd, "_send_alerts", send_alerts)
    monkeypatch.setattr(outlook_cmd.scan_run, "_scan_lock", asyncio.Lock())
    assert asyncio.run(outlook_cmd.run_next_session_outlook(SUNDAY)) is result
    (digest,) = channel.sent
    assert digest["embed"].description.startswith("**Outlook for Monday 2026-10-12**")
    assert sent_alerts == [(channel, result.alerts)]


def test_a_failing_scan_posts_outlook_unavailable(monkeypatch):
    channel = FakeChannel()

    def boom(run_date):
        raise RuntimeError("boom")

    monkeypatch.setattr(outlook_cmd, "_alerts_channel", lambda: channel)
    monkeypatch.setattr(outlook_cmd.outlook_run, "run_outlook", boom)
    monkeypatch.setattr(outlook_cmd.scan_run, "_scan_lock", asyncio.Lock())
    result = asyncio.run(outlook_cmd.run_next_session_outlook(SUNDAY))
    assert result.unavailable == "scan failed (RuntimeError: boom)" and result.alerts == []
    assert "Outlook unavailable: scan failed (RuntimeError: boom)" in channel.sent[0]["embed"].description


def test_no_alerts_channel_posts_nothing_and_does_not_scan(monkeypatch):
    ran = []
    monkeypatch.setattr(outlook_cmd, "_alerts_channel", lambda: None)
    monkeypatch.setattr(outlook_cmd.outlook_run, "run_outlook", lambda d: ran.append(d))
    assert asyncio.run(outlook_cmd.run_next_session_outlook(SUNDAY)) is None
    assert ran == []


def test_a_huge_digest_is_split_into_discord_sized_embeds():
    lines = [OutlookLine(f"T{i:04d}", "bullish", "Break & Retest", 102.0, 100.5, 106.0,
                         risk_dollars=120.0) for i in range(400)]
    result = OutlookResult(run_date=SUNDAY, target=MONDAY, plans=lines)
    embeds = outlook_cmd.digest_embeds(result)
    assert len(embeds) > 1
    assert all(len(e.description) <= 2000 for e in embeds)
    joined = "\n".join(e.description for e in embeds)
    assert "T0000" in joined and "T0399" in joined


def test_both_loops_start_with_the_bot():
    assert loops_mod.next_session_scan in loops_mod._always_on_loops()
    assert loops_mod.next_session_wrapup in loops_mod._always_on_loops()
