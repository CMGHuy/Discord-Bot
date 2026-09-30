"""v111 §3: one INFO line per successful ticker-bearing push, named by v110's Kind."""
import asyncio
import logging
from types import SimpleNamespace

import discord

from swingbot import config
from swingbot.commands.scanning import alerts
from swingbot.core import presentation as ui
from swingbot.core.infra import posted_log
from swingbot.core.infra.posted_log import log_posted
from swingbot.core.presentation.kinds import Kind
from swingbot.core.scanning import lifecycle_embeds as life


def _lines(caplog):
    return [r.getMessage() for r in caplog.records if r.name == posted_log.log.name]


def test_line_names_kind_ticker_and_channel(caplog):
    member = next(iter(Kind))
    with caplog.at_level(logging.INFO, logger=posted_log.log.name):
        log_posted(SimpleNamespace(kind=member), "AAPL", SimpleNamespace(name="trades"))
    assert _lines(caplog) == [f"alert posted kind={member.name} ticker=AAPL channel=trades"]


def test_a_command_context_is_named_by_its_channel(caplog):
    member = next(iter(Kind))
    ctx = SimpleNamespace(channel=SimpleNamespace(name="bot-commands"))
    with caplog.at_level(logging.INFO, logger=posted_log.log.name):
        log_posted(SimpleNamespace(kind=member), None, ctx)
    assert _lines(caplog) == [f"alert posted kind={member.name} ticker=- channel=bot-commands"]


def test_an_explicit_kind_names_an_embed_that_carries_none(caplog):
    with caplog.at_level(logging.INFO, logger=posted_log.log.name):
        log_posted(discord.Embed(), "MSFT", SimpleNamespace(name="c"), kind=Kind.DIGEST)
    assert _lines(caplog) == ["alert posted kind=DIGEST ticker=MSFT channel=c"]


class _Chan:
    def __init__(self, name, fail=False):
        self.name, self.fail, self.sent = name, fail, []

    async def send(self, *args, **kwargs):
        if self.fail:
            raise RuntimeError("discord 500")
        self.sent.append(kwargs)
        return SimpleNamespace(id=len(self.sent))


def _view_stub(monkeypatch):
    monkeypatch.setattr("swingbot.commands.views.PlanActionView",
                        lambda plan_id, author_id=None: SimpleNamespace(message=None))


def _send(monkeypatch, chan, member, simple=None, plan=None, simple_embed=None):
    monkeypatch.setattr(ui, "push_kwargs", lambda embed: {"embed": embed})
    monkeypatch.setattr(alerts, "_simple_alert_channel", lambda: simple)
    monkeypatch.setattr(config, "MAX_ALERTS_PER_SCAN", 10)
    embed = SimpleNamespace(kind=member, footer=None)
    asyncio.run(alerts._send_alerts(chan, [(embed, None, plan, simple_embed)]))


def test_send_alerts_logs_each_successful_send_once(monkeypatch, caplog):
    member = next(iter(Kind))
    with caplog.at_level(logging.INFO, logger=posted_log.log.name):
        _send(monkeypatch, _Chan("trades"), member)
    assert _lines(caplog) == [f"alert posted kind={member.name} ticker=- channel=trades"]


def test_a_failed_send_logs_no_posted_line(monkeypatch, caplog):
    member = next(iter(Kind))
    with caplog.at_level(logging.INFO, logger=posted_log.log.name):
        _send(monkeypatch, _Chan("trades", fail=True), member)
    assert _lines(caplog) == []


def test_the_simple_mirror_gets_its_own_line(monkeypatch, caplog):
    _view_stub(monkeypatch)
    plan = SimpleNamespace(ticker="NVDA", plan_id="p1")
    with caplog.at_level(logging.INFO, logger=posted_log.log.name):
        _send(monkeypatch, _Chan("full"), Kind.STRATEGY_SIGNAL, simple=_Chan("simple"),
              plan=plan, simple_embed=SimpleNamespace(kind=Kind.SETUP_SIMPLE))
    assert _lines(caplog) == [
        "alert posted kind=SETUP_SIMPLE ticker=NVDA channel=simple",
        "alert posted kind=STRATEGY_SIGNAL ticker=NVDA channel=full",
    ]


def test_a_failed_mirror_logs_no_mirror_line(monkeypatch, caplog):
    _view_stub(monkeypatch)
    plan = SimpleNamespace(ticker="NVDA", plan_id="p1")
    with caplog.at_level(logging.INFO, logger=posted_log.log.name):
        _send(monkeypatch, _Chan("full"), Kind.STRATEGY_SIGNAL, simple=_Chan("simple", fail=True),
              plan=plan, simple_embed=SimpleNamespace(kind=Kind.SETUP_SIMPLE))
    assert _lines(caplog) == ["alert posted kind=STRATEGY_SIGNAL ticker=NVDA channel=full"]


