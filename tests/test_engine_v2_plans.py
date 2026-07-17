from types import SimpleNamespace
import numpy as np
import swingbot.config as config
from swingbot.core.performance import TradeLog
from swingbot.core.scanning import engine
from tests.helpers import make_ohlcv

def _item():
    return SimpleNamespace(plan_v2=None)   # or a real ScanItem fixture

def _scenario():
    return SimpleNamespace(direction="bullish", entry=100.0, stop_loss=95.0,
                           take_profit=110.0, target_sources=["EMA21"],
                           stop_sources=["Rolling support"])

def test_flag_off_attaches_nothing(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "off")
    item = _item()
    engine.attach_plan_v2(item, _scenario(), make_ohlcv([100.0] * 60),
                          "AAPL", "4w", level_map=([], []))
    assert item.plan_v2 is None

def test_flag_shadow_attaches_plan_without_touching_legacy(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "shadow")
    item = _item()
    sc = _scenario()
    engine.attach_plan_v2(item, sc, make_ohlcv([100.0] * 60),
                          "AAPL", "4w", level_map=([], []))
    assert item.plan_v2 is not None
    assert item.plan_v2.source == "confluence"
    # legacy scenario numbers untouched -- the embed keeps reading these
    assert sc.entry == 100.0 and sc.take_profit == 110.0

def test_plan_construction_failure_never_kills_the_scan(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "shadow")
    monkeypatch.setattr(engine, "build_confluence_plan",
                        lambda *a, **k: 1 / 0)
    item = _item()
    engine.attach_plan_v2(item, _scenario(), make_ohlcv([100.0] * 60),
                          "AAPL", "4w", level_map=([], []))   # must not raise
    assert item.plan_v2 is None

def _structured_df():
    """Trend up, then a 60-bar consolidation between roughly ±5% of the
    trend's last close -- gives every level source (rolling S/R, Donchian,
    pivots, Bollinger, fibs) real structure on both sides of price, so
    levels.build_scenarios() reliably produces at least one genuine
    scenario. Same recipe as test_levels_scenarios.py's proven fixture.
    """
    rng = np.random.RandomState(7)
    trend = list(100 * np.cumprod(1 + rng.normal(0.002, 0.01, 120)))
    box = [trend[-1] * (1 + 0.05 * np.sin(i / 4)) for i in range(60)]
    return make_ohlcv(trend + box)


def test_sync_run_scan_gates_attach_plan_v2_on_all_ok(monkeypatch, tmp_path):
    """
    Real regression test for the `if all_ok:` gate around the
    attach_plan_v2(...) call at engine.py:676-677, driven through the
    actual `_sync_run_scan` code path -- not a direct call to
    attach_plan_v2, which is what the old version of this test did (and
    which passes identically whether the gate exists, is True/False, or
    is deleted entirely -- it never touched _sync_run_scan at all).

    Every scenario levels.build_scenarios() actually returns has already
    cleared min_reward/min_stop_distance/max_stop_distance/min_risk_reward
    (see build_scenarios' own docstring: a scenario failing any of those
    hard filters is simply never built). That leaves exactly two
    requirement checks in _build_requirement_checks that a real, built
    scenario can still fail: min_confluence and min_confidence. This test
    uses _sync_run_scan's own `min_confluence` override parameter (the
    same lever `!check <N>` uses) to force those two checks to fail (Run
    1: all_ok=False) or pass (Run 2, contrast: all_ok=True) for every
    scenario found, without hand-crafting exact price levels.

    Hard-filter config values (MIN_REWARD_PCT/MIN_STOP_DISTANCE_PCT/
    MAX_STOP_LOSS_PCT/MIN_RISK_REWARD_RATIO) are loosened so scenario
    *construction* itself -- already covered by test_levels_scenarios.py
    -- isn't what's under test here; only the all_ok gate is.

    engine.dedup_scan_items is monkeypatched to capture the real
    ScanItem objects exactly as built (plan_v2 already attached or not,
    per the gate at engine.py:676-677) and then short-circuits to `[]`,
    so the expensive/network-touching alert-building loop further down
    (chart rendering, earnings lookups, secondary notifications) never
    runs -- that loop is irrelevant to the gate under test here and
    would otherwise make this test slow and non-hermetic.
    """
    df = _structured_df()

    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "shadow")
    monkeypatch.setattr(config, "MIN_REWARD_PCT", 0.5)
    monkeypatch.setattr(config, "MIN_STOP_DISTANCE_PCT", 0.0)
    monkeypatch.setattr(config, "MAX_STOP_LOSS_PCT", 50.0)
    monkeypatch.setattr(config, "MIN_RISK_REWARD_RATIO", 0.0)
    # engine.py also floors the min-reward requirement at 15% of the horizon's
    # OWN sr_target_min_pct (see engine.py's effective_min_reward comment) --
    # 4w's default (15.0) floors it at 2.25%, above this fixture's nearest
    # S/R distance (~1.35-1.78%), so no scenario would ever get built without
    # loosening this horizon setting too. This only relaxes a per-horizon
    # constant used to *build* a scenario -- unrelated to the all_ok gate.
    monkeypatch.setitem(engine.HORIZONS["4w"], "sr_target_min_pct", 1.0)

    monkeypatch.setattr(engine, "load_watchlist", lambda: ["TEST"])
    monkeypatch.setattr(
        engine, "get_daily_data",
        lambda ticker, period=None: df.copy() if ticker == "TEST" else None,
    )
    monkeypatch.setattr(engine, "get_current_price", lambda ticker: None)
    monkeypatch.setattr(engine, "trade_log", TradeLog(path=str(tmp_path / "trades.json")))
    monkeypatch.setattr(engine, "is_stop_requested", lambda: False)

    captured = {}

    def _capture_and_shortcircuit(items):
        captured["items"] = list(items)
        return []   # skip the alert-building loop entirely -- plan_v2 is already decided by here

    monkeypatch.setattr(engine, "dedup_scan_items", _capture_and_shortcircuit)

    # --- Run 1: an unreachable min_confluence means every scenario fails
    # the min_confluence requirement -> all_ok=False for all of them.
    engine._sync_run_scan("4w", require_confirmation=False, progress=None, min_confluence=999_999)
    failing_items = captured["items"]
    assert failing_items, "fixture must produce at least one real scenario to exercise the gate"
    assert all(item.plan_v2 is None for item in failing_items), (
        "attach_plan_v2 must NOT be called (plan_v2 must stay None) for a scenario that "
        "fails a requirement check -- the engine.py:676-677 `if all_ok:` gate regressed"
    )

    # --- Run 2 (contrast): min_confluence=0 and the confidence floor
    # dropped to 1 (the lowest level) make both remaining soft
    # requirements pass for every real scenario -> all_ok=True for all.
    monkeypatch.setattr(config, "MIN_ALERT_CONFIDENCE_LEVEL", 1)
    captured.clear()
    engine._sync_run_scan("4w", require_confirmation=False, progress=None, min_confluence=0)
    passing_items = captured["items"]
    assert passing_items, "fixture must produce at least one real scenario to exercise the gate"
    assert all(item.plan_v2 is not None for item in passing_items), (
        "attach_plan_v2 SHOULD be called (plan_v2 must be set) for a scenario that passes "
        "every requirement check -- the engine.py:676-677 `if all_ok:` gate's other branch"
    )
