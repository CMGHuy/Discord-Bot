from types import SimpleNamespace

from swingbot.core.planning.plan_types import PlanStatus, TradePlanV2
from swingbot.core.scanning import analyze, strategy_pass as sp
from tests.helpers import make_ohlcv


def _plan():
    return TradePlanV2(plan_id="p", ticker="AAPL", created_at="2026-09-16", source="confluence",
                       strategy="MACD", horizon_key="3m", direction="bullish", entry_type="market",
                       trigger_price=100.0, entry_price=100.0, expiry_bars=5, stop_loss=95.0, tp1=110.0,
                       tp1_fraction=0.5, tp2=None, breakeven_trigger_fraction=0.5, trail_atr_mult=2.0,
                       quality_score=0, quality_breakdown=[], badge="WEAK", badge_stats={}, status=PlanStatus.PENDING)


def test_attach_plan_v2_stamps_with_item_readings(monkeypatch):
    import swingbot.config as config
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(analyze, "_build_quality_inputs", lambda *args, **kwargs: {})
    monkeypatch.setattr(analyze, "build_confluence_plan", lambda *args, **kwargs: _plan())
    monkeypatch.setattr(analyze, "primary_strategy_for", lambda scenario: "MACD")
    seen = {}
    monkeypatch.setattr(analyze, "stamp_entry_context",
                        lambda plan, df, asof: (seen.update(asof=asof), setattr(plan, "entry_context", {"stamped": True})))
    df = make_ohlcv([100.0] * 300, start="2025-06-02")
    item = SimpleNamespace(rs_combined=61.0, sector_rs_percentile=55.0, conf=None, htf_bias=None, target_confluence=None)
    scenario = SimpleNamespace(direction="bullish", entry=100.0)
    analyze.attach_plan_v2(item, scenario, df, "AAPL", "3m", rs_percentile=64.0, regime2_state="bull_quiet")
    assert item.plan_v2.entry_context == {"stamped": True}
    assert seen["asof"] == {"regime2_state": "bull_quiet", "rs_pctile": 64.0, "sector_pctile": 55.0, "rs_combined": 61.0}


def test_strategy_plan_stamps_once(monkeypatch):
    calls = []
    monkeypatch.setattr(sp, "build_strategy_plan", lambda *args, **kwargs: _plan())
    monkeypatch.setattr(sp, "stamp_badge", lambda plan: None)
    monkeypatch.setattr(sp, "stamp_cohort", lambda plan, state: None)
    monkeypatch.setattr(sp, "stamp_entry_context", lambda plan, df, asof: calls.append(asof))
    df = make_ohlcv([100.0] * 300, start="2025-06-02")
    sp.build_strategy_plan_at(df, ticker="AAPL", strategy="MACD", horizon_key="3m", direction="bullish",
                              regime2_state="bear_quiet", asof={"rs_pctile": 10.0})
    assert calls == [{"rs_pctile": 10.0, "regime2_state": "bear_quiet"}]


def test_live_and_replay_use_the_same_stamper():
    from swingbot.core.backtesting import backtest_scenarios as bs
    from swingbot.core.planning import params
    assert analyze.stamp_entry_context is params.stamp_entry_context
    assert bs.stamp_entry_context is params.stamp_entry_context
    assert sp.stamp_entry_context is params.stamp_entry_context
