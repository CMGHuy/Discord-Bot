"""Plan v8 Task V4 Step 2: the legacy full-close loops must not close a
v2 plan-linked trade at its target.

A v2 trade is logged with `take_profit = plan.tp1`. Both legacy loops
(`close_if_live_price_hit`, `update_open_trades`) run BEFORE plan_manager's
tick in the same 60s trade_monitor pass, so they used to full-close the
trade as a plain `win` the first time price touched TP1 -- and the manager's
own `tp1_partial` leg then silently no-opped (append_leg_by_plan needs a
still-open trade). Scale-out was dead in the live log and no runner ever
rode to TP2.

The stop side deliberately stays live for these trades as a backstop.
"""
import json
from unittest.mock import patch

import pytest

from swingbot import config
from swingbot.core.performance import TradeLog
from swingbot.core.plan_engine import PlanStatus
from swingbot.core.plan_manager import PlanManager
from swingbot.core.plan_store import PlanStore
from tests.conftest import make_ohlcv
from tests.fake_feed import FakePriceFeed
from tests.test_plan_manager_pending import _pending


def _trade(plan_id=None, direction="bullish"):
    t = {"id": "t1", "ticker": "AAPL", "direction": direction, "status": "open",
         "entry": 100.0, "stop_loss": 95.0, "take_profit": 110.0,
         "opened_at": "2026-07-01T10:00:00+00:00"}
    if direction == "bearish":
        t.update(stop_loss=105.0, take_profit=90.0)
    if plan_id:
        t["plan_id"] = plan_id
    return t


@pytest.fixture
def log_factory(tmp_path, monkeypatch):
    """TradeLog over a tmp trades.json, with the journal write path pinned to
    tmp and off the network (same isolation as test_near_tp_bypass).

    Every plan_id referenced by the trades is also registered as an ACTIVE
    plan in a tmp PlanStore, and the lazily-imported PlanStore is redirected
    to it. That is what makes these trades *manager-owned* rather than merely
    plan-tagged: `manager_owns_target` requires a plan the manager will
    actually poll, because a plan_id pointing at nothing is owned by no one
    (see tests/test_unowned_target_close.py). Without this the fixture
    described a scenario it never built, and silently read the real
    data/plans.json besides."""
    monkeypatch.setattr("swingbot.core.analytics.journal.config.DATA_DIR", str(tmp_path))
    plan_store = PlanStore(path=str(tmp_path / "plans.json"))
    monkeypatch.setattr("swingbot.core.plan_store.PlanStore",
                        lambda *a, **k: plan_store)

    def _make(trades):
        for pid in {t["plan_id"] for t in trades if t.get("plan_id")}:
            plan_store.add(_pending(plan_id=pid, status=PlanStatus.ACTIVE))
        path = tmp_path / "trades.json"
        path.write_text(json.dumps(trades))
        return TradeLog(path=str(path))

    return _make


# -- live-price path (trade_monitor's 60s tick) ----------------------------

def test_live_price_at_tp1_leaves_manager_owned_trade_open(log_factory, monkeypatch):
    monkeypatch.setattr(config, "INTRADAY_MANAGER_V2", True)
    log = log_factory([_trade(plan_id="p1")])
    with patch("swingbot.core.data.get_daily_data", return_value=None):
        assert log.close_if_live_price_hit("AAPL", live_price=111.0) == []
    assert log._trades[0]["status"] == "open"   # TP1 is the manager's call


def test_live_price_at_tp1_still_closes_legacy_trade(log_factory, monkeypatch):
    monkeypatch.setattr(config, "INTRADAY_MANAGER_V2", True)
    log = log_factory([_trade()])               # no plan_id
    with patch("swingbot.core.data.get_daily_data", return_value=None):
        closed = log.close_if_live_price_hit("AAPL", live_price=111.0)
    assert [t["status"] for t in closed] == ["win"]


def test_manager_off_still_closes_plan_trade_at_tp1(log_factory, monkeypatch):
    """With the manager off nothing else watches TP1 -- handing the target
    over then would strand the trade open forever."""
    monkeypatch.setattr(config, "INTRADAY_MANAGER_V2", False)
    log = log_factory([_trade(plan_id="p1")])
    with patch("swingbot.core.data.get_daily_data", return_value=None):
        closed = log.close_if_live_price_hit("AAPL", live_price=111.0)
    assert [t["status"] for t in closed] == ["win"]


