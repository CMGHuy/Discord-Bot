from types import SimpleNamespace
import swingbot.config as config
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
