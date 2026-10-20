"""v172 § 0: one equity definition, `swingbot/core/tracking/equity.py`.

Hand-computed throughout. The PARTIAL fixture is 10 shares bought at 100;
TP1 banks half (5 shares) at 110 = +50, leaving 5 shares open.
"""
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from swingbot.core.analytics import metrics
from swingbot.core.tracking import equity

UTC = timezone.utc
TP1_AT = "2026-08-03T15:00:00+00:00"
TP1 = {"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1", "closed_at": TP1_AT}


def _trade(trade_id="t1", *, ticker="AAPL", status="open", legs=(), pnl=None, closed_at=None,
           exit_price=None, shares=10, entry=100.0, direction="bullish", plan_id=None,
           ledger="main", opened_at="2026-08-01T14:00:00+00:00", origin=None):
    trade = {"id": trade_id, "ticker": ticker, "direction": direction, "status": status,
             "entry": entry, "stop_loss": 95.0, "exit_price": exit_price, "shares": shares,
             "realized_pnl_amount": pnl, "opened_at": opened_at, "closed_at": closed_at,
             "legs": list(legs), "plan_id": plan_id, "ledger": ledger}
    if origin is not None:
        trade["origin"] = origin
    return trade


def _closed(trade_id, pnl, closed_at, **kw):
    return _trade(trade_id, status="win" if pnl >= 0 else "loss", pnl=pnl, closed_at=closed_at,
                  exit_price=100.0 + pnl / 10, **kw)


def _at(text):
    return datetime.fromisoformat(text)


# --- moved helpers: same behaviour, same objects in the admin ---------------

def test_open_shares_is_the_remaining_fraction_of_the_original_size():
    assert equity.open_shares(10, []) == 10.0
    assert equity.open_shares(10, [{"fraction": 0.5}]) == 5.0
    assert equity.open_shares(10, [{"fraction": 0.7}, {"fraction": 0.6}]) == 0.0
    assert equity.open_shares(None, [{"fraction": 0.5}]) is None


def test_unrealized_pnl_amount_keeps_its_formula():
    assert equity.unrealized_pnl_amount(100.0, "bullish", 5, 110.0) == 50.0
    assert equity.unrealized_pnl_amount(100.0, "bearish", 5, 110.0) == -50.0
    assert equity.unrealized_pnl_amount(100.0, "bullish", 0, 110.0) is None
    assert equity.unrealized_pnl_amount(None, "bullish", 5, 110.0) is None
    assert equity.unrealized_pnl_amount(100.0, "bullish", 5, None) is None


def test_the_admin_re_imports_the_core_helpers():
    import swingbot.admin.app  # noqa: F401  (initialises api_v1 routes; a cold api_v1 import cycles)
    from swingbot.admin import dashboard as dash
    from swingbot.admin.api_v1 import trades

    assert dash.unrealized_pnl_amount is equity.unrealized_pnl_amount
    assert trades._open_shares is equity.open_shares


def test_unrealized_decimal_is_exact_to_the_cent():
    # 3 x (100.35 - 100.1) is 0.7499999... in floats, exactly 0.75 in Decimal.
    assert equity.unrealized_decimal(100.1, "bullish", 3, 100.35) == Decimal("0.75")
    assert equity.unrealized_decimal(100.1, "bearish", 3, 100.35) == Decimal("-0.75")
    assert equity.unrealized_decimal(100.0, "bullish", None, 101.0) is None


def test_unrealized_decimal_rounds_to_the_admin_amount():
    exact = equity.unrealized_decimal(101.37, "bullish", 7.5, 104.91)
    assert float(exact.quantize(equity.CENT)) == equity.unrealized_pnl_amount(
        101.37, "bullish", 7.5, 104.91)


# --- parsing ------------------------------------------------------------------

def test_parse_ts_returns_tz_aware_utc():
    assert equity.parse_ts("2026-08-03T15:00:00+00:00") == datetime(2026, 8, 3, 15, tzinfo=UTC)
    assert equity.parse_ts("2026-08-03T11:00:00-04:00") == datetime(2026, 8, 3, 15, tzinfo=UTC)
    assert equity.parse_ts("2026-08-03T15:00:00") == datetime(2026, 8, 3, 15, tzinfo=UTC)
    assert equity.parse_ts(datetime(2026, 8, 3, 15)) == datetime(2026, 8, 3, 15, tzinfo=UTC)
    assert equity.parse_ts(None) is None
    assert equity.parse_ts("not a time") is None