def test_stop_backstop_still_fires_for_manager_owned_trade(log_factory, monkeypatch):
    monkeypatch.setattr(config, "INTRADAY_MANAGER_V2", True)
    log = log_factory([_trade(plan_id="p1")])
    with patch("swingbot.core.data.get_daily_data", return_value=None):
        closed = log.close_if_live_price_hit("AAPL", live_price=94.0)
    assert [t["status"] for t in closed] == ["loss"]


def test_bearish_manager_owned_target_also_handed_over(log_factory, monkeypatch):
    monkeypatch.setattr(config, "INTRADAY_MANAGER_V2", True)
    log = log_factory([_trade(plan_id="p1", direction="bearish")])
    with patch("swingbot.core.data.get_daily_data", return_value=None):
        assert log.close_if_live_price_hit("AAPL", live_price=89.0) == []
        closed = log.close_if_live_price_hit("AAPL", live_price=106.0)
    assert [t["status"] for t in closed] == ["loss"]     # stop side unchanged


# -- bar path (inside the full scan) ---------------------------------------

def _bars(closes):
    return make_ohlcv(closes, spread_pct=4.0, start="2026-07-02")


def test_bar_scan_does_not_close_manager_owned_trade_at_target(log_factory, monkeypatch):
    monkeypatch.setattr(config, "INTRADAY_MANAGER_V2", True)
    log = log_factory([_trade(plan_id="p1")])
    with patch("swingbot.core.data.get_daily_data", return_value=None):
        assert log.update_open_trades("AAPL", _bars([112.0, 113.0])) == []
    assert log._trades[0]["status"] == "open"


def test_bar_scan_still_closes_legacy_trade_at_target(log_factory, monkeypatch):
    monkeypatch.setattr(config, "INTRADAY_MANAGER_V2", True)
    log = log_factory([_trade()])
    with patch("swingbot.core.data.get_daily_data", return_value=None):
        closed = log.update_open_trades("AAPL", _bars([112.0, 113.0]))
    assert [t["status"] for t in closed] == ["win"]


def test_bar_scan_stop_backstop_still_fires(log_factory, monkeypatch):
    monkeypatch.setattr(config, "INTRADAY_MANAGER_V2", True)
    log = log_factory([_trade(plan_id="p1")])
    with patch("swingbot.core.data.get_daily_data", return_value=None):
        closed = log.update_open_trades("AAPL", _bars([93.0]))
    assert [t["status"] for t in closed] == ["loss"]


# -- the race itself, in trade_monitor's real order ------------------------

def test_tp1_partial_survives_the_legacy_check_in_the_same_tick(tmp_path, monkeypatch):
    """One trade_monitor tick: legacy SL/TP check first, then the manager --
    the exact order commands/scanning.py:trade_monitor runs them in. The TP1
    leg must land on the trade, and the runner must still be open."""
    monkeypatch.setattr(config, "INTRADAY_MANAGER_V2", True)
    monkeypatch.setattr("swingbot.core.analytics.journal.config.DATA_DIR", str(tmp_path))

    feed = FakePriceFeed()
    feed.set_series("AAPL", [106.0, 116.0])   # fill (trigger 105), then TP1 (110)
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(_pending(tp1=110.0, tp2=125.0))
    log = TradeLog(path=str(tmp_path / "trades.json"))
    mgr = PlanManager(store, feed.get_price, atr_fn=lambda t: 2.0, trade_log=log)

    assert [e.transition for e in mgr.poll()] == ["filled"]

    with patch("swingbot.core.data.get_daily_data", return_value=None):
        assert log.close_if_live_price_hit("AAPL", live_price=116.0) == []
        assert [e.transition for e in mgr.poll()] == ["tp1_partial"]

    log.refresh()
    [t] = [t for t in log.get_trades(status=None, limit=10) if t.get("plan_id") == "p1"]
    assert t["status"] == "open"                        # runner still riding
    assert [l["reason"] for l in t["legs"]] == ["tp1"]
    assert t["legs"][0]["fraction"] < 1.0               # partial, not the whole position
