"""v232 V232-9 / V232-9b: per-trade rows, the checkpoint and the layer 1 runner."""
import dataclasses
import datetime as dt
import json
import sys
from pathlib import Path

import pytest

from swingbot.core.planning.plan_types import PlanStatus, TradePlanV2, plan_to_dict
from tests.helpers import make_ohlcv

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "reports"))
from reconcile import layer1_run, records  # noqa: E402

FRICTIONS = {"slippage_bps": 5.0, "commission_per_trade": 1.0,
             "commission_risk_basis": 100.0, "min_risk_fraction": 0.0}
START = dt.date(2026, 10, 5)
F = (100.0, 100.6, 99.6, 100.0)
WIN = [F, (100.0, 100.8, 99.6, 100.5), (100.5, 101.0, 100.0, 100.8),
       (100.8, 104.5, 100.5, 104.0)] + [(104.0, 104.4, 103.6, 104.0)] * 6


def _frame(rows, start="2026-10-05"):
    return make_ohlcv(rows, start=start)


def _mirror(rows):
    return [(200 - o, 200 - lo, 200 - hi, 200 - c) for o, hi, lo, c in rows]


def _split_frame():
    split = _frame(WIN)
    split.iloc[5:, :4] = split.iloc[5:, :4] * 0.5          # a 2:1 split inside the window
    return split


BARS = {"AAA": (_frame(WIN), _frame(WIN)),
        "BBB": (_frame(_mirror(WIN)), _frame(_mirror(WIN))),
        "CCC": (_frame(WIN), _split_frame()),
        "DDD": (_frame(WIN[:2]), _frame(WIN[:2])),                          # ends 10-06
        "EEE": (_frame(WIN[2:], start="2026-10-07"), _frame(WIN[2:], start="2026-10-07"))}


def _bars(ticker):
    return BARS.get(ticker, (None, None))


def _rec(plan_id="P1", ticker="AAA", direction="bullish", klass="closed", **plan_kw):
    long = direction == "bullish"
    plan = dict(plan_id=plan_id, ticker=ticker, created_at="2026-10-06T15:00:00+00:00",
                source="confluence", strategy="RSI", horizon_key="2w", direction=direction,
                entry_type="market", trigger_price=100.0, entry_price=100.0, expiry_bars=3,
                stop_loss=98.0 if long else 102.0, tp1=104.0 if long else 96.0,
                tp1_fraction=1.0, tp2=None, breakeven_trigger_fraction=0.5, trail_atr_mult=2.5,
                quality_score=0, quality_breakdown=[], badge="WEAK", badge_stats={},
                status=PlanStatus.CLOSED, status_history=[],
                issued_at="2026-10-06T15:00:00+00:00")
    plan.update(plan_kw)
    doc = plan_to_dict(TradePlanV2(**plan))
    trade = {"id": f"T-{plan_id}", "plan_id": plan_id, "ticker": ticker, "direction": direction,
             "entry": 100.2 if long else 99.8, "stop_loss": doc["stop_loss"],
             "take_profit": doc["tp1"], "opened_at": "2026-10-06T15:01:00+00:00",
             "closed_at": "2026-10-08T17:00:00+00:00", "exit_price": 104.0 if long else 96.0,
             "close_reason": "tp1", "legs": [], "ledger": "weak"}
    journal = {"trade_id": trade["id"], "outcome": "win", "r_realized": 1.727}
    if klass == "manual":
        trade["close_reason"] = "manual"
    if klass == "still_open":
        trade, journal = {**trade, "closed_at": None, "exit_price": None}, None
    if klass == "unfilled":
        trade = journal = None
    if klass == "no_journal":
        journal = None
    return records.LiveRecord(plan_id, ticker, direction, doc, trade, journal)


def _row(rec, **kw):
    return layer1_run.row_for(rec, _bars, frictions=FRICTIONS, **kw)


