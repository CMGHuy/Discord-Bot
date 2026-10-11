"""v152 D3: _send_alerts(apply_cooldown=True) holds a repeat alert before the
cap, records posts only after Discord accepted them, and fails open; the
daily digest states how many alerts the cooldown held today."""
import asyncio
import logging
import types

import discord
import pytest

from swingbot import config
from swingbot.commands.scanning import alerts, cooldown
from swingbot.commands.scanning.alerts import _send_alerts, send_then_short
from swingbot.core.presentation import kinds
from swingbot.core.presentation.kinds import Kind

PIDS = {
    "AAPL": "6f1c2a3b-4d5e-4f60-8a7b-9c0d1e2f3a41",
    "MSFT": "6f1c2a3b-4d5e-4f60-8a7b-9c0d1e2f3a42",
    "NVDA": "6f1c2a3b-4d5e-4f60-8a7b-9c0d1e2f3a43",
}


class Chan:
    def __init__(self, fail_on=()):
        self.sent, self.calls, self.fail_on = [], 0, set(fail_on)

    async def send(self, *args, **kwargs):
        self.calls += 1
        if self.calls in self.fail_on:
            raise RuntimeError("discord is having a day")
        self.sent.append(kwargs)
        return types.SimpleNamespace(id=self.calls)


class FakeCooldown:
    def __init__(self, held_tickers=()):
        self.held_tickers = set(held_tickers)
        self.checked, self.recorded = [], []

    def suppressed(self, plan, now=None):
        self.checked.append(plan.ticker)
        return plan.ticker in self.held_tickers

    def record(self, plan, outcome, now=None):
        self.recorded.append((plan.ticker, outcome))


def _plan(ticker):
    return types.SimpleNamespace(plan_id=PIDS[ticker], ticker=ticker, direction="bullish",
                                 horizon_key="4w")


def _alert(ticker, plan=None):
    plan = plan if plan is not None else _plan(ticker)
    return (discord.Embed(title=ticker), None, plan, discord.Embed(title=f"{ticker}-simple"))


@pytest.fixture
def env(monkeypatch):
    from swingbot.commands import views
    from swingbot.core.analytics import rank

    class View:
        def __init__(self, plan_id, author_id=None):
            self.plan_id, self.message = plan_id, None

    simple = Chan()
    monkeypatch.setattr(views, "PlanActionView", View)
    monkeypatch.setattr(alerts, "rank_plans", lambda plans, today=None: list(plans))
    monkeypatch.setattr(rank, "follow_score", lambda plan: 50.0)
    monkeypatch.setattr(config, "DISCORD_CHANNEL_FIREHOSE_ID", "", raising=False)
    monkeypatch.setattr(config, "MAX_ALERTS_PER_SCAN", 10, raising=False)
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_SIMPLE_ID", "999", raising=False)
    monkeypatch.setattr(alerts, "bot", types.SimpleNamespace(get_channel=lambda _id: simple),
                        raising=False)
    return simple


@pytest.fixture
def fake_cd(monkeypatch):
    def install(held_tickers=()):
        fake = FakeCooldown(held_tickers)
        monkeypatch.setattr(cooldown, "suppressed", fake.suppressed)
        monkeypatch.setattr(cooldown, "record", fake.record)
        return fake
    return install


def _titles(chan):
    return [s["embed"].title for s in chan.sent]


def test_the_default_path_never_reads_or_writes_the_cooldown(env, fake_cd):
    fake = fake_cd({"AAPL"})
    main = Chan()
    held = asyncio.run(_send_alerts(main, [_alert("AAPL"), _alert("MSFT")]))
    assert held == []
    assert _titles(main) == ["AAPL", "MSFT"]
    assert fake.checked == [] and fake.recorded == []


def test_a_held_alert_posts_neither_the_alert_nor_its_mirror(env, fake_cd):
    fake = fake_cd({"AAPL"})
    main = Chan()
    aapl = _plan("AAPL")
    held = asyncio.run(_send_alerts(main, [_alert("AAPL", aapl), _alert("MSFT")],
                                    apply_cooldown=True))
    assert held == [aapl]
    assert _titles(main) == ["MSFT"]
    assert _titles(env) == ["MSFT-simple"]
    assert fake.recorded == [("AAPL", "suppressed"), ("MSFT", "posted")]


def test_the_cap_ranks_only_what_survives(env, fake_cd, monkeypatch):
    fake_cd({"AAPL"})
    monkeypatch.setattr(config, "MAX_ALERTS_PER_SCAN", 1, raising=False)
    main = Chan()
    asyncio.run(_send_alerts(main, [_alert("AAPL"), _alert("MSFT"), _alert("NVDA")],
                             apply_cooldown=True))
    assert _titles(main) == ["MSFT"]
    assert main.sent[0]["embed"].footer.text == "+1 more: NVDA (50)"


def test_a_legacy_alert_passes_without_a_check(env, fake_cd):
    fake = fake_cd({"AAPL"})
    main = Chan()
    held = asyncio.run(_send_alerts(main, [("E-legacy", None, None)], apply_cooldown=True))
    assert held == [] and fake.checked == [] and fake.recorded == []
    assert [s["embed"] for s in main.sent] == ["E-legacy"]


