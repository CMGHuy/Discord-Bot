"""v189 B4: risk of loss to the stop -- what a fill at the current working
stop would still lose below entry, floored at 0 per position. Shown beside
enforced heat, never instead of it (display only)."""
import ast
import logging
import math
from pathlib import Path

import pytest

from swingbot.core.edge.heat import risk_of_loss_amount
from swingbot.core.scanning import scan_run
from swingbot.core.tracking.equity import position_risk_of_loss
from tests.analytics.test_golden_partial_trade_metrics import (golden_open_trade,
                                                               load_golden, open_case)

G = load_golden()["trade"]


def test_a_long_stop_below_entry_loses_shares_times_distance():
    assert risk_of_loss_amount(100.0, 95.0, "bullish", 100) == 500.0


def test_a_short_stop_above_entry_loses_shares_times_distance():
    assert risk_of_loss_amount(100.0, 105.0, "bearish", 40) == 200.0


@pytest.mark.parametrize("entry, stop, direction", [
    (100.0, 106.66666666666667, "bullish"),   # the golden runner floor
    (100.0, 100.0, "bullish"),                # break-even
    (100.0, 93.0, "bearish"),                 # a short's stop ratcheted into profit
])
def test_a_stop_at_or_past_entry_risks_nothing(entry, stop, direction):
    assert risk_of_loss_amount(entry, stop, direction, 50) == 0.0


@pytest.mark.parametrize("entry, stop, direction, shares", [
    (None, 95.0, "bullish", 100), (100.0, None, "bullish", 100),
    (100.0, 95.0, "bullish", None), (math.nan, 95.0, "bullish", 100),
    (100.0, math.inf, "bearish", 100), (100.0, 95.0, "bullish", math.nan),
    (100.0, 95.0, "sideways", 100),
])
def test_missing_or_non_finite_inputs_are_zero_never_nan(entry, stop, direction, shares):
    assert risk_of_loss_amount(entry, stop, direction, shares) == 0.0


def _plan(status: str, *, working_stop=None, legs=None) -> dict:
    return {"plan_id": "golden-plan", "status": status, "direction": G["direction"],
            "entry_price": G["entry"], "stop_loss": G["stop_loss"],
            "working_stop": working_stop, "legs_realized": legs or []}


@pytest.mark.parametrize("name", [c["name"] for c in load_golden()["open_cases"]])
def test_the_golden_runner_at_its_floor_risks_nothing(name):
    case = open_case(name)
    plan = _plan("PARTIAL", working_stop=case["working_stop"], legs=[dict(G["tp1_leg"])])
    assert position_risk_of_loss(golden_open_trade(), plan) == case["risk_of_loss_amount"]


def test_an_active_plan_without_a_working_stop_uses_its_risk_stop():
    assert position_risk_of_loss(golden_open_trade(), _plan("ACTIVE")) == 500.0   # 100 x (100 - 95)


def test_a_break_even_stop_risks_nothing():
    assert position_risk_of_loss(golden_open_trade(), _plan("ACTIVE", working_stop=100.0)) == 0.0


def test_a_partial_counts_only_its_open_shares():
    """50 shares still held after TP1, stop back at the risk stop: 50 x 5."""
    plan = _plan("PARTIAL", legs=[dict(G["tp1_leg"])])
    assert position_risk_of_loss(golden_open_trade(), plan) == 250.0


@pytest.mark.parametrize("status", ["PENDING", "CLOSED", "CANCELLED"])
def test_a_plan_that_is_not_held_has_no_risk_of_loss(status):
    assert position_risk_of_loss(golden_open_trade(), _plan(status)) is None


def test_a_trade_with_no_plan_uses_its_own_stop_and_size():
    assert position_risk_of_loss(golden_open_trade(), None) == 500.0


def test_the_heat_block_line_names_the_enforced_heat(caplog):
    with caplog.at_level(logging.INFO, logger=scan_run.log.name):
        scan_run._log_heat_block("AAPL", 5.4, 1.0, 6.0)
    assert "heat blocked (enforced 5.40% + 1.00% > cap 6.00%) AAPL" in caplog.text


def test_the_scan_heat_gate_logs_every_block():
    """The confluence lane's heat gate is inline in `_sync_run_scan`; pin
    that the branch which flags `item.heat_blocked` also logs the line."""
    tree = ast.parse(Path(scan_run.__file__).read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
              and n.name == "_sync_run_scan")
    gate = next(n for n in ast.walk(fn)
                if isinstance(n, ast.If) and "heat_chk" in ast.unparse(n.test))
    called = {ast.unparse(c.func) for c in ast.walk(gate) if isinstance(c, ast.Call)}
    assert "_log_heat_block" in called
