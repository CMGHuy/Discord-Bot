"""v232 V232-12: the reconciliation table and its self-check."""
import dataclasses
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "reports"))
from reconcile import layer1_run, table  # noqa: E402

LIVE = ("closed", "manual")


def _values(bt, exit_only, no_fill):
    return {"fill_model": "v1", "r_exit_only": exit_only, "exit_only_outcome": "win",
            "exit_only_class": "win", "r_as_backtest": None if no_fill else bt,
            "r_rebased": None, "stop_shift_pct": None, "backtest_no_fill": no_fill}


def _row(i, klass="closed", side="long", era="headline", refusal=None, gross=1.0, cost=0.1,
         bt=0.4, exit_only=0.8, no_fill=False):
    scored = klass == "closed" and refusal is None
    live = klass in LIVE and refusal not in table.NO_LIVE_R
    values = {m: _values(bt, exit_only, no_fill) for m in ("v1", "v2")} if scored else {}
    effects = {m: {"exit": gross - exit_only, "entry": None if no_fill else exit_only - bt}
               for m in values}
    return layer1_run.TradeRow(
        trade_id=f"T{i}", plan_id=f"P{i}", ticker="AAA", strategy="RSI", horizon_key="2w",
        ledger="main", side=side, era=era, klass=klass, refusal=refusal,
        entry_date="2026-10-06", stamp_source="issued_at", issue_bucket="mid_day",
        r_live_gross=gross if live else None, cost_r=cost if live else None,
        r_live_net=gross - cost if live else None, values=values, effects=effects, tags=(),
        gap=None, entry_slip=None, poll_fill=None, live_class="win" if live else None,
        unfilled_reason=None, would_fill={})


BOOK = [_row(1, gross=1.0, cost=0.1, bt=0.4, exit_only=0.8),
        _row(2, gross=-1.0, cost=0.1, bt=-1.0, exit_only=-0.5),
        _row(3, gross=2.0, cost=0.2, bt=1.5, exit_only=2.5),
        _row(4, gross=0.5, cost=0.1, no_fill=True),
        _row(5, klass="manual", gross=-0.3, cost=0.05),
        _row(6, refusal="split_in_window", gross=0.7, cost=0.1),
        _row(7, refusal="no_journal"),
        _row(8, klass="manual", refusal="zero_risk"),
        _row(9, klass="still_open"),
        _row(10, klass="unfilled"),
        _row(11, side="short", gross=-2.0),
        _row(12, era="earlier", gross=-3.0)]


def _table(rows=BOOK, **kw):
    kw = {"side": "long", "fill_model": "v1", "era": "headline", **kw}
    return table.build_table(rows, **kw), kw


def test_every_line_is_a_per_trade_sum():
    lines, _ = _table()
    assert [line.key for line in lines] == list(table.LINE_KEYS)
    got = {line.key: (round(line.total_r, 6), line.n) for line in lines}
    assert got == {"backtest": (0.9, 3), "entry": (1.9, 3), "exit": (-0.8, 3),
                   "live_gross": (2.0, 3), "costs": (0.4, 3), "live_net": (1.6, 3),
                   "backtest_no_fill": (0.4, 1), "manual": (-0.35, 1), "refused": (0.6, 3),
                   "book_net": (2.25, 8)}
    assert table.book_total(BOOK, side="long", era="headline") == pytest.approx(2.25)


def test_the_self_check_passes_on_a_consistent_book():
    lines, kw = _table()
    table.self_check(lines, BOOK, **kw)


def test_rows_without_live_r_are_counted_not_summed():
    lines, _ = _table()
    refused = next(line for line in lines if line.key == "refused")
    assert (refused.n, round(refused.total_r, 6)) == (3, 0.6)
    assert "2 without live R (no journal R or zero risk)" in refused.label
    clean, _ = _table([r for r in BOOK if r.refusal not in table.NO_LIVE_R])
    assert next(line for line in clean if line.key == "refused").label == table.LABELS["refused"]


def test_self_check_fails_on_a_tampered_effect():
    row = BOOK[0]
    effects = {**row.effects, "v1": {**row.effects["v1"], "exit": row.effects["v1"]["exit"] + 0.5}}
    rows = [dataclasses.replace(row, effects=effects)] + BOOK[1:]
    lines, kw = _table(rows)
    with pytest.raises(table.ReconcileError, match="live_gross"):
        table.self_check(lines, rows, **kw)


def test_self_check_fails_on_a_tampered_live_net():
    rows = [dataclasses.replace(BOOK[0], r_live_net=BOOK[0].r_live_net + 0.3)] + BOOK[1:]
    lines, kw = _table(rows)
    with pytest.raises(table.ReconcileError, match="live_net"):
        table.self_check(lines, rows, **kw)


def test_self_check_fails_on_a_tampered_line():
    lines, kw = _table()
    lines[0] = dataclasses.replace(lines[0], total_r=lines[0].total_r + 0.5)
    with pytest.raises(table.ReconcileError, match="line backtest"):
        table.self_check(lines, BOOK, **kw)


def test_a_mismatch_inside_the_tolerance_passes():
    lines, kw = _table()
    lines[-1] = dataclasses.replace(lines[-1], total_r=lines[-1].total_r + 0.004)
    table.self_check(lines, BOOK, **kw)


def test_an_empty_direction_gives_zero_lines_and_passes():
    lines, kw = _table(side="short", era="earlier")
    assert all(line.total_r == 0.0 and line.n == 0 for line in lines)
    table.self_check(lines, BOOK, **kw)


def test_the_fill_model_decides_backtest_no_fill():
    row = BOOK[0]
    v2 = {**row.values["v2"], "backtest_no_fill": True, "r_as_backtest": None}
    rows = [dataclasses.replace(row, values={**row.values, "v2": v2},
                                effects={**row.effects, "v2": {**row.effects["v2"],
                                                               "entry": None}})] + BOOK[1:]
    lines, kw = _table(rows, fill_model="v2")
    got = {line.key: line.n for line in lines}
    assert (got["backtest"], got["backtest_no_fill"], got["book_net"]) == (2, 2, 8)
    table.self_check(lines, rows, **kw)


def test_the_selection_line_reads_counts_and_rows():
    counts = {"long": {"headline": {"matched": 3, "live_only": {"n": 2},
                                    "replay_only": {"n": 4}, "outside_replay": 1}}}
    assert table.selection_line(counts, BOOK, side="long", era="headline") == (
        "Selection, counts only: matched 3 · live-only 2 · replay-only 4"
        " · outside the replay (strategy-sourced) 1 · still open 1 · unfilled 1")
