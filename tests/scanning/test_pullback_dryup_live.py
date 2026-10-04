"""v122 live gates reject before plan construction on completed bars."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from swingbot import config
from swingbot.core.edge import gates
from swingbot.core.scanning import analyze, strategy_pass as sp, scan_run, engine, dedup
from tests.helpers import make_ohlcv
from tests.scanning.test_strategy_pass_emit import _Store, _Log, _plan
from tests.scanning.test_engine_v2_plans import _setup_minimal_scan, _structured_df


@pytest.mark.parametrize('scope,strategy,blocked', [
    ('strategy', 'Fibonacci', True), ('strategy', 'MACD', False),
    ('confluence', 'Fibonacci', False), ('off', 'Fibonacci', False),
])
def test_strategy_rejects_before_build(monkeypatch, scope, strategy, blocked):
    monkeypatch.setattr(config, 'PULLBACK_DRYUP_SCOPE', scope)
    monkeypatch.setattr(config, 'PULLBACK_DRYUP_MAX_RATIO', 0.8)
    monkeypatch.setattr(gates, 'pullback_vol_ratio', lambda *a: 5.0)
    builder = Mock(return_value=_plan())
    monkeypatch.setattr(sp, 'build_strategy_plan_at', builder)
    monkeypatch.setattr(sp, 'risk_sizing_ok', lambda p: True)
    deps = sp._PassDeps(_Store(), _Log(), 'paper', set(), lambda t: None)
    result = sp.PassResult()
    sp._emit_signal(result, make_ohlcv([100.] * 70), ticker='TEST', strategy=strategy,
                    direction='bullish', horizon='4w', bar_date='2024-04-08', regime=None, deps=deps)
    assert result.pullback_volume == int(blocked)
    assert len(result.plans) == int(not blocked)
    assert builder.call_count == int(not blocked)


@pytest.mark.parametrize('hour,expected', [(15, 69), (21, 70)])
def test_confluence_uses_completed_bars(monkeypatch, hour, expected):
    monkeypatch.setattr(config, 'PULLBACK_DRYUP_SCOPE', 'confluence')
    monkeypatch.setattr(config, 'PULLBACK_DRYUP_MAX_RATIO', 0.8)
    frames = []
    def ratio(frame, direction):
        frames.append(frame)
        return 5.0
    monkeypatch.setattr(gates, 'pullback_vol_ratio', ratio)
    df = make_ohlcv([100.] * 70)
    now = datetime.combine(df.index[-1].date(), datetime.min.time(), tzinfo=timezone.utc).replace(hour=hour)
    stats = {'failed_counts': {'pullback_volume': 0}}
    scenarios = [SimpleNamespace(direction='bullish')]
    assert analyze._apply_pullback_dryup(scenarios, df, stats, 'TEST', '4w', now) == []
    assert stats['failed_counts']['pullback_volume'] == 1
    assert len(frames[0]) == expected
    assert frames[0].equals(df.iloc[:expected])


def test_strategy_funnel_counts_real_rejections(monkeypatch):
    monkeypatch.setattr(config, 'STRATEGY_ALERTS_MODE', 'shadow')
    monkeypatch.setattr(config, 'PULLBACK_DRYUP_SCOPE', 'strategy')
    monkeypatch.setattr(config, 'PULLBACK_DRYUP_MAX_RATIO', 0.8)
    monkeypatch.setattr(gates, 'pullback_vol_ratio', lambda *args: 5.0)
    monkeypatch.setattr(sp, 'strategy_signals', lambda *a, **k: [('Fibonacci', 'bullish')])
    monkeypatch.setattr(sp, '_shadow_step', lambda *a, **k: None)
    monkeypatch.setattr(scan_run, 'live_horizons', lambda: ['4w'])
    monkeypatch.setattr(scan_run, 'PlanStore', _Store)
    monkeypatch.setattr(scan_run, '_compression_hooks', lambda *a: (None, None))
    monkeypatch.setattr(scan_run, '_compression_seen', set)
    summary = scan_run._maybe_run_strategy_pass(
        tickers=['TEST'], fresh_data={'TEST': make_ohlcv([100.] * 70)}, spy_df=None,
        regimes=None, rs_cache=None, sector_of_ticker={}, etf_symbol_of_sector={},
        sector_etf_frames={}, trade_log=_Log(), alerts=[], require_confirmation=False)
    assert summary['strategy_pullback_volume'] == 1
    assert summary['strategy_plans'] == 0


def test_live_scan_off_then_confluence(monkeypatch, tmp_path, stub_batch_fetch):
    _setup_minimal_scan(monkeypatch, tmp_path)
    monkeypatch.setattr(config, 'PULLBACK_DRYUP_MAX_RATIO', 0.8)
    frames = []
    def ratio(frame, direction):
        frames.append(frame)
        return 5.0
    monkeypatch.setattr(gates, 'pullback_vol_ratio', ratio)
    monkeypatch.setattr(dedup, 'dedup_scan_items', lambda items: [])
    monkeypatch.setattr(config, 'PULLBACK_DRYUP_SCOPE', 'off')
    before = engine.ScanProgress()
    engine._sync_run_scan('4w', require_confirmation=False, progress=before, min_confluence=0)
    assert before.funnel['scenarios_found'] > 0
    assert frames == []
    assert before.funnel['failed_pullback_volume'] == 0
    monkeypatch.setattr(config, 'PULLBACK_DRYUP_SCOPE', 'confluence')
    after = engine.ScanProgress()
    engine._sync_run_scan('4w', require_confirmation=False, progress=after, min_confluence=0)
    assert after.funnel['scenarios_found'] == 0
    assert after.funnel['failed_pullback_volume'] == before.funnel['scenarios_found']
    assert frames and all(len(frame) == len(_structured_df()) for frame in frames)


def test_strategy_funnel_off_includes_zero_pullback_count(monkeypatch):
    monkeypatch.setattr(config, 'STRATEGY_ALERTS_MODE', 'off')
    summary = scan_run._maybe_run_strategy_pass(
        tickers=[], fresh_data={}, spy_df=None, regimes=None, rs_cache=None,
        sector_of_ticker={}, etf_symbol_of_sector={}, sector_etf_frames={},
        trade_log=_Log(), alerts=[], require_confirmation=False)
    assert summary['strategy_pullback_volume'] == 0
