"""v189 B1/B3: the golden scaled-out trade on the Trades API rows.

Every expected figure comes from `tests/analytics/golden_partial_trade.json`
(hand-computed: 100 sh, f 0.5, entry 100, stop 95 so 1R = $5/share, TP1 +2R
on 50% = +1.0R and $500). The Vitest specs read the same file (V189-21/22),
so the API and the screen cannot drift.
"""
import pytest

import swingbot.admin.app  # noqa: F401 -- initializes API routes before importing one endpoint
from swingbot.admin.api_v1.trades import (_attach_unrealized_pnl, _expand_plan_row,
                                          _row_from_plan, _row_from_trade,
                                          _strip_internal_fields)
from tests.admin.test_trades_partial_row import partial_plan
from tests.analytics.test_golden_partial_trade_metrics import (closed_case,
                                                               golden_closed_trade,
                                                               golden_open_trade,
                                                               load_golden, open_case)

@pytest.fixture(autouse=True)
def _same_currency(monkeypatch):
    """The admin_app fixture pins every ticker to the account currency; these
    tests call the row helpers directly, so pin it here (identity, no rate)."""
    from swingbot.core.marketdata import fx
    monkeypatch.setattr(fx, "quote_currency_code", lambda ticker: fx.account_currency_code())


G = load_golden()
TOL = G["tolerance"]
OPEN = [c["name"] for c in G["open_cases"]]
CLOSED = [c["name"] for c in G["closed_cases"]]
PLAN_ID = "golden-plan"


def golden_plan(status: str = "PARTIAL", legs: list[dict] | None = None) -> dict:
    """The golden trade's plan: TP1 banked, the runner's stop at the v39 floor."""
    g = G["trade"]
    if legs is None:
        legs = [dict(g["tp1_leg"], closed_at="2026-08-02T14:00:00+00:00")]
    return partial_plan(plan_id=PLAN_ID, ticker=g["ticker"], status=status,
                        direction=g["direction"], entry_price=g["entry"],
                        trigger_price=g["entry"], stop_loss=g["stop_loss"],
                        tp1=g["tp1"], tp2=g["tp2"], tp1_fraction=g["tp1_fraction"],
                        working_stop=open_case("quote_113")["working_stop"],
                        legs_realized=legs)


def priced_rows(plan: dict, trade: dict, quote: float | None, *, passes: int = 1) -> list[dict]:
    """`list_trades`' order: expand, price the open rows, attach live P&L
    (`passes` times, as a sort on r_multiple does), strip transient keys."""
    rows = _expand_plan_row(plan, trade, set())
    for row in rows:
        if row["status"] not in ("CLOSED", "CANCELLED"):
            row["current_price"] = quote
    for _ in range(passes):
        _attach_unrealized_pnl(rows)
    _strip_internal_fields(rows)
    return rows


def open_trade() -> dict:
    return dict(golden_open_trade(), plan_id=PLAN_ID)


@pytest.mark.parametrize("name", OPEN)
def test_open_runner_row_matches_the_golden_case(name):
    case = open_case(name)
    runner = priced_rows(golden_plan(), open_trade(), case["quote"])[-1]
    assert runner["status"] == "PARTIAL"
    assert runner["shares"] == case["shares"]                    # remaining, as today
    assert runner["entry_shares"] == case["entry_shares"]        # B1: the original size
    assert runner["banked_r"] == pytest.approx(case["banked_r"])  # the TP1 leg's own R, unchanged
    assert runner["banked_contribution_r"] == pytest.approx(case["banked_contribution_r"])
    assert runner["realized_pnl_amount"] == (
        None if case["unrealized_pnl_amount"] is None
        else pytest.approx(case["unrealized_pnl_amount"], abs=0.01))
    if case["r_multiple"] is None:
        assert runner["r_multiple"] is None                      # never the banked R alone
    else:
        assert runner["r_multiple"] == pytest.approx(case["r_multiple"], abs=TOL)


@pytest.mark.parametrize("name", OPEN)
def test_banked_dollars_are_priced_on_entry_shares(name):
    """B1: the banked leg is fraction x ORIGINAL size. On `shares` (the
    remaining 50) it reads $250, the (1 - f) bug the screens showed."""
    case = open_case(name)
    runner = priced_rows(golden_plan(), open_trade(), case["quote"])[-1]
    move = runner["banked_exit_price"] - runner["entry"]
    assert move * runner["entry_shares"] * runner["banked_fraction"] == pytest.approx(
        case["banked_amount"])
    assert move * runner["shares"] * runner["banked_fraction"] != pytest.approx(
        case["banked_amount"])


