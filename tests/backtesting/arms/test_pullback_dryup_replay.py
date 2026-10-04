"""Replay dry-up admission precedes plan construction and position occupancy."""
import pytest

from swingbot import config
from swingbot.core.backtesting.arms.engine import run_arm
from swingbot.core.backtesting.arms import strategy_engine
from swingbot.core.edge import gates
from swingbot.core.market import entry_filters
from swingbot.scan_params import ScanParams
from tests.backtesting.test_v74_fixture import load_v74_fixture

WINDOW = ('1900-01-01', '2100-12-31')
PULLBACKS = {'Fibonacci', 'EMA Crossover', 'Break & Retest', 'RSI',
             'RSI Divergence', 'MA Ribbon', 'VWAP'}


@pytest.fixture(scope='module')
def frame():
    return load_v74_fixture()['AAPL']


def boom(*args):
    raise AssertionError('inactive dry-up must not compute volume')


@pytest.mark.parametrize('scope,ratio', [('off', .60), ('confluence', 0.0), ('strategy', 0.0)])
def test_inactive_gate_never_computes(frame, monkeypatch, scope, ratio):
    base = run_arm('AAPL', frame, ('confluence', 'strategy'), ('4w',), WINDOW, {})
    assert base
    monkeypatch.setattr(gates, 'pullback_vol_ratio', boom)
    assert run_arm('AAPL', frame, ('confluence', 'strategy'), ('4w',), WINDOW,
                   {'PULLBACK_DRYUP_SCOPE': scope, 'PULLBACK_DRYUP_MAX_RATIO': ratio}) == base


def test_confluence_scope_removes_heavy_pullbacks(frame, monkeypatch):
    base = run_arm('AAPL', frame, ('confluence',), ('4w',), WINDOW, {})
    assert base
    monkeypatch.setattr(gates, 'pullback_vol_ratio', lambda *args: 5.0)
    assert run_arm('AAPL', frame, ('confluence',), ('4w',), WINDOW,
                   {'PULLBACK_DRYUP_SCOPE': 'confluence', 'PULLBACK_DRYUP_MAX_RATIO': .60}) == []


def test_strategy_scope_preserves_confluence(frame, monkeypatch):
    base = run_arm('AAPL', frame, ('confluence',), ('4w',), WINDOW, {})
    assert base
    monkeypatch.setattr(gates, 'pullback_vol_ratio', boom)
    assert run_arm('AAPL', frame, ('confluence',), ('4w',), WINDOW,
                   {'PULLBACK_DRYUP_SCOPE': 'strategy', 'PULLBACK_DRYUP_MAX_RATIO': .60}) == base


@pytest.mark.parametrize('horizon', ['4w', '3m'])
def test_strategy_scope_filters_only_frozen_pullbacks(frame, monkeypatch, horizon):
    base = run_arm('AAPL', frame, ('strategy',), (horizon,), WINDOW, {})
    assert any(trade.strategy in PULLBACKS for trade in base)
    monkeypatch.setattr(gates, 'pullback_vol_ratio', lambda *args: 5.0)
    gated = run_arm('AAPL', frame, ('strategy',), (horizon,), WINDOW,
                    {'PULLBACK_DRYUP_SCOPE': 'strategy', 'PULLBACK_DRYUP_MAX_RATIO': .60})
    assert gated == [trade for trade in base if trade.strategy not in PULLBACKS]


@pytest.mark.parametrize('entry_mode,blocked', [('pullback', True), ('cross', False)])
def test_gated_plan_respects_ema_mode(frame, monkeypatch, entry_mode, blocked):
    monkeypatch.setattr(config, 'PULLBACK_DRYUP_SCOPE', 'strategy')
    monkeypatch.setattr(config, 'PULLBACK_DRYUP_MAX_RATIO', .60)
    monkeypatch.setitem(entry_filters.DEFAULT_PARAMS['EMA Crossover'], 'entry_mode', entry_mode)
    monkeypatch.setattr(gates, 'pullback_vol_ratio', lambda *args: 5.0)
    sentinel = object()
    monkeypatch.setattr(strategy_engine, 'build_strategy_plan', lambda *args, **kwargs: sentinel)
    result = strategy_engine.StrategyEngine._gated_plan(
        frame, len(frame) - 1, ticker='AAPL', strategy='EMA Crossover',
        horizon_key='4w', direction='bullish', level_map=None, params=ScanParams.from_config())
    assert result is (None if blocked else sentinel)