def test_to_decimal_goes_through_str():
    assert equity.to_decimal(0.1) == Decimal("0.1")
    assert equity.to_decimal(None) is None
    assert equity.to_decimal(Decimal("2.50")) == Decimal("2.50")


# --- realized walk ------------------------------------------------------------

def test_a_partial_trades_banked_tp1_leg_is_realized_at_its_own_time():
    legs = equity.realized_legs([_trade(legs=[TP1], plan_id="P1")])
    assert legs == [equity.RealizedLeg(at=_at(TP1_AT), amount=Decimal("50.0"), trade_id="t1")]


def test_legs_are_sorted_by_time_across_trades():
    trades = [_closed("late", 20.0, "2026-08-05T19:00:00+00:00"),
              _closed("early", -30.0, "2026-08-02T19:00:00+00:00")]
    assert [leg.trade_id for leg in equity.realized_legs(trades)] == ["early", "late"]


def test_weak_and_outlook_trades_never_enter_the_realized_walk():
    trades = [_closed("main", 10.0, "2026-08-02T19:00:00+00:00"),
              _closed("weak", 99.0, "2026-08-02T19:00:00+00:00", ledger="weak"),
              _closed("outlook", 77.0, "2026-08-02T19:00:00+00:00", origin="next_session")]
    assert [leg.trade_id for leg in equity.realized_legs(trades)] == ["main"]


def test_a_leg_with_no_amount_or_no_close_time_is_skipped():
    unsized = _trade("unsized", status="win", pnl=None, closed_at="2026-08-02T19:00:00+00:00",
                     exit_price=105.0, shares=None)
    undated = _closed("undated", 10.0, None)
    assert equity.realized_legs([unsized, undated]) == []


def test_realized_balance_counts_legs_at_or_before_t():
    legs = equity.realized_legs([_closed("a", 10.0, "2026-08-02T19:00:00+00:00"),
                                 _closed("b", -4.0, "2026-08-03T19:00:00+00:00")])
    start = Decimal("1000")
    assert equity.realized_balance_at(start, legs, _at("2026-08-02T18:59:59+00:00")) == Decimal("1000")
    assert equity.realized_balance_at(start, legs, _at("2026-08-02T19:00:00+00:00")) == Decimal("1010.0")
    assert equity.realized_balance_at(start, legs, _at("2026-08-09T00:00:00+00:00")) == Decimal("1006.0")


def test_decimal_sums_match_to_the_cent():
    trades = [_closed("a", 0.1, "2026-08-02T19:00:00+00:00"),
              _closed("b", 0.2, "2026-08-02T20:00:00+00:00")]
    total = equity.realized_balance_at(Decimal("0"), equity.realized_legs(trades),
                                       _at("2026-08-03T00:00:00+00:00"))
    assert total == Decimal("0.3")


def test_the_walk_ends_where_the_existing_equity_curve_ends():
    closed = [_closed("a", 12.5, "2026-08-02T19:00:00+00:00"),
              _closed("b", -7.25, "2026-08-04T19:00:00+00:00"),
              _closed("c", 30.0, "2026-08-06T19:00:00+00:00")]
    curve = metrics.equity_curve(closed, 1000.0)
    walk = equity.realized_balance_at(Decimal("1000"), equity.realized_legs(closed),
                                      _at("2026-09-01T00:00:00+00:00"))
    assert float(walk) == pytest.approx(curve["points"][-1]["balance"])


# --- open positions -----------------------------------------------------------

def test_open_positions_follow_the_dashboard_plan_filter():
    trades = [_trade("legacy"),                                     # no plan -> kept as is
              _trade("pending", plan_id="PP"),                      # PENDING placeholder -> dropped
              _trade("partial", plan_id="PA", legs=[TP1]),          # PARTIAL -> remaining shares
              _trade("weak", ledger="weak"),                        # weak ledger -> dropped
              _closed("closed", 5.0, "2026-08-02T19:00:00+00:00")]  # not open -> dropped
    plans = {"PP": {"plan_id": "PP", "status": "PENDING"},
             "PA": {"plan_id": "PA", "status": "PARTIAL", "legs_realized": [TP1]}}
    live = equity.live_open_positions(trades, plans)
    assert [(p["id"], p["shares"]) for p in live] == [("legacy", 10), ("partial", 5.0)]


