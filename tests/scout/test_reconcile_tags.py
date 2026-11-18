"""v232 V232-8 / V232-8b: mechanism tags and the slip distributions."""
import dataclasses
import sys
from pathlib import Path

import pytest

from swingbot.core.planning.plan_types import PlanStatus, TradePlanV2, plan_to_dict
from tests.helpers import make_ohlcv

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "reports"))
from reconcile import records, tags  # noqa: E402

CALM = (100.5, 101.0, 100.0, 100.5)
ROWS = [CALM, CALM, CALM, (100.8, 104.5, 100.5, 104.0)] + [(104.0, 104.4, 103.6, 104.0)] * 4


def _mirror(row):
    o, hi, lo, c = row
    return (200 - o, 200 - lo, 200 - hi, 200 - c)


def _t(direction="bullish", plan=None, trade=None, rows=None, live_class="win",
       exit_only_class="win", exit_pos=3):
    long = direction == "bullish"
    doc = dict(plan_id="P1", ticker="AAA", created_at="2026-10-06T15:00:00+00:00",
               source="confluence", strategy="RSI", horizon_key="2w", direction=direction,
               entry_type="market", trigger_price=100.0, entry_price=100.0, expiry_bars=3,
               stop_loss=98.0 if long else 102.0, tp1=104.0 if long else 96.0,
               tp1_fraction=1.0, tp2=None, breakeven_trigger_fraction=0.5, trail_atr_mult=2.5,
               quality_score=0, quality_breakdown=[], badge="WEAK", badge_stats={},
               status=PlanStatus.CLOSED, status_history=[],
               issued_at="2026-10-06T15:00:00+00:00")
    doc.update(plan or {})
    plan_doc = plan_to_dict(TradePlanV2(**doc))
    trade_doc = {"id": "T1", "plan_id": "P1", "entry": 100.05 if long else 99.95,
                 "stop_loss": plan_doc["stop_loss"], "take_profit": plan_doc["tp1"],
                 "opened_at": "2026-10-06T15:01:00+00:00",       # 11:01 ET
                 "closed_at": "2026-10-08T17:00:00+00:00",       # 13:00 ET
                 "exit_price": 104.0 if long else 96.0, "close_reason": "tp1", "legs": []}
    trade_doc.update(trade or {})
    bars = [r if long else _mirror(r) for r in ROWS]
    for k, row in (rows or {}).items():
        bars[k] = row
    rec = records.LiveRecord("P1", "AAA", direction, plan_doc, trade_doc,
                             {"outcome": live_class, "r_realized": 1.9})
    risk = abs(trade_doc["entry"] - plan_doc["stop_loss"])
    return tags.TagInput(rec, make_ohlcv(bars, start="2026-10-05"), 1, exit_pos, risk, 1.9,
                         1.9, live_class, exit_only_class)


LEGS = [{"fraction": 0.5, "exit_price": 104.0, "r": 1.9, "reason": "tp1_partial"},
        {"fraction": 0.5, "exit_price": 100.05, "r": 0.0, "reason": "tp1_runner_be"}]
POSITIVE = {
    "same_day_exit": dict(trade={"closed_at": "2026-10-06T19:00:00+00:00"}),
    "wick_missed": dict(rows={2: (100.5, 101.0, 97.9, 100.5)}),
    "both_levels_bar": dict(rows={2: (100.5, 104.2, 97.9, 100.5)}),
    "gap_through": dict(rows={3: (104.6, 104.8, 104.0, 104.2)}),
    "exit_outside_rth": dict(trade={"closed_at": "2026-10-08T21:30:00+00:00"}),
    "entry_outside_rth": dict(trade={"opened_at": "2026-10-06T13:00:00+00:00"}),
    "first_15min": dict(trade={"opened_at": "2026-10-06T13:40:00+00:00"}),
    "live_stop_moved": dict(plan={"working_stop": 100.05, "be_armed_session": "2026-10-07"}),
    "levels_edited": dict(trade={"stop_loss": 97.0}),
    "scaled_out": dict(trade={"legs": LEGS}),
    "time_stop": dict(trade={"close_reason": "time_exit"}),
    "earnings_in_window": dict(trade={"risk_features": {"days_to_earnings": 1}}),
    "short_gap_against": dict(direction="bearish", rows={2: (103.8, 104.0, 103.0, 103.5)}),
    "outcome_flip_live_better": dict(live_class="win", exit_only_class="loss"),
    "outcome_flip_live_worse": dict(live_class="loss", exit_only_class="win"),
}


def test_every_tag_has_a_rule_and_a_positive_fixture():
    assert set(tags.RULES) == set(tags.TAGS)
    assert set(POSITIVE) <= set(tags.TAGS) and len(tags.TAGS) >= 15


def test_the_base_fixture_carries_no_tag():
    assert tags.tags_for(_t()) == ()
    assert tags.tags_for(_t("bearish")) == ()


@pytest.mark.parametrize("tag", list(POSITIVE))
def test_each_tag_fires_on_its_positive_case(tag):
    assert tag in tags.tags_for(_t(**POSITIVE[tag]))


