"""v189 B2: the Calendar adds each leg's CONTRIBUTION (fraction x r), never
the leg's R at full size. With the golden trade, TP1 (+2R on 50%) plus a
runner (+3R on 50%) is +2.5R, not +5R. A whole single-exit trade, dollars,
counts and outcomes are unchanged. Every expected value is hand-computed."""
import pytest

from swingbot.core.analytics.pnl_calendar import day_summary, day_totals, joined_rows
from swingbot.core.tracking.performance import expand_realized_legs, expand_trade_legs
from tests.analytics.test_golden_partial_trade_metrics import (closed_case, golden_closed_trade,
                                                               load_golden)

DAY = "2026-08-03"
CLOSED_AT = "2026-08-03T20:00:00+00:00"
TOL = load_golden()["tolerance"]


def _other_trade() -> dict:
    """The fixture's -1R single-exit loss: 100 sh, entry 50, stop 48, out at 48."""
    other = load_golden()["calendar_day"]["other_trade"]
    return {**other, "id": "loss-1", "strategy": "S/R Confluence",
            "opened_at": "2026-08-01T14:00:00+00:00", "closed_at": CLOSED_AT,
            "realized_pnl_amount": round(other["shares"] * (other["exit_price"] - other["entry"]), 2),
            "target_sources": [], "stop_sources": []}


def _golden_day_rows() -> list[dict]:
    day = load_golden()["calendar_day"]
    gold = golden_closed_trade(closed_case(day["golden_case"]), closed_at=CLOSED_AT)
    return joined_rows([gold, _other_trade()], [])


# --- leg parts carry their weight ---------------------------------------------

def test_leg_parts_carry_fraction_and_leg_r():
    gold = golden_closed_trade(closed_case("manual"), closed_at=CLOSED_AT)
    parts = expand_trade_legs(gold)
    assert [(p["fraction"], p["leg_r"]) for p in parts] == [(0.5, 2.0), (0.5, 3.0)]


def test_the_open_remainder_part_carries_its_fraction_and_no_r():
    trade = {"status": "open", "shares": 100, "entry": 100.0, "direction": "bullish",
             "stop_loss": 95.0, "exit_price": None,
             "legs": [{"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1"}]}
    remainder = expand_trade_legs(trade)[-1]
    assert (remainder["status"], remainder["fraction"], remainder["leg_r"]) == ("open", 0.5, None)


def test_a_trade_without_legs_comes_back_unchanged():
    trade = _other_trade()
    assert expand_trade_legs(trade) == [trade]
    assert "fraction" not in expand_realized_legs(trade)[0]


# --- the golden day -------------------------------------------------------------

def test_golden_day_rows_carry_contributions():
    rows = _golden_day_rows()
    # TP1 0.5 x 2.0 = 1.0; runner 0.5 x 3.0 = 1.5; the loss (48-50)/2 = -1.0 whole.
    assert [r["r_multiple"] for r in rows] == pytest.approx([1.0, 1.5, -1.0])
    assert [r["outcome"] for r in rows] == ["win", "win", "loss"]
    # Dollars per row: 50 x 10 = 500, the closing leg carries 1250 - 500 = 750, -200.
    assert [r["pnl_amount"] for r in rows] == [500.0, 750.0, -200.0]


def test_golden_day_summary_matches_the_fixture():
    expected = load_golden()["calendar_day"]
    summary = day_summary(DAY, _golden_day_rows())
    assert summary["net_r"] == pytest.approx(expected["net_r"], abs=TOL)
    assert summary["net_pnl_amount"] == pytest.approx(expected["net_pnl_amount"])
    assert summary["trade_count"] == expected["trade_count"]
    assert summary["win_rate"] == pytest.approx(expected["win_rate"], abs=TOL)


def test_golden_day_totals_add_contributions():
    totals = day_totals(_golden_day_rows())
    assert totals["total_r"] == pytest.approx(1.5)
    assert (totals["winners"], totals["losers"]) == (2, 1)
    assert totals["total_ccy"] == pytest.approx(1050.0)


# --- edges ----------------------------------------------------------------------

def test_a_leg_without_r_contributes_its_derived_r_times_its_fraction():
    golden = load_golden()
    gold = golden_closed_trade(closed_case("manual"), closed_at=CLOSED_AT)
    gold["legs"] = [{**leg, "closed_at": CLOSED_AT}
                    for leg in golden["missing_leg_r_case"]["legs"]]
    rows = joined_rows([gold], [])
    # 0.5 x (110-100)/5 = 1.0 and 0.5 x (115-100)/5 = 1.5; together the fixture's 2.5.
    assert [r["r_multiple"] for r in rows] == pytest.approx([1.0, 1.5])
    assert day_summary(DAY, rows)["net_r"] == pytest.approx(golden["missing_leg_r_case"]["net_r"])


def test_a_bearish_leg_contribution_keeps_its_sign():
    trade = {"id": "short-1", "ticker": "SHRT", "strategy": "S/R Confluence",
             "direction": "bearish", "status": "loss", "shares": 10, "entry": 100.0,
             "stop_loss": 105.0, "exit_price": 103.0, "realized_pnl_amount": 35.0,
             "opened_at": "2026-08-01T14:00:00+00:00", "closed_at": CLOSED_AT,
             "target_sources": [], "stop_sources": [],
             "legs": [{"fraction": 0.5, "exit_price": 90.0, "closed_at": CLOSED_AT},
                      {"fraction": 0.5, "exit_price": 103.0, "closed_at": CLOSED_AT}]}
    rows = joined_rows([trade], [])
    # 0.5 x (100-90)/5 = +1.0 ; 0.5 x (100-103)/5 = -0.3
    assert [r["r_multiple"] for r in rows] == pytest.approx([1.0, -0.3])


def test_a_banked_leg_of_an_open_runner_counts_its_contribution():
    trade = {"id": "open-1", "ticker": "GOLD", "strategy": "S/R Confluence",
             "direction": "bullish", "status": "open", "shares": 100, "entry": 100.0,
             "stop_loss": 95.0, "exit_price": None, "realized_pnl_amount": None,
             "opened_at": "2026-08-01T14:00:00+00:00", "closed_at": None,
             "target_sources": [], "stop_sources": [],
             "legs": [{"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1",
                       "closed_at": CLOSED_AT}]}
    rows = joined_rows([trade], [])
    assert [r["r_multiple"] for r in rows] == pytest.approx([1.0])
    assert rows[0]["pnl_amount"] == 500.0


def test_a_whole_trade_still_prefers_the_journal_r():
    entry = {"trade_id": "loss-1", "outcome": "loss", "r_realized": -0.9}
    rows = joined_rows([_other_trade()], [entry])
    assert [r["r_multiple"] for r in rows] == [-0.9]


def test_a_whole_trade_without_a_journal_entry_is_its_own_r():
    rows = joined_rows([_other_trade()], [])
    assert [r["r_multiple"] for r in rows] == pytest.approx([-1.0])
