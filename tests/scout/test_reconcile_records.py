"""v232 V232-6: export records, populations and rehydration."""
import datetime as dt
import json
import sys
from pathlib import Path

import pytest

from swingbot.core.planning.plan_types import PlanStatus, TradePlanV2, plan_to_dict

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "reports"))
from reconcile import records  # noqa: E402


def _plan_doc(**kw):
    base = dict(plan_id="P1", ticker="AAA", created_at="2026-10-06T15:00:00+00:00",
                source="confluence", strategy="RSI", horizon_key="2w", direction="bullish",
                entry_type="market", trigger_price=100.0, entry_price=100.0, expiry_bars=3,
                stop_loss=98.0, tp1=104.0, tp1_fraction=1.0, tp2=None,
                breakeven_trigger_fraction=0.5, trail_atr_mult=2.5, quality_score=0,
                quality_breakdown=[], badge="WEAK", badge_stats={}, status=PlanStatus.CLOSED,
                status_history=[{"status": "ACTIVE", "reason": "filled", "at": "x"}],
                issued_at="2026-10-06T15:00:00+00:00")
    base.update(kw)
    return plan_to_dict(TradePlanV2(**base))


TRADE = {"id": "T1", "plan_id": "P1", "ticker": "AAA", "direction": "bullish", "entry": 100.2,
         "stop_loss": 98.0, "take_profit": 104.0, "opened_at": "2026-10-06T15:01:00+00:00",
         "closed_at": "2026-10-08T17:00:00+00:00", "exit_price": 104.0, "status": "win",
         "close_reason": "tp1", "ledger": "weak", "legs": []}
JOURNAL = {"trade_id": "T1", "outcome": "win", "r_realized": 1.73}


def _write(tmp_path, lines):
    path = tmp_path / "export.jsonl"
    path.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8", newline="\n")
    return path


def _rec(plan=None, trade=TRADE, journal=JOURNAL):
    plan = plan or _plan_doc()
    return records.LiveRecord(plan["plan_id"], plan["ticker"], plan["direction"], plan, trade, journal)


def test_load_export_reads_every_kind_and_fingerprints(tmp_path):
    path = _write(tmp_path, [
        {"kind": "plan", "plan": _plan_doc(), "trade": TRADE, "journal": JOURNAL},
        {"kind": "rejection", "ticker": "BBB", "gate": "rs", "strategy": "RSI", "horizon": "2w",
         "signal_date": "2026-10-07"},
        {"kind": "watchlist", "ticker": "ZZZ", "added_at": "2026-01-01"},
        {"kind": "watchlist", "ticker": "AAA", "added_at": "2026-01-01"},
        {"kind": "deploy", "entry": {"ts": "2026-10-01T10:00:00Z", "git_sha": "abc"}},
    ])
    prints = {}
    export = records.load_export(path, input_fingerprints=prints)
    assert [r.plan_id for r in export.records] == ["P1"]
    assert export.records[0].side == "long"
    assert export.rejections[0]["gate"] == "rs"
    assert export.watchlist == ("AAA", "ZZZ")
    assert export.deploys[0]["git_sha"] == "abc"
    assert [len(v) for v in prints.values()] == [64]


def test_an_unknown_kind_names_its_line(tmp_path):
    path = _write(tmp_path, [{"kind": "watchlist", "ticker": "A", "added_at": "x"}, {"kind": "row"}])
    with pytest.raises(ValueError, match="line 2"):
        records.load_export(path)


def test_empty_rejections_and_deploys_are_measured_zeros(tmp_path):
    export = records.load_export(_write(tmp_path, [{"kind": "plan", "plan": _plan_doc(),
                                                    "trade": None, "journal": None}]))
    assert export.rejections == () and export.deploys == () and export.watchlist == ()


def test_until_drops_later_plans_and_rejections(tmp_path):
    late = _plan_doc(plan_id="P2", issued_at="2026-10-20T15:00:00+00:00")
    path = _write(tmp_path, [
        {"kind": "plan", "plan": _plan_doc(), "trade": None, "journal": None},
        {"kind": "plan", "plan": late, "trade": None, "journal": None},
        {"kind": "rejection", "ticker": "B", "gate": "g", "strategy": "s", "horizon": "2w",
         "signal_date": "2026-10-21"},
    ])
    export = records.load_export(path, until=dt.date(2026, 10, 9))
    assert [r.plan_id for r in export.records] == ["P1"] and export.rejections == ()


