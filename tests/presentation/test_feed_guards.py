"""v170 guards over every execution-feed message kind (spec § Testing).

* every FEED_SYMBOLS key is used by at least one rendered message, and no
  glyph is shared by two keys;
* instructions.py writes no glyph literal (every glyph comes from the table);
* D2: every order line carries its broker verb for its direction, every
  cancel says CANCEL, every stop move says MOVE <stop verb>, and no message
  carries the other direction's verbs;
* the comparison glyphs follow the direction.
"""
from pathlib import Path

import pytest

from swingbot.core.planning.plan_manager import PlanEvent
from swingbot.core.presentation import instructions as ins
from swingbot.core.presentation import tokens
from swingbot.core.presentation.instructions import Instruction
from tests.planning.test_compression_time_exit import _short
from tests.planning.test_plan_engine_model import _plan

S = tokens.FEED_SYMBOLS
DIRECTIONS = ("bullish", "bearish")

_LEVELS = {
    "bullish": dict(trigger_price=102.5, stop_loss=98.4, tp1=106.0, tp2=110.0),
    "bearish": dict(trigger_price=97.5, stop_loss=101.6, tp1=94.0, tp2=90.0),
}

_VERBS = {
    "bullish": dict(entry=("BUY STOP", "BUY AT MARKET"), stop="SELL STOP",
                    limit="SELL LIMIT", exit="SELL AT MARKET"),
    "bearish": dict(entry=("SELL STOP", "SELL SHORT AT MARKET"), stop="BUY STOP",
                    limit="BUY LIMIT", exit="BUY TO COVER AT MARKET"),
}

#: verbs that belong only to the other direction.
_FORBIDDEN = {
    "bullish": ("BUY LIMIT", "BUY TO COVER", "SELL SHORT", "MOVE BUY STOP"),
    "bearish": ("SELL LIMIT", "SELL AT MARKET", "BUY AT MARKET", "MOVE SELL STOP"),
}

_ORDER_KEYS = ("entry", "stop", "tp1", "tp2", "expiry", "invalid")
_CLOSE_VERBS = (ins.EXITED, ins.CLOSE_AT_MARKET)


def _allowed(direction: str) -> dict[str, tuple[str, ...]]:
    """What may follow each order glyph: the direction's order verb, or one
    of the two fill reports."""
    v = _VERBS[direction]
    return {"entry": (*v["entry"], "FILLED"),
            "stop": (v["stop"], f"MOVE {v['stop']}"),
            "tp1": (v["limit"], "TP1 FILLED"),
            "tp2": (v["limit"],),
            "expiry": ("CANCEL",),
            "invalid": ("CANCEL",)}


def _ev(transition, **detail):
    return PlanEvent("p1", transition, detail)


def _pending(direction, **kw):
    base = dict(entry_type="stop_entry", direction=direction, entry_price=None,
                tp1_fraction=0.5, trail_atr_mult=3.0, breakeven_trigger_fraction=0.5,
                created_at="2026-09-10", expiry_bars=5, status="PENDING",
                **_LEVELS[direction])
    base.update(kw)
    return _plan(**base)


def _held(direction, status="ACTIVE", **kw):
    return _pending(direction, entry_price=_LEVELS[direction]["trigger_price"],
                    status=status, **kw)


def _legs(direction):
    lv = _LEVELS[direction]
    return [{"fraction": 0.5, "exit_price": lv["tp1"], "r": 0.85, "reason": "tp1"},
            {"fraction": 0.5, "exit_price": lv["tp2"], "r": 1.83, "reason": "tp1_runner_tp2"}]


def _tickets(direction):
    money = ins.money_from(54.35, "$")
    kw = dict(logged=True, not_logged_reason=None, money=money, level=4)
    return [ins.ticket_for(_pending(direction), **kw),
            ins.ticket_for(_pending(direction, entry_type="market"), **kw),
            ins.ticket_for(_pending(direction, tp2=None), **kw),
            ins.ticket_for(_pending(direction), logged=False,
                           not_logged_reason="kill switch on", money=money)]


