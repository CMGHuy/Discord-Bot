"""V192-10: execution-feed copy for a market plan waiting for its next open --
the DAY stop-order instruction, the new cancels, the missed open, the gap-target
close -- under the v170 feed guards, plus the registry kind and both kind maps."""
import importlib.util
from pathlib import Path

import pytest

from swingbot.core.planning.plan_manager import PlanEvent
from swingbot.core.presentation import instructions as ins
from swingbot.core.presentation import tokens
from swingbot.core.presentation.kinds import Family, Kind
from swingbot.core.scanning import execution_embeds as ee
from swingbot.core.scanning import lifecycle_embeds as le
from tests.planning.test_plan_engine_model import _plan
from tests.presentation.test_feed_guards import _FORBIDDEN, _VERBS, _allowed, _order_glyph_hits

S = tokens.FEED_SYMBOLS
LEVELS = {
    "bullish": dict(trigger_price=100.0, stop_loss=98.5, tp1=103.0, tp2=105.0, reclaim_level=99.5),
    "bearish": dict(trigger_price=100.0, stop_loss=101.5, tp1=97.0, tp2=95.0, reclaim_level=100.5),
}
NEW = ("gap_reclaim_order", "cancelled_open_through_stop", "cancelled_gap_no_reclaim")


def _waiting(direction="bullish", **kw):
    base = dict(source="confluence", strategy="S/R Confluence", entry_type="market",
                direction=direction, waits_next_open=True, reclaim_atr=2.0,
                status="PENDING", **LEVELS[direction])
    base.update(kw)
    return _plan(**base)


def _order_event(direction):
    lv = LEVELS[direction]
    return PlanEvent("p1", "gap_reclaim_order", {
        "entry_price": 100.0, "open_price": 99.0 if direction == "bullish" else 101.0,
        "reclaim_level": lv["reclaim_level"], "tif": "DAY",
        "order": "buy_stop" if direction == "bullish" else "sell_stop"})


def _messages(direction):
    lv = LEVELS[direction]
    cancelled = _waiting(direction, status="CANCELLED")
    events = [
        (_waiting(direction), _order_event(direction)),
        (cancelled, PlanEvent("p1", "cancelled_open_through_stop",
                              {"live_price": lv["stop_loss"], "phase": "open"})),
        (cancelled, PlanEvent("p1", "cancelled_open_through_stop",
                              {"live_price": lv["stop_loss"], "phase": "premarket"})),
        (cancelled, PlanEvent("p1", "cancelled_gap_no_reclaim",
                              {"entry_price": 100.0, "session": "2026-10-14"})),
        (cancelled, PlanEvent("p1", "cancelled_expired",
                              {"reason": "missed_open", "bars_waited": 0, "session": "2026-10-14",
                               "cancel_resting_order": True})),
    ]
    return [ins.instruction_for(plan, event, money=ins.money_from(54.35, "$"))
            for plan, event in events]


# --- the registry and the kind maps ------------------------------------------------

def test_the_reclaim_order_kind():
    assert Kind.RECLAIM_ORDER.family is Family.ENTRY
    assert Kind.RECLAIM_ORDER.label == "STOP ORDER AT ENTRY"


@pytest.mark.parametrize("table", [le.PLAN_EVENT_KINDS, ee._EVENT_KINDS])
def test_both_kind_maps_carry_the_new_transitions(table):
    assert table["cancelled_open_through_stop"] is Kind.INVALIDATED
    assert table["cancelled_gap_no_reclaim"] is Kind.EXPIRED
    assert table["gap_reclaim_order"] is Kind.RECLAIM_ORDER


def test_every_new_transition_has_a_builder():
    assert set(NEW) <= set(ins._BUILDERS)


# --- the v170 guards on the new messages --------------------------------------------

@pytest.mark.parametrize("direction", ["bullish", "bearish"])
def test_every_order_glyph_leads_its_broker_verb(direction):
    allowed = _allowed(direction)
    for instruction in _messages(direction):
        for key, after in _order_glyph_hits(instruction):
            assert after.startswith(allowed[key]), (key, after, instruction)


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
def test_no_message_carries_the_other_directions_verbs(direction):
    for instruction in _messages(direction):
        text = "\n".join((instruction.headline, *instruction.lines))
        assert [v for v in _FORBIDDEN[direction] if v in text] == [], instruction


def test_instructions_py_still_writes_no_glyph_literal():
    source = Path(ins.__file__).read_text(encoding="utf-8")
    assert [key for key, glyph in S.items() if glyph in source] == []


# --- the stop-order instruction --------------------------------------------------------

