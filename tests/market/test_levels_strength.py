"""v36 Task 3: Level.strength, the cached grading pass wired into
build_level_map. Uses HORIZONS["2w"] (small lookbacks) so a repeated-bounce
frame stays short."""
import numpy as np

from swingbot import config
from swingbot.core.market import levels
from swingbot.core.market.levels import Level
from swingbot.core.market.strategy_types import HORIZONS
from tests.helpers import make_ohlcv

_H = HORIZONS["2w"]


def _frame_with_repeated_bounce_at(level: float):
    """Trend down toward `level`, then oscillate just above it with the low
    wicking down to exactly `level` and closing back above every few bars --
    real rejections for grade_level to see, and a rolling low/EMA cluster
    that lands close to `level` for _cluster_levels to find."""
    rng = np.random.RandomState(5)
    lead_in = list((level * 1.2) * np.cumprod(1 + rng.normal(-0.004, 0.006, 60)))
    box = []
    for i in range(60):
        if i % 5 == 0:
            # wick down to the level, close back above it: a rejection
            box.append((level + 0.4, level + 0.6, level, level + 0.3))
        else:
            close = level + 0.3 + 0.1 * np.sin(i)
            box.append((close, close * 1.002, close * 0.999, close))
    return make_ohlcv(lead_in + box)


def _build_level_map(df, ticker=None):
    """Wraps levels.build_level_map with HORIZONS["2w"] and both Level lists
    flattened into one, matching the shape the tests below iterate over."""
    current_price = float(df["Close"].iloc[-1])
    supports, resistances = levels.build_level_map(
        df, _H, current_price, ticker=ticker, horizon_key="2w")
    return supports + resistances


def test_level_has_a_strength_field_defaulting_to_none():
    assert Level(price=100.0, sources=["EMA"]).strength is None


def test_strength_populated_when_flag_on(monkeypatch):
    monkeypatch.setattr(config, "LEVEL_TOUCH_STRENGTH", True)
    levels = _build_level_map(_frame_with_repeated_bounce_at(100.0))
    graded = [lv for lv in levels if abs(lv.price - 100.0) < 1.0]
    assert graded and graded[0].strength["available"] is True


def test_strength_absent_when_flag_off(monkeypatch):
    monkeypatch.setattr(config, "LEVEL_TOUCH_STRENGTH", False)
    levels = _build_level_map(_frame_with_repeated_bounce_at(100.0))
    assert all(lv.strength is None for lv in levels)


def test_grade_is_cached_per_bar(monkeypatch):
    """Second scan on the same final bar must not recompute -- this is the
    difference between fitting in SCAN_INTERVAL_MINUTES and not."""
    calls = []
    monkeypatch.setattr("swingbot.core.market.levels.grade_level",
                        lambda *a, **k: calls.append(1) or
                        {"score": 0.5, "touches": 0, "rejections": 0,
                         "breaks": 0, "available": False})
    monkeypatch.setattr(config, "LEVEL_TOUCH_STRENGTH", True)
    df = _frame_with_repeated_bounce_at(100.0)
    _build_level_map(df, ticker="AAPL")
    first = len(calls)
    _build_level_map(df, ticker="AAPL")
    assert len(calls) == first, "second identical scan should hit the cache"


def test_method_count_is_unaffected_by_strength():
    """Touch strength grades level QUALITY. It must never add a source, or it
    becomes a backdoor into v32's honesty cap."""
    lv = Level(price=100.0, sources=["EMA", "VWAP"])
    before = len(lv.sources)
    lv.strength = {"score": 0.9, "touches": 5, "rejections": 5,
                   "breaks": 0, "available": True}
    assert len(lv.sources) == before