OUTCOME_KEYS = {"values", "effects", "gap", "entry_slip", "poll_fill", "live_class"}


def test_a_scored_row_carries_both_fill_models_and_telescopes():
    row = _row(_rec())
    assert row.scored and row.refusal is None and row.klass == "closed"
    assert set(row.values) == set(row.effects) == {"v1", "v2"}
    assert row.r_live_net == pytest.approx(row.r_live_gross - row.cost_r)
    for model, v in row.values.items():
        eff = row.effects[model]
        assert row.r_live_gross - v["r_as_backtest"] == pytest.approx(eff["exit"] + eff["entry"])
    assert row.live_class == "win" and row.entry_date == "2026-10-06"
    assert (row.ledger, row.side, row.era, row.stamp_source) == ("weak", "long", "headline",
                                                                 "issued_at")
    assert row.entry_slip is not None and row.poll_fill is not None


def test_a_short_is_scored_on_its_mirrored_bars():
    row = _row(_rec("P2", "BBB", "bearish"))
    assert row.scored and row.side == "short" and row.values["v1"]["exit_only_outcome"] == "win"


@pytest.mark.parametrize("klass", ["still_open", "unfilled"])
def test_unscored_rows_carry_no_backtest_outcome(klass):
    row = _row(_rec(klass=klass, status=PlanStatus.CANCELLED,
                    status_history=[{"status": "CANCELLED", "reason": "expired", "at": "x"}]))
    assert not row.scored
    assert (row.values, row.effects, row.tags) == ({}, {}, ())
    assert all(getattr(row, k) in (None, {}, ()) for k in OUTCOME_KEYS)
    assert (row.r_live_gross, row.r_live_net) == (None, None)
    names = {f.name for f in dataclasses.fields(layer1_run.TradeRow)}
    assert not names & {"outcome", "r_multiple", "exit_date"}
    if klass == "unfilled":
        assert row.unfilled_reason == "expired"
        assert set(row.would_fill) == {"v1", "v2"}
        assert all(v in (True, False, None) for v in row.would_fill.values())
    else:
        assert row.would_fill == {} and row.unfilled_reason is None


def test_an_unfilled_plan_on_refused_bars_has_no_would_fill():
    row = _row(_rec("P5", "CCC", klass="unfilled"), start=START)
    assert row.refusal == "split_in_window"
    assert row.would_fill == {"v1": None, "v2": None}


def test_a_manual_close_keeps_live_r_only():
    row = _row(_rec(klass="manual"))
    assert row.klass == "manual" and not row.scored and row.refusal is None
    assert row.r_live_net is not None and row.values == {} and row.tags == ()


@pytest.mark.parametrize("ticker,kw,klass,expected", [
    ("CCC", {"start": START}, "closed", "split_in_window"),
    ("DDD", {}, "closed", "bars_end_early"),
    ("ZZZ", {}, "closed", "no_bars"),
    ("EEE", {"start": START}, "closed", "no_fill_bar"),
    ("AAA", {}, "no_journal", "no_journal"),
])
def test_refusals_keep_the_live_net_where_it_exists(ticker, kw, klass, expected):
    row = _row(_rec("PX", ticker, klass=klass), **kw)
    assert row.refusal == expected and expected in layer1_run.REFUSALS
    assert not row.scored and row.values == {}
    assert (row.r_live_net is None) == (expected == "no_journal")


def test_a_fill_on_the_issued_stop_is_refused_zero_risk():
    rec = _rec()
    rec = dataclasses.replace(rec, trade={**rec.trade, "entry": 98.0})
    row = _row(rec)
    assert row.refusal == "zero_risk" and row.r_live_net is None


def test_a_row_survives_a_json_round_trip():
    row = _row(_rec())
    again = layer1_run.TradeRow.from_dict(json.loads(json.dumps(row.to_dict())))
    assert again == row and isinstance(again.tags, tuple)

