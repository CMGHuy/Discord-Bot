"""v227: the short headline the admin site speaks for each simple-channel post."""
import dataclasses
import math
from types import SimpleNamespace

import discord
import pytest

from swingbot import config
from swingbot.core.presentation import components as c
from swingbot.core.presentation import feed_headline as fh
from swingbot.core.presentation import short_notice
from swingbot.core.presentation.kinds import Family, Kind
from swingbot.core.scanning import alert_embeds as ae
from swingbot.core.scanning import execution_embeds
from tests.presentation.test_market_on_open_alert import _market
from tests.scanning.test_embeds_v3 import (make_item, make_plan_v2,  # noqa: F401
                                           _isolated_scan_snapshots)

FIVE = (Family.NEW_SETUP, Family.ENTRY, Family.MANAGE, Family.WATCH, Family.RESULT)


def _embed(direction=None, entry_price=None):
    return SimpleNamespace(direction=direction, entry_price=entry_price)


def test_the_five_simple_channel_families_in_order():
    assert fh.FEED_FAMILIES == FIVE


def test_every_kind_of_the_five_families_has_a_phrase():
    missing = [k.name for k in Kind if k.family in FIVE and k not in fh.KIND_PHRASES]
    assert missing == []
    assert not [k.name for k in fh.KIND_PHRASES if k.family not in FIVE]


@pytest.mark.parametrize("kind,embed,ticker,expected", [
    (Kind.SETUP_SIMPLE, _embed("bullish", 187.5), "AAPL", "New long alert, AAPL, buy at 187.50"),
    (Kind.SETUP_ALERT, _embed("bearish", 42.0), "TSLA", "New short alert, TSLA, sell at 42.00"),
    (Kind.STRATEGY_SIGNAL, _embed(None, 10.0), "AMD", "New alert, AMD, entry 10.00"),
    (Kind.TICKET_PLACE, _embed("bullish", 99.991), "NVDA", "Place order, NVDA, buy at 99.99"),
    (Kind.TICKET_DO_NOT_PLACE, _embed("bullish", 99.0), "NVDA", "Do not place, NVDA"),
    (Kind.FILLED, _embed("bullish", 187.5), "MSFT", "Order filled, MSFT"),
    (Kind.CANCEL, _embed("bullish"), "MSFT", "Order cancelled, MSFT"),
    (Kind.MOVE_STOP, _embed(), "MSFT", "Move stop loss, MSFT"),
    (Kind.TP1_HIT, _embed(), "MSFT", "Take profit one, MSFT"),
    (Kind.STOPPED, _embed(), "MSFT", "Stopped out, MSFT"),
    (Kind.NEAR_STOP, _embed(), "MSFT", "Near stop, MSFT"),
    (Kind.RISK_CAP, _embed(), None, "Cancelled by risk cap"),
])
def test_headlines(kind, embed, ticker, expected):
    assert fh.feed_headline(kind, embed, ticker) == expected


@pytest.mark.parametrize("price", [None, 0, -5.0, math.nan, math.inf, "abc", "187.5x"])
def test_a_missing_or_bad_price_drops_the_clause(price):
    assert fh.feed_headline(Kind.SETUP_SIMPLE, _embed("bullish", price), "AAPL") == "New long alert, AAPL"


@pytest.mark.parametrize("ticker", [None, "", "   ", math.nan, 12])
def test_a_missing_or_odd_ticker_is_dropped(ticker):
    assert fh.feed_headline(Kind.FILLED, _embed(), ticker) == "Order filled"


def test_an_embed_without_the_attributes_is_fine():
    assert fh.feed_headline(Kind.SETUP_SIMPLE, discord.Embed(), "AAPL") == "New alert, AAPL"
    assert fh.feed_headline(Kind.SETUP_SIMPLE, object(), "AAPL") == "New alert, AAPL"


def test_a_kind_without_a_phrase_falls_back_to_its_label_lower_cased():
    assert fh.feed_headline(Kind.BOT_ONLINE, _embed(), None) == "online"
    assert fh.kind_phrase(Kind.HEALTH_ALERT) == "health alert"


