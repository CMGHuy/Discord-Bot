"""v245 V245-10: the prefix cache never changes `_scan_one`'s output.

Over successive truncations of a long frame, with one cache carried across
them the way live scans carry it across days, and with the live price varied
inside a day, the cache-on snapshot equals the cache-off snapshot exactly.
Cached values are frozen; no scan can change them.
"""
import copy
import dataclasses
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from swingbot.core.market import trendlines
from swingbot.core.market.levels import Level
from swingbot.core.market.strategy_types import LEGACY_HORIZONS
from swingbot.core.scanning import analyze, structure
from swingbot.core.scanning.structure import StructureCache
from tests.scanning.test_engine_v2_plans import _structured_df
from tests.scanning.v245_golden_cases import (CASE_BY_NAME, GOLDEN_NOW, HERMETIC_IO, TICKER, GoldenCase,
                                              first_diff, frozen_clock, run_case, snapshot)

WAVE = CASE_BY_NAME["wave_forming"].frame      # 421 rows, last row dated 2024-03-15
LONG = CASE_BY_NAME["long_forming"].frame      # 1561 rows: longer than MAX_PIVOT_SCAN_BARS


def _at(day, hour: int, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=timezone.utc)


def _intraday(df, hour: int = 19, minute: int = 0) -> datetime:
    """A clock on the last row's own date: that row is today's forming bar."""
    return _at(df.index[-1].date(), hour, minute)


def _next_morning(df) -> datetime:
    """13:00 UTC the next business day: the last row is yesterday's completed bar."""
    return _at((df.index[-1] + pd.offsets.BDay(1)).date(), 13)


def _case(df: pd.DataFrame, mult: float) -> GoldenCase:
    price = round(float(df["Close"].iloc[-1]) * mult, 4)
    return GoldenCase(f"n{len(df)}x{mult}", lambda: df.copy(), tuple(LEGACY_HORIZONS), None, False,
                      lambda _frame: price)


def _same(monkeypatch, df, mult, now, cache, label) -> None:
    """One scan with the cache and one without: same frame, price and clock."""
    frozen_clock(monkeypatch, now)
    case = _case(df, mult)
    cached = run_case(case, structure=cache, now=now)
    plain = run_case(case, structure=None, now=now)
    assert cached == plain, f"{label}: {first_diff(cached, plain)}"


def _sweep(monkeypatch, base: pd.DataFrame, lengths) -> StructureCache:
    cache = StructureCache(1000)                     # carried across every day, as live scans do
    for n in lengths:
        df = base.iloc[:n].copy()
        for mult in (1.0, 0.96):                     # at the close, then through a nearer stop
            _same(monkeypatch, df, mult, _intraday(df), cache, f"n={n} intraday x{mult}")
        _same(monkeypatch, df, 1.0, _next_morning(df), cache, f"n={n} next morning")
    return cache


def test_wave_sweep_cache_on_equals_cache_off(monkeypatch):
    cache = _sweep(monkeypatch, WAVE(), (419, 420, 421))
    assert cache.stats()["cache_hits"] > 0           # the warm path really ran


@pytest.mark.slow
def test_long_sweep_crosses_the_trim(monkeypatch):
    cache = _sweep(monkeypatch, LONG(), (1499, 1500, 1501, 1561))
    assert cache.stats()["cache_hits"] > 0


