"""v202 V202-2: activity rows from plans -- alert, paper fill, TP1."""
from datetime import datetime, timezone

import pytest

from swingbot.admin.api_v1 import live_events as ev

ALERTED = "2026-10-29T08:00:00+00:00"


def _plan(**over):
    plan = {"plan_id": "p1", "ticker": "MSFT", "direction": "bullish",
            "created_at": ALERTED, "entry_price": 418.5, "status_history": [],
            "legs_realized": []}
    return {**plan, **over}


@pytest.mark.parametrize("raw, word", [
    ("bullish", "long"), ("bearish", "short"), ("Long", "long"), ("short", "short"),
    (None, ""), ("sideways", ""),
])
def test_direction_word(raw, word):
    assert ev.direction_word(raw) == word


@pytest.mark.parametrize("raw, expected", [
    (datetime(2026, 10, 29, 7, 31, tzinfo=timezone.utc), "2026-10-29T07:31:00+00:00"),
    (datetime(2026, 10, 29, 7, 31), "2026-10-29T07:31:00+00:00"),        # naive is UTC
    ("2026-10-29T09:31:00+02:00", "2026-10-29T07:31:00+00:00"),
    ("2026-10-29T07:31:00Z", "2026-10-29T07:31:00+00:00"),
    ("not a time", None), ("", None), (None, None), (17, None),
])
def test_iso_at(raw, expected):
    assert ev.iso_at(raw) == expected


def test_event_row_shape():
    row = ev.event_row(ALERTED, "trade_closed", "NVDA closed · TP2", "positive", 812,
                       {"r": 2.1, "amount": 441.0})
    assert row == {"at": ALERTED, "kind": "trade_closed", "text": "NVDA closed · TP2",
                   "tone": "positive", "ref": "812", "pnl": {"r": 2.1, "amount": 441.0}}
    assert ev.event_row(ALERTED, "killswitch", "Killswitch released", "neutral", None)["ref"] is None
    assert ev.event_row(ALERTED, "killswitch", "x", "neutral", None)["pnl"] is None


@pytest.mark.parametrize("r, tone", [(1.0, "positive"), (-0.4, "negative"), (0.0, "neutral"),
                                     (None, "neutral")])
def test_tone_for(r, tone):
    assert ev.tone_for(r) == tone


def test_plan_alerted_row():
    [row] = ev.plan_alerted_rows([_plan()])
    assert row == {"at": ALERTED, "kind": "plan_alerted",
                   "text": "Alert · MSFT long · entry 418.50", "tone": "info",
                   "ref": "p1", "pnl": None}


def test_plan_alerted_prefers_the_trigger_and_reads_a_datetime_column():
    plan = _plan(trigger_price=420.0, created_at=datetime(2026, 10, 29, 8, tzinfo=timezone.utc))
    [row] = ev.plan_alerted_rows([plan])
    assert row["text"] == "Alert · MSFT long · entry 420.00"
    assert row["at"] == ALERTED


def test_plan_alerted_without_price_or_time():
    assert ev.plan_alerted_rows([_plan(entry_price=None)])[0]["text"] == "Alert · MSFT long"
    assert ev.plan_alerted_rows([_plan(created_at=None)]) == []
    assert ev.plan_alerted_rows([]) == []


def test_paper_fill_is_the_first_active_transition():
    plan = _plan(ticker="XLE", direction="bearish", entry_price=92.1, status_history=[
        {"status": "PENDING", "reason": "created", "at": ALERTED},
        {"status": "ACTIVE", "reason": "stop_entry_fill", "at": "2026-10-29T13:35:00+00:00"},
        {"status": "PARTIAL", "reason": "tp1", "at": "2026-10-29T15:00:00+00:00"},
        {"status": "ACTIVE", "reason": "late", "at": "2026-10-29T16:00:00+00:00"},
    ])
    [row] = ev.paper_filled_rows([plan])
    assert row == {"at": "2026-10-29T13:35:00+00:00", "kind": "paper_filled",
                   "text": "Paper fill · XLE short at 92.10", "tone": "info",
                   "ref": "p1", "pnl": None}


def test_opened_at_never_yields_a_fill():
    """trades.opened_at (and any opened_at on a record) is the alert time."""
    plan = _plan(opened_at="2026-10-29T08:00:00+00:00", status="PENDING",
                 status_history=[{"status": "PENDING", "at": ALERTED}])
    assert ev.paper_filled_rows([plan]) == []


def test_a_fill_without_a_time_yields_no_row():
    plan = _plan(status_history=[{"status": "ACTIVE", "reason": "limit_fill"}])
    assert ev.paper_filled_rows([plan]) == []
    assert ev.paper_filled_rows([_plan(status_history=None)]) == []


def _tp1_plan(**leg_over):
    leg = {"fraction": 0.5, "exit_price": 110.0, "r": 1.0, "reason": "tp1",
           "closed_at": "2026-10-29T14:10:00+00:00", **leg_over}
    return _plan(ticker="NVDA", entry_price=100.0, legs_realized=[leg])


def test_tp1_row_with_r_and_amount():
    [row] = ev.tp1_hit_rows([_tp1_plan()], {"p1": 42})
    assert row == {"at": "2026-10-29T14:10:00+00:00", "kind": "tp1_hit", "text": "TP1 · NVDA",
                   "tone": "positive", "ref": "p1", "pnl": {"r": 1.0, "amount": 210.0}}


def test_tp1_amount_on_a_short():
    plan = _plan(ticker="XLE", direction="bearish", entry_price=92.1, legs_realized=[
        {"fraction": 0.5, "exit_price": 90.1, "r": 0.8, "reason": "tp1",
         "closed_at": "2026-10-29T14:10:00+00:00"}])
    [row] = ev.tp1_hit_rows([plan], {"p1": 10})
    assert row["pnl"] == {"r": 0.8, "amount": 10.0}


def test_tp1_without_shares_keeps_r_and_drops_the_amount():
    [row] = ev.tp1_hit_rows([_tp1_plan()], {})
    assert row["pnl"] == {"r": 1.0, "amount": None}


def test_tp1_tone_follows_r():
    assert ev.tp1_hit_rows([_tp1_plan(r=-0.2)], {})[0]["tone"] == "negative"
    [no_r] = ev.tp1_hit_rows([_tp1_plan(r=None)], {})
    assert (no_r["tone"], no_r["pnl"]) == ("neutral", None)


def test_no_tp1_row_without_its_time_or_for_other_legs():
    assert ev.tp1_hit_rows([_tp1_plan(closed_at=None)], {"p1": 1}) == []
    assert ev.tp1_hit_rows([_tp1_plan(reason="stop")], {"p1": 1}) == []
    assert ev.tp1_hit_rows([_plan(legs_realized=None)], {}) == []
