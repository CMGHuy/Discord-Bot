"""V183-7: a paper short gapped through its stop books the R of its real fill
(-2.4R here), never a clamped -1R; the gap cut halves the dollars, not the R."""
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.analytics.metrics import r_multiple
from swingbot.core.planning import account
from swingbot.core.planning.plan_manager import PlanEvent, PlanManager
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.planning.plan_types import PlanStatus
from swingbot.core.tracking.performance import TradeLog, settle_legs
from tests.planning.test_plan_engine_model import _plan
from tests.store_seed import seed_store

STAMP = {"rule": "gap_p99", "up_gap_p99_pct": 4.0, "n_up_gaps": 120}
STOP_STAMP = {"rule": "stop", "up_gap_p99_pct": 4.0, "n_up_gaps": 120}


@pytest.fixture
def tlog(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "MAX_POSITION_VALUE_ABSOLUTE", 0.0)
    monkeypatch.setattr(config, "MAX_RISK_AMOUNT_ABSOLUTE", 0.0)
    monkeypatch.setattr(account.opex, "size_mult", lambda *a, **k: 1.0)
    seed_store("account", {"balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 100.0,
                           "sizing_mode": "risk_pct", "balance_history": []})
    return TradeLog()


def _gap_bar():
    """Tomorrow's bar (after the trade's opened_at), opening 104.80 over a 102 stop."""
    day = (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    return pd.DataFrame({"Open": [104.8], "High": [105.5], "Low": [104.0], "Close": [105.0]},
                        index=pd.DatetimeIndex([day]))


def _log_short(tlog, ticker, stamp, plan_id=None):
    trade_id = tlog.log_trade(
        ticker=ticker, strategy="Bear Flag", horizon_key="4w", direction="bearish",
        confidence_level=3, confidence_label="Medium", entry=100.0, stop_loss=102.0,
        take_profit=96.0, plan_id=plan_id, gap_sizing=stamp)
    return trade_id


def _closed(tlog, trade_id):
    return next(t for t in tlog.get_trades(status=None, limit=None) if t["id"] == trade_id)


def test_a_short_gapped_through_its_stop_books_its_real_r(tlog):
    trade_id = _log_short(tlog, "TSLA", STAMP)
    tlog.update_open_trades("TSLA", _gap_bar(), live_price=None)
    record = _closed(tlog, trade_id)
    assert record["status"] == "loss"
    assert record["exit_price"] == pytest.approx(104.8)
    assert r_multiple(record) == pytest.approx(-2.4)
    assert record["shares"] == 25.0
    assert record["realized_pnl_amount"] == pytest.approx(-120.0, abs=0.01)


def test_the_gap_cut_halves_the_dollar_loss_not_the_r(tlog):
    cut = _log_short(tlog, "TSLA", STAMP)
    plain = _log_short(tlog, "NIO", STOP_STAMP)
    tlog.update_open_trades("TSLA", _gap_bar(), live_price=None)
    tlog.update_open_trades("NIO", _gap_bar(), live_price=None)
    cut_rec, plain_rec = _closed(tlog, cut), _closed(tlog, plain)
    assert r_multiple(cut_rec) == pytest.approx(r_multiple(plain_rec)) == pytest.approx(-2.4)
    assert plain_rec["realized_pnl_amount"] == pytest.approx(-240.0, abs=0.01)
    assert cut_rec["realized_pnl_amount"] == pytest.approx(-120.0, abs=0.01)


def test_a_plan_linked_short_closed_past_its_stop_books_its_real_r(tlog):
    plan = _plan(plan_id="s1", ticker="TSLA", direction="bearish", trigger_price=100.0,
                 entry_price=100.0, stop_loss=102.0, tp1=96.0, tp2=92.0,
                 status=PlanStatus.ACTIVE, gap_sizing=STAMP)
    _log_short(tlog, "TSLA", STAMP, plan_id="s1")
    store = PlanStore()
    store.add(plan)
    mgr = PlanManager(store, lambda *a, **k: None, trade_log=tlog)
    mgr._on_event(store.get("s1"), PlanEvent("s1", "closed", {
        "reason": "loss", "exit_price": 104.8, "session": "regular", "_terminal_persisted": False}))
    record = tlog.trade_for_plan("s1")
    assert record["status"] == "loss"
    assert r_multiple(record) == pytest.approx(-2.4)
    assert record["realized_pnl_amount"] == settle_legs(record)
    assert record["realized_pnl_amount"] == pytest.approx(-120.0, abs=0.01)
