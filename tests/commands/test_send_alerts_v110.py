"""v110: _send_alerts pushes content lines and isolates every send; the
digest carries one registry content line; deep-scan candidates show ▲/▼."""
import asyncio
import logging
import types

import discord
import pytest

from swingbot import config
from swingbot.commands.scanning import alerts
from swingbot.commands.scanning.alerts import _send_alerts, deep_scan_report
from swingbot.core import presentation as ui
from swingbot.core.presentation import kinds
from swingbot.core.presentation.kinds import Kind


class Chan:
    def __init__(self, fail_on=()):
        self.sent, self.calls, self.fail_on = [], 0, set(fail_on)

    async def send(self, *args, **kwargs):
        self.calls += 1
        if self.calls in self.fail_on:
            raise RuntimeError("discord is having a day")
        self.sent.append(kwargs)
        return types.SimpleNamespace(id=self.calls)


@pytest.fixture
def simple(monkeypatch):
    chan = Chan()
    monkeypatch.setattr(config, "DISCORD_CHANNEL_FIREHOSE_ID", "", raising=False)
    monkeypatch.setattr(config, "MAX_ALERTS_PER_SCAN", 10, raising=False)
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_SIMPLE_ID", "999", raising=False)
    monkeypatch.setattr(alerts, "bot", types.SimpleNamespace(get_channel=lambda _id: chan),
                        raising=False)
    return chan


def test_one_failing_send_does_not_abort_the_batch(simple, caplog):
    """v110 §6.2 regression: the main send was unguarded, so one failure lost
    every alert after it."""
    main = Chan(fail_on={1})
    batch = [("E1", None, None, "S1"), ("E2", None, None, "S2"), ("E3", None, None, "S3")]
    with caplog.at_level(logging.WARNING, logger="swing-bot"):
        asyncio.run(_send_alerts(main, batch))
    assert [s["embed"] for s in main.sent] == ["E2", "E3"]
    assert [s["embed"] for s in simple.sent] == ["S1", "S2", "S3"]
    failures = [r for r in caplog.records if "rest of the batch" in r.getMessage()]
    assert len(failures) == 1 and failures[0].exc_info is not None


def test_pushed_embeds_carry_their_content_line_on_both_channels(simple):
    main = Chan()
    full = ui.push_embed(Kind.SETUP_ALERT, "AAPL", "bullish", "Lv4 ⭐")
    mirror = ui.push_embed(Kind.SETUP_SIMPLE, "AAPL", "bullish", "Lv4")
    asyncio.run(_send_alerts(main, [(full, None, None, mirror)]))
    assert main.sent[0]["content"] == "🆕 NEW SETUP · ▲ LONG AAPL · ALERT · Lv4 ⭐"
    assert main.sent[0]["silent"] is True
    assert simple.sent[0] == {"embed": mirror,
                              "content": "🆕 NEW SETUP · ▲ LONG AAPL · SIMPLE · Lv4"}


@pytest.fixture
def digest_env(monkeypatch):
    from swingbot.commands import stats, views
    from swingbot.core.planning import plan_store
    from swingbot.core.scanning import embeds

    class View:
        def __init__(self, plan_id, author_id=None):
            self.message = None

    monkeypatch.setattr(plan_store, "PlanStore", lambda: types.SimpleNamespace(all=lambda: []))
    monkeypatch.setattr(stats, "_fake_item_from_plan", lambda plan: plan)
    monkeypatch.setattr(embeds, "build_embed",
                        lambda item, *a, **k: discord.Embed(title=item.plan_id))
    monkeypatch.setattr(views, "PlanActionView", View)


def test_digest_sends_one_content_line_for_the_batch(digest_env, monkeypatch):
    plans = [types.SimpleNamespace(plan_id="p1"), types.SimpleNamespace(plan_id="p2")]
    monkeypatch.setattr(alerts, "digest_payload", lambda all_plans, today, max_n: plans)
    chan = Chan()
    asyncio.run(alerts._post_daily_digest(chan))
    assert len(chan.sent) == 2                     # no separate 📌 header message
    assert chan.sent[0]["content"] == kinds.content_line(
        Kind.DIGEST, "", detail="2 VALIDATED plan(s), ranked by follow score")
    assert chan.sent[0]["content"].startswith("🆕 NEW SETUP · TOP PLANS")
    assert "content" not in chan.sent[1]
    assert [s["embed"].title for s in chan.sent] == ["p1", "p2"]


def test_an_empty_digest_still_says_so_through_the_registry(digest_env, monkeypatch):
    monkeypatch.setattr(alerts, "digest_payload", lambda all_plans, today, max_n: [])
    chan = Chan()
    asyncio.run(alerts._post_daily_digest(chan))
    assert chan.sent == [
        {"content": "🆕 NEW SETUP · TOP PLANS · no VALIDATED plans qualified today"}]


def test_deep_scan_report_marks_each_candidates_direction():
    def item(ticker, direction, score):
        plan = types.SimpleNamespace(strategy="MACD", direction=direction)
        return types.SimpleNamespace(ticker=ticker, quality_score=score,
                                     trigger_distance_pct=1.2, plan=plan)

    lines = deep_scan_report([item("AAA", "bullish", 80), item("BBB", "bearish", 60)]).splitlines()
    assert lines[0].lower().startswith("watchlist candidates for monday")
    assert lines[1].startswith("▲ AAA") and lines[2].startswith("▼ BBB")
    assert all("🔭" not in line for line in lines)
