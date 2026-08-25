"""close_if_live_price_hit -- the 60s trade_monitor's fast SL/TP check.

It predates plan-engine v2 and was never updated for it, leaving it the only
close path that disagrees with its two siblings on both of the conventions
they document:

  * `update_open_trades` (performance.py:622) excludes `plan_id` trades and
    `check_near_tp_timeout` (:1230) skips them, because a v2 trade record's
    take_profit/stop_loss are frozen at log_trade time and never updated
    after TP1 -- run_manager_tick owns those. tests/test_trade_monitor_task.py
    asserts in as many words that run_manager_tick is "the ONLY code path
    that monitors plan_id-linked trades' SL/TP".
  * `update_open_trades` (:683-695) fills at the observed `live_price`, "not
    the nominal stop/target level ... it's a real price we actually saw, not
    a theoretical perfect fill".
"""
import pytest

from swingbot import config
from swingbot.core.tracking.performance import TradeLog


def _log(log, **over):
    kwargs = dict(ticker="AAPL", strategy="RSI", horizon_key="4w",
                  direction="bullish", confidence_level=4,
                  confidence_label="Strong", entry=100.0,
                  stop_loss=95.0, take_profit=110.0)
    kwargs.update(over)
    return log.log_trade(**kwargs)


@pytest.fixture
def log(tmp_path, monkeypatch):
    # DATA_DIR too: _settle_account_balance -> apply_realized_pnl writes
    # account.json with no path=, and parallel workers racing the real file
    # is a documented past failure (tests/planning/test_account_legs.py).
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    return TradeLog(path=str(tmp_path / "trades.json"))


def test_plan_linked_trades_are_left_to_the_plan_manager(log):
    """Closing a v2 trade here books the FULL position at TP1 and clears the
    runner: the later tp1_partial event finds no open trade (silent no-op),
    and so does the eventual close_plan_trade. The whole scale-out mechanism
    -- TP1 fraction plus runner TP2/trail -- never reaches trades.json or the
    account for any plan-linked trade."""
    _log(log, plan_id="p-1")

    assert log.close_if_live_price_hit("AAPL", 111.0) == []
    assert log.get_trades(limit=None)[0]["status"] == "open"


def test_exit_price_is_the_price_actually_observed_not_the_nominal_stop(log):
    """Recording the nominal stop re-introduces the fake -1.00 R the gap-fill
    handling elsewhere removed. Because this runs every 60s while a scan takes
    minutes, it wins the race on essentially every non-plan trade, so losses
    are systematically truncated at the stop and expectancy is inflated."""
    _log(log)

    closed = log.close_if_live_price_hit("AAPL", 88.0)   # gapped through 95.0

    assert len(closed) == 1
    assert closed[0]["status"] == "loss"
    assert closed[0]["exit_price"] == pytest.approx(88.0)


def test_a_normal_target_hit_still_closes_at_the_observed_price(log):
    _log(log)

    closed = log.close_if_live_price_hit("AAPL", 112.5)

    assert len(closed) == 1
    assert closed[0]["status"] == "win"
    assert closed[0]["exit_price"] == pytest.approx(112.5)
