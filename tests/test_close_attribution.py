"""Plan v8 Task V29: a close has to say how it came to be written.

`scripts/reconcile_open_plans.py` replays the bars missed during downtime and
resolves a bar spanning both levels AS THE STOP, so a reconciled close books
the full gap move rather than a managed `MAX_LOSS_PCT` stop-out. Pooling those
with live-polled closes makes an outage indistinguishable from strategy decay.

Measured on the live book on 2026-08-06, closes since 2026-08-03:

    reconcile-booked   n=32   WR 35.71%   expR -1.041
    live-polled        n=30   WR 39.29%   expR -0.342

V29's rollback trigger compares a 5-day expectancy against a baseline, so
without this split it fires on operational incidents and rolls back whatever
change happened to be in flight.
"""
import pytest

from swingbot.core.performance import TradeLog, close_attribution


@pytest.fixture
def log(tmp_path):
    return TradeLog(path=str(tmp_path / "trades.json"))


def _open(log, plan_id):
    return log.log_trade(
        ticker="AAPL", strategy="RSI", horizon_key="4w", direction="bullish",
        confidence_level=3, confidence_label="Moderate",
        entry=100.0, stop_loss=95.0, take_profit=110.0,
        plan_id=plan_id, tier="B", badge="WEAK", source="confluence")


def _close(log, plan_id):
    log.close_plan_trade(plan_id, {"fraction": 1.0, "exit_price": 95.0,
                                   "r": -1.0, "reason": "stop"}, "loss")


def test_an_ordinary_close_is_stamped_live(log):
    tid = _open(log, "p1")
    _close(log, "p1")
    assert log.get_trade_by_id(tid)["close_source"] == "live"


def test_a_close_inside_the_reconcile_block_is_stamped_reconcile(log):
    tid = _open(log, "p1")
    with close_attribution("reconcile"):
        _close(log, "p1")
    assert log.get_trade_by_id(tid)["close_source"] == "reconcile"


def test_the_attribution_is_restored_afterwards(log):
    """A reconcile run must not leave the process labelling every later close
    as reconciled -- the bot and the script share this module."""
    with close_attribution("reconcile"):
        pass
    tid = _open(log, "p2")
    _close(log, "p2")
    assert log.get_trade_by_id(tid)["close_source"] == "live"


def test_the_attribution_is_restored_even_when_the_block_raises(log):
    """The reconcile script wraps its whole entry point, and `main()` exits by
    raising SystemExit -- if that skipped the restore, the stamp would leak."""
    with pytest.raises(SystemExit):
        with close_attribution("reconcile"):
            raise SystemExit(0)
    tid = _open(log, "p3")
    _close(log, "p3")
    assert log.get_trade_by_id(tid)["close_source"] == "live"


def test_a_manual_close_is_neither_live_nor_reconcile(log):
    """The admin UI's Close button is a human override with no exit price --
    it is not evidence about the strategy either way, so it must not land in
    the live cohort the rollback trigger watches."""
    tid = _open(log, "p4")
    assert log.close_trade_manual(tid) is True
    assert log.get_trade_by_id(tid)["close_source"] == "manual"
