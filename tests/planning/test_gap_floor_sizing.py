"""v183 Part A: the gap floor inside compute_position_size."""
import pytest

from swingbot import config
from swingbot.core.planning import account
from swingbot.core.planning.account import _gap_fields, _sizing_distance, compute_position_size

GAP_KEYS = {"gap_risk_amount", "gap_sized", "gap_floor_pct"}
WEAK = {"win_rate": 0.60, "avg_win_r": 0.3, "avg_loss_r": 1.0, "n": 200}


@pytest.fixture(autouse=True)
def _no_opex(monkeypatch):
    monkeypatch.setattr(account.opex, "size_mult", lambda *a, **k: 1.0)
    monkeypatch.setattr(config, "PORTFOLIO_TARGET_DAILY_VOL_PCT", 0.7)


def _cfg(mode="risk_pct", **over):
    cfg = {"balance": 10_000.0, "risk_pct": 1.0, "sizing_mode": mode, "position_pct": 10.0,
           "max_position_pct": 100.0, "max_position_value_absolute": 0, "max_risk_amount_absolute": 0}
    cfg.update(over)
    return cfg


def test_no_floor_is_todays_dict_exactly():
    out = compute_position_size(100.0, 98.0, _cfg())
    assert out == {"shares": 50.0, "risk_amount": 100.0, "position_value": 5000.0, "capped": False,
                   "balance": 10_000.0, "risk_pct": 1.0, "position_pct": 10.0, "max_position_pct": 100.0,
                   "max_position_value_absolute": 0.0, "max_risk_amount_absolute": 0.0, "mode": "risk_pct"}
    assert compute_position_size(100.0, 98.0, _cfg(), gap_floor_pct=None) == out


def test_gap_wider_than_stop_cuts_shares_and_keeps_risk_on_the_stop():
    # short: entry 100, stop 102 (2.00 away); p99 up-gap 3% -> sizes on 3.00
    out = compute_position_size(100.0, 102.0, _cfg(), gap_floor_pct=3.0)
    assert out["shares"] == 33.33
    assert out["risk_amount"] == 66.67          # final shares x STOP distance
    assert out["gap_risk_amount"] == 100.0      # final shares x sizing distance = the dollar cap
    assert out["gap_sized"] is True
    assert out["gap_floor_pct"] == 3.0
    assert out["mode"] == "risk_pct"


def test_stop_wider_than_gap_is_unchanged_but_reports_gap_risk():
    plain = compute_position_size(100.0, 105.0, _cfg())
    out = compute_position_size(100.0, 105.0, _cfg(), gap_floor_pct=3.0)
    assert {k: out[k] for k in plain} == plain
    assert set(out) - set(plain) == GAP_KEYS
    assert (out["shares"], out["gap_risk_amount"], out["gap_sized"]) == (20.0, 100.0, False)


def test_binding_position_cap_is_not_reported_as_a_gap_cut():
    # max_position_pct 20 -> at most 20 shares at 100 whatever the distance
    out = compute_position_size(100.0, 102.0, _cfg(max_position_pct=20.0), gap_floor_pct=3.0)
    assert out["shares"] == 20.0
    assert out["gap_sized"] is False
    assert out["gap_risk_amount"] == 60.0


def test_absolute_risk_cap_uses_the_sizing_distance():
    # stop-only: 50 shares, risk cap 60/2 = 30 -> 30 ; gap: 33.33, risk cap 60/3 = 20 -> 20
    plain = compute_position_size(100.0, 102.0, _cfg(max_risk_amount_absolute=60.0))
    out = compute_position_size(100.0, 102.0, _cfg(max_risk_amount_absolute=60.0), gap_floor_pct=3.0)
    assert plain["shares"] == 30.0
    assert out["shares"] == 20.0 and out["gap_sized"] is True and out["capped"] is True
    assert out["gap_risk_amount"] == 60.0       # never above the absolute dollar cap


def test_account_pct_feels_the_floor_only_through_the_absolute_risk_cap():
    free = compute_position_size(100.0, 101.0, _cfg("account_pct"), gap_floor_pct=3.0)
    assert free["shares"] == 10.0 and free["gap_sized"] is False and free["gap_risk_amount"] == 30.0
    capped = compute_position_size(100.0, 101.0, _cfg("account_pct", max_risk_amount_absolute=15.0),
                                   gap_floor_pct=3.0)
    assert capped["shares"] == 5.0 and capped["gap_sized"] is True
    assert capped["risk_amount"] == 5.0 and capped["gap_risk_amount"] == 15.0
    assert compute_position_size(100.0, 101.0, _cfg("account_pct", max_risk_amount_absolute=15.0))["shares"] == 10.0


@pytest.mark.parametrize("mode, kwargs, plain_shares, gap_shares", [
    ("risk_pct", {}, 50.0, 33.33),
    ("kelly", {"strategy_stats": WEAK}, 12.5, 8.33),
    ("vol_target", {"ticker_atr_pct": 3.0}, 35.0, 23.33),
    ("min_of_all", {"strategy_stats": WEAK, "ticker_atr_pct": 3.0}, 12.5, 8.33),
    ("account_pct", {}, 10.0, 10.0),
])
def test_every_mode_only_ever_shrinks(mode, kwargs, plain_shares, gap_shares):
    plain = compute_position_size(100.0, 102.0, _cfg(mode), **kwargs)
    out = compute_position_size(100.0, 102.0, _cfg(mode), gap_floor_pct=3.0, **kwargs)
    assert plain["shares"] == plain_shares
    assert out["shares"] == gap_shares
    assert out["shares"] <= plain["shares"]
    assert out["gap_sized"] is (gap_shares < plain_shares)
    assert out["risk_amount"] <= plain["risk_amount"]


def test_zero_balance_and_zero_stop_still_return_none():
    assert compute_position_size(100.0, 102.0, _cfg(balance=0.0), gap_floor_pct=3.0) is None
    assert compute_position_size(100.0, 100.0, _cfg(), gap_floor_pct=3.0) is None


def test_helpers():
    assert _sizing_distance(100.0, 2.0, None) == 2.0
    assert _sizing_distance(100.0, 2.0, 3.0) == 3.0
    assert _sizing_distance(100.0, 5.0, 3.0) == 5.0
    assert _gap_fields(10.0, 10.0, 3.0, None) == {}
    assert _gap_fields(10.0, 15.0, 3.0, 3.0) == {"gap_risk_amount": 30.0, "gap_sized": True, "gap_floor_pct": 3.0}
