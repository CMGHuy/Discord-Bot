"""v232 V232-10: layer 2 adapter, matching and selection counts."""
import dataclasses
import datetime as dt
import sys
from pathlib import Path

import pytest

from swingbot.core.scanning.scan_replay import ReplayAlert
from tests.scout.test_reconcile_records import _plan_doc

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "reports"))
from reconcile import layer2, records  # noqa: E402

D6 = dt.date(2026, 10, 6)          # EDT: 15:00Z is 11:00 ET


def _signal(ticker="AAA", day="2026-10-06", direction="bullish", horizon="2w", **kw):
    base = dict(lane="base", ticker=ticker, direction=direction, source="confluence", mode=None,
                decision_date=day, horizon_key=horizon, strategy="RSI", entry=100.0, stop=98.0,
                target=104.0, planned_rr=2.0, outcome="win", r_multiple=2.0,
                exit_date="2026-10-09")
    base.update(kw)
    return layer2.adapt(ReplayAlert(**base))


def _doc(plan_id="P1", ticker="AAA", issued="2026-10-06T15:00:00+00:00", **kw):
    return _plan_doc(plan_id=plan_id, ticker=ticker, created_at="2026-10-06", issued_at=issued,
                     **kw)


def _rec(doc, opened=None, closed="2026-10-08T17:00:00+00:00"):
    trade = None if opened is None else {"id": "T-" + doc["plan_id"], "ticker": doc["ticker"],
                                         "opened_at": opened, "closed_at": closed}
    return records.LiveRecord(doc["plan_id"], doc["ticker"], doc["direction"], doc, trade, None)


def _export(*recs, rejections=()):
    return records.Export(tuple(recs), tuple(rejections), (), ())


def _plans(*recs, rows=None):
    return layer2.live_plans(_export(*recs), rows or {})


class _Row:
    def __init__(self, r_live_net):
        self.r_live_net = r_live_net


def test_adapt_keeps_levels_and_drops_every_outcome_field():
    signal = _signal(lane="short_universe", mode="isolated", direction="bearish")
    assert set(signal.to_dict()).isdisjoint(layer2.OUTCOME_FIELDS)
    assert (signal.decision_date, signal.entry, signal.stop, signal.target) == (
        "2026-10-06", 100.0, 98.0, 104.0)
    assert layer2.ReplaySignal.from_dict(signal.to_dict()) == signal


@pytest.mark.parametrize("field", ["outcome", "r_multiple", "exit_date"])
def test_from_dict_refuses_an_outcome_field(field):
    with pytest.raises(ValueError, match=field):
        layer2.ReplaySignal.from_dict({**_signal().to_dict(), field: "x"})


@pytest.mark.parametrize("name", ["ReplaySignal", "LivePlan", "MatchResult"])
def test_no_layer2_structure_has_an_outcome_field(name):
    fields = {f.name for f in dataclasses.fields(getattr(layer2, name))}
    assert fields.isdisjoint(layer2.OUTCOME_FIELDS)


def test_live_plans_carry_issued_levels_and_live_net():
    market, stop_entry = _plans(
        _rec(_doc()), _rec(_doc("P2", entry_type="stop_entry", trigger_price=101.0)),
        rows={"P1": _Row(1.25)})
    assert (market.session, market.entry, market.stop, market.target) == (D6, 100.0, 98.0, 104.0)
    assert market.r_live_net == 1.25 and stop_entry.r_live_net is None
    assert stop_entry.entry == 101.0      # the issued trigger, not the fill-written entry_price


@pytest.mark.parametrize("issued,bucket", [
    ("2026-10-06T14:00:00+00:00", "open_to_1030"),
    ("2026-10-06T16:00:00+00:00", "mid_day"),
    ("2026-10-06T19:30:00+00:00", "last_hour"),
    ("2026-10-06T21:00:00+00:00", "outside_session"),
    (None, "created_at")])
def test_each_issue_time_bucket(issued, bucket):
    (plan,) = _plans(_rec(_doc(issued=issued)))
    assert plan.bucket == bucket and plan.session == D6


@pytest.mark.parametrize("day,matched", [("2026-10-02", 0), ("2026-10-05", 1),
                                         ("2026-10-06", 1), ("2026-10-07", 1),
                                         ("2026-10-08", 0)])
def test_match_window_is_one_session_either_side(day, matched):
    result = layer2.match([_signal(day=day)], _plans(_rec(_doc())))
    assert len(result.matched) == matched
    assert len(result.live_only) == len(result.replay_only) == 1 - matched