@pytest.mark.parametrize("direction, stop_verb, refrain, side", [
    ("bullish", "BUY STOP", "buy", "below"), ("bearish", "SELL STOP", "short", "above")])
def test_the_reclaim_order_instruction(direction, stop_verb, refrain, side):
    instruction = _messages(direction)[0]
    assert instruction.verb == ins.PLACE
    assert instruction.headline == (f"{S['entry']} {stop_verb} 100.00 DAY · "
                                    f"don't {refrain} at the open")
    level = LEVELS[direction]["reclaim_level"]
    assert instruction.lines[0].startswith(
        f"Opened at {101.0 if direction == 'bearish' else 99.0:.2f}, at or {side} {level:.2f}")
    assert "fills only if price trades through 100.00 today" in instruction.lines[1]
    keys = {key for key, _after in _order_glyph_hits(instruction)}
    assert {"entry", "stop", "tp1"} <= keys


# --- cancels ---------------------------------------------------------------------------

@pytest.mark.parametrize("direction, market", [("bullish", "BUY AT MARKET"),
                                               ("bearish", "SELL SHORT AT MARKET")])
def test_cancels_name_the_order_they_withdraw(direction, market):
    _order, through, premarket, no_reclaim, missed = _messages(direction)
    entry_stop = _VERBS[direction]["entry"][0]
    assert through.headline == f"{S['invalid']} CANCEL {market} ON OPEN"
    assert premarket.headline == through.headline
    assert no_reclaim.headline == f"{S['expiry']} CANCEL {entry_stop} 100.00 (DAY)"
    assert missed.headline == f"{S['expiry']} CANCEL {market} ON OPEN"
    assert all(i.verb == ins.CANCEL for i in (through, premarket, no_reclaim, missed))


def test_the_cancel_reasons_read_the_event():
    _order, through, premarket, no_reclaim, missed = _messages("bullish")
    assert through.lines == ("opened at 98.50, at or through the stop 98.50; never filled",)
    assert premarket.lines == ("traded at 98.50 before the open, at or through the stop 98.50 "
                               "on two checks; never filled",)
    assert no_reclaim.lines == ("opened toward the stop and never traded back through 100.00 "
                                "on 2026-10-14; never filled",)
    assert missed.lines == ("the bot saw no price at the 2026-10-14 open; never filled",)


def test_a_stop_entry_cancel_is_unchanged():
    plan = _plan(entry_type="stop_entry", trigger_price=102.5, stop_loss=98.4, tp1=106.0,
                 created_at="2026-09-10", status="CANCELLED")
    instruction = ins.instruction_for(plan, PlanEvent("p1", "cancelled_invalidated", {}))
    assert instruction.headline == f"{S['invalid']} CANCEL BUY STOP 102.50"


def test_the_gap_target_close_names_its_reason():
    plan = _waiting(status="CLOSED", entry_price=103.2, stop_ceiling_pct=10.0)
    instruction = ins.instruction_for(plan, PlanEvent("p1", "closed", {
        "reason": "gap_target", "exit_price": 103.2, "session": "regular"}))
    assert instruction.verb == ins.EXITED
    assert instruction.headline.endswith("EXITED @ 103.20 · opened past TP1")


# --- the rendered embeds -------------------------------------------------------------

def test_the_reclaim_order_renders_as_its_kind(monkeypatch):
    monkeypatch.setattr(ee, "_linked_trade", lambda plan_id: None)
    monkeypatch.setattr(ee, "_sizing_snapshot", lambda entry, plan: {"shares": 54.35})
    embed = ee.build_instruction_embed(_waiting(), _order_event("bullish"))
    assert "STOP ORDER AT ENTRY" in embed.title


def test_render_feed_samples_renders_every_sample(monkeypatch):
    path = Path(__file__).resolve().parents[2] / "scripts" / "dev" / "render_feed_samples.py"
    spec = importlib.util.spec_from_file_location("render_feed_samples", path)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    # _render patches these module attributes; register them so monkeypatch restores them
    monkeypatch.setattr(ee, "_sizing_snapshot", ee._sizing_snapshot)
    monkeypatch.setattr(ee, "_linked_trade", ee._linked_trade)
    names = [name for name, *_rest in script.SAMPLES]
    for wanted in ("reclaim order long", "reclaim order short", "cancel open through stop",
                   "cancel premarket through stop", "cancel no reclaim", "cancel missed open",
                   "closed gap target"):
        assert wanted in names
    for name, plan_kw, event, logged, realized in script.SAMPLES:
        assert script._render(plan_kw, event, logged, realized), name