def test_short_side_for_bearish():
    assert _rec(plan=_plan_doc(direction="bearish")).side == "short"


@pytest.mark.parametrize("trade,journal,plan_kw,expected", [
    (None, None, {}, "unfilled"),
    ({**TRADE, "closed_at": None}, None, {}, "still_open"),
    (TRADE, JOURNAL, {}, "closed"),
    ({**TRADE, "close_reason": "manual"}, JOURNAL, {}, "manual"),
    (TRADE, JOURNAL, {"status_history": [{"status": "ACTIVE", "reason": "filled", "at": "a"},
                                         {"status": "CLOSED", "reason": "manual_bulk", "at": "b"}]},
     "manual"),
    (TRADE, None, {}, "closed"),
])
def test_class_of(trade, journal, plan_kw, expected):
    assert records.class_of(_rec(plan=_plan_doc(**plan_kw), trade=trade, journal=journal)) == expected


def test_era_boundary_is_inclusive():
    at = {**TRADE, "opened_at": "2026-09-15T08:54:50+00:00"}
    before = {**TRADE, "opened_at": "2026-09-15T08:54:49+00:00"}
    assert records.era_of(_rec(trade=at)) == "headline"
    assert records.era_of(_rec(trade=before)) == "earlier"


def test_era_of_an_unfilled_plan_uses_the_plan_stamp():
    plan = _plan_doc(issued_at="2026-09-01T15:00:00+00:00")
    assert records.era_of(_rec(plan=plan, trade=None, journal=None)) == "earlier"


def test_ledger_of_defaults_to_main():
    assert records.ledger_of(_rec()) == "weak"
    assert records.ledger_of(_rec(trade=None, journal=None)) == "main"


@pytest.mark.parametrize("plan_kw,expected", [
    ({"status": PlanStatus.CANCELLED,
      "status_history": [{"status": "CANCELLED", "reason": "expired", "at": "a"}]}, "expired"),
    ({"status": PlanStatus.PENDING, "status_history": []}, "pending"),
    ({"status": PlanStatus.CLOSED}, "unknown"),
])
def test_unfilled_reason(plan_kw, expected):
    rec = _rec(plan=_plan_doc(**plan_kw), trade=None, journal=None)
    assert records.unfilled_reason(rec) == expected


def test_rehydrate_resets_to_issued_state_and_keeps_the_issued_stop():
    doc = _plan_doc(entry_type="stop_entry", entry_price=100.4, working_stop=100.4,
                    tp1_fraction=0.5, tp2=108.0, legs_realized=[{"fraction": 0.5}],
                    runner_high_close=105.0)
    plan, scale_out = records.rehydrate(doc)
    assert plan.status == PlanStatus.PENDING and plan.status_history == []
    assert plan.working_stop is None and plan.legs_realized == [] and plan.runner_high_close is None
    assert plan.stop_loss == 98.0 and plan.tp1 == 104.0 and plan.tp2 == 108.0
    assert scale_out is True
    assert doc["working_stop"] == 100.4 and doc["status_history"]   # export untouched


def test_rehydrate_clears_a_fill_written_entry_price():
    assert records.rehydrate(_plan_doc(entry_type="limit", entry_price=99.5))[0].entry_price is None
    waiting = _plan_doc(entry_type="market", entry_price=101.0, waits_next_open=True)
    assert records.rehydrate(waiting)[0].entry_price is None
    assert records.rehydrate(_plan_doc())[0].entry_price == 100.0


def test_rehydrate_scale_out_follows_tp1_fraction():
    assert records.rehydrate(_plan_doc(tp1_fraction=1.0))[1] is False


def test_deploys_between_filters_by_new_york_date():
    export = records.Export((), (), (), (
        {"ts": "2026-10-10T03:00:00Z", "git_sha": "late"},     # 2026-10-09 in New York
        {"ts": "2026-09-14T12:00:00Z", "git_sha": "early"},
        {"git_sha": "no_ts"},
    ))
    got = records.deploys_between(export, dt.date(2026, 9, 15), dt.date(2026, 10, 9))
    assert [d["git_sha"] for d in got] == ["late"]
