"""v189 D3.2/D3.3 + A2: the admin close of a plan is one transaction.

The plan row is locked first, then the linked trade, then the account (the
plan -> trade -> account order every path uses); the quote and the runner-path
stamp are read before the lock. The plan, the trade, its runner leg on BOTH
stores and the balance point commit together or not at all, and the journal
hook runs only after commit. A plan whose status moved before the lock is a
409 and nothing is written.
"""
import pytest

import swingbot.admin.app  # noqa: F401  (loads the api_v1 package in order)
from swingbot.admin.api_v1 import trade_commands as tc
from swingbot.core.analytics import runner_path as rp
from swingbot.core.db.engine import LockTimeout
from swingbot.core.db.repositories.plans import PlanRepository
from swingbot.core.marketdata.data import PriceQuote
from swingbot.core.planning import account as account_module
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.tracking import performance as perf
from swingbot.core.tracking.performance import TradeLog
from tests.admin.api_v1_contract import assert_error
from tests.admin.test_api_v1_trades import _plan, _trade
from tests.analytics.test_golden_partial_trade_metrics import closed_case, load_golden
from tests.store_seed import seed_store

_LOGIN = {"username": "admin", "password": "admin"}
PLAN_ID = "55555555-5555-4555-8555-555555555555"
TRADE_ID = "bbbbbbbbbbbbbbbb"
G = load_golden()["trade"]
TP1_AT = "2026-08-05T15:00:00+00:00"
MANUAL = closed_case("manual")


def _tp1_leg():
    return {**G["tp1_leg"], "closed_at": TP1_AT}


def _golden_partial_plan():
    return {**_plan(PLAN_ID, ticker=G["ticker"], status="PARTIAL"),
            "entry_price": G["entry"], "stop_loss": G["stop_loss"], "tp1": G["tp1"],
            "tp2": G["tp2"], "tp1_fraction": G["tp1_fraction"], "legs_realized": [_tp1_leg()],
            "status_history": [
                {"status": "ACTIVE", "reason": "stop_entry_fill", "at": "2026-08-04T14:00:00+00:00"},
                {"status": "PARTIAL", "reason": "tp1_partial", "at": TP1_AT}]}


def _golden_open_trade():
    return {**_trade(TRADE_ID, plan_id=PLAN_ID, ticker=G["ticker"]),
            "entry": G["entry"], "stop_loss": G["stop_loss"], "take_profit": G["tp1"],
            "target2": G["tp2"], "shares": G["shares"],
            "position_value": G["shares"] * G["entry"], "legs": [_tp1_leg()]}


@pytest.fixture
def golden(admin_app, monkeypatch):
    """The golden PARTIAL plan and its open trade; the live quote is the
    manual case's runner exit (115) unless a test sets golden["price"]."""
    seed_store("account", {"balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0,
                           "sizing_mode": "risk_pct", "balance_history": []})
    seed_store("plans", [_golden_partial_plan()])
    seed_store("trades", [_golden_open_trade()])
    state = {"price": MANUAL["runner_exit"], "journal": []}

    def detail(*args, **kwargs):
        return None if state["price"] is None else PriceQuote(state["price"], False)

    monkeypatch.setattr("swingbot.core.marketdata.data.get_current_price_detail", detail)
    monkeypatch.setattr("swingbot.core.marketdata.data.get_current_price", lambda *a, **k: None)
    monkeypatch.setattr(rp, "cached_daily_bars", lambda ticker: None)
    monkeypatch.setattr(perf, "_after_close", lambda trade: state["journal"].append(trade["id"]))
    return state


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


def _legs(record):
    return [(leg["fraction"], leg["exit_price"], round(leg["r"], 6), leg["reason"])
            for leg in record]


def test_a_manual_partial_close_writes_the_runner_leg_to_both_stores(golden, logged_in):
    assert logged_in.post(f"/api/v1/trades/{PLAN_ID}/close").status_code == 200
    plan = PlanStore().get(PLAN_ID)
    trade = TradeLog().get_trade_by_id(TRADE_ID)
    assert plan.status == "CLOSED"
    runner = plan.legs_realized[-1]
    assert (runner["fraction"], runner["exit_price"], runner["reason"]) == (0.5, 115.0, "manual")
    assert runner["r"] == pytest.approx(MANUAL["runner_r"])
    assert runner["closed_at"] == plan.status_history[-1]["at"]
    assert _legs(plan.legs_realized) == _legs(trade["legs"])


def test_the_trade_is_labelled_and_settled_with_its_balance_point(golden, logged_in):
    logged_in.post(f"/api/v1/trades/{PLAN_ID}/close")
    trade = TradeLog().get_trade_by_id(TRADE_ID)
    assert trade["status"] == MANUAL["status"]
    assert trade["close_reason"] == "manual (plan close, admin UI)"
    assert trade["realized_pnl_amount"] == pytest.approx(MANUAL["realized_pnl_amount"])
    assert [p["pnl_amount"] for p in account_module.get_balance_history()] == [1250.0]
    assert golden["journal"] == [TRADE_ID], "the journal hook ran once, after commit"