def test_ticker_and_side_must_be_equal():
    result = layer2.match([_signal(direction="bearish"), _signal(ticker="BBB")],
                          _plans(_rec(_doc())))
    assert result.matched == [] and len(result.replay_only) == 2


def test_ties_go_to_the_same_horizon_then_the_nearest_date():
    exact_other, late_same, exact_same = (_signal(horizon="1m"), _signal(day="2026-10-07"),
                                          _signal())
    result = layer2.match([exact_other, late_same], _plans(_rec(_doc())))
    assert [s for _, s in result.matched] == [late_same]
    result = layer2.match([late_same, exact_same], _plans(_rec(_doc())))
    assert [s for _, s in result.matched] == [exact_same] and result.replay_only == [late_same]


def test_matching_is_one_to_one():
    plans = _plans(_rec(_doc("P1")), _rec(_doc("P2", issued="2026-10-07T15:00:00+00:00")))
    result = layer2.match([_signal()], plans)
    assert [p.plan_id for p, _ in result.matched] == ["P1"]
    assert [p.plan_id for p in result.live_only] == ["P2"]


def test_strategy_sourced_plans_sit_outside_the_replay():
    result = layer2.match([_signal()], _plans(_rec(_doc(source="strategy"))))
    assert [p.plan_id for p in result.outside_replay] == ["P1"]
    assert result.matched == [] and result.live_only == [] and len(result.replay_only) == 1


def test_each_replay_only_reason():
    held = _rec(_doc("P8", "OPN"), opened="2026-10-01T15:01:00+00:00", closed=None)
    gone = _rec(_doc("P9", "OLD"), opened="2026-10-01T15:01:00+00:00",
                closed="2026-10-02T15:00:00+00:00")
    rejection = {"ticker": "REJ", "gate": "rs_gate", "strategy": "RSI", "horizon": "2w",
                 "signal_date": "2026-10-06"}
    export = _export(held, gone, rejections=[rejection])
    reason = layer2.replay_only_reason
    assert reason(_signal(ticker="REJ"), export) == ("gate_rejection", "rs_gate")
    assert reason(_signal(ticker="OPN"), export) == ("open_position", None)
    assert reason(_signal(ticker="OLD"), export) == ("unexplained", None)


def test_level_diffs_are_entry_percent_and_distance_ratios():
    (plan,) = _plans(_rec(_doc()))
    diffs = layer2.level_diffs(plan, _signal(entry=101.0, stop=98.0, target=107.0))
    assert diffs["entry_pct"] == pytest.approx(1.0)
    assert diffs["stop_ratio"] == pytest.approx(1.5)       # 3 / 2
    assert diffs["target_ratio"] == pytest.approx(1.5)     # 6 / 4


def test_selection_counts_per_side_and_era_with_measured_zeros():
    rejection = {"ticker": "GGG", "gate": "earnings", "strategy": "RSI", "horizon": "2w",
                 "signal_date": "2026-10-06"}
    export = _export(_rec(_doc("P1"), opened="2026-10-06T15:01:00+00:00"),       # matched
                     _rec(_doc("P2", "BBB", issued="2026-10-06T21:00:00+00:00")),
                     _rec(_doc("P3", "CCC", issued=None)),
                     _rec(_doc("P4", "DDD", source="strategy")),
                     rejections=[rejection])
    plans = layer2.live_plans(export, {"P1": _Row(0.5), "P2": _Row(-1.0)})
    signals = [_signal(), _signal(ticker="EEE"), _signal(ticker="GGG"),
               _signal(ticker="ZZZ", day="2026-09-10")]
    counts = layer2.selection_counts(layer2.match(signals, plans), export)
    cell = counts["long"]["headline"]
    assert cell["matched"] == 1 and cell["outside_replay"] == 1
    assert cell["level_diffs"]["entry_pct"] == [0.0]
    live = cell["live_only"]
    assert (live["n"], live["unexplained"], live["live_r_n"], live["live_r_net"]) == (2, 1, 1, -1.0)
    assert live["by_bucket"]["created_at"] == 1 and live["by_bucket"]["outside_session"] == 1
    assert cell["replay_only"] == {"n": 2, "by_gate": {"earnings": 1}, "by_reason": {
        "gate_rejection": 1, "open_position": 0, "unexplained": 1}}
    assert counts["long"]["earlier"]["replay_only"]["n"] == 1
    assert counts["short"]["headline"]["matched"] == 0
    assert {side: set(eras) for side, eras in counts.items()} == {
        "long": {"headline", "earlier"}, "short": {"headline", "earlier"}}
