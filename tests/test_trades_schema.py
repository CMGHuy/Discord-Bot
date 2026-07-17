import pytest

from swingbot.core.performance import TradeLog, settle_legs


def _trade(**kw):
    base = {"id": "t1", "ticker": "AAPL", "direction": "bullish",
            "entry": 100.0, "stop_loss": 95.0, "take_profit": 110.0,
            "status": "open", "shares": 10.0}
    base.update(kw)
    return base


def test_legacy_record_loads_untouched(tmp_path):
    path = tmp_path / "trades.json"
    path.write_text('[{"id": "old1", "ticker": "AAPL", "status": "win", '
                    '"entry": 100, "stop_loss": 95, "take_profit": 110, '
                    '"direction": "bullish", "exit_price": 110}]')
    log = TradeLog(path=str(path))
    stats = log.get_stats()
    assert stats["wins"] == 1        # no KeyError on missing legs/plan_id


def test_two_leg_pnl_sums_fractions():
    t = _trade(legs=[
        {"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1"},
        {"fraction": 0.5, "exit_price": 100.0, "r": 0.0, "reason": "tp1_runner_be"},
    ])
    # 10 shares: leg1 = 10*0.5*(110-100) = 50; leg2 = 0 -> 50.0
    assert settle_legs(t) == pytest.approx(50.0)


def test_bearish_legs_sign():
    t = _trade(direction="bearish", entry=100.0,
               legs=[{"fraction": 1.0, "exit_price": 90.0, "r": 2.0, "reason": "tp1"}])
    assert settle_legs(t) == pytest.approx(100.0)   # 10 * (100-90)


def test_unsized_trade_settles_none():
    t = _trade(shares=None, legs=[{"fraction": 1.0, "exit_price": 110.0,
                                   "r": 2.0, "reason": "tp1"}])
    assert settle_legs(t) is None