def test_a_failed_send_records_no_post(env, fake_cd):
    fake = fake_cd()
    main = Chan(fail_on={1})
    asyncio.run(_send_alerts(main, [_alert("MSFT"), _alert("NVDA")], apply_cooldown=True))
    assert _titles(main) == ["NVDA"]
    assert fake.recorded == [("NVDA", "posted")]


def test_a_broken_cooldown_store_still_posts_every_alert(env, monkeypatch, caplog):
    class Broken:
        def __getattr__(self, name):
            def _raise(*args, **kwargs):
                raise RuntimeError("database is having a day")
            return _raise

    monkeypatch.setattr(cooldown, "alert_posts_repo", lambda: Broken())
    main = Chan()
    with caplog.at_level(logging.WARNING):
        held = asyncio.run(_send_alerts(main, [_alert("AAPL"), _alert("MSFT")],
                                        apply_cooldown=True))
    assert held == []
    assert _titles(main) == ["AAPL", "MSFT"]
    assert any("posting the alert anyway" in r.getMessage() for r in caplog.records)


def test_a_held_alert_writes_neither_its_plan_nor_its_trade(env, fake_cd, monkeypatch):
    from swingbot.core.planning.plan_store import PlanStore
    from swingbot.core.tracking.performance import TradeLog
    from tests.planning.test_plan_engine_model import _plan as stored_plan

    plan = stored_plan(plan_id=PIDS["AAPL"])
    PlanStore().add(plan)

    def _no_write(*args, **kwargs):
        raise AssertionError("the cooldown must not write the book")

    monkeypatch.setattr(PlanStore, "update", _no_write)
    monkeypatch.setattr(TradeLog, "_db_upsert", staticmethod(_no_write))
    fake_cd({"AAPL"})
    held = asyncio.run(_send_alerts(Chan(), [_alert("AAPL", plan)], apply_cooldown=True))
    assert held == [plan]
    assert PlanStore().get(PIDS["AAPL"]).status == "PENDING"


def _short_lane(monkeypatch, held_by_batch):
    calls = []

    async def fake_send(dest, batch, route_by_confidence=False, *, apply_cooldown=False):
        calls.append((list(batch), apply_cooldown))
        return list(held_by_batch.get(batch[0], []))

    async def fake_short(**kw):
        return ["SHORT"]

    monkeypatch.setattr(config, "SHORT_UNIVERSE_ENABLED", True)
    monkeypatch.setattr(config, "SHORT_UNIVERSE_BROAD_ENABLED", True)
    monkeypatch.setattr(alerts, "_send_alerts", fake_send)
    monkeypatch.setattr(alerts.scan_engine, "run_short_universe_scan", fake_short)
    return calls


def test_send_then_short_forwards_the_flag_and_returns_every_held_plan(monkeypatch):
    calls = _short_lane(monkeypatch, {"BASE": ["held-base"], "SHORT": ["held-short"]})
    held = asyncio.run(send_then_short("chan", ["BASE"], apply_cooldown=True))
    assert held == ["held-base", "held-short"]
    assert calls == [(["BASE"], True), (["SHORT"], True)]


def test_send_then_short_defaults_to_no_cooldown(monkeypatch):
    calls = _short_lane(monkeypatch, {})
    assert asyncio.run(send_then_short("chan", ["BASE"])) == []
    assert calls == [(["BASE"], False), (["SHORT"], False)]


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


HELD_LINE = " · 2 alert(s) held by the symbol cooldown today"


def test_the_digest_header_states_todays_held_count(digest_env, monkeypatch):
    plans = [types.SimpleNamespace(plan_id=PIDS["AAPL"], ticker="AAPL")]
    monkeypatch.setattr(alerts, "digest_payload", lambda all_plans, today, max_n: plans)
    monkeypatch.setattr(cooldown, "held_today", lambda now=None: 2)
    chan = Chan()
    asyncio.run(alerts._post_daily_digest(chan))
    assert chan.sent[0]["content"] == kinds.content_line(
        Kind.DIGEST, "", detail="1 VALIDATED plan(s), ranked by follow score") + HELD_LINE


def test_the_empty_digest_states_todays_held_count(digest_env, monkeypatch):
    monkeypatch.setattr(alerts, "digest_payload", lambda all_plans, today, max_n: [])
    monkeypatch.setattr(cooldown, "held_today", lambda now=None: 2)
    chan = Chan()
    asyncio.run(alerts._post_daily_digest(chan))
    assert chan.sent == [{"content": kinds.content_line(
        Kind.DIGEST, "", detail="no VALIDATED plans qualified today") + HELD_LINE}]


def test_no_held_alerts_leave_the_digest_line_unchanged(digest_env, monkeypatch):
    monkeypatch.setattr(alerts, "digest_payload", lambda all_plans, today, max_n: [])
    monkeypatch.setattr(cooldown, "held_today", lambda now=None: 0)
    chan = Chan()
    asyncio.run(alerts._post_daily_digest(chan))
    assert chan.sent == [{"content": kinds.content_line(
        Kind.DIGEST, "", detail="no VALIDATED plans qualified today")}]
