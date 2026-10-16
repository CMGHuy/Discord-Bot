"""v161 TS5: bar-reading cuts -- coverage, split guard, gaps, liquidity, fill reality, reversals.

Bars are fixture CSVs in tmp_path. The rules under test are frozen in the plan
(TS5 "Rules this task freezes"); the reversal tests pin that only bars strictly
after the exit day are read."""
from __future__ import annotations

import sys
from dataclasses import fields
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))
from autopsy import bars, rows  # noqa: E402

DAYS = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2026-02-02", periods=45)]


def _row(**kw):
    base = {f.name: None for f in fields(rows.BookRow) if f.name != "bars"}
    base.update(row_kind="trade", close_reason="", direction="bullish")
    base.update(kw)
    return rows.BookRow(**base)


def _trade(**kw):
    base = dict(ticker="AAA", plan_date=DAYS[24], entry_date=DAYS[25], planned_entry=100.0,
                entry=100.0, stop=98.0, take_profit=104.0, stop_width_atr=1.0,
                entry_type="stop_entry", gross_r=1.0, outcome="win", close_reason="tp1",
                exit_date=DAYS[28])
    base.update(kw)
    return _row(**base)


def _plan(**kw):
    base = dict(row_kind="plan", ticker="AAA", plan_date=DAYS[24], planned_entry=100.0,
                entry_type="stop_entry", expiry_bars=2, plan_status="CANCELLED",
                plan_status_reason="expired")
    base.update(kw)
    return _row(**base)


def _series(close=99.0, volume=1_000_000):
    """One bar per DAYS entry: Open = Close = close, High/Low half a point away."""
    return [[day, close, close + 0.5, close - 0.5, close, volume] for day in DAYS]


