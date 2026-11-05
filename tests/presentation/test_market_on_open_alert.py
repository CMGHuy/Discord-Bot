"""V192-12: the alert says 'Enter at the open (market-on-open)' and shows X for a
market plan waiting for its next open; every other plan renders as before."""
import pytest

from swingbot import config
from swingbot.core.presentation import instructions as ins
from swingbot.core.presentation import tokens
from swingbot.core.scanning import alert_embeds as ae
from tests.planning.test_plan_engine_model import _plan
from tests.presentation.test_feed_guards import _FORBIDDEN, _allowed, _order_glyph_hits

S = tokens.FEED_SYMBOLS


def _market(direction="bullish", **kw):
    levels = (dict(stop_loss=98.5, tp1=103.0, tp2=105.0) if direction == "bullish"
              else dict(stop_loss=101.5, tp1=97.0, tp2=95.0))
    base = dict(source="confluence", strategy="S/R Confluence", entry_type="market",
                direction=direction, trigger_price=100.0, status="PENDING",
                waits_next_open=True, **levels)
    base.update(kw)
    return _plan(**base)


@pytest.fixture(autouse=True)
def _url(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_PUBLIC_URL", "https://example.test")


def test_the_line_is_the_specs_wording():
    assert ins.MARKET_ON_OPEN == "Enter at the open (market-on-open)"


@pytest.mark.parametrize("plan", [
    _market(waits_next_open=None, status="ACTIVE", entry_price=100.0),   # knob off: today's plan
    _market(entry_type="stop_entry", waits_next_open=None),
    _market(status="ACTIVE", entry_price=99.8),                          # already filled
])
def test_no_line_for_a_plan_that_does_not_wait(plan):
    assert ins.market_on_open_lines(plan) == []
    assert ae._market_on_open_fields(plan) == []


def test_a_waiting_plan_without_a_veto_has_the_open_line_only():
    assert ins.market_on_open_lines(_market()) == [ins.MARKET_ON_OPEN]


@pytest.mark.parametrize("direction, level, side, refrain, order", [
    ("bullish", 99.5, "below", "buy", "BUY STOP"),
    ("bearish", 100.5, "above", "short", "SELL STOP"),
])
def test_the_x_reference_line(direction, level, side, refrain, order):
    lines = ins.market_on_open_lines(_market(direction, reclaim_level=level, reclaim_atr=2.0))
    assert lines == [ins.MARKET_ON_OPEN,
                     f"If it opens at or {side} {level:.2f} (toward the stop): don't {refrain} "
                     f"at the open; the bot posts a DAY {order} at 100.00"]


@pytest.mark.parametrize("direction, verb", [("bullish", "BUY AT MARKET"),
                                             ("bearish", "SELL SHORT AT MARKET")])
def test_the_ticket_orders_on_the_open(direction, verb):
    plan = _market(direction, reclaim_level=99.5 if direction == "bullish" else 100.5)
    ticket = ins.ticket_for(plan, logged=True, not_logged_reason=None,
                            money=ins.money_from(54.35, "$"), level=4)
    assert ticket.headline.startswith(f"{S['entry']} {verb} ON OPEN ~100.00 · ")
    assert ticket.lines[:2] == tuple(ins.market_on_open_lines(plan))
    allowed = _allowed(direction)
    for key, after in _order_glyph_hits(ticket):
        assert after.startswith(allowed[key]), (key, after)
    text = "\n".join((ticket.headline, *ticket.lines))
    assert [v for v in _FORBIDDEN[direction] if v in text] == []


def test_a_knob_off_market_ticket_is_unchanged():
    plan = _market(waits_next_open=None, status="ACTIVE", entry_price=100.0)
    ticket = ins.ticket_for(plan, logged=True, not_logged_reason=None,
                            money=ins.money_from(54.35, "$"), level=4)
    assert ticket.headline.startswith(f"{S['entry']} BUY AT MARKET ~100.00 · ")
    assert "ON OPEN" not in ticket.headline
    assert ins.MARKET_ON_OPEN not in ticket.lines


def test_the_field_carries_the_lines():
    plan = _market(reclaim_level=99.5)
    assert ae._market_on_open_fields(plan) == [
        (ae.MARKET_ON_OPEN_FIELD, "\n".join(ins.market_on_open_lines(plan)), False)]
    assert ae._market_on_open_fields(None) == []


def test_the_strategy_alert_and_its_simple_mirror_show_the_line():
    plan = _market(source="strategy", strategy="Fibonacci", reclaim_level=99.5)
    full = ae.build_strategy_alert_embed(plan)
    assert [f.value for f in full.fields if f.name == ae.MARKET_ON_OPEN_FIELD] == [
        "\n".join(ins.market_on_open_lines(plan))]
    simple = ae.build_strategy_simple_embed(plan)
    assert ins.MARKET_ON_OPEN in simple.description


def test_a_strategy_alert_that_does_not_wait_has_no_field():
    plan = _market(source="strategy", strategy="Fibonacci", waits_next_open=None,
                   status="ACTIVE", entry_price=100.0)
    assert ae.MARKET_ON_OPEN_FIELD not in [f.name for f in ae.build_strategy_alert_embed(plan).fields]
    assert ins.MARKET_ON_OPEN not in ae.build_strategy_simple_embed(plan).description
