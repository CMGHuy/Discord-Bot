"""v227: only an accepted simple-channel send records a feed post -- never a failed
send, the history copy, or a history-only status embed."""
import asyncio
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.commands.scanning import alerts
from swingbot.core import presentation as ui
from swingbot.core.presentation.kinds import Kind
from swingbot.core.scanning import lifecycle_embeds as life


class _Chan:
    def __init__(self, name, fail=False):
        self.name, self.fail, self.sent = name, fail, []

    async def send(self, *args, **kwargs):
        if self.fail:
            raise RuntimeError("discord 500")
        self.sent.append(kwargs)
        return SimpleNamespace(id=len(self.sent))


def _bot(**channels):
    return SimpleNamespace(get_channel=lambda cid: channels.get(str(int(cid))))


@pytest.fixture
def calls(monkeypatch):
    """Every record_feed_post call either sender makes, as (embed, ticker)."""
    seen: list[tuple] = []

    def record(embed, ticker, kind=None):
        seen.append((embed, ticker))

    monkeypatch.setattr(alerts, "record_feed_post", record)
    monkeypatch.setattr(life, "record_feed_post", record)
    monkeypatch.setattr(ui, "push_kwargs", lambda embed, view=None: {"embed": embed})
    monkeypatch.setattr(alerts, "_ticket_view", lambda embed, plan: None)
    monkeypatch.setattr(life, "_feed_view", lambda plan_id: None)
    return seen


# --- alerts._mirror: new setups, tickets, strategy mirrors ----------------------------

def test_an_accepted_mirror_records_the_simple_embed_once(calls):
    embed = SimpleNamespace(kind=Kind.SETUP_SIMPLE)
    plan = SimpleNamespace(ticker="NVDA", plan_id="p1")
    assert asyncio.run(alerts._mirror(_Chan("simple"), embed, plan)) is True
    assert calls == [(embed, "NVDA")]


def test_a_mirror_without_a_plan_records_a_null_ticker(calls):
    embed = SimpleNamespace(kind=Kind.STRATEGY_SIGNAL)
    assert asyncio.run(alerts._mirror(_Chan("simple"), embed, None)) is True
    assert calls == [(embed, None)]


def test_a_failed_mirror_records_nothing(calls):
    ok = asyncio.run(alerts._mirror(_Chan("simple", fail=True), SimpleNamespace(kind=Kind.SETUP_SIMPLE),
                                    SimpleNamespace(ticker="NVDA", plan_id="p1")))
    assert ok is False and calls == []


def test_no_simple_channel_records_nothing(calls):
    assert asyncio.run(alerts._mirror(None, SimpleNamespace(kind=Kind.SETUP_SIMPLE), None)) is False
    assert calls == []


# --- lifecycle_embeds._send_instruction: fills, cancels, stops, TP1, results ----------

_PLAN = SimpleNamespace(plan_id="p1", ticker="AMD", direction="bullish")
_EVENT = SimpleNamespace(plan_id="p1", transition="be_moved", detail={})


def _instruction(feed, history):
    embed = SimpleNamespace(kind=Kind.BE_MOVED)
    pinged = asyncio.run(life._send_instruction(feed, history, embed, _PLAN, _EVENT))
    return embed, pinged


def test_an_accepted_feed_send_records_once_and_the_history_copy_never(calls):
    feed, history = _Chan("feed"), _Chan("history")
    embed, pinged = _instruction(feed, history)
    assert pinged is True and len(feed.sent) == 1 and len(history.sent) == 1
    assert calls == [(embed, "AMD")]


def test_a_failed_feed_send_records_nothing_even_when_history_takes_it(calls):
    history = _Chan("history")
    _embed, pinged = _instruction(_Chan("feed", fail=True), history)
    assert pinged is True and len(history.sent) == 1
    assert calls == []


def test_no_feed_channel_history_only_records_nothing(calls):
    _embed, pinged = _instruction(None, _Chan("history"))
    assert pinged is True and calls == []


def test_a_history_only_status_event_records_nothing(calls, monkeypatch):
    from swingbot.core.planning import plan_store
    monkeypatch.setattr(plan_store, "PlanStore", lambda: SimpleNamespace(get=lambda pid: _PLAN))
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_SIMPLE_ID", "1")
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_HISTORY_ID", "2")
    monkeypatch.setattr(life, "build_plan_event_embed", lambda p, e: SimpleNamespace(kind=Kind.EXPIRED))
    history = _Chan("history")
    event = SimpleNamespace(plan_id="p1", transition="something_else", detail={})
    asyncio.run(life.notify_plan_events(_bot(**{"1": _Chan("feed"), "2": history}), [event]))
    assert len(history.sent) == 1 and calls == []


def test_a_feed_event_through_notify_plan_events_records_once(calls, monkeypatch):
    from swingbot.core.planning import plan_store
    from swingbot.core.scanning import execution_embeds
    embed = SimpleNamespace(kind=Kind.BE_MOVED)
    monkeypatch.setattr(plan_store, "PlanStore", lambda: SimpleNamespace(get=lambda pid: _PLAN))
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_SIMPLE_ID", "1")
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_HISTORY_ID", "2")
    monkeypatch.setattr(execution_embeds, "build_instruction_embed", lambda p, e: embed)
    monkeypatch.setattr(life, "_delivery", lambda p, e: None)
    asyncio.run(life.notify_plan_events(_bot(**{"1": _Chan("feed"), "2": _Chan("history")}), [_EVENT]))
    assert calls == [(embed, "AMD")]


def test_both_senders_call_the_recorder_right_after_log_posted():
    import inspect
    for fn, line in ((alerts._mirror, "log_posted(simple_embed"),
                     (life._send_instruction, "log_posted(embed, plan.ticker, feed)")):
        src = inspect.getsource(fn)
        after = src.split(line, 1)[1].splitlines()[1].strip()
        assert after.startswith("record_feed_post("), fn.__name__