def test_held_now_is_the_plan_filter_alone():
    trades = [_trade("weak", ledger="weak", plan_id="PA")]
    plans = {"PA": {"plan_id": "PA", "status": "ACTIVE", "legs_realized": []}}
    assert [p["id"] for p in equity.held_now(trades, plans)] == ["weak"]


# --- snapshot -----------------------------------------------------------------

def _partial_book():
    trade = _trade("partial", plan_id="PA", legs=[TP1])
    plans = {"PA": {"plan_id": "PA", "status": "PARTIAL", "legs_realized": [TP1]}}
    return [trade], plans


def test_snapshot_realizes_the_tp1_leg_and_prices_only_the_runner():
    trades, plans = _partial_book()
    snap = equity.snapshot_at(trades, plans, {"AAPL": 112.0}, _at("2026-08-03T16:00:00+00:00"),
                              Decimal("1000"))
    assert snap == equity.EquitySnapshot(realized_balance=Decimal("1050.0"),
                                         unrealized_pnl=Decimal("60.00"),
                                         equity=Decimal("1110.00"), open_n=1, skipped_n=0)


def test_mark_to_market_does_not_dip_at_tp1():
    before_trade = _trade("partial", plan_id="PA")
    before_plans = {"PA": {"plan_id": "PA", "status": "ACTIVE", "legs_realized": []}}
    before = equity.snapshot_at([before_trade], before_plans, {"AAPL": 110.0},
                                _at("2026-08-03T14:59:00+00:00"), Decimal("1000"))
    trades, plans = _partial_book()
    after = equity.snapshot_at(trades, plans, {"AAPL": 110.0},
                               _at("2026-08-03T15:01:00+00:00"), Decimal("1000"))
    assert before.equity == after.equity == Decimal("1100.00")


def test_unpriced_and_unsized_positions_are_skipped_never_priced_at_zero():
    trades = [_trade("priced", ticker="AAPL"),
              _trade("unpriced", ticker="MSFT"),
              _trade("unsized", ticker="NVDA", shares=None)]
    snap = equity.snapshot_at(trades, {}, {"AAPL": 101.0, "NVDA": 120.0, "MSFT": 0.0},
                              _at("2026-08-03T16:00:00+00:00"), Decimal("1000"))
    assert (snap.unrealized_pnl, snap.open_n, snap.skipped_n) == (Decimal("10.00"), 1, 2)
    assert snap.equity == Decimal("1010.00")


def test_a_weak_open_position_is_never_summed_with_the_main_book():
    trades = [_trade("main"), _trade("weak", ticker="MSFT", ledger="weak")]
    snap = equity.snapshot_at(trades, {}, {"AAPL": 101.0, "MSFT": 200.0},
                              _at("2026-08-03T16:00:00+00:00"), Decimal("0"))
    assert (snap.unrealized_pnl, snap.open_n, snap.skipped_n) == (Decimal("10.00"), 1, 0)


# --- I/O seams ----------------------------------------------------------------

def test_starting_balance_is_the_account_base_balance(monkeypatch):
    monkeypatch.setattr("swingbot.core.planning.account.load_account_config",
                        lambda: {"base_balance": 2500.5})
    assert equity.starting_balance() == Decimal("2500.5")


def test_starting_balance_defaults_to_zero(monkeypatch):
    monkeypatch.setattr("swingbot.core.planning.account.load_account_config", lambda: {})
    assert equity.starting_balance() == Decimal("0.0")


def test_plans_are_keyed_by_plan_id(monkeypatch):
    from swingbot.core.planning.plan_store import PlanStore

    monkeypatch.setattr(PlanStore, "records", lambda self: [{"plan_id": "P1", "status": "ACTIVE"}])
    assert equity.load_plans_by_id() == {"P1": {"plan_id": "P1", "status": "ACTIVE"}}