def test_the_daily_digest_logs_each_plan_as_digest(monkeypatch, caplog):
    from swingbot.commands import stats
    from swingbot.core.planning import plan_store
    from swingbot.core.scanning import embeds
    _view_stub(monkeypatch)
    plans = [SimpleNamespace(plan_id="p1", ticker="AAA"), SimpleNamespace(plan_id="p2", ticker="BBB")]
    monkeypatch.setattr(plan_store, "PlanStore", lambda: SimpleNamespace(all=lambda: []))
    monkeypatch.setattr(stats, "_fake_item_from_plan", lambda plan: plan)
    monkeypatch.setattr(embeds, "build_embed", lambda item, *a, **k: discord.Embed(title=item.plan_id))
    monkeypatch.setattr(alerts, "digest_payload", lambda all_plans, today, max_n: plans)
    with caplog.at_level(logging.INFO, logger=posted_log.log.name):
        asyncio.run(alerts._post_daily_digest(_Chan("digest")))
    assert _lines(caplog) == ["alert posted kind=DIGEST ticker=AAA channel=digest",
                              "alert posted kind=DIGEST ticker=BBB channel=digest"]


def _bot(**channels):
    return SimpleNamespace(get_channel=lambda cid: channels.get(str(int(cid))))


def test_closed_trade_notices_log_only_when_the_send_succeeds(monkeypatch, caplog):
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_HISTORY_ID", "5")
    monkeypatch.setattr(ui, "push_kwargs", lambda embed: {"embed": embed})
    monkeypatch.setattr(life, "build_closed_trade_embed",
                        lambda trade: SimpleNamespace(kind=Kind.WIN))
    trades = [{"id": "t1", "ticker": "AAPL", "status": "win"}]
    with caplog.at_level(logging.INFO, logger=posted_log.log.name):
        asyncio.run(life.notify_closed_trades(_bot(**{"5": _Chan("hist", fail=True)}), trades))
        assert _lines(caplog) == []
        asyncio.run(life.notify_closed_trades(_bot(**{"5": _Chan("hist")}), trades))
    assert _lines(caplog) == ["alert posted kind=WIN ticker=AAPL channel=hist"]


def test_near_close_notices_log_the_warning_ticker(monkeypatch, caplog):
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_HISTORY_ID", "5")
    monkeypatch.setattr(ui, "push_kwargs", lambda embed: {"embed": embed})
    monkeypatch.setattr(life, "build_near_close_embed",
                        lambda warning: SimpleNamespace(kind=Kind.NEAR_STOP))
    warnings = [{"trade": {"id": "t1", "ticker": "TSLA"}}]
    with caplog.at_level(logging.INFO, logger=posted_log.log.name):
        asyncio.run(life.notify_near_close(_bot(**{"5": _Chan("hist")}), warnings))
    assert _lines(caplog) == ["alert posted kind=NEAR_STOP ticker=TSLA channel=hist"]


def _plan_events_env(monkeypatch, transition):
    from swingbot.core.planning import plan_store
    from swingbot.core.scanning import execution_embeds
    plan = SimpleNamespace(plan_id="p1", ticker="AMD", direction="bullish")
    monkeypatch.setattr(plan_store, "PlanStore", lambda: SimpleNamespace(get=lambda pid: plan))
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_SIMPLE_ID", "1")
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_HISTORY_ID", "2")
    monkeypatch.setattr(ui, "push_kwargs", lambda embed: {"embed": embed})
    monkeypatch.setattr(life, "build_plan_event_embed",
                        lambda p, e: SimpleNamespace(kind=Kind.EXPIRED))
    monkeypatch.setattr(execution_embeds, "build_instruction_embed",
                        lambda p, e: SimpleNamespace(kind=Kind.BE_MOVED))
    monkeypatch.setattr(life, "_delivery", lambda p, e: None)
    return SimpleNamespace(plan_id="p1", transition=transition, detail={})


def test_a_feed_event_logs_a_line_for_the_feed_and_the_history_copy(monkeypatch, caplog):
    event = _plan_events_env(monkeypatch, "be_moved")
    bot = _bot(**{"1": _Chan("feed"), "2": _Chan("history")})
    with caplog.at_level(logging.INFO, logger=posted_log.log.name):
        asyncio.run(life.notify_plan_events(bot, [event]))
    assert _lines(caplog) == ["alert posted kind=BE_MOVED ticker=AMD channel=feed",
                              "alert posted kind=BE_MOVED ticker=AMD channel=history"]


def test_a_history_only_event_logs_one_line(monkeypatch, caplog):
    event = _plan_events_env(monkeypatch, "something_else")
    bot = _bot(**{"1": _Chan("feed"), "2": _Chan("history")})
    with caplog.at_level(logging.INFO, logger=posted_log.log.name):
        asyncio.run(life.notify_plan_events(bot, [event]))
    assert _lines(caplog) == ["alert posted kind=EXPIRED ticker=AMD channel=history"]
