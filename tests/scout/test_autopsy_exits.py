"""v161 TS6: exit cuts, give-back over all trades, stop extras and alert-supply tallies."""
from __future__ import annotations

import sys
from dataclasses import fields
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))
from autopsy import exits, rows  # noqa: E402


def _row(**kw):
    base = {f.name: None for f in fields(rows.BookRow) if f.name != "bars"}
    base.update(row_kind="trade", close_reason="", direction="bullish")
    base.update(kw)
    return rows.BookRow(**base)


def _cut(name, row):
    return dict(exits.exit_cuts())[name](row)


def test_exit_cuts_are_the_four_ledger_names_in_order():
    assert [name for name, _ in exits.exit_cuts()] == [
        "exit_reason", "near_tp_close", "gap_through_stop", "holding_bucket"]
    assert exits.STOP_CUTS == {"exit_reason", "gap_through_stop", "near_stop_reversal"}


@pytest.mark.parametrize("reason, bucket", [
    ("loss", "stop"), ("tp1", "tp1"), ("tp1_runner_tp2", "runner_tp2"), ("tp1_runner_be", "runner_be"),
    ("scratch", "scratch"), ("time_exit", "timeout"), ("auto (near-TP stall)", "timeout"),
    ("auto (near-TP timeout)", "timeout"), ("auto (price monitor)", "other")])
def test_exit_reason_uses_the_live_book_bucket_rule(reason, bucket):
    assert _cut("exit_reason", _row(close_reason=reason, outcome="win", gross_r=0.5)) == bucket


@pytest.mark.parametrize("reason, label", [
    ("auto (near-TP stall)", "near_tp_stall"), ("AUTO (NEAR-TP TIMEOUT)", "near_tp_timeout"),
    ("loss", "other_exit"), ("", "other_exit")])
def test_near_tp_closes_are_split_from_every_other_exit(reason, label):
    assert _cut("near_tp_close", _row(close_reason=reason, gross_r=0.4)) == label


@pytest.mark.parametrize("reason, outcome, stop", [
    ("loss", "loss", True), ("STOP", "loss", True), ("auto (price monitor)", "loss", True),
    ("auto (price monitor)", "win", False), ("tp1", "win", False), (None, "loss", False), (" loss ", "loss", False),
    ("auto (price monitor) legacy", "loss", True)])
def test_is_stop_exit(reason, outcome, stop):
    assert exits.is_stop_exit(_row(close_reason=reason, outcome=outcome)) is stop


@pytest.mark.parametrize("reason, gross, label", [
    ("loss", -1.4, "through_stop"), ("loss", -1.0, "at_stop"), ("loss", -1.004, "at_stop"),
    ("tp1", -1.4, None)])
def test_gap_through_stop_is_read_on_stop_exits_only(reason, gross, label):
    row = _row(close_reason=reason, outcome="loss" if reason == "loss" else "win", gross_r=gross)
    assert _cut("gap_through_stop", row) == label


@pytest.mark.parametrize("days, label", [(1.0, "2w|le_2d"), (4.0, "2w|3_5d"), (10.0, "2w|6_10d"),
                                         (11.0, "2w|gt_10d")])
def test_holding_bucket_is_per_horizon(days, label):
    assert _cut("holding_bucket", _row(horizon="2w", holding_days=days, gross_r=0.1)) == label


def test_holding_bucket_needs_a_horizon_and_holding_days():
    assert _cut("holding_bucket", _row(horizon=None, holding_days=3.0)) is None
    assert _cut("holding_bucket", _row(horizon="2w", holding_days=None)) is None


def test_stop_extra_reports_atr_width_dollar_loss_at_fixed_risk_and_overshoot():
    members = [
        _row(stop_width_atr=1.0, net_r=-1.0, gross_r=-1.0, close_reason="loss", outcome="loss"),
        _row(stop_width_atr=2.0, net_r=-1.5, gross_r=-1.5, close_reason="loss", outcome="loss"),
        _row(stop_width_atr=None, net_r=0.5, gross_r=0.6, close_reason="tp1", outcome="win"),
    ]
    extra = exits.stop_extra(members, balance=10_000.0)
    assert extra["mean_stop_atr"] == pytest.approx(1.5)
    assert extra["dollar_loss_at_2pct"] == pytest.approx(250.0)   # 1.25 R x 2% x 10 000
    assert extra["mean_overshoot_r"] == pytest.approx(0.5)


def test_stop_extra_without_inputs_is_none_not_zero():
    assert exits.stop_extra([_row(net_r=0.4, gross_r=0.5)], balance=10_000.0) == {
        "mean_stop_atr": None, "dollar_loss_at_2pct": None, "mean_overshoot_r": None}


def test_giveback_covers_losers_as_well_as_winners():
    trades = [_row(mfe_r=2.0, gross_r=1.0), _row(mfe_r=1.5, gross_r=-1.0),
              _row(mfe_r=None, gross_r=0.3)]
    assert exits.giveback_summary(trades) == {"n": 2, "mean": 1.75, "median": 1.75}
    assert exits.giveback_summary([]) == {"n": 0, "mean": None, "median": None}


def _plans():
    out = [_row(row_kind="plan", plan_date="2026-03-02", plan_hour=7)]
    out += [_row(row_kind="plan", plan_date="2026-03-03", plan_hour=h) for h in (12, 17, None)]
    out += [_row(row_kind="trade", plan_date="2026-03-04 14:00:00", plan_hour=8) for _ in range(8)]
    out.append(_row(row_kind="trade", plan_date=None, plan_hour=None))   # a trade with no plan
    return out


@pytest.fixture
def supply_tallies():
    rejections = [rows.RejectionCount(date="2026-03-02", reason="risk_cap", count=4),
                  rows.RejectionCount(date="2026-03-03", reason="risk_cap", count=1),
                  rows.RejectionCount(date="2026-03-03", reason="a;b", count=2)]
    return exits.alert_supply_tallies(_plans(), rejections)


def test_alert_supply_counts_days_and_plans(supply_tallies):
    tallies = supply_tallies
    by = {t.id: t for t in tallies}
    assert [t.id for t in tallies][:4] == [
        "alerts_per_day=1", "alerts_per_day=2_3", "alerts_per_day=4_6", "alerts_per_day=7_plus"]
    assert (by["alerts_per_day=1"].count, by["alerts_per_day=1"].extra) == (1, {"plans": 1})
    assert (by["alerts_per_day=2_3"].count, by["alerts_per_day=2_3"].extra) == (1, {"plans": 3})
    assert (by["alerts_per_day=7_plus"].count, by["alerts_per_day=7_plus"].extra) == (1, {"plans": 8})
    assert by["alerts_per_day=4_6"].count == 0


def test_alert_supply_counts_sessions_and_before_open(supply_tallies):
    by = {t.id: t for t in supply_tallies}
    assert by["alert_hour_session=premarket"].count == 9
    assert by["alert_hour_session=regular"].count == 1
    assert by["alert_hour_session=after_close"].count == 1
    assert by["alert_hour_session=unknown"].count == 1
    assert (by["actionable_before_open=yes"].count, by["actionable_before_open=no"].count,
            by["actionable_before_open=unknown"].count) == (10, 1, 1)


def test_alert_supply_sums_and_sorts_sanitized_rejections(supply_tallies):
    tallies = supply_tallies
    by = {t.id: t for t in tallies}
    assert [t.id for t in tallies if t.cut == "rejection_reason"] == [
        "rejection_reason=risk_cap", "rejection_reason=a,b"]
    assert by["rejection_reason=risk_cap"].count == 5
    assert by["rejection_reason=risk_cap"].extra == {"days": 2}
