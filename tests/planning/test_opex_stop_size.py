"""Opex widens the ATR stop and shrinks the position.

The stop half is modelled on tests/edge/test_edge_stops.py, which covers the
same `stop_mult` seam for E31's MAE multiplier -- including its point that
`_atr_plan` is the SHARED sizing source for the live builder and the
backtest, so anything composed into it must stay flag-gated.
"""
import pytest

from swingbot import config
from swingbot.core.market import opex
from swingbot.core.planning.plan_engine import build_strategy_plan
from tests.helpers import make_ohlcv


@pytest.fixture(scope="module")
def df():
    return make_ohlcv([100 + i * 0.5 for i in range(80)])


def _plan(df, **kw):
    return build_strategy_plan(df, len(df) - 1, ticker="TEST", strategy="RSI",
                               horizon_key="4w", direction="bullish", **kw)


@pytest.fixture
def monthly_opex(monkeypatch):
    monkeypatch.setattr(config, "OPEX_CAUTION_ENABLED", True)
    monkeypatch.setattr(config, "OPEX_STOP_WIDEN_PCT", 10.0)
    monkeypatch.setattr(config, "OPEX_SIZE_REDUCTION_PCT", 25.0)
    monkeypatch.setattr(opex, "current_tier", lambda *a, **k: opex.MONTHLY)


def test_stop_is_wider_on_monthly_opex(df, monkeypatch, monthly_opex):
    """The whole point: same bar, same strategy, a stop further from entry.

    Compared as an absolute price rather than a distance because TradePlanV2
    has no single `entry` field (it carries `trigger_price` and
    `entry_price`); on a bullish plan the stop sits below entry, so widening
    can only move it DOWN.
    """
    wide = _plan(df)
    monkeypatch.setattr(opex, "current_tier", lambda *a, **k: None)
    base = _plan(df)
    assert base is not None and wide is not None
    assert wide.stop_loss < base.stop_loss


def test_stop_is_bit_identical_when_the_flag_is_off(df, monkeypatch):
    """Inert by default -- and this is the assertion that proves the
    multiplier never leaks into the backtest's shared sizing path."""
    monkeypatch.setattr(config, "OPEX_CAUTION_ENABLED", False)
    off = _plan(df)
    monkeypatch.setattr(opex, "current_tier", lambda *a, **k: opex.MONTHLY)
    still_off = _plan(df)      # tier says monthly, but the flag rules
    assert off.stop_loss == still_off.stop_loss


def test_opex_composes_with_an_explicit_stop_mult(df, monthly_opex, monkeypatch):
    """An explicit caller multiplier is kept and widened on top, not
    replaced -- 1.2 * 1.10, never 1.10."""
    both = _plan(df, stop_mult=1.2)
    assert both.stop_mult_applied == pytest.approx(1.2 * 1.10)
    # The reference reaches the same effective multiplier the ordinary way,
    # with opex out of the picture -- left on, it would be widened too and
    # the comparison would be 1.32 against 1.452.
    monkeypatch.setattr(opex, "current_tier", lambda *a, **k: None)
    only_caller = _plan(df, stop_mult=1.2 * 1.10)
    assert both.stop_loss == pytest.approx(only_caller.stop_loss, rel=1e-9)


def test_zero_widen_is_a_no_op(df, monthly_opex, monkeypatch):
    monkeypatch.setattr(config, "OPEX_STOP_WIDEN_PCT", 0.0)
    assert opex.stop_mult() == 1.0


from swingbot.core.planning.account import compute_position_size

#: The mode key is `sizing_mode` (account.py:473), NOT `mode` -- an unknown
#: key would silently fall through to the risk_pct default and make the
#: account_pct case below pass for the wrong reason. Both absolute caps are
#: pinned to 0 so the schema's own defaults cannot clip these figures.
BASE_CFG = {
    "balance": 10_000.0,
    "risk_pct": 1.0,
    "position_pct": 20.0,
    "max_position_pct": 100.0,
    "max_position_value_absolute": 0.0,
    "max_risk_amount_absolute": 0.0,
    "sizing_mode": "risk_pct",
}


def test_risk_pct_mode_scales_down(monthly_opex):
    got = compute_position_size(100.0, 95.0, dict(BASE_CFG))
    # 1% of 10k = $100 risk / $5 stop = 20 shares, cut 25% -> 15
    assert got["shares"] == pytest.approx(15, abs=0.01)


def test_account_pct_mode_scales_down(monthly_opex):
    got = compute_position_size(100.0, 95.0,
                                {**BASE_CFG, "sizing_mode": "account_pct"})
    # 20% of 10k = $2000 / $100 = 20 shares, cut 25% -> 15
    assert got["shares"] == pytest.approx(15, abs=0.01)


def test_size_is_untouched_when_the_flag_is_off(monkeypatch):
    monkeypatch.setattr(config, "OPEX_CAUTION_ENABLED", False)
    got = compute_position_size(100.0, 95.0, dict(BASE_CFG))
    assert got["shares"] == pytest.approx(20, abs=0.01)