def _write(tmp_path, ticker, series):
    out = tmp_path / "bars"
    out.mkdir(exist_ok=True)
    lines = ["Date,Open,High,Low,Close,Volume"]
    lines += [",".join(str(v) for v in bar) for bar in series]
    (out / f"{ticker}.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def _cut(name, row):
    return dict(bars.bar_cuts())[name](row)


def test_bar_cuts_are_the_four_ledger_names_in_order():
    assert [name for name, _ in bars.bar_cuts()] == [
        "open_gap_bucket", "gapped_through_entry", "dollar_volume_bucket", "near_stop_reversal"]


def test_load_bars_uses_the_cache_file_name_and_returns_none_without_a_file(tmp_path):
    d = _write(tmp_path, "BRK_B", _series())
    _write(tmp_path, "_GSPC", _series())
    assert list(bars.load_bars(d, "BRK/B")["day"])[:2] == DAYS[:2]
    assert bars.load_bars(d, "^GSPC") is not None
    assert bars.load_bars(d, "ZZZ") is None
    assert bars.load_bars(None, "BRK/B") is None


@pytest.mark.parametrize("close, covered", [(110.0, True), (140.0, False)])
def test_the_split_guard_uncovers_rows_whose_plan_day_close_is_off_scale(tmp_path, close, covered):
    series = _series()
    series[24][4] = close
    row = _trade()
    assert bars.enrich_with_bars([row], _write(tmp_path, "AAA", series)) == int(covered)
    assert row.bars["covered"] is covered


def test_no_bars_dir_leaves_every_row_uncovered():
    row = _trade()
    assert bars.enrich_with_bars([row], None) == 0
    assert row.bars["covered"] is False
    assert row.bars["fill_status"] == "filled"
    assert all(_cut(name, row) is None for name, _ in bars.bar_cuts())


def test_the_covered_count_is_closed_trades_only(tmp_path):
    d = _write(tmp_path, "AAA", _series())
    assert bars.enrich_with_bars([_trade(), _plan(), _trade(gross_r=None)], d) == 1


def test_dollar_volume_is_the_20_bar_mean_ending_at_the_plan_day(tmp_path):
    series = _series(close=10.0)
    series[25][5] = 10 ** 9   # the fill day, after the plan day: must not count
    series[4][5] = 10 ** 9    # 21st bar back: outside the window
    row = _trade(planned_entry=10.0, entry=10.0, stop=9.8, take_profit=10.4)
    bars.enrich_with_bars([row], _write(tmp_path, "AAA", series))
    assert row.bars["dollar_volume"] == pytest.approx(1e7)
    assert _cut("dollar_volume_bucket", row) == "lt_20m"


def test_dollar_volume_needs_twenty_bars(tmp_path):
    row = _trade(plan_date=DAYS[10], entry_date=DAYS[11])
    bars.enrich_with_bars([row], _write(tmp_path, "AAA", _series()))
    assert row.bars["covered"] is True
    assert row.bars["dollar_volume"] is None
    assert _cut("dollar_volume_bucket", row) is None


@pytest.mark.parametrize("value, label", [(1e7, "lt_20m"), (3e7, "20m_50m"), (1e8, "50m_200m"),
                                          (5e8, "ge_200m")])
def test_dollar_volume_buckets(value, label):
    row = _row()
    row.bars = {"covered": True, "dollar_volume": value}
    assert _cut("dollar_volume_bucket", row) == label


def test_a_bullish_stop_entry_that_opens_above_its_trigger_gapped_through(tmp_path):
    series = _series()
    series[25][1], series[25][2] = 101.5, 102.0
    row = _trade()
    bars.enrich_with_bars([row], _write(tmp_path, "AAA", series))
    assert row.bars["fill_day_open"] == 101.5
    assert row.bars["open_gap_pct"] == pytest.approx(1.5)
    assert row.bars["gapped_through"] is True
    assert _cut("open_gap_bucket", row) == "adverse_large"
    assert _cut("gapped_through_entry", row) == "gapped"


def test_a_bearish_limit_that_opens_beyond_its_limit_filled_better(tmp_path):
    series = _series()
    series[25][1] = 101.0
    row = _trade(direction="bearish", entry_type="limit", stop=102.0, take_profit=96.0)
    bars.enrich_with_bars([row], _write(tmp_path, "AAA", series))
    assert row.bars["open_gap_pct"] == pytest.approx(-1.0)
    assert row.bars["gapped_through"] is True
    assert _cut("open_gap_bucket", row) == "favourable"


def test_a_market_entry_has_a_gap_but_no_gapped_through_flag(tmp_path):
    row = _trade(entry_type="market", planned_entry=99.0)
    bars.enrich_with_bars([row], _write(tmp_path, "AAA", _series()))
    assert row.bars["open_gap_pct"] == pytest.approx(0.0)
    assert _cut("open_gap_bucket", row) == "flat"
    assert row.bars["gapped_through"] is None
    assert _cut("gapped_through_entry", row) is None


@pytest.mark.parametrize("touch_index, expected", [(26, "expired_unfilled"), (27, "never_touched"),
                                                   (None, "never_touched")])
def test_an_expired_plan_is_split_by_whether_its_window_reached_the_trigger(
        tmp_path, touch_index, expected):
    series = _series()   # High 99.5, below the 100 trigger
    if touch_index is not None:
        series[touch_index][2] = 100.2   # window = DAYS[25], DAYS[26] (expiry_bars 2)
    row = _plan()
    bars.enrich_with_bars([row], _write(tmp_path, "AAA", series))
    assert row.bars["fill_status"] == expected


@pytest.mark.parametrize("touch_index, expected", [(27, "expired_unfilled"), (26, "never_touched")])
def test_a_valid_session_plan_only_reads_its_named_session(tmp_path, touch_index, expected):
    series = _series()
    series[touch_index][2] = 100.2
    row = _plan(valid_session=DAYS[27])
    bars.enrich_with_bars([row], _write(tmp_path, "AAA", series))
    assert row.bars["fill_status"] == expected


def test_a_bearish_limit_plan_is_touched_by_a_high_at_its_limit(tmp_path):
    series = _series()
    series[25][2] = 100.0
    row = _plan(direction="bearish", entry_type="limit")
    bars.enrich_with_bars([row], _write(tmp_path, "AAA", series))
    assert row.bars["fill_status"] == "expired_unfilled"


def test_an_expired_plan_whose_window_runs_past_the_bars_is_unknown(tmp_path):
    row = _plan(plan_date=DAYS[43])
    bars.enrich_with_bars([row], _write(tmp_path, "AAA", _series()))
    assert row.bars["fill_status"] == "unknown"


@pytest.mark.parametrize("status, reason, expected", [
    ("PENDING", None, "open"), ("ACTIVE", "stop_entry_fill", "filled"),
    ("PARTIAL", "tp1", "filled"), ("CANCELLED", "risk_cap", "risk_cap"),
    ("CANCELLED", "invalidated", "invalidated"), ("CANCELLED", "expired", "unknown"),
    ("CANCELLED", "something_else", "unknown")])
def test_plan_status_maps_to_a_fill_status_without_bars(status, reason, expected):
    row = _plan(plan_status=status, plan_status_reason=reason)
    bars.enrich_with_bars([row], None)
    assert row.bars["fill_status"] == expected


def _stopped(**kw):
    base = dict(close_reason="loss", outcome="loss", gross_r=-1.0)
    base.update(kw)
    return _trade(**base)


def test_a_stop_out_that_later_reaches_the_target_reversed(tmp_path):
    series = _series()
    series[31][2] = 104.5
    row = _stopped()
    bars.enrich_with_bars([row], _write(tmp_path, "AAA", series))
    assert (row.bars["reversal"], row.bars["wider_stop_lost"]) == (True, False)
    assert _cut("near_stop_reversal", row) == "reversed_to_target"


def test_a_wider_stop_hit_before_the_target_still_lost(tmp_path):
    series = _series()
    series[30][3] = 96.5    # wider stop = 98 - 0.5 x ATR 2 = 97
    series[31][2] = 104.5
    row = _stopped()
    bars.enrich_with_bars([row], _write(tmp_path, "AAA", series))
    assert _cut("near_stop_reversal", row) == "wider_stop_lost"


def test_a_bar_hitting_both_counts_the_wider_stop_first(tmp_path):
    series = _series()
    series[30][2], series[30][3] = 104.5, 96.5
    row = _stopped()
    bars.enrich_with_bars([row], _write(tmp_path, "AAA", series))
    assert _cut("near_stop_reversal", row) == "wider_stop_lost"


def test_the_exit_day_bar_is_never_read(tmp_path):
    series = _series()
    series[28][2] = 110.0   # the exit day itself: reading it would be lookahead into the stop bar
    row = _stopped()
    bars.enrich_with_bars([row], _write(tmp_path, "AAA", series))
    assert _cut("near_stop_reversal", row) == "no_resolution"


def test_fewer_than_reversal_bars_after_the_exit_is_unknown(tmp_path):
    row = _stopped(exit_date=DAYS[40])
    bars.enrich_with_bars([row], _write(tmp_path, "AAA", _series()))
    assert row.bars["reversal"] is None
    assert _cut("near_stop_reversal", row) is None


@pytest.mark.parametrize("reason, outcome, stopped", [
    ("loss", "loss", True), ("stop", "loss", True), ("auto (price monitor)", "loss", True),
    ("auto (price monitor)", "win", False), ("tp1_runner_tp2", "win", False),
    ("auto (near-TP stall)", "win", False)])
def test_only_stop_exits_get_a_reversal_reading(tmp_path, reason, outcome, stopped):
    series = _series()
    series[31][2] = 104.5
    row = _trade(close_reason=reason, outcome=outcome, gross_r=-1.0 if stopped else 1.0)
    bars.enrich_with_bars([row], _write(tmp_path, "AAA", series))
    assert (_cut("near_stop_reversal", row) is not None) is stopped


def test_fill_tallies_list_every_status_in_order_with_bar_covered_counts():
    filled, never, plain = _trade(), _plan(), _plan()
    filled.bars = {"fill_status": "filled", "covered": True}
    never.bars = {"fill_status": "never_touched", "covered": True}
    tallies = bars.fill_tallies([filled, never, plain])   # `plain` was never enriched
    assert [t.id for t in tallies] == [f"fill_status={s}" for s in bars.FILL_STATUS_ORDER]
    by = {t.value: t for t in tallies}
    assert by["filled"].count == 1 and by["never_touched"].count == 1
    assert by["unknown"].count == 1 and by["unknown"].extra == {"bar_covered": 0, "of_plans": 3}
    assert by["risk_cap"].count == 0


def test_liquidity_and_coverage_are_unchanged_when_future_bars_are_removed(tmp_path):
    series = _series()
    series[25][4], series[25][5] = 900.0, 10 ** 9
    full, truncated = _trade(), _trade()
    bars.enrich_with_bars([full], _write(tmp_path, "AAA", series))
    bars.enrich_with_bars([truncated], _write(tmp_path, "AAA", series[:25]))
    assert full.bars["covered"] is truncated.bars["covered"] is True
    assert full.bars["dollar_volume"] == truncated.bars["dollar_volume"] == 99e6


def test_missing_plan_day_anchors_before_fill_and_falls_back_to_entry_price(tmp_path):
    series = _series()
    series[25][4], series[25][5] = 900.0, 10 ** 9
    row = _trade(plan_date=None, planned_entry=None)
    bars.enrich_with_bars([row], _write(tmp_path, "AAA", series))
    assert row.bars["covered"] is True
    assert row.bars["dollar_volume"] == 99e6
    assert row.bars["open_gap_pct"] is None


@pytest.mark.parametrize("plan_date", [None, "2026-01-01"])
def test_no_anchor_leaves_the_row_uncovered(tmp_path, plan_date):
    row = _trade(plan_date=plan_date, entry_date=DAYS[0])
    assert bars.enrich_with_bars([row], _write(tmp_path, "AAA", _series())) == 0
    assert row.bars["covered"] is False


@pytest.mark.parametrize("high, low, expected", [
    (102.5, 95.5, "reversed_to_target"), (103.0, 95.5, "wider_stop_lost")])
def test_bearish_reversal_checks_the_wider_high_before_the_target_low(
        tmp_path, high, low, expected):
    series = _series(close=101.0)
    series[30][2], series[30][3] = high, low
    row = _stopped(direction="bearish", stop=102.0, take_profit=96.0)
    bars.enrich_with_bars([row], _write(tmp_path, "AAA", series))
    assert _cut("near_stop_reversal", row) == expected


def test_reversal_ignores_bars_after_its_ten_bar_window(tmp_path):
    series = _series()
    series[39][2] = 105.0
    full, truncated = _stopped(), _stopped()
    bars.enrich_with_bars([full], _write(tmp_path, "AAA", series))
    bars.enrich_with_bars([truncated], _write(tmp_path, "AAA", series[:39]))
    assert _cut("near_stop_reversal", full) == "no_resolution"
    assert _cut("near_stop_reversal", truncated) == "no_resolution"


@pytest.mark.parametrize("plan_day, entry_day, covered", [
    ("2026-01-20", "2026-01-21", True),
    (None, "2026-01-20", True),
    ("2026-01-21", "2026-01-22", False),
    (None, "2026-01-21", False),
    ("2026-03-02", "2026-03-03", False)])
def test_anchor_lag_is_bounded_but_accepts_a_holiday_weekend(tmp_path, plan_day, entry_day, covered):
    # Friday Jan 16 -> Tuesday Jan 20 is four calendar days (MLK holiday Monday).
    d = _write(tmp_path, "AAA", [["2026-01-16", 100, 101, 99, 100, 1000000]])
    row = _trade(plan_date=plan_day, entry_date=entry_day)
    assert bars.enrich_with_bars([row], d) == int(covered)
    assert row.bars["covered"] is covered


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize("column", [4, 5])
def test_nonfinite_dollar_volume_observations_leave_liquidity_unknown(tmp_path, value, column):
    series = _series()
    series[10][column] = value
    row = _trade()
    bars.enrich_with_bars([row], _write(tmp_path, "AAA", series))
    assert row.bars["dollar_volume"] is None
    assert _cut("dollar_volume_bucket", row) is None


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_fill_open_leaves_gap_unknown(tmp_path, value):
    series = _series()
    series[25][1] = value
    row = _trade()
    bars.enrich_with_bars([row], _write(tmp_path, "AAA", series))
    assert row.bars["fill_day_open"] is None
    assert _cut("open_gap_bucket", row) is None
    assert _cut("gapped_through_entry", row) is None


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_plan_window_high_leaves_expiry_unknown(tmp_path, value):
    series = _series()
    series[25][2] = value
    row = _plan()
    bars.enrich_with_bars([row], _write(tmp_path, "AAA", series))
    assert row.bars["fill_status"] == "unknown"


@pytest.mark.parametrize("column", [2, 3])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_reversal_bar_leaves_counterfactual_unknown(tmp_path, column, value):
    series = _series()
    series[30][column] = value
    row = _stopped()
    bars.enrich_with_bars([row], _write(tmp_path, "AAA", series))
    assert row.bars["reversal"] is None
    assert row.bars["wider_stop_lost"] is None


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_cut_values_are_uncovered(value):
    row = _trade()
    row.bars = {"dollar_volume": value, "open_gap_pct": value}
    assert _cut("dollar_volume_bucket", row) is None
    assert _cut("open_gap_bucket", row) is None