def _lifecycle(direction):
    lv = _LEVELS[direction]
    entry, live = lv["trigger_price"], ins.money_from(54.35, "$")
    partial = _held(direction, status="PARTIAL", legs_realized=_legs(direction)[:1])
    events = [
        (_held(direction), _ev("filled", entry_price=entry)),
        (_held(direction), _ev("be_moved", working_stop=entry)),
        (partial, _ev("tp1_partial", fraction=0.5, exit_price=lv["tp1"], r=0.85,
                      reason="tp1", working_stop=entry)),
        (partial, _ev("stop_moved", new=(entry + lv["tp1"]) / 2, r_moved=0.4)),
        (_pending(direction), _ev("cancelled_expired")),
        (_pending(direction), _ev("cancelled_invalidated")),
        (_pending(direction), _ev("cancelled_risk_cap", entry_price=entry,
                                  stop_loss=lv["stop_loss"], planned_loss_pct=4.0,
                                  max_planned_loss_pct=2.0)),
    ]
    return [ins.instruction_for(plan, event, money=live) for plan, event in events]


def _closes(direction):
    lv = _LEVELS[direction]
    entry = lv["trigger_price"]

    def settled(amount):
        return ins.money_from(54.35, "$", realized_amount=amount)

    closes = [
        (_held(direction, status="CLOSED", legs_realized=_legs(direction)),
         _ev("closed", reason="tp1_runner_tp2", exit_price=lv["tp2"], session="regular"),
         settled(300.0)),
        (_held(direction, status="CLOSED"),
         _ev("closed", reason="loss", exit_price=lv["stop_loss"], session="regular"),
         settled(-222.0)),
        (_held(direction, status="CLOSED"),
         _ev("closed", reason="scratch", exit_price=entry, session="regular"),
         settled(0.0)),
        (_held(direction, status="CLOSED"),
         _ev("closed", reason="loss", exit_price=lv["stop_loss"], session="extended"),
         None),
    ]
    return [ins.instruction_for(plan, event, money=money) for plan, event, money in closes]


def _time_exits():
    """The compression short is the only strategy with a time exit."""
    money = ins.money_from(12.6, "$")
    due = {"cover_fraction": 1.0, "auction_time": "2026-12-01T16:00:00-05:00",
           "late": False, "notice_id": "p1:time_exit_due:2026-12-01"}
    unresolved = {"cover_fraction": 1.0, "reason": "official closing-auction price unavailable",
                  "notice_id": "p1:time_exit_unresolved:2026-12-01"}
    closed = _short(status="CLOSED", time_exit_due_date="2026-12-01")
    return [ins.instruction_for(_short(), _ev("time_exit_due", **due), money=money),
            ins.instruction_for(_short(), _ev("time_exit_unresolved", **unresolved), money=money),
            ins.instruction_for(closed, _ev("closed", reason="time_exit", exit_price=98.0,
                                            session="regular"),
                                money=ins.money_from(12.6, "$", realized_amount=25.2))]


def rendered_feed() -> list[tuple[str, Instruction]]:
    """(direction, instruction) for every execution-feed message kind."""
    feed = [(d, i) for d in DIRECTIONS
            for i in (*_tickets(d), *_lifecycle(d), *_closes(d))]
    return feed + [("bearish", i) for i in _time_exits()]


def _texts(instruction: Instruction) -> tuple[str, ...]:
    return (instruction.headline, *instruction.lines)


def _order_glyph_hits(instruction: Instruction) -> list[tuple[str, str]]:
    """(key, text right after the glyph) for every order glyph in the message."""
    return [(key, after.lstrip())
            for text in _texts(instruction)
            for key in _ORDER_KEYS
            for after in text.split(S[key])[1:]]