def test_spoken_text_never_says_none_or_nan_for_any_kind():
    for kind in Kind:
        for embed in (_embed(), _embed("bullish", None), _embed("sideways", math.nan)):
            text = fh.feed_headline(kind, embed, None)
            assert text and "None" not in text and "nan" not in text.split(", ")
            assert ", ," not in text and not text.endswith(", ")


def test_kind_phrase_without_a_side_drops_the_placeholder():
    assert fh.kind_phrase(Kind.SETUP_SIMPLE) == "New alert"
    assert fh.kind_phrase(Kind.SETUP_SIMPLE, "long") == "New long alert"
    assert fh.kind_phrase(Kind.FILLED, "long") == "Order filled"


def test_sample_headlines():
    assert fh.sample_headline(Kind.SETUP_SIMPLE) == "New long alert, AAPL, buy at 187.50"
    assert fh.sample_headline(Kind.TICKET_PLACE) == "Place order, AAPL, buy at 187.50"
    assert fh.sample_headline(Kind.FILLED) == "Order filled, AAPL"
    assert fh.sample_headline(Kind.NEAR_TP) == "Near target, AAPL"


# --- the embeds carry what the headline reads ---------------------------------------

def test_push_embed_carries_direction_and_no_price():
    embed = c.push_embed(Kind.FILLED, "MSFT", "bearish")
    assert embed.direction == "bearish" and embed.entry_price is None


def test_status_embed_carries_neither():
    embed = c.status_embed("Title", "Body", 0x123456)
    assert embed.direction is None and embed.entry_price is None


def test_the_new_slots_never_reach_discord():
    embed = c.push_embed(Kind.SETUP_SIMPLE, "AAPL", "bullish", "Lv3")
    embed.entry_price = 187.5
    payload = embed.to_dict()
    assert "direction" not in payload and "entry_price" not in payload
    assert c.push_kwargs(embed) == {"embed": embed, "content": embed.push_text}


@pytest.fixture
def _alerts_env(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(config, "CURRENCY_SYMBOL", "$")
    monkeypatch.setattr(config, "ADMIN_PUBLIC_URL", "https://example.test")
    monkeypatch.setattr(short_notice, "completed_session_date", lambda: "2026-10-01")
    monkeypatch.setattr(execution_embeds, "_sizing_snapshot", lambda entry, plan: {
        "shares": 20.0, "risk_amount": 100.0, "position_value": 2000.0, "mode": "risk_pct"})


def test_the_strategy_mirror_carries_its_trigger_price(_alerts_env):
    plan = _market(source="strategy", strategy="Fibonacci", trigger_price=101.25)
    embed = ae.build_strategy_simple_embed(plan)
    assert embed.direction == "bullish" and embed.entry_price == 101.25
    assert fh.feed_headline(embed.kind, embed, plan.ticker).endswith("buy at 101.25")


def test_the_simple_alert_carries_the_entry_it_prints(_alerts_env, monkeypatch):
    # The legacy simple alert prints "Entry **x.xx**"; with the v2 engine on it is the ticket.
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "off")
    item = make_item(plan_v2=make_plan_v2())
    embed = ae.build_simple_alert(item)
    assert embed.direction == item.result.trend
    assert isinstance(embed.entry_price, float) and embed.entry_price > 0
    assert f"Entry **{embed.entry_price:.2f}**" in embed.description


def test_the_simple_alert_on_the_v2_path_carries_the_trigger_price(_alerts_env):
    item = make_item(plan_v2=make_plan_v2(trigger_price=123.4))
    embed = ae.build_simple_alert(item)
    assert embed.direction == item.result.trend
    assert embed.entry_price == item.plan_v2.trigger_price


def test_the_ticket_carries_its_trigger_price(_alerts_env):
    item = make_item(plan_v2=dataclasses.replace(make_plan_v2(trigger_price=123.4), stop_loss=95.0))
    item.paper_logged = True
    embed = execution_embeds.build_ticket_embed(item, item.plan_v2)
    assert embed.kind in (Kind.TICKET_PLACE, Kind.TICKET_DO_NOT_PLACE)
    assert embed.entry_price == 123.4 and embed.direction == "bullish"
