"""v189 golden partial trade, metrics side (spec § Testing).

`golden_partial_trade.json` is the one fixture backend and frontend tests
share; every number in it is hand-computed (1R = $5/share, each leg 50
shares, TP1 +2R on 50% = +1.0R and $500). The helpers below are imported
by later v189 tests (calendar, plan manager, manual close, trades rows).
"""
import json
from pathlib import Path

import pytest

from swingbot.core.analytics import metrics
from swingbot.core.planning.exit_sim import runner_floor
from swingbot.core.planning.exit_sim_v2 import walk_v2
from swingbot.core.tracking.equity import open_shares, unrealized_pnl_amount
from swingbot.core.tracking.performance import closed_pnl_pct, settle_legs
from tests.backtesting.test_pullback_dryup_witness import pin_code_defaults
from tests.helpers import make_ohlcv
from tests.planning.test_exit_sim_v2_walk import ENTRY, FREE, TP1_BAR, _plan

FIXTURE_PATH = Path(__file__).with_name("golden_partial_trade.json")


def load_golden() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def closed_case(name: str) -> dict:
    return next(c for c in load_golden()["closed_cases"] if c["name"] == name)


def open_case(name: str) -> dict:
    return next(c for c in load_golden()["open_cases"] if c["name"] == name)


def _base(trade_id: str) -> dict:
    g = load_golden()["trade"]
    return {"id": trade_id, "ticker": g["ticker"], "direction": g["direction"],
            "shares": g["shares"], "entry": g["entry"], "stop_loss": g["stop_loss"],
            "take_profit": g["tp1"], "target2": g["tp2"], "tp1_fraction": g["tp1_fraction"],
            "strategy": "S/R Confluence", "target_sources": [], "stop_sources": [],
            "opened_at": "2026-08-01T14:00:00+00:00"}


def golden_closed_trade(case: dict, *, closed_at: str | None = None,
                        trade_id: str = "golden-1", runner_reason: str = "manual") -> dict:
    """The golden trade closed through `case`'s runner exit, legs written the
    way the live engine writes them (each leg with its own r)."""
    g = load_golden()["trade"]
    runner_r = (case["runner_exit"] - g["entry"]) / g["risk_per_share"]
    legs = [dict(g["tp1_leg"]),
            {"fraction": 1.0 - g["tp1_fraction"], "exit_price": case["runner_exit"],
             "r": runner_r, "reason": runner_reason}]
    if closed_at is not None:
        for leg in legs:
            leg["closed_at"] = closed_at
    trade = {**_base(trade_id), "exit_price": case["runner_exit"], "legs": legs,
             "status": case["status"], "close_reason": case["close_reason"],
             "closed_at": closed_at}
    trade["realized_pnl_amount"] = settle_legs(trade)
    return trade


def golden_open_trade(*, trade_id: str = "golden-open") -> dict:
    """The golden trade with TP1 banked and the runner still open."""
    g = load_golden()["trade"]
    return {**_base(trade_id), "exit_price": None, "legs": [dict(g["tp1_leg"])],
            "status": "open", "closed_at": None, "realized_pnl_amount": None}


TOL = load_golden()["tolerance"]
CLOSED = [c["name"] for c in load_golden()["closed_cases"]]
OPEN = [c["name"] for c in load_golden()["open_cases"]]


@pytest.mark.parametrize("name", CLOSED)
def test_closed_case_r_figures(name):
    case = closed_case(name)
    trade = golden_closed_trade(case)
    assert trade["legs"][1]["r"] == pytest.approx(case["runner_r"], abs=TOL)
    assert metrics._blended_r_raw(trade) == pytest.approx(case["net_r"], abs=TOL)
    assert metrics.r_multiple(trade) == pytest.approx(case["net_r"], abs=TOL)


