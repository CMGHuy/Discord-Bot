"""V183-8: the order block's gap-risk line -- one wording function, and the same
text on the full Discord alert, the simple mirror, the v81 ticket and the
email/push body. Longs, switch-off shorts and pre-v183 plans print nothing new."""
import dataclasses

import pytest

from swingbot import config
from swingbot.core.infra import notifier
from swingbot.core.presentation import short_notice
from swingbot.core.presentation.gap_risk import GAP_CUT_TEXT, GAP_NA_TEXT, gap_risk_line
from swingbot.core.scanning import execution_embeds
from swingbot.core.scanning.alert_embeds import GAP_RISK_FIELD, build_embed, build_simple_alert
from tests.scanning.test_embeds_v3 import (PERF_STATS_EMPTY, make_item, make_plan_v2,
                                           _isolated_scan_snapshots)  # noqa: F401

CUT = {"shares": 25.0, "risk_amount": 50.0, "gap_risk_amount": 100.0,
       "gap_sized": True, "gap_floor_pct": 4.0}
NOT_CUT = {"shares": 50.0, "risk_amount": 200.0, "gap_risk_amount": 200.0,
           "gap_sized": False, "gap_floor_pct": 1.1}
NO_P99 = {"shares": 50.0, "risk_amount": 200.0, "gap_risk_amount": None,
          "gap_sized": False, "gap_floor_pct": None}
PLAIN = {"shares": 20.0, "risk_amount": 100.0, "position_value": 2000.0, "mode": "risk_pct"}
CUT_LINE = "Risk $50 at stop · $100 on a p99 gap (4.0%) · size cut for gap risk"


def test_the_copy_constants():
    assert GAP_CUT_TEXT == "size cut for gap risk"
    assert GAP_NA_TEXT == "gap risk n/a"


@pytest.mark.parametrize("sizing,expected", [
    (CUT, CUT_LINE),
    (NOT_CUT, "Risk $200 at stop · $200 on a p99 gap (1.1%)"),
    (NO_P99, "Risk $200 at stop · gap risk n/a"),
    (dict(NO_P99, gap_floor_pct=3.0), "Risk $200 at stop · gap risk n/a"),
    (dict(NO_P99, risk_amount=None), "Risk n/a at stop · gap risk n/a"),
    (PLAIN, None),
    (None, None),
    ({}, None),
])
def test_gap_risk_line_wording(sizing, expected):
    assert gap_risk_line(sizing) == expected


def test_currency_and_thousands():
    sizing = {"risk_amount": 1234.4, "gap_risk_amount": 2468.8, "gap_sized": True, "gap_floor_pct": 2.76}
    assert gap_risk_line(sizing, currency="€") == (
        "Risk €1,234 at stop · €2,469 on a p99 gap (2.8%) · size cut for gap risk")


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(config, "CURRENCY_SYMBOL", "$")
    monkeypatch.setattr(short_notice, "completed_session_date", lambda: "2026-10-01")


def _embed_text(embed):
    return "\n".join([embed.description or "", *(f.name + "\n" + f.value for f in embed.fields)])


def _item(monkeypatch, sizing, direction="bearish"):
    monkeypatch.setattr(execution_embeds, "_sizing_snapshot", lambda entry, plan: sizing)
    stop = 102.0 if direction == "bearish" else 95.0
    item = make_item(plan_v2=dataclasses.replace(make_plan_v2(direction=direction), stop_loss=stop))
    item.result.trend = direction
    item.paper_logged = True
    return item


def _renderings(item):
    return {
        "discord": _embed_text(build_embed(item, "x", PERF_STATS_EMPTY, None, None)),
        "simple": _embed_text(build_simple_alert(item)),
        "ticket": _embed_text(execution_embeds.build_ticket_embed(item, item.plan_v2)),
        "email/push": notifier._build_alert_texts(item, item.plan, item.conf)[1],
    }


def test_every_alert_channel_shows_the_line_for_a_cut_short(monkeypatch):
    for name, text in _renderings(_item(monkeypatch, CUT)).items():
        assert CUT_LINE in text, name


def test_a_short_without_p99_says_gap_risk_n_a_on_every_channel(monkeypatch):
    for name, text in _renderings(_item(monkeypatch, NO_P99)).items():
        assert "Risk $200 at stop · gap risk n/a" in text, name


def test_the_line_sits_in_the_order_block(monkeypatch):
    item = _item(monkeypatch, CUT)
    ticket = execution_embeds.build_ticket_embed(item, item.plan_v2)
    assert CUT_LINE in ticket.description               # with the stop/TP lines, not a stray field
    full = build_embed(item, "x", PERF_STATS_EMPTY, None, None)
    assert [f.value for f in full.fields if f.name == GAP_RISK_FIELD] == [CUT_LINE]
    body = notifier._build_alert_texts(item, item.plan, item.conf)[1].splitlines()
    rr = next(i for i, line in enumerate(body) if line.startswith("R:R"))
    assert body[rr + 1] == CUT_LINE


@pytest.mark.parametrize("sizing", [PLAIN, None])
def test_a_long_or_unstamped_plan_prints_nothing_new(monkeypatch, sizing):
    for direction in ("bullish", "bearish"):
        item = _item(monkeypatch, sizing, direction)
        for name, text in _renderings(item).items():
            assert "p99" not in text and GAP_NA_TEXT not in text, (direction, name)
        full = build_embed(item, "x", PERF_STATS_EMPTY, None, None)
        assert GAP_RISK_FIELD not in [f.name for f in full.fields]


def test_a_long_ticket_and_email_are_byte_identical_without_the_hook(monkeypatch):
    item = _item(monkeypatch, PLAIN, "bullish")
    before = (execution_embeds.build_ticket_embed(item, item.plan_v2).description,
              notifier._build_alert_texts(item, item.plan, item.conf))
    monkeypatch.setattr(execution_embeds, "ticket_gap_line", lambda plan: None)
    after = (execution_embeds.build_ticket_embed(item, item.plan_v2).description,
             notifier._build_alert_texts(item, item.plan, item.conf))
    assert before == after
