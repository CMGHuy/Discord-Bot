"""v189 D2 on the manual-close path, and close_trade_manual's transaction mode.

A manual close that leaves two or more realized legs (TP1 banked, then the
runner closed by hand) is labelled by the sign of its unrounded blended net R:
win above +0.01R, loss below -0.01R, closed/scratch inside, closed/unscored
when the net cannot be computed. A close that leaves one leg or none keeps
today's `closed` exactly. With `conn=` the close joins the caller's
transaction: no quote is fetched, the balance point rolls back with it, and
the journal/snapshot hooks wait for `after_commit`.
"""
import logging
import math

import pytest

from swingbot.core.analytics import metrics
from swingbot.core.db.engine import transaction
from swingbot.core.planning import account as account_module
from swingbot.core.tracking import performance as perf
from swingbot.core.tracking.performance import TradeLog, run_after_commit
from tests.admin.test_api_v1_trades import _trade
from tests.analytics.test_golden_partial_trade_metrics import closed_case, load_golden
from tests.store_seed import seed_store

G = load_golden()["trade"]
LABELS = load_golden()["label_table"]


def _golden_open(trade_id="t1", tp1_r=None):
    leg = dict(G["tp1_leg"])
    if tp1_r is not None:
        leg["r"] = tp1_r
    return {"id": trade_id, "ticker": G["ticker"], "status": "open",
            "direction": G["direction"], "entry": G["entry"], "stop_loss": G["stop_loss"],
            "shares": G["shares"], "legs": [leg]}


def _price_for_net(net_r: float) -> float:
    """The runner exit that gives the golden trade a blended net R of `net_r`."""
    tp1 = G["tp1_leg"]["fraction"] * G["tp1_leg"]["r"]
    runner_r = (net_r - tp1) / (1.0 - G["tp1_fraction"])
    return G["entry"] + runner_r * G["risk_per_share"]


@pytest.fixture
def book(monkeypatch):
    """In-memory trades table; no account, journal, snapshot or network."""
    state = {"rows": [_golden_open()], "upserts": []}
    monkeypatch.setattr(TradeLog, "_all", lambda self: state["rows"])
    monkeypatch.setattr(TradeLog, "_db_upsert",
                        staticmethod(lambda trade, conn=None: state["upserts"].append(dict(trade))))
    monkeypatch.setattr(TradeLog, "_settle_account_balance", lambda self, trade: None)
    monkeypatch.setattr(perf, "_after_close", lambda trade: None)
    monkeypatch.setattr(perf, "_refresh_snapshot_safely", lambda: None)
    monkeypatch.setattr("swingbot.core.marketdata.data.get_current_price", lambda *a, **k: None)
    return state


@pytest.mark.parametrize("row", LABELS, ids=[str(r["net_r"]) for r in LABELS])
def test_a_scaled_out_manual_close_is_labelled_by_net_r(book, row):
    assert TradeLog().close_trade_manual(
        "t1", reason="manual (admin UI)", exit_price=_price_for_net(row["net_r"])) is True
    trade = book["rows"][0]
    assert len(trade["legs"]) == 2
    assert metrics._blended_r_raw(trade) == pytest.approx(row["net_r"], abs=1e-9)
    assert trade["status"] == row["status"]
    assert trade["close_reason"] == (row["close_reason"] or "manual (admin UI)")


def test_the_golden_manual_close_is_a_win_at_2_5r(book):
    case = closed_case("manual")
    TradeLog().close_trade_manual("t1", exit_price=case["runner_exit"])
    trade = book["rows"][0]
    assert trade["legs"][-1]["r"] == pytest.approx(case["runner_r"])
    assert metrics.r_multiple(trade) == pytest.approx(case["net_r"])
    assert (trade["status"], trade["close_reason"]) == ("win", "manual")


def test_a_single_leg_manual_close_keeps_todays_closed_label(book):
    """An unscaled ACTIVE trade closed by hand at a loss is still `closed`:
    D2 relabels only closes with two or more realized legs."""
    book["rows"] = [{**_golden_open(), "legs": []}]
    TradeLog().close_trade_manual("t1", reason="manual (admin UI)", exit_price=90.0)
    trade = book["rows"][0]
    assert (trade["status"], trade["close_reason"]) == ("closed", "manual (admin UI)")
    assert trade["exit_price"] == pytest.approx(90.0)


