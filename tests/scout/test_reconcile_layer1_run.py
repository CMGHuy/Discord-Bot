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
    trade = {"trade_id": f"T-{plan_id}", "plan_id": plan_id, "ticker": ticker, "direction": direction,
             "entry": 100.2 if long else 99.8, "stop_loss": doc["stop_loss"],
             "take_profit": doc["tp1"], "opened_at": "2026-10-06T15:01:00+00:00",
             "closed_at": "2026-10-08T17:00:00+00:00", "exit_price": 104.0 if long else 96.0,
             "close_reason": "tp1", "legs": [], "ledger": "weak"}
    journal = {"trade_id": trade["trade_id"], "outcome": "win", "r_realized": 1.727}
    if klass == "manual":
        trade["close_reason"] = "manual"
    if klass == "still_open":
        trade, journal = {**trade, "closed_at": None, "exit_price": None}, None
    if klass == "unfilled":
        trade = journal = None
    if klass == "no_journal":
        journal = None
    if klass == "null_r":
        journal = {**journal, "r_realized": None}
    if klass == "manual_null_r":
        trade["close_reason"] = "manual"
        journal = {**journal, "r_realized": None}
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


def test_a_row_names_the_trade_by_the_exported_trade_id_column():
    # Production trade docs carry no "id": the export merges the trade_id column in.
    assert _row(_rec()).trade_id == "T-P1"
    assert _row(_rec(klass="unfilled")).trade_id is None


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
    ("AAA", {}, "null_r", "no_journal"),
    ("AAA", {}, "manual_null_r", "no_journal"),
])
def test_refusals_keep_the_live_net_where_it_exists(ticker, kw, klass, expected):
    row = _row(_rec("PX", ticker, klass=klass), **kw)
    assert row.refusal == expected and expected in layer1_run.REFUSALS
    assert not row.scored and row.values == {}
    assert (row.r_live_net is None) == (expected == "no_journal")


def test_a_null_journal_r_is_classed_by_its_trade_and_carries_no_engine_values():
    for klass in ("null_r", "manual_null_r"):
        rec = _rec("PN", klass=klass)
        row = _row(rec)
        assert row.klass == records.class_of(rec) and row.refusal == "no_journal"
        assert row.r_live_gross is None and row.cost_r is None and row.r_live_net is None
        assert row.values == {} and row.effects == {} and row.tags == () and not row.scored


def test_a_fill_on_the_issued_stop_is_refused_zero_risk():
    rec = _rec()
    rec = dataclasses.replace(rec, trade={**rec.trade, "entry": 98.0})
    row = _row(rec)
    assert row.refusal == "zero_risk" and row.r_live_net is None


def test_a_row_survives_a_json_round_trip():
    row = _row(_rec())
    again = layer1_run.TradeRow.from_dict(json.loads(json.dumps(row.to_dict())))
    assert again == row and isinstance(again.tags, tuple)


from reconcile import checkpoint  # noqa: E402

def test_the_checkpoint_appends_and_reads_back(tmp_path):
    ck = checkpoint.JsonlCheckpoint(tmp_path / "sub" / "rows.jsonl")
    assert ck.done() == set() and ck.rows() == []
    ck.append("P1", {"a": 1})
    ck.append("P2", {"a": 2})
    ck.append("P1", {"a": 3})
    assert ck.done() == {"P1", "P2"} and ck.rows() == [{"a": 3}, {"a": 2}]
    assert ck.path.read_bytes().endswith(b"\n")


def test_the_checkpoint_drops_a_torn_last_line_on_open(tmp_path):
    path = tmp_path / "rows.jsonl"
    path.write_text('{"key": "P1", "row": {"a": 1}}\n{"key": "P2", "ro', encoding="utf-8")
    ck = checkpoint.JsonlCheckpoint(path)
    assert ck.done() == {"P1"}
    ck.append("P2", {"a": 2})
    assert [json.loads(x)["key"] for x in path.read_text(encoding="utf-8").splitlines()] == [
        "P1", "P2"]


def test_a_malformed_middle_line_raises(tmp_path):
    path = tmp_path / "rows.jsonl"
    path.write_text('{"key": "P1", "row": {}}\nnot json\n{"key": "P2", "row": {}}\n',
                    encoding="utf-8")
    with pytest.raises(ValueError, match="line 2"):
        checkpoint.JsonlCheckpoint(path).done()


def test_the_checkpoint_refuses_nan(tmp_path):
    with pytest.raises(ValueError):
        checkpoint.JsonlCheckpoint(tmp_path / "rows.jsonl").append("P1", {"r": float("nan")})


def _export(*recs):
    return records.Export(records=tuple(recs), rejections=(), watchlist=(), deploys=())


def _book():
    return _export(_rec("P1", "AAA"), _rec("P2", "BBB", "bearish"),
                   _rec("P3", "AAA", klass="unfilled"), _rec("P4", "CCC"))


class Counting:
    def __init__(self):
        self.calls = []

    def __call__(self, ticker):
        self.calls.append(ticker)
        return _bars(ticker)