def _half_day(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    o, c = float(out["Open"].iloc[-1]), float(out["Close"].iloc[-1])
    out.iloc[-1, out.columns.get_loc("High")] = round(max(o, c) * 1.002, 4)
    out.iloc[-1, out.columns.get_loc("Low")] = round(min(o, c) * 0.998, 4)
    out.iloc[-1, out.columns.get_loc("Volume")] = round(float(out["Volume"].iloc[-2]) * 0.3)
    return out


def test_half_day_bar(monkeypatch):
    cache = StructureCache(100)
    df = _half_day(WAVE())
    for mult in (1.0, 1.012):
        _same(monkeypatch, df, mult, _intraday(df, 18, 30), cache, f"half day x{mult}")


def test_intraday_scans_hit_every_entry(monkeypatch):
    frozen_clock(monkeypatch, GOLDEN_NOW)
    df, cache = WAVE(), StructureCache(100)
    run_case(_case(df, 1.0), structure=cache)
    entries = cache.stats()["cache_entries"]
    cache.reset_counters()
    run_case(_case(df, 0.96), structure=cache)
    stats = cache.stats()
    assert entries >= len(structure.TRENDLINE_UNITS)
    assert (stats["cache_hits"], stats["cache_misses"]) == (entries, 0)


def test_a_new_day_misses_every_unit(monkeypatch):
    frozen_clock(monkeypatch, GOLDEN_NOW)
    base, cache = WAVE(), StructureCache(100)
    run_case(_case(base.iloc[:420].copy(), 1.0), structure=cache)
    cache.reset_counters()
    run_case(_case(base, 1.0), structure=cache)      # one more session: every prefix moved
    assert cache.stats()["cache_hits"] == 0


def test_restated_history_misses(monkeypatch):
    frozen_clock(monkeypatch, GOLDEN_NOW)
    df, cache = WAVE(), StructureCache(100)
    run_case(_case(df, 1.0), structure=cache)
    split = df.copy()
    ohlc = ["Open", "High", "Low", "Close"]
    split[ohlc] = (split[ohlc] * 0.5).round(4)
    split["Volume"] = split["Volume"] * 2
    cache.reset_counters()
    _same(monkeypatch, split, 1.0, GOLDEN_NOW, cache, "2:1 split")
    assert cache.stats()["cache_hits"] == 0


def _revised(df: pd.DataFrame) -> pd.DataFrame:
    """Lower one mid-history low pivot's Close and Low by 3 %. The first and
    last prefix rows are untouched, so prefix_fingerprint cannot see it."""
    trimmed, trim_start = trendlines.trimmed_frame(df)
    pivots = trendlines._volume_confirmed_pivots(trimmed, "low")
    bar = trim_start + pivots[len(pivots) // 2][0]
    out = df.copy()
    for col in ("Close", "Low"):
        out.iloc[bar, out.columns.get_loc(col)] = round(float(out[col].iloc[bar]) * 0.97, 4)
    return out


def test_revision_behind_an_unchanged_fingerprint(monkeypatch):
    frozen_clock(monkeypatch, GOLDEN_NOW)
    df, cache = WAVE(), StructureCache(100)
    revised = _revised(df)
    m = len(df) - 1
    assert structure.prefix_fingerprint(df, m) == structure.prefix_fingerprint(revised, m)
    assert trendlines._volume_confirmed_pivots(revised, "low") != trendlines._volume_confirmed_pivots(df, "low")
    run_case(_case(df, 1.0), structure=cache)
    cache.reset_counters()
    _same(monkeypatch, revised, 1.0, GOLDEN_NOW, cache, "mid-history revision")
    assert cache.stats()["cache_hits"] > 0           # the stale entry was served by key, then verified


def _assert_frozen(value, path: str = "entry") -> None:
    if value is None or isinstance(value, (str, bytes, bool, int, float, np.generic)):
        return
    if isinstance(value, tuple):
        for i, item in enumerate(value):
            _assert_frozen(item, f"{path}[{i}]")
        return
    if isinstance(value, Level):                     # spec: a cached Level carries tuple sources
        assert isinstance(value.sources, tuple), f"{path}.sources is {type(value.sources).__name__}"
        _assert_frozen(value.sources, f"{path}.sources")
        return
    if dataclasses.is_dataclass(value) and value.__dataclass_params__.frozen:
        for field in dataclasses.fields(value):
            _assert_frozen(getattr(value, field.name), f"{path}.{field.name}")
        return
    raise AssertionError(f"{path}: {type(value).__name__} is mutable")


def test_cached_values_are_frozen(monkeypatch):
    frozen_clock(monkeypatch, GOLDEN_NOW)
    for frame in (WAVE, LONG):
        df, cache = frame(), StructureCache(100)
        values = structure.ticker_prefixes(cache, TICKER, df)
        assert values
        for name, value in values.items():
            _assert_frozen(value, name)


HF = {"min_reward_pct": 0.5, "max_stop_loss_pct": 50.0, "min_stop_distance_pct": 0.0,
      "min_risk_reward_ratio": 0.01, "mtf_adjacent_gate": False, "confluence_deviation_pct": 1.0}


@pytest.fixture
def loose(monkeypatch):
    monkeypatch.setitem(analyze.HORIZONS["4w"], "sr_target_min_pct", 1.0)


def _scan(df, price, cache) -> dict:
    return analyze._scan_one("T0", df, ["4w"], None, None, 0, 0, live_prices={"T0": price},
                             hard_filters=dict(HF), io=HERMETIC_IO, structure=cache, now=GOLDEN_NOW)


def _vandalise(stats: dict) -> int:
    """Mutate everything a caller can reach in a scan's items; returns how much."""
    touched = 0
    for item in stats["items"]:
        if isinstance(item.trendline_candidates, list):
            item.trendline_candidates.append((1.0, "vandal"))
            touched += 1
        for side in item.level_map or ():
            for level in side:
                level.sources.append("vandal")
                touched += 1
    return touched


def test_two_prices_against_one_entry_are_independent(loose, monkeypatch):
    frozen_clock(monkeypatch, GOLDEN_NOW)
    df, cache = _structured_df(), StructureCache(10)
    close = float(df["Close"].iloc[-1])
    first = _scan(df, close, cache)
    entries = structure.ticker_prefixes(cache, "T0", df)
    before = copy.deepcopy(entries)
    assert _vandalise(first) > 0, "the structured frame must build items with a level map"
    second = snapshot(_scan(df, close * 1.01, cache))
    plain = snapshot(_scan(df, close * 1.01, None))
    assert second == plain, first_diff(second, plain)
    after = structure.ticker_prefixes(cache, "T0", df)
    assert after == before
    assert all(after[name] is entries[name] for name in entries)   # the same objects, unchanged