def test_a_partial_closed_without_a_price_stays_one_leg_and_closed(book):
    TradeLog().close_trade_manual("t1", reason="manual (admin UI)")
    trade = book["rows"][0]
    assert len(trade["legs"]) == 1
    assert (trade["status"], trade["close_reason"]) == ("closed", "manual (admin UI)")


def test_a_nan_price_is_no_price(book):
    """`if price:` let NaN through (NaN is truthy) and wrote a NaN leg."""
    TradeLog().close_trade_manual("t1", exit_price=float("nan"))
    trade = book["rows"][0]
    assert len(trade["legs"]) == 1
    assert trade.get("exit_price") is None
    assert trade["status"] == "closed"


def test_an_uncomputable_net_is_unscored_with_a_warning(book, caplog):
    book["rows"] = [_golden_open(tp1_r=float("nan"))]
    with caplog.at_level(logging.WARNING):
        TradeLog().close_trade_manual("t1", reason="manual (admin UI)", exit_price=115.0)
    trade = book["rows"][0]
    assert (trade["status"], trade["close_reason"]) == ("closed", "unscored")
    assert any("t1" in record.getMessage() for record in caplog.records)


# --- transaction mode (real database) --------------------------------------------

TRADE_ID = "bbbbbbbbbbbbbbbb"


@pytest.fixture
def db_book(monkeypatch):
    """The golden PARTIAL trade (TP1 banked) open in the database. Returns
    the list the journal and snapshot hooks append to."""
    def no_fetch(*args, **kwargs):
        raise AssertionError("no quote may be fetched inside a transaction")

    monkeypatch.setattr("swingbot.core.marketdata.data.get_current_price", no_fetch)
    seed_store("account", {"balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0,
                           "sizing_mode": "risk_pct", "balance_history": []})
    seed_store("trades", [{**_trade(TRADE_ID, ticker=G["ticker"]), "entry": G["entry"],
                           "stop_loss": G["stop_loss"], "shares": G["shares"],
                           "legs": [dict(G["tp1_leg"])]}])
    journal = []
    monkeypatch.setattr(perf, "_after_close", lambda trade: journal.append(trade["id"]))
    monkeypatch.setattr(perf, "_refresh_snapshot_safely", lambda: journal.append("snapshot"))
    return journal


def test_inside_a_transaction_the_hooks_wait_for_commit(db_book):
    hooks = []
    with transaction() as tx:
        assert TradeLog().close_trade_manual(
            TRADE_ID, reason="manual (plan close, admin UI)",
            exit_price=closed_case("manual")["runner_exit"], conn=tx, after_commit=hooks) is True
        assert db_book == []
    assert db_book == []
    run_after_commit(hooks)
    assert db_book == [TRADE_ID, "snapshot"]
    trade = TradeLog().get_trade_by_id(TRADE_ID)
    assert trade["status"] == "win"
    assert trade["realized_pnl_amount"] == pytest.approx(closed_case("manual")["realized_pnl_amount"])
    points = account_module.get_balance_history()
    assert [round(p["pnl_amount"], 2) for p in points] == [1250.0]


def test_a_rolled_back_manual_close_leaves_no_trace(db_book):
    with pytest.raises(RuntimeError):
        with transaction() as tx:
            TradeLog().close_trade_manual(TRADE_ID, exit_price=115.0, conn=tx, after_commit=[])
            raise RuntimeError("the plan write after it failed")
    trade = TradeLog().get_trade_by_id(TRADE_ID)
    assert trade["status"] == "open" and len(trade["legs"]) == 1
    assert account_module.get_balance_history() == []
    assert db_book == []


def test_no_quote_is_fetched_inside_a_transaction(db_book):
    with transaction() as tx:
        TradeLog().close_trade_manual(TRADE_ID, exit_price=None, conn=tx, after_commit=[])
    trade = TradeLog().get_trade_by_id(TRADE_ID)
    assert (trade["status"], len(trade["legs"])) == ("closed", 1)


def test_an_already_closed_trade_is_untouched_in_a_transaction(db_book):
    with transaction() as tx:
        TradeLog().close_trade_manual(TRADE_ID, exit_price=115.0, conn=tx, after_commit=[])
    with transaction() as tx:
        assert TradeLog().close_trade_manual(TRADE_ID, exit_price=120.0, conn=tx,
                                             after_commit=[]) is False
    assert TradeLog().get_trade_by_id(TRADE_ID)["exit_price"] == pytest.approx(115.0)
    assert math.isclose(account_module.get_balance_history()[-1]["pnl_amount"], 1250.0)
