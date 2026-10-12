"""v135 live call sites: the strategy pass vetoes a built plan before it is stored, the
confluence scan vetoes a scenario before it is scored, and both count under `headroom`."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from swingbot import config
from swingbot.core.edge import gates
from swingbot.core.market.levels import Level
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.scanning import analyze, dedup, engine, scan_run
from swingbot.core.scanning import strategy_pass as sp
from tests.helpers import make_ohlcv
from tests.scanning.test_engine_v2_plans import _setup_minimal_scan
from tests.scanning.test_strategy_pass_emit import _Log, _plan, _Store

# test_strategy_pass_emit._plan(): bullish, trigger 100.0, stop 94.0 -> risk 6.0.
# A two-family resistance at 101.0 is 0.167R beyond entry: inside every grid value.
BLOCKED_MAP = ([], [Level(101.0, ["EMA50", "Rolling S/R"])])
CLEAR_MAP = ([], [Level(120.0, ["EMA50", "Rolling S/R"])])


def _knobs(monkeypatch, scope, min_r=0.75):
    monkeypatch.setattr(config, "HEADROOM_SCOPE", scope)
    monkeypatch.setattr(config, "HEADROOM_MIN_R", min_r)


def _emit(monkeypatch, strategy, level_map=BLOCKED_MAP):
    builder, maps = Mock(return_value=_plan()), Mock(return_value=level_map)
    monkeypatch.setattr(sp, "build_strategy_plan_at", builder)
    monkeypatch.setattr(sp, "build_level_map", maps)
    monkeypatch.setattr(sp, "risk_sizing_ok", lambda plan: True)
    deps = sp._PassDeps(_Store(), _Log(), "paper", set(), lambda ticker: None)
    result, frame = sp.PassResult(), make_ohlcv([100.0] * 70)
    sp._emit_signal(result, frame, ticker="TEST", strategy=strategy, direction="bullish",
                    horizon="4w", bar_date="2024-04-08", regime=None, deps=deps)
    return result, builder, maps, frame


@pytest.mark.parametrize("scope,min_r,strategy,blocked,builds_map", [
    ("strategy", 0.75, "Fibonacci", True, True),
    ("strategy", 0.75, "MACD", False, False),
    ("strategy", 0.0, "Fibonacci", False, False),
    ("confluence", 0.75, "Fibonacci", False, False),
    ("off", 0.75, "Fibonacci", False, False),
])
def test_strategy_veto_after_the_plan_is_built(monkeypatch, scope, min_r, strategy, blocked, builds_map):
    _knobs(monkeypatch, scope, min_r)
    result, builder, maps, _frame = _emit(monkeypatch, strategy)
    assert builder.call_count == 1                      # the veto reads the built plan
    assert result.headroom == int(blocked)
    assert len(result.plans) == int(not blocked)
    assert maps.call_count == int(builds_map)           # an inactive gate builds no map


def test_a_clear_path_is_not_vetoed(monkeypatch):
    _knobs(monkeypatch, "strategy")
    result, _builder, maps, _frame = _emit(monkeypatch, "Fibonacci", CLEAR_MAP)
    assert result.headroom == 0 and len(result.plans) == 1 and maps.call_count == 1


def test_the_live_map_is_built_on_the_frame_the_pass_handed_over(monkeypatch):
    """NO-LOOKAHEAD: the map reads the completed frame itself, split at its last close."""
    _knobs(monkeypatch, "strategy")
    _result, _builder, maps, frame = _emit(monkeypatch, "Fibonacci")
    df, horizon, price = maps.call_args.args
    assert df is frame and horizon is HORIZONS["4w"]
    assert price == float(frame["Close"].iloc[-1])


def _scenario():
    return SimpleNamespace(direction="bullish", entry=100.0, stop_loss=98.0)


def test_confluence_helper_drops_and_counts(monkeypatch):
    _knobs(monkeypatch, "confluence")
    stats = {"failed_counts": {"headroom": 0}}
    kept = analyze._apply_headroom([_scenario()], *BLOCKED_MAP, stats, "TEST", "4w")
    assert kept == [] and stats["failed_counts"]["headroom"] == 1


@pytest.mark.parametrize("scope,min_r", [("off", 0.75), ("strategy", 0.75), ("confluence", 0.0)])
def test_confluence_helper_is_a_no_op_when_inactive(monkeypatch, scope, min_r):
    _knobs(monkeypatch, scope, min_r)
    stats, scenario = {"failed_counts": {"headroom": 0}}, _scenario()
    assert analyze._apply_headroom([scenario], *BLOCKED_MAP, stats, "TEST", "4w") == [scenario]
    assert stats["failed_counts"]["headroom"] == 0


def _strategy_summary(monkeypatch):
    monkeypatch.setattr(sp, "strategy_signals", lambda *a, **k: [("Fibonacci", "bullish")])
    monkeypatch.setattr(sp, "_shadow_step", lambda *a, **k: None)
    monkeypatch.setattr(sp, "build_strategy_plan_at", lambda *a, **k: _plan())
    monkeypatch.setattr(sp, "build_level_map", lambda *a, **k: BLOCKED_MAP)
    monkeypatch.setattr(sp, "risk_sizing_ok", lambda plan: True)
    monkeypatch.setattr(scan_run, "live_horizons", lambda: ["4w"])
    monkeypatch.setattr(scan_run, "PlanStore", _Store)
    monkeypatch.setattr(scan_run, "_compression_hooks", lambda *a: (None, None))
    monkeypatch.setattr(scan_run, "_compression_seen", set)
    return scan_run._maybe_run_strategy_pass(
        tickers=["TEST"], fresh_data={"TEST": make_ohlcv([100.0] * 70)}, spy_df=None,
        regimes=None, rs_cache=None, sector_of_ticker={}, etf_symbol_of_sector={},
        sector_etf_frames={}, trade_log=_Log(), alerts=[], require_confirmation=False)


def test_strategy_funnel_counts_real_rejections(monkeypatch):
    monkeypatch.setattr(config, "STRATEGY_ALERTS_MODE", "shadow")
    _knobs(monkeypatch, "strategy")
    summary = _strategy_summary(monkeypatch)
    assert summary["strategy_headroom"] == 1 and summary["strategy_plans"] == 0


def test_strategy_funnel_off_includes_a_zero_headroom_count(monkeypatch):
    monkeypatch.setattr(config, "STRATEGY_ALERTS_MODE", "off")
    summary = scan_run._maybe_run_strategy_pass(
        tickers=[], fresh_data={}, spy_df=None, regimes=None, rs_cache=None,
        sector_of_ticker={}, etf_symbol_of_sector={}, sector_etf_frames={},
        trade_log=_Log(), alerts=[], require_confirmation=False)
    assert summary["strategy_headroom"] == 0


def test_live_scan_off_then_confluence(monkeypatch, tmp_path, stub_batch_fetch):
    """End to end through _sync_run_scan: off reads nothing; confluence hands the predicate
    the scan's own levels and counts every rejection in the funnel."""
    _setup_minimal_scan(monkeypatch, tmp_path)
    monkeypatch.setattr(config, "HEADROOM_MIN_R", 1.0)
    seen = []

    def rejects(entry, stop, direction, levels, min_r):
        seen.append(list(levels))
        return True
    monkeypatch.setattr(gates, "headroom_rejects", rejects)
    monkeypatch.setattr(dedup, "dedup_scan_items", lambda items: [])
    monkeypatch.setattr(config, "HEADROOM_SCOPE", "off")
    before = engine.ScanProgress()
    engine._sync_run_scan("4w", require_confirmation=False, progress=before, min_confluence=0)
    assert before.funnel["scenarios_found"] > 0
    assert seen == [] and before.funnel["failed_headroom"] == 0
    monkeypatch.setattr(config, "HEADROOM_SCOPE", "confluence")
    after = engine.ScanProgress()
    engine._sync_run_scan("4w", require_confirmation=False, progress=after, min_confluence=0)
    assert after.funnel["scenarios_found"] == 0
    assert after.funnel["failed_headroom"] == before.funnel["scenarios_found"]
    assert seen and all(levels and all(isinstance(level, Level) for level in levels)
                        for levels in seen)
