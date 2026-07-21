import pytest

from swingbot.core.edge.heat import heat_check, open_heat, trade_risk_pct

BALANCE = 10_000.0


def _trade(entry, stop, shares):
    return {"entry": entry, "stop_loss": stop, "shares": shares}


def test_trade_risk_pct_from_prices():
    # (100-98) * 100 shares = $200 = 2% of 10k
    assert trade_risk_pct(_trade(100.0, 98.0, 100), BALANCE) == pytest.approx(2.0)


def test_trade_risk_pct_prefers_recorded_value():
    assert trade_risk_pct({"risk_pct": 1.5}, BALANCE) == 1.5


def test_open_heat_sums():
    trades = [_trade(100.0, 98.0, 100)] * 3   # 3 x 2%
    assert open_heat(trades, BALANCE) == pytest.approx(6.0)


def test_heat_check_blocks_at_cap():
    trades = [_trade(100.0, 98.0, 100)] * 3   # 6% open = at the 6% cap
    chk = heat_check(trades, BALANCE, candidate_risk_pct=1.0, cap_pct=6.0)
    assert chk["allowed"] is False
    assert chk["remaining"] == pytest.approx(0.0)


def test_closing_one_frees_heat():
    trades = [_trade(100.0, 98.0, 100)] * 2   # 4% open
    chk = heat_check(trades, BALANCE, candidate_risk_pct=1.0, cap_pct=6.0)
    assert chk["allowed"] is True
    assert chk["remaining"] == pytest.approx(2.0)
