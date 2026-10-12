"""v153 SP13: /backtest and /backtestwatchlist live in backtest.py, keep their
sync payload, and hand typed options straight to the shared handlers."""
import asyncio
import datetime as dt
import inspect

from discord import app_commands

from swingbot.bot_core import bot
from swingbot.commands import backtest as backtest_mod
from swingbot.commands import reply as reply_mod
from swingbot.commands.reply import CtxReply, InteractionReply
from tests.commands.reply_harness import FakeContext, FakeInteraction, comparable, run_both


def _capture(monkeypatch, name):
    seen = {}

    async def fake(reply, *args, **kwargs):
        seen.update(reply=reply, args=args, kwargs=kwargs)
    monkeypatch.setattr(backtest_mod, name, fake)
    return seen


def test_twins_live_in_backtest_py_and_slash_py_no_longer_defines_them():
    from swingbot.commands import slash
    source = inspect.getsource(slash)
    assert 'name="backtest"' not in source and 'name="backtestwatchlist"' not in source
    assert bot.tree.get_command("backtest") is backtest_mod.slash_backtest
    assert bot.tree.get_command("backtestwatchlist") is backtest_mod.slash_backtestwatchlist


def test_moved_twins_keep_their_description_and_options():
    assert backtest_mod.slash_backtest.description == "Backtest a ticker against historical data"
    assert [p.name for p in backtest_mod.slash_backtest.parameters] == [
        "ticker", "horizon", "strategy", "from_date", "to_date", "setups"]
    assert backtest_mod.slash_backtestwatchlist.description == (
        "Backtest every watchlist ticker, ranked by expectancy")
    assert [p.name for p in backtest_mod.slash_backtestwatchlist.parameters] == [
        "horizon", "strategy", "from_date", "to_date"]


def test_slash_backtest_keeps_the_chosen_horizon_when_strategy_is_omitted(monkeypatch):
    seen = _capture(monkeypatch, "handle_backtest")
    asyncio.run(backtest_mod.slash_backtest.callback(
        FakeInteraction([]), ticker="aapl", horizon=app_commands.Choice(name="4w", value="4w"),
        strategy=None, from_date="2024-01-01", to_date=None, setups=True))

    assert isinstance(seen["reply"], InteractionReply)
    assert seen["args"] == ("aapl", "4w", "all", "2024-01-01", None, True)


def test_slash_strategy_choice_becomes_the_canonical_name(monkeypatch):
    seen = _capture(monkeypatch, "handle_backtestwatchlist")
    asyncio.run(backtest_mod.slash_backtestwatchlist.callback(
        FakeInteraction([]), horizon=None,
        strategy=app_commands.Choice(name="EMA Crossover", value="ema"), from_date=None, to_date=None))

    assert seen["args"] == ("all", "EMA Crossover", None, None)


def test_every_strategy_choice_maps_to_a_canonical_name():
    from swingbot.commands.slash import STRATEGY_CHOICES
    for choice in STRATEGY_CHOICES:
        expected = "all" if choice.value == "all" else backtest_mod.STRATEGY_MAP[choice.value]
        assert backtest_mod._strategy_from_choice(choice) == expected
    assert backtest_mod._strategy_from_choice(None) == "all"


def test_backtest_multi_send_order_is_identical_on_both_surfaces(monkeypatch):
    from tests.commands.parity_cases.backtest import _ONE, _stub_one
    _stub_one(_ONE)(monkeypatch)

    run = run_both(lambda reply: backtest_mod.handle_backtest(reply, "aapl"), monkeypatch)

    contents = [event[1] for event in comparable(run.ctx_events)]
    assert contents == [event[1] for event in comparable(run.inter_events)]
    assert len(contents) == 3
    assert contents[0] == "Backtesting **AAPL**… this can take a few seconds."
    assert contents[1].startswith("Backtest — **AAPL** (250 bars of history):")
    assert contents[2].startswith("**Win rate by strategy**")


def test_backtestwatchlist_prefix_answer_ends_with_the_tip(monkeypatch):
    monkeypatch.setattr(reply_mod, "_today", lambda: reply_mod.PREFIX_TIP_UNTIL - dt.timedelta(days=1))
    monkeypatch.setattr(backtest_mod, "load_watchlist", lambda: [])
    monkeypatch.setattr(backtest_mod, "_sync_backtest_watchlist", lambda *a: ([], []))
    events: list = []

    asyncio.run(backtest_mod.backtestwatchlist_cmd.callback(FakeContext(events, qualified_name="backtestwatchlist")))

    assert events[-1][1] == "Tip: this is now /backtestwatchlist"


def test_prefix_backtest_passes_parsed_tokens_to_the_handler(monkeypatch):
    seen = _capture(monkeypatch, "handle_backtest")
    asyncio.run(backtest_mod.backtest_cmd.callback(
        FakeContext([]), "tsla", "4w", "bnr", "from:2024-01-01", "setups"))

    assert isinstance(seen["reply"], CtxReply)
    assert seen["args"] == ("tsla", "4w", "Break & Retest", "2024-01-01", None, True)