@pytest.mark.parametrize("name", CLOSED)
def test_closed_case_dollars_and_pct_on_whole_position_notional(name):
    case = closed_case(name)
    trade = golden_closed_trade(case)
    assert trade["realized_pnl_amount"] == pytest.approx(case["realized_pnl_amount"], abs=0.01)
    # pnl_pct basis: realized dollars over 100 x 100 = $10,000 (closed_pnl_pct).
    assert closed_pnl_pct(trade) == pytest.approx(case["pnl_pct"], abs=TOL)


@pytest.mark.parametrize("name", CLOSED)
def test_closed_case_label(name):
    case = closed_case(name)
    assert metrics.net_outcome(golden_closed_trade(case)) == (case["status"], case["close_reason"])


def test_floor_case_is_the_v39_runner_floor():
    g = load_golden()["trade"]
    assert closed_case("floor")["runner_exit"] == pytest.approx(runner_floor(g["entry"], g["tp1"]))


def test_missing_leg_r_case_derives_r_from_exit_prices():
    golden = load_golden()
    trade = {**_base("missing-r"), "legs": golden["missing_leg_r_case"]["legs"]}
    assert metrics.r_multiple(trade) == pytest.approx(golden["missing_leg_r_case"]["net_r"])


@pytest.mark.parametrize("name", OPEN)
def test_open_case_metrics(name):
    case = open_case(name)
    trade = golden_open_trade()
    g = load_golden()["trade"]
    assert trade["legs"][0]["r"] == case["banked_r"]
    assert metrics.banked_contribution_r(trade["legs"]) == pytest.approx(case["banked_contribution_r"])
    assert settle_legs(trade) == pytest.approx(case["banked_amount"])
    assert open_shares(trade["shares"], trade["legs"]) == case["shares"]
    assert trade["shares"] == case["entry_shares"]
    assert case["working_stop"] == pytest.approx(runner_floor(g["entry"], g["tp1"]))
    blended = metrics.open_trade_r(trade, case["quote"])
    if case["r_multiple"] is None:
        assert blended is None
    else:
        assert blended == pytest.approx(case["r_multiple"], abs=TOL)


def test_open_quote_case_unrealized_and_profit_to_stop():
    case = open_case("quote_113")
    trade = golden_open_trade()
    held = open_shares(trade["shares"], trade["legs"])
    assert unrealized_pnl_amount(trade["entry"], trade["direction"], held, case["quote"]) == \
        pytest.approx(case["unrealized_pnl_amount"])
    # Open profit to stop: 50 x (113 - 106.67) = 316.67; risk of loss: the
    # working stop is above entry, so nothing below entry can be lost.
    assert held * (case["quote"] - case["working_stop"]) == \
        pytest.approx(case["open_profit_to_stop"], abs=0.01)
    assert max(0.0, trade["entry"] - case["working_stop"]) * held == case["risk_of_loss_amount"]


# --- the parity pin: live and backtest label the gap case differently --------

@pytest.fixture
def _pinned(monkeypatch):
    pin_code_defaults(monkeypatch)


def test_backtest_still_labels_the_gap_case_win(_pinned):
    """D2 is live-only (spec D2, last bullet). exit_sim_v2 labels a scaled-out
    trade by the TP1 event, so the runner gapping to an open of 88 is a `win`
    there while the live label is `loss`. If this fails, the closed
    acceptance gates have moved: stop, do not edit exit_sim_v2."""
    case = closed_case("gap")
    gap_bar = (case["runner_exit"], case["runner_exit"] + 1.0,
               case["runner_exit"] - 1.0, case["runner_exit"])
    df = make_ohlcv([ENTRY, TP1_BAR, gap_bar])
    res = walk_v2(df, 0, 100.0, _plan(tp1_fraction=0.5), 10, FREE, scale_out=True)
    assert res.legs[1]["exit_price"] == case["runner_exit"]
    assert res.r_total == pytest.approx(case["net_r"], abs=TOL)
    assert res.outcome == case["backtest_label"] == "win"
    assert metrics.net_outcome(golden_closed_trade(case)) == ("loss", None)