def test_the_banked_tp1_leg_row_is_its_own_closed_trade():
    leg = priced_rows(golden_plan(), open_trade(), open_case("quote_113")["quote"])[0]
    assert leg["status"] == "CLOSED"
    assert (leg["shares"], leg["entry_shares"]) == (50.0, 100)
    assert leg["r_multiple"] == pytest.approx(2.0)
    assert leg["realized_pnl_amount"] == pytest.approx(500.0)
    assert (leg["banked_r"], leg["banked_contribution_r"]) == (None, None)


def test_a_second_attach_pass_keeps_the_blended_r():
    """A sort on r_multiple prices every row first, then the page again."""
    runner = priced_rows(golden_plan(), open_trade(), 113.0, passes=2)[-1]
    assert runner["r_multiple"] == pytest.approx(2.3, abs=TOL)
    assert runner["shares"] == 50.0


@pytest.mark.parametrize("name", CLOSED)
def test_closed_whole_position_row_matches_the_golden_case(name):
    case = closed_case(name)
    trade = dict(golden_closed_trade(case, closed_at="2026-08-05T15:00:00+00:00"),
                 plan_id=PLAN_ID)
    row = _row_from_plan(golden_plan("CLOSED", legs=trade["legs"]), trade, set())
    assert row["outcome"] == case["status"]
    assert (row["shares"], row["entry_shares"]) == (100, 100)
    assert row["r_multiple"] == pytest.approx(case["net_r"], abs=TOL)
    assert row["realized_pnl_amount"] == pytest.approx(case["realized_pnl_amount"], abs=0.01)
    assert row["pnl_pct"] == pytest.approx(case["pnl_pct"], abs=TOL)
    # banked_contribution_r travels with banked_r: both or neither.
    assert (row["banked_r"] is None) == (row["banked_contribution_r"] is None)


@pytest.mark.parametrize("name", CLOSED)
def test_closed_leg_rows_sum_to_the_trades_realized_dollars(name):
    case = closed_case(name)
    trade = dict(golden_closed_trade(case, closed_at="2026-08-05T15:00:00+00:00"),
                 plan_id=PLAN_ID)
    rows = _expand_plan_row(golden_plan("CLOSED", legs=trade["legs"]), trade, set())
    assert [r["shares"] for r in rows] == [50.0, 50.0]
    assert [r["entry_shares"] for r in rows] == [100, 100]
    assert rows[0]["r_multiple"] == pytest.approx(2.0)
    assert rows[1]["r_multiple"] == pytest.approx(case["runner_r"], abs=TOL)
    assert sum(r["realized_pnl_amount"] for r in rows) == pytest.approx(
        case["realized_pnl_amount"], abs=0.01)


def test_a_bearish_runner_blends_with_the_sign_flipped():
    """The golden trade mirrored: entry 100, stop 105, TP1 90 (+2R on 50%),
    quote 87 is +2.6R live, so 1.0 + 0.5 x 2.6 = 2.30R."""
    plan = partial_plan(plan_id=PLAN_ID, direction="bearish", entry_price=100.0,
                        trigger_price=100.0, stop_loss=105.0, tp1=90.0, tp2=80.0,
                        working_stop=93.33333333333333, tp1_fraction=0.5,
                        legs_realized=[{"fraction": 0.5, "exit_price": 90.0, "r": 2.0,
                                        "reason": "tp1"}])
    trade = dict(open_trade(), direction="bearish", stop_loss=105.0)
    runner = priced_rows(plan, trade, 87.0)[-1]
    assert runner["banked_contribution_r"] == pytest.approx(1.0)
    assert runner["r_multiple"] == pytest.approx(2.3, abs=TOL)


def test_a_banked_leg_without_r_has_no_blended_r():
    """A leg written without `r` cannot be weighted: the row says so (None)
    rather than showing the whole position's live R (2.6) as the trade's."""
    plan = golden_plan(legs=[{"fraction": 0.5, "exit_price": 110.0, "reason": "tp1"}])
    runner = priced_rows(plan, open_trade(), 113.0)[-1]
    assert runner["banked_contribution_r"] is None
    assert runner["r_multiple"] is None


def test_an_active_row_keeps_the_whole_position_live_r():
    plan = golden_plan("ACTIVE", legs=[])
    plan["working_stop"] = None
    row = priced_rows(plan, open_trade(), 113.0)[0]
    assert row["r_multiple"] == pytest.approx(2.6)               # (113 - 100) / 5, as today
    assert (row["entry_shares"], row["shares"]) == (100, 100)
    assert row["banked_contribution_r"] is None


def test_a_legacy_row_carries_entry_shares_and_no_banked_contribution():
    trade = {"id": "L1", "ticker": "AAPL", "status": "open", "direction": "bullish",
             "entry": 100.0, "stop_loss": 95.0, "take_profit": 110.0, "shares": 7,
             "opened_at": "2026-09-01T09:00:00+00:00"}
    row = _row_from_trade(trade, set())
    assert (row["entry_shares"], row["banked_contribution_r"]) == (7, None)
