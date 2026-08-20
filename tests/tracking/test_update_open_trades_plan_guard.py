"""Root-cause regression: TP1 -> PARTIAL trades were being closed a second
time (and wrongly) by the legacy per-bar SL/TP scanner before the real v2
runner close (TP2 or trailing stop) ever got a chance to fire.

update_open_trades() only ever knows a trade's ORIGINAL stop_loss/take_profit
(snapshotted once at log_trade() time) -- it never learns about a v2 plan's
break-even stop move or its TP2 target. Once TP1 fires, live price sits at or
above that stale take_profit, so the very next scan re-triggers hit_target
and closes the trade early -- silently swallowing the real runner leg, since
close_plan_trade() can no longer find an "open" trade to attach it to.
"""
import json

import pandas as pd

from swingbot.core.tracking.performance import TradeLog


def _bars(rows):
    idx = pd.to_datetime([r[0] for r in rows])
    return pd.DataFrame(
        {"Open": [r[1] for r in rows], "High": [r[2] for r in rows],
         "Low": [r[3] for r in rows], "Close": [r[4] for r in rows]},
        index=idx,
    )


def _trade(plan_id=None, *, stop_loss=95.0, take_profit=110.0):
    t = {"id": "t1", "ticker": "AAPL", "direction": "bullish", "status": "open",
         "entry": 100.0, "stop_loss": stop_loss, "take_profit": take_profit,
         "opened_at": "2026-07-01T10:00:00+00:00", "shares": 10}
    if plan_id:
        t["plan_id"] = plan_id
    return t


def test_manager_owned_partial_trade_is_not_closed_by_the_legacy_scanner(tmp_path):
    """The runner is still open (working_stop=BE, real target=TP2), but the
    trade record's stale take_profit still reads TP1 (110) -- a bar that
    revisits/exceeds that level must not close the trade out from under
    plan_manager."""
    path = tmp_path / "trades.json"
    path.write_text(json.dumps([_trade(plan_id="p1")]))
    log = TradeLog(path=str(path))

    df = _bars([("2026-07-02", 111.0, 112.0, 110.5, 111.5)])  # revisits old TP1
    closed = log.update_open_trades("AAPL", df, live_price=111.5)

    assert closed == []
    reloaded = json.loads(path.read_text())
    assert reloaded[0]["status"] == "open"     # plan_manager still owns this


def test_legacy_trade_still_closes_on_target_hit(tmp_path):
    """Unguarded (no plan_id): the legacy single-target close path is
    unchanged."""
    path = tmp_path / "trades.json"
    path.write_text(json.dumps([_trade()]))
    log = TradeLog(path=str(path))

    df = _bars([("2026-07-02", 111.0, 112.0, 110.5, 111.5)])
    closed = log.update_open_trades("AAPL", df, live_price=111.5)

    assert len(closed) == 1
    assert closed[0]["status"] == "win"