FEED = rendered_feed()
#: every message but the closes, whose headline glyphs the exit word by design
#: (their order line, the exit verb, is checked separately).
ORDERED = [(d, i) for d, i in FEED if i.verb not in _CLOSE_VERBS]


# --- the symbol table ---------------------------------------------------------

def test_every_symbol_key_is_used_by_a_rendered_message():
    text = "\n".join(t for _d, i in FEED for t in _texts(i))
    unused = [key for key, glyph in S.items() if glyph not in text]
    assert unused == []


def test_no_glyph_is_shared_by_two_keys():
    assert len(set(S.values())) == len(S)


def test_instructions_py_writes_no_glyph_literal():
    source = Path(ins.__file__).read_text(encoding="utf-8")
    assert [key for key, glyph in S.items() if glyph in source] == []


# --- D2: broker verbs ----------------------------------------------------------

def test_rendered_feed_covers_every_message_kind_in_both_directions():
    for direction in DIRECTIONS:
        verbs = {i.verb for d, i in FEED if d == direction}
        assert verbs >= {ins.PLACE, ins.DO_NOT_PLACE, ins.FILLED, ins.MOVE_STOP,
                         ins.CANCEL, ins.EXITED, ins.CLOSE_AT_MARKET}, direction


@pytest.mark.parametrize("index", range(len(ORDERED)))
def test_every_order_glyph_leads_its_directions_broker_verb(index):
    direction, instruction = ORDERED[index]
    allowed = _allowed(direction)
    for key, after in _order_glyph_hits(instruction):
        assert after.startswith(allowed[key]), (key, after, instruction)


def test_every_place_ticket_quotes_entry_stop_and_target_orders():
    for direction, instruction in FEED:
        if instruction.verb != ins.PLACE:
            continue
        keys = [key for key, _after in _order_glyph_hits(instruction)]
        assert {"entry", "stop", "tp1"} <= set(keys), (direction, instruction)
        assert instruction.headline.startswith(f"{S['entry']} "), instruction.headline
    for direction in DIRECTIONS:
        runner = f"{S['tp2']} {_VERBS[direction]['limit']} "
        assert any(runner in t for d, i in FEED if d == direction and i.verb == ins.PLACE
                   for t in _texts(i)), direction


def test_every_stop_move_names_the_move_verb():
    for direction, instruction in FEED:
        if instruction.verb == ins.MOVE_STOP:
            move = f"MOVE {_VERBS[direction]['stop']}"
            assert any(move in t for t in _texts(instruction)), instruction


def test_every_cancel_says_cancel_and_names_the_entry_order():
    for direction, instruction in FEED:
        if instruction.verb == ins.CANCEL:
            assert f"CANCEL {_VERBS[direction]['entry'][0]}" in instruction.headline, instruction


def test_every_close_and_time_exit_names_the_exit_verb():
    for direction, instruction in FEED:
        if instruction.verb in _CLOSE_VERBS:
            exit_verb = _VERBS[direction]["exit"]
            assert any(exit_verb in t for t in _texts(instruction)), instruction


def test_no_message_carries_the_other_directions_verbs():
    for direction, instruction in FEED:
        text = "\n".join(_texts(instruction))
        assert [v for v in _FORBIDDEN[direction] if v in text] == [], instruction


# --- comparison glyphs ----------------------------------------------------------

@pytest.mark.parametrize("direction,arm,cancel", [
    ("bullish", "at_or_above", "at_or_below"),
    ("bearish", "at_or_below", "at_or_above"),
])
def test_comparison_glyphs_follow_the_direction(direction, arm, cancel):
    ticket = _tickets(direction)[0]                 # the stop-entry ticket
    breakeven = [t for t in ticket.lines if t.startswith(S["breakeven"])]
    assert len(breakeven) == 1 and S[arm] in breakeven[0] and S[cancel] not in breakeven[0]
    after_invalid = [after for key, after in _order_glyph_hits(ticket) if key == "invalid"]
    assert after_invalid and after_invalid[0].startswith(f"CANCEL if {S[cancel]} ")
