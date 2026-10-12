"""v151: the Why panel's pure gate and calendar rows.

Thresholds are passed in (GateThresholds), never read from config, so this
file patches nothing.
"""
import ast
import datetime as dt
import pathlib

import pytest

from swingbot.core.presentation.why_view import GateThresholds, calendar_rows, gate_rows

D = dt.date.fromisoformat
LIVE = GateThresholds(rs_gate=True, rs_laggard_pct=25.0, rs_leader_pct=0.0, regime_gates=False)


def _row(rows, key):
    return next(r for r in rows if r["key"] == key)


def test_rows_come_in_a_fixed_order_with_the_full_shape():
    rows = gate_rows("bearish", {}, {}, None, LIVE)
    assert [r["key"] for r in rows] == ["rs", "regime", "earnings"]
    for row in rows:
        assert set(row) == {"key", "label", "value", "threshold", "margin", "applies", "parts", "note"}


def test_rs_bearish_cleared_is_a_positive_margin():
    ctx = {"rs_combined": 18.0, "rs_pctile": 20.0, "sector_pctile": 30.0}
    rs = _row(gate_rows("bearish", ctx, {}, None, LIVE), "rs")
    assert rs["label"] == "Relative strength"
    assert rs["value"] == 18.0
    assert rs["threshold"] == 25.0
    assert rs["margin"] == pytest.approx(7.0)
    assert rs["applies"] is True
    assert rs["note"] is None
    assert rs["parts"] == [{"label": "Ticker RS pctile", "value": 20.0},
                           {"label": "Sector RS pctile", "value": 30.0}]


def test_rs_bearish_failed_is_a_negative_margin():
    rs = _row(gate_rows("bearish", {"rs_combined": 40.0}, {}, None, LIVE), "rs")
    assert rs["margin"] == pytest.approx(-15.0)
    assert rs["applies"] is True


def test_rs_bullish_arm_disabled_at_zero():
    rs = _row(gate_rows("bullish", {"rs_combined": 70.0}, {}, None, LIVE), "rs")
    assert rs["threshold"] == 0.0
    assert rs["applies"] is False
    assert rs["margin"] is None
    assert rs["note"] == "bullish arm disabled"


def test_rs_bullish_arm_live_measures_value_minus_threshold():
    leader = GateThresholds(rs_gate=True, rs_laggard_pct=25.0, rs_leader_pct=60.0, regime_gates=False)
    rs = _row(gate_rows("bullish", {"rs_combined": 70.0}, {}, None, leader), "rs")
    assert rs["applies"] is True
    assert rs["margin"] == pytest.approx(10.0)


def test_rs_gate_off_keeps_the_row_but_does_not_apply():
    off = GateThresholds(rs_gate=False, rs_laggard_pct=25.0, rs_leader_pct=0.0, regime_gates=False)
    rs = _row(gate_rows("bearish", {"rs_combined": 18.0}, {}, None, off), "rs")
    assert rs["value"] == 18.0
    assert rs["threshold"] == 25.0
    assert rs["applies"] is False
    assert rs["margin"] is None
    assert rs["note"] == "RS gate off"


def test_rs_falls_back_to_the_ticker_pctile():
    rs = _row(gate_rows("bearish", {"rs_pctile": 22.0}, {}, None, LIVE), "rs")
    assert rs["value"] == 22.0
    assert rs["margin"] == pytest.approx(3.0)


def test_all_missing_values_are_none_never_a_sentinel():
    rows = gate_rows("bearish", None, None, None, LIVE)
    rs, regime, earnings = (_row(rows, k) for k in ("rs", "regime", "earnings"))
    assert rs["value"] is None and rs["margin"] is None and rs["applies"] is False
    assert rs["note"] == "exempt"
    assert rs["parts"] == [{"label": "Ticker RS pctile", "value": None},
                           {"label": "Sector RS pctile", "value": None}]
    assert regime["value"] is None
    assert earnings["value"] is None


def test_regime_row_carries_the_cohort_note_and_the_switch():
    ctx = {"regime2_state": "BULL_QUIET"}
    regime = _row(gate_rows("bullish", ctx, {}, "BULL_QUIET-LONG", LIVE), "regime")
    assert regime["label"] == "Regime"
    assert regime["value"] == "BULL_QUIET"
    assert regime["threshold"] is None and regime["margin"] is None
    assert regime["applies"] is False
    assert regime["note"] == "BULL_QUIET-LONG"
    on = GateThresholds(rs_gate=True, rs_laggard_pct=25.0, rs_leader_pct=0.0, regime_gates=True)
    assert _row(gate_rows("bullish", ctx, {}, None, on), "regime")["applies"] is True


def test_earnings_none_does_not_apply_and_says_so():
    earnings = _row(gate_rows("bullish", {}, {"days_to_earnings": None}, None, LIVE), "earnings")
    assert earnings["label"] == "Days to earnings"
    assert earnings["applies"] is False
    assert earnings["note"] == "not recorded on this plan"


def test_earnings_recorded_applies_with_no_note():
    earnings = _row(gate_rows("bullish", {}, {"days_to_earnings": 12}, None, LIVE), "earnings")
    assert earnings["value"] == 12
    assert earnings["applies"] is True
    assert earnings["note"] is None


# --- calendar_rows -------------------------------------------------------

def test_a_window_spanning_one_monthly_opex():
    assert calendar_rows(D("2026-10-01"), D("2026-10-31")) == [
        {"date": "2026-10-16", "kind": "opex_monthly", "label": "Monthly OPEX"}]


def test_a_holiday_shifted_thursday():
    # 19 Apr 2030 is Good Friday and the third Friday: the expiration moves to Thursday.
    assert calendar_rows(D("2030-04-01"), D("2030-04-30")) == [
        {"date": "2030-04-18", "kind": "opex_monthly", "label": "Monthly OPEX"}]


def test_window_edges_are_inclusive_and_span_months():
    rows = calendar_rows(D("2026-09-18"), D("2026-10-16"))
    assert [r["date"] for r in rows] == ["2026-09-18", "2026-10-16"]


def test_an_empty_window():
    assert calendar_rows(D("2026-10-19"), D("2026-11-10")) == []
    assert calendar_rows(D("2026-10-31"), D("2026-10-01")) == []


def test_dates_past_coverage_return_no_row():
    assert calendar_rows(D("2031-01-01"), D("2031-03-31")) == []
    assert [r["date"] for r in calendar_rows(D("2030-12-01"), D("2031-01-31"))] == ["2030-12-20"]


# --- the no-config property ------------------------------------------------

@pytest.mark.parametrize("module", ["why_view.py", "components.py"])
def test_presentation_module_imports_no_config(module):
    path = pathlib.Path("swingbot/core/presentation") / module
    tree = ast.parse(path.read_text(encoding="utf-8"))
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            offenders += [a.name for a in node.names if a.name.startswith("swingbot.config")]
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").startswith("swingbot.config"):
                offenders.append(node.module)
            if node.module == "swingbot" and any(a.name == "config" for a in node.names):
                offenders.append("swingbot.config")
    assert not offenders, f"{module} imports {offenders}"