@pytest.mark.parametrize("tag,case", [
    ("wick_missed", dict(rows={3: (100.8, 104.5, 97.9, 104.0)})),     # the exit day itself
    ("wick_missed", dict(plan={"working_stop": 100.4, "be_armed_session": "2026-10-07"},
                         rows={2: (100.5, 101.0, 100.3, 100.5)})),   # stop moved only after 10-07
    ("short_gap_against", dict(rows={2: (103.8, 104.0, 103.0, 103.5)})),   # a long
    ("earnings_in_window", dict(trade={"risk_features": {"days_to_earnings": 5}})),
    ("earnings_in_window", dict(trade={"risk_features": {"days_to_earnings": None}})),
    ("levels_edited", dict(trade={"stop_loss": 98.004})),              # rounding, not an edit
    ("first_15min", dict(trade={"opened_at": "2026-10-06T13:45:00+00:00"})),   # 09:45 ET
    ("outcome_flip_live_better", dict(live_class="win", exit_only_class="scratch")),
])
def test_near_misses_do_not_fire(tag, case):
    assert tag not in tags.tags_for(_t(**case))


def test_wick_missed_uses_the_moved_stop_after_its_session():
    case = dict(plan={"working_stop": 100.4, "be_armed_session": "2026-10-06"},
                rows={2: (100.5, 101.0, 100.3, 100.5)})
    assert "wick_missed" in tags.tags_for(_t(**case))


def test_earnings_falls_back_to_the_journal_features():
    t = _t()
    rec = records.LiveRecord("P1", "AAA", "bullish", t.rec.plan, t.rec.trade,
                             {**t.rec.journal, "risk_features": {"days_to_earnings": 0}})
    assert "earnings_in_window" in tags.tags_for(dataclasses.replace(t, rec=rec))


POSITIVE.update({
    "entry_slip": dict(trade={"entry": 100.3}),
    "poll_fill": dict(trade={"exit_price": 103.7}),
})


def test_all_seventeen_tags_have_a_rule_and_a_positive_fixture():
    assert len(tags.TAGS) == 17 and tags.TAGS[-2:] == ("entry_slip", "poll_fill")
    assert set(tags.RULES) == set(tags.TAGS) == set(POSITIVE)


@pytest.mark.parametrize("tag", ["entry_slip", "poll_fill"])
def test_the_slip_tags_fire_past_the_cut_off_only(tag):
    assert tag in tags.tags_for(_t(**POSITIVE[tag]))
    assert tag not in tags.tags_for(_t())        # 0.05 / 2.05 = 0.024R slip, 0R poll


def test_gap_detail_sizes_a_long_gap():
    gap = tags.gap_detail(_t(rows={3: (104.6, 104.8, 104.0, 104.2)}))
    risk = 2.05
    assert gap["gap_r"] == pytest.approx(4.1 / risk)
    assert gap["gap_pct"] == pytest.approx((104.6 / 100.5 - 1) * 100)
    assert gap["exit_vs_open_r"] == pytest.approx(-0.6 / risk)
    assert gap["exit_vs_stop_r"] == pytest.approx(6.0 / risk)
    assert tags.gap_detail(_t()) is None


def test_gap_detail_signs_a_short_gap_against_the_position():
    gap = tags.gap_detail(_t("bearish", rows={2: (102.5, 103.0, 102.0, 102.6)},
                             trade={"exit_price": 102.5}))
    assert gap["gap_r"] == pytest.approx(-(102.5 - 99.5) / 2.05)
    assert gap["exit_vs_stop_r"] == pytest.approx(-(102.5 - 102.0) / 2.05)


@pytest.mark.parametrize("direction,plan,fill,expected_bps,risk", [
    ("bullish", {}, 100.3, 30.0, 2.3),
    ("bearish", {}, 99.7, 30.0, 2.3),
    ("bullish", {"entry_type": "stop_entry", "entry_price": 101.4, "trigger_price": 101.0},
     101.2, 0.2 / 101.0 * 1e4, 3.2),
])
def test_entry_slip_is_adverse_positive_against_the_planned_entry(direction, plan, fill,
                                                                  expected_bps, risk):
    bps, r = tags.entry_slip(_t(direction, plan=plan, trade={"entry": fill}))
    assert bps == pytest.approx(expected_bps)
    assert r == pytest.approx(expected_bps / 1e4 * (101.0 if plan else 100.0) / risk)


@pytest.mark.parametrize("plan,trade,expected", [
    ({}, {"exit_price": 103.7}, (0.3 / 104.0 * 1e4, 0.3 / 2.05)),
    ({"working_stop": 100.05}, {"close_reason": "stop", "exit_price": 99.95},
     (0.1 / 100.05 * 1e4, 0.1 / 2.05)),
    ({"working_stop": 100.05}, {"legs": LEGS[:1] + [{**LEGS[1], "exit_price": 100.0}]},
     (0.05 / 100.05 * 1e4, 0.05 / 2.05)),
    ({}, {"close_reason": "manual", "exit_price": 101.0}, None),
    ({}, {"close_reason": "timeout", "exit_price": 101.0}, None),
])
def test_poll_fill_measures_the_exit_against_the_level_it_hit(plan, trade, expected):
    got = tags.poll_fill(_t(plan=plan, trade=trade))
    if expected is None:
        assert got is None
    else:
        assert got == pytest.approx(expected)