def test_a_failed_plan_write_rolls_the_trade_close_back(golden, monkeypatch):
    def refuse(self, plan, *, conn=None):
        raise RuntimeError("plan row write failed")

    monkeypatch.setattr(PlanStore, "update", refuse)
    store = PlanStore()
    with pytest.raises(RuntimeError):
        tc._close_plan(store, store.get(PLAN_ID))
    assert PlanStore().get(PLAN_ID).status == "PARTIAL"
    trade = TradeLog().get_trade_by_id(TRADE_ID)
    assert trade["status"] == "open" and len(trade["legs"]) == 1
    assert account_module.get_balance_history() == []
    assert golden["journal"] == [], "no hook runs for a rolled-back close"


def test_a_failed_balance_write_leaves_the_plan_open(golden, monkeypatch):
    def refuse(*args, **kwargs):
        raise RuntimeError("account store down")

    monkeypatch.setattr(perf.account_module, "apply_realized_pnl", refuse)
    store = PlanStore()
    with pytest.raises(RuntimeError):
        tc._close_plan(store, store.get(PLAN_ID))
    plan = PlanStore().get(PLAN_ID)
    assert plan.status == "PARTIAL" and len(plan.legs_realized) == 1
    assert TradeLog().get_trade_by_id(TRADE_ID)["status"] == "open"


def test_a_plan_closed_before_the_lock_is_a_409_and_nothing_changes(golden, logged_in,
                                                                      monkeypatch):
    """The bot closes the plan while the admin's stamp quote is in flight."""
    def stamp_while_the_bot_closes(ticker):
        PlanRepository().patch(PLAN_ID, {"status": "CLOSED"})
        return None

    monkeypatch.setattr(tc, "_override_stamp", stamp_while_the_bot_closes)
    assert_error(logged_in.post(f"/api/v1/trades/{PLAN_ID}/close"), "conflict", 409)
    trade = TradeLog().get_trade_by_id(TRADE_ID)
    assert trade["status"] == "open" and len(trade["legs"]) == 1
    assert account_module.get_balance_history() == []


def test_a_lock_timeout_is_a_409(golden, logged_in, monkeypatch):
    def busy(store, plan, reason="manual"):
        raise LockTimeout("plan row held by the bot")

    monkeypatch.setattr(tc, "_close_plan", busy)
    assert_error(logged_in.post(f"/api/v1/trades/{PLAN_ID}/close"), "conflict", 409)


def test_no_quote_closes_both_stores_unpriced(golden, logged_in):
    golden["price"] = None
    assert logged_in.post(f"/api/v1/trades/{PLAN_ID}/close").status_code == 200
    plan = PlanStore().get(PLAN_ID)
    trade = TradeLog().get_trade_by_id(TRADE_ID)
    assert plan.status == "CLOSED" and len(plan.legs_realized) == 1
    assert (trade["status"], len(trade["legs"])) == ("closed", 1)


def test_a_zero_risk_partial_close_leaves_both_stores_with_the_same_legs(golden, logged_in):
    entry = G["entry"]
    seed_store("plans", [{**_golden_partial_plan(), "stop_loss": entry}])
    seed_store("trades", [{**_golden_open_trade(), "stop_loss": entry}])
    assert logged_in.post(f"/api/v1/trades/{PLAN_ID}/close").status_code == 200
    plan = PlanStore().get(PLAN_ID)
    trade = TradeLog().get_trade_by_id(TRADE_ID)
    assert len(plan.legs_realized) == len(trade["legs"]) == 1


def test_the_quote_and_the_daily_bars_are_read_before_a_transaction_opens(golden, logged_in,
                                                                         monkeypatch):
    import threading
    open_on = set()
    real_tx = tc.transaction
    seen = {}

    class Tracked:
        def __init__(self, *a, **k):
            self.cm = real_tx(*a, **k)

        def __enter__(self):
            open_on.add(threading.get_ident())
            return self.cm.__enter__()

        def __exit__(self, *exc):
            try:
                return self.cm.__exit__(*exc)
            finally:
                open_on.discard(threading.get_ident())

    def guard(name, inner):
        def wrapped(*a, **k):
            seen[name] = threading.get_ident() in open_on
            return inner(*a, **k)
        return wrapped

    monkeypatch.setattr(tc, "transaction", Tracked)
    import swingbot.core.marketdata.data as data_module
    monkeypatch.setattr(data_module, "get_current_price_detail",
                        guard("quote", data_module.get_current_price_detail))
    monkeypatch.setattr(rp, "cached_daily_bars", guard("bars", rp.cached_daily_bars))
    assert logged_in.post(f"/api/v1/trades/{PLAN_ID}/close").status_code == 200
    assert seen == {"quote": False, "bars": False}
