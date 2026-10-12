"""v153 SP14: /watchlist and !watchlist share handle_watchlist."""
import asyncio
import datetime as dt
import inspect

from swingbot.bot_core import bot
from swingbot.commands import reply as reply_mod
from swingbot.commands import watchlist as watchlist_mod
from tests.commands.parity_cases.watchlist import _stub
from tests.commands.reply_harness import FakeContext, comparable, run_both


def _tip_window_open(monkeypatch):
    monkeypatch.setattr(reply_mod, "_today", lambda: reply_mod.PREFIX_TIP_UNTIL - dt.timedelta(days=1))


def test_action_table_is_the_slash_choice_list():
    choices = [c.value for c in watchlist_mod.slash_watchlist.parameters[0].choices]
    assert list(watchlist_mod.WATCHLIST_ACTIONS) == ["show", "add", "remove", "clear"] == choices


def test_watchlist_twin_lives_in_watchlist_py_with_its_payload_unchanged():
    from swingbot.commands import slash
    assert 'name="watchlist"' not in inspect.getsource(slash)
    assert bot.tree.get_command("watchlist") is watchlist_mod.slash_watchlist
    assert watchlist_mod.slash_watchlist.description == "Show, add, or remove tickers from the watchlist"
    assert [p.name for p in watchlist_mod.slash_watchlist.parameters] == ["action", "ticker"]
    assert [c.name for c in watchlist_mod.slash_watchlist.parameters[0].choices] == [
        "Show", "Add", "Remove", "Clear"]


def test_missing_ticker_is_the_same_text_on_both_surfaces_and_ephemeral_only_on_slash(monkeypatch):
    run = run_both(lambda reply: watchlist_mod.handle_watchlist(reply, "add"), monkeypatch)

    assert run.ctx_events == [("send", watchlist_mod.MISSING_TICKER, None, (), None, False)]
    assert run.inter_events == [("send", watchlist_mod.MISSING_TICKER, None, (), None, True)]
    assert run.ctx_reply.failed and run.inter_reply.failed


def test_unknown_action_names_the_valid_actions(monkeypatch):
    run = run_both(lambda reply: watchlist_mod.handle_watchlist(reply, "rename", "AAPL"), monkeypatch)

    assert comparable(run.ctx_events) == comparable(run.inter_events)
    text = run.ctx_events[0][1]
    assert "rename" in text and "show, add, remove, clear" in text


def test_prefix_add_stores_the_upper_cased_ticker_and_ends_with_the_tip(monkeypatch):
    _tip_window_open(monkeypatch)
    _stub()(monkeypatch)
    stored, cached = [], []
    monkeypatch.setattr(watchlist_mod, "add_ticker", lambda t: stored.append(t) or ["AAPL", t])
    monkeypatch.setattr(watchlist_mod, "ensure_cached_background", cached.append)
    events: list = []

    asyncio.run(watchlist_mod.watchlist_add.callback(FakeContext(events, qualified_name="watchlist add"), "nvda"))

    assert stored == ["NVDA"] and cached == ["NVDA"]
    assert events[0][1] == "Added **NVDA**. Watchlist: AAPL, NVDA"
    assert events[-1][1] == "Tip: this is now /watchlist add"


def test_bare_prefix_add_answers_the_guard_without_a_tip(monkeypatch):
    _tip_window_open(monkeypatch)
    events: list = []

    asyncio.run(watchlist_mod.watchlist_add.callback(FakeContext(events, qualified_name="watchlist add")))

    assert [event[1] for event in events] == [watchlist_mod.MISSING_TICKER]


def test_prefix_group_shows_the_list_and_tips_the_show_choice(monkeypatch):
    _tip_window_open(monkeypatch)
    _stub()(monkeypatch)
    events: list = []

    asyncio.run(watchlist_mod.watchlist_cmd.callback(FakeContext(events, qualified_name="watchlist")))

    assert [event[1] for event in events] == [
        "Current watchlist: AAPL, MSFT", "Tip: this is now /watchlist show"]