def _run(path, export=None, bars=None, out=None):
    return layer1_run.run_layer1(export or _book(), bars or _bars,
                                 checkpoint.JsonlCheckpoint(path), frictions=FRICTIONS,
                                 start=START, out=(out.append if out is not None else print))


def test_run_layer1_returns_rows_in_export_order_and_checkpoints_each(tmp_path):
    path = tmp_path / "trade-rows.jsonl"
    rows = _run(path)
    assert [r.plan_id for r in rows] == ["P1", "P2", "P3", "P4"]
    assert checkpoint.JsonlCheckpoint(path).done() == {"T-P1", "T-P2", "P3", "T-P4"}
    assert [r.scored for r in rows] == [True, True, False, False]
    assert rows[3].refusal == "split_in_window"


def test_bars_load_once_per_ticker(tmp_path):
    bars = Counting()
    _run(tmp_path / "rows.jsonl", bars=bars)
    assert sorted(bars.calls) == ["AAA", "BBB", "CCC"]


def test_a_restart_skips_finished_trades_and_returns_equal_rows(tmp_path):
    path = tmp_path / "rows.jsonl"
    first = _run(path)
    bars = Counting()
    assert _run(path, bars=bars) == first
    assert bars.calls == []


def _second_trade(rec, trade_id="T-P1b", r_realized=-1.0, exit_price=98.0):
    """The same plan re-entered: a second exported line, its own trade and journal."""
    trade = {**rec.trade, "trade_id": trade_id, "exit_price": exit_price, "close_reason": "stop"}
    journal = {"trade_id": trade_id, "outcome": "loss", "r_realized": r_realized}
    return dataclasses.replace(rec, trade=trade, journal=journal)


def _two_trade_book():
    first = _rec("P1", "AAA")
    return _export(first, _second_trade(first), _rec("P3", "AAA", klass="unfilled"))


def test_the_unit_key_is_the_trade_id_else_the_plan_id():
    first = _rec("P1", "AAA")
    assert records.unit_key(first) == "T-P1" == _row(first).key
    assert records.unit_key(_second_trade(first)) == "T-P1b" == _row(_second_trade(first)).key
    unfilled = _rec("P3", klass="unfilled")
    assert records.unit_key(unfilled) == "P3" == _row(unfilled).key


def test_two_trades_on_one_plan_are_two_rows_each_counted_once(tmp_path):
    from reconcile import table
    path = tmp_path / "rows.jsonl"
    rows = _run(path, export=_two_trade_book())
    assert [(r.plan_id, r.trade_id) for r in rows] == [("P1", "T-P1"), ("P1", "T-P1b"),
                                                        ("P3", None)]
    assert rows[0].r_live_gross > 0 > rows[1].r_live_gross
    assert checkpoint.JsonlCheckpoint(path).done() == {"T-P1", "T-P1b", "P3"}
    want = rows[0].r_live_gross - rows[0].cost_r + rows[1].r_live_gross - rows[1].cost_r
    assert table.book_total(rows, side="long", era="headline") == pytest.approx(want)
    for m in ("v1", "v2"):
        lines = table.build_table(rows, side="long", fill_model=m)
        table.self_check(lines, rows, side="long", fill_model=m, era="headline")
        assert lines[-1].n == 2 and lines[-1].total_r == pytest.approx(want)


def test_a_restart_skips_each_trade_of_a_two_trade_plan_exactly_once(tmp_path):
    path = tmp_path / "rows.jsonl"
    book = _two_trade_book()
    first = _run(path, export=_export(book.records[0]))            # killed after T-P1
    bars = Counting()
    rows = _run(path, export=book, bars=bars)
    assert [r.trade_id for r in rows] == ["T-P1", "T-P1b", None]
    assert rows[0] == first[0]
    keys = [json.loads(x)["key"] for x in path.read_text(encoding="utf-8").splitlines()]
    assert keys == ["T-P1", "T-P1b", "P3"]
    again = Counting()
    assert _run(path, export=book, bars=again) == rows and again.calls == []


def test_a_torn_last_line_is_rescored(tmp_path):
    path = tmp_path / "rows.jsonl"
    first = _run(path)
    data = path.read_bytes()
    last = data.rstrip(b"\n").rsplit(b"\n", 1)[-1]
    path.write_bytes(data[:len(data) - 1 - len(last) // 2])          # killed mid-line
    bars = Counting()
    assert _run(path, bars=bars) == first
    assert bars.calls == ["CCC"]                                      # only P4 again
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 4 and all(json.loads(line) for line in lines)


def test_a_refusal_follows_the_tickers_latest_exit(tmp_path):
    early = _rec("Q1", "DDD")
    early = dataclasses.replace(early, trade={**early.trade,
                                              "closed_at": "2026-10-06T19:00:00+00:00"})
    rows = _run(tmp_path / "rows.jsonl", export=_export(early, _rec("Q2", "DDD")))
    assert [r.refusal for r in rows] == ["bars_end_early", "bars_end_early"]


def test_progress_reports_the_percent_done(tmp_path):
    out = []
    _run(tmp_path / "rows.jsonl", out=out)
    assert "4 to go" in out[0] and out[-1].endswith("4/4 trades (100%)")

