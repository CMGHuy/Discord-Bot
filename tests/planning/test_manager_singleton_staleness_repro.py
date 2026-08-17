"""Repro for the 'trade fired by Discord but never shows/updates on the
Dashboard' bug: run_manager_tick()'s module-level `_MANAGER` singleton
snapshots PlanStore() ONCE, on its first tick, and never reloads it. Any
plan added afterward through a fresh PlanStore() instance (exactly what
core/scanning/engine.py:1549 does for every new alert) is invisible to
every later poll() -- and the next unrelated plan's `store.update()` call
overwrites plans.json with the stale in-memory snapshot, erasing the new
plan from disk entirely.

Not a hypothetical: this is the SAME pattern
tests/planning/test_trade_monitor_wiring.py works around by resetting
`pm._MANAGER = None` before every single test.
"""
import swingbot.config as config
from swingbot.core.planning import plan_manager as pm
from swingbot.core.planning.plan_engine import PlanStatus
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.tracking.performance import TradeLog
from tests.planning.test_plan_manager_pending import _pending


def test_plan_added_after_first_tick_is_polled_on_the_next_tick(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "INTRADAY_MANAGER_V2", True)
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    pm._MANAGER = None

    # PlanManager.price_fn is captured once, at construction, by reference --
    # monkeypatching `pm._price_fn` again after tick 1 would silently no-op
    # against the already-built singleton, so route both ticks through one
    # mutable box instead (this is what a real live-price fetch effectively
    # is: the same callable, a different answer each call).
    price = {"v": 100.0}
    monkeypatch.setattr(pm, "_price_fn", lambda t: price["v"])
    monkeypatch.setattr(pm, "_bars_since", lambda ticker, created_at: 0)

    # Tick 1: an older plan exists (price below its trigger: no event) --
    # this is what constructs the singleton and snapshots PlanStore().
    PlanStore().add(_pending(plan_id="old", ticker="AAPL", trigger_price=105.0))
    assert pm.run_manager_tick() == []

    # A NEW alert fires mid-session -- exactly like engine.py's
    # `PlanStore().add(plan_v2)` using its own fresh instance.
    PlanStore().add(_pending(plan_id="new", ticker="MSFT", trigger_price=50.0))
    assert PlanStore().get("new") is not None      # on disk, confirmed

    # Tick 2: price crosses the NEW plan's trigger (and not the old one's).
    # If the manager reloaded current state it would fire a "filled" event
    # for "new".
    price["v"] = 51.0
    events = pm.run_manager_tick()
    assert any(e.plan_id == "new" for e in events), (
        "the plan added after the manager singleton was built was never "
        "polled -- it will never fill, never check SL/TP, and never close, "
        "matching the reported 'stuck' Dashboard trade"
    )


def test_plan_added_after_first_tick_is_not_erased_from_disk(tmp_path, monkeypatch):
    """The sharper failure mode: the OLD plan's own update() call -- e.g. its
    price crossing ITS trigger on this same tick -- calls store._save(),
    which serializes the manager's stale in-memory dict and clobbers
    plans.json, permanently losing the newer plan even though it was
    already durably written to disk a moment earlier."""
    monkeypatch.setattr(config, "INTRADAY_MANAGER_V2", True)
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    pm._MANAGER = None

    price = {"v": 100.0}
    monkeypatch.setattr(pm, "_price_fn", lambda t: price["v"])
    monkeypatch.setattr(pm, "_bars_since", lambda ticker, created_at: 0)

    PlanStore().add(_pending(plan_id="old", ticker="AAPL", trigger_price=105.0))
    assert pm.run_manager_tick() == []

    PlanStore().add(_pending(plan_id="new", ticker="MSFT", trigger_price=50.0))
    assert PlanStore().get("new") is not None

    # This tick fills "old" (its own trigger crossed) -- store.update("old")
    # fires inside poll() and does the clobbering save.
    price["v"] = 999.0
    pm.run_manager_tick()

    assert PlanStore().get("new") is not None, (
        "an unrelated plan's status transition erased a newer plan from "
        "plans.json -- the Discord alert fired but the trade vanished "
        "from the store the Dashboard reads"
    )


def test_legacy_trade_logged_between_ticks_is_not_erased_from_disk(tmp_path, monkeypatch):
    """The trades.json half of the same bug. `_MANAGER.trade_log` (built by
    `run_manager_tick()`) is its OWN `TradeLog()` instance -- a different
    object from the `engine.trade_log` / `commands.scanning.trade_log`
    singleton every legacy/v1 alert actually logs through. A legacy trade
    logged via that shared singleton between two manager ticks must survive
    the manager's own next write to trades.json (e.g. a v2 plan's TP1
    partial), not get silently wiped by a stale in-memory snapshot."""
    monkeypatch.setattr(config, "INTRADAY_MANAGER_V2", True)
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    pm._MANAGER = None

    price = {"v": 106.0}   # crosses "old"'s trigger (105) on tick 1
    monkeypatch.setattr(pm, "_price_fn", lambda t: price["v"])
    monkeypatch.setattr(pm, "_bars_since", lambda ticker, created_at: 0)

    # Tick 1: "old" fills -- constructs _MANAGER, and its OWN trade_log logs
    # the resulting trade (trades.json now has exactly this one row).
    PlanStore().add(_pending(plan_id="old", ticker="AAPL", trigger_price=105.0,
                              tp1=110.0, tp1_fraction=0.5))
    events = pm.run_manager_tick()
    assert [e.transition for e in events] == ["filled"]

    # Between ticks, a plain scan alert logs a legacy trade through what is,
    # in production, the shared `engine.trade_log` singleton -- a fresh
    # instance here, same file.
    TradeLog(path=str(tmp_path / "trades.json")).log_trade(
        ticker="ZZZ", strategy="RSI", horizon_key="2w", direction="bullish",
        confidence_level=1, confidence_label="A", entry=10.0, stop_loss=9.0,
        take_profit=11.0,
    )
    assert len(TradeLog(path=str(tmp_path / "trades.json")).get_trades(limit=None)) == 2

    # Tick 2: "old" taps TP1 -- _MANAGER.trade_log.append_leg_by_plan() fires
    # and saves. Without a reload first, this save serializes only the
    # trade this stale instance already knew about, erasing "ZZZ".
    price["v"] = 111.0
    events = pm.run_manager_tick()
    assert [e.transition for e in events] == ["tp1_partial"]

    trades = TradeLog(path=str(tmp_path / "trades.json")).get_trades(limit=None)
    assert any(t["ticker"] == "ZZZ" for t in trades), (
        "a legacy trade logged between manager ticks was erased from "
        "trades.json by the manager's own next write -- exactly the "
        "'fired by Discord but missing from the Dashboard' report"
    )
