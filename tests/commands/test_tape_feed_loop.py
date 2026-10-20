"""v171 D7: the bot feeds the shared tape once a minute in session."""
import asyncio

import pytest

from swingbot import config
from swingbot.commands.scanning import loops as loops_mod
from swingbot.core.marketdata import data
from swingbot.core.marketdata.shared import tape
from swingbot.core.marketdata.shared.kinds import Asker


@pytest.fixture
def feed(monkeypatch):
    monkeypatch.setattr(config, "TAPE_SHARED_ENABLED", True)
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    monkeypatch.setattr(data, "is_us_market_active", lambda: True)
    monkeypatch.setattr(tape, "demanded_symbols", lambda now: ["^GSPC", "SI=F"])
    calls = []
    monkeypatch.setattr(tape, "refresh_tape",
                        lambda syms, *, asker, max_age_s=None: calls.append((syms, asker, max_age_s)) or {})
    return calls


def _tick():
    asyncio.run(loops_mod.tape_feed.coro())


def test_one_refresh_per_tick_at_the_background_tier(feed):
    _tick()
    assert feed == [(["^GSPC", "SI=F"], Asker.BACKGROUND, 30.0)]


@pytest.mark.parametrize("attr,value", [("TAPE_SHARED_ENABLED", False), ("MARKETDATA_LAYER", "count")])
def test_flag_off_or_layer_not_on_does_nothing(feed, monkeypatch, attr, value):
    monkeypatch.setattr(config, attr, value)
    _tick()
    assert feed == []


def test_out_of_session_does_nothing(feed, monkeypatch):
    monkeypatch.setattr(data, "is_us_market_active", lambda: False)
    _tick()
    assert feed == []


def test_a_failed_refresh_is_logged_not_raised(feed, monkeypatch, caplog):
    def boom(*a, **k):
        raise RuntimeError("yahoo down")
    monkeypatch.setattr(tape, "refresh_tape", boom)
    _tick()
    assert "tape_feed" in caplog.text


def test_registered_last_as_an_always_on_loop():
    loops = loops_mod._always_on_loops()
    assert loops[-1] is loops_mod.tape_feed
    assert loops.index(loops_mod.daily_reanchor) < loops.index(loops_mod.tape_feed)
