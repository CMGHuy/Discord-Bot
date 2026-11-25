"""v245 V245-9: the prefix cache and one `now` reach `_scan_one` at the two live call sites."""
import logging
from datetime import timedelta
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.market import trendlines
from swingbot.core.scanning import analyze, scan_run, short_run, structure
from swingbot.core.scanning.structure import StructureCache
from tests.scanning.test_engine_v2_plans import _structured_df
from tests.scanning.test_mtf_gate import _scan_with_funnel
from tests.scanning.v245_golden_cases import (CASES, GOLDEN_NOW, HERMETIC_IO, first_diff,
                                              frozen_clock, load_golden, run_case)
from tests.store_seed import seed_store

HF = {"min_reward_pct": 0.5, "max_stop_loss_pct": 50.0, "min_stop_distance_pct": 0.0,
      "min_risk_reward_ratio": 0.01, "mtf_adjacent_gate": False, "confluence_deviation_pct": 1.0}
LONG = next(c for c in CASES if c.name == "long_completed")


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
def test_cache_on_matches_the_golden_cold_and_warm(case, monkeypatch):
    frozen_clock(monkeypatch)
    golden = load_golden()[case.name]
    cache = StructureCache(100)
    for _ in range(2):                                   # cold (builds), then warm (hits)
        got = run_case(case, structure=cache)
        assert got == golden, first_diff(got, golden)


def test_a_warm_scan_hits_every_unit(monkeypatch):
    frozen_clock(monkeypatch)
    cache = StructureCache(100)
    run_case(LONG, structure=cache)
    cache.reset_counters()
    run_case(LONG, structure=cache)
    assert cache.stats()["cache_hits"] == len(structure.PREFIX_UNITS) and cache.stats()["cache_misses"] == 0


def test_a_failing_prefix_build_warns_and_computes_uncached(monkeypatch, caplog):
    frozen_clock(monkeypatch)

    def boom(*args, **kwargs):
        raise ValueError("bad prefix")

    monkeypatch.setattr(trendlines, "build_trendline_prefix", boom)
    cache = StructureCache(100)
    with caplog.at_level(logging.WARNING, logger=structure.__name__):
        got = run_case(LONG, structure=cache)
    assert got == load_golden()[LONG.name]
    assert "GOLD" in caplog.text and cache.stats()["cache_entries"] == len(structure.PREFIX_UNITS) - len(structure.TRENDLINE_UNITS)


def test_now_reaches_both_clock_readers(monkeypatch):
    seen = []
    real_band, real_dryup = analyze._band_live, analyze._apply_pullback_dryup

    def band(*args, **kwargs):
        seen.append(("band", args[3]))
        return real_band(*args, **kwargs)

    def dryup(*args, **kwargs):
        seen.append(("dryup", kwargs.get("now")))
        return real_dryup(*args, **kwargs)

    monkeypatch.setattr(analyze, "_band_live", band)
    monkeypatch.setattr(analyze, "_apply_pullback_dryup", dryup)
    when = GOLDEN_NOW + timedelta(days=3)
    run_case(LONG, now=when)
    assert {name for name, _ in seen} == {"band", "dryup"}
    assert all(value == when for _, value in seen)


@pytest.fixture
def loose(monkeypatch):
    monkeypatch.setitem(analyze.HORIZONS["4w"], "sr_target_min_pct", 1.0)


def _items(df, cache):
    stats = analyze._scan_one("T0", df, ["4w"], None, None, 0, 0, hard_filters=dict(HF),
                              io=HERMETIC_IO, structure=cache, now=GOLDEN_NOW)
    assert stats["items"], "the structured frame must build a 4w scenario"
    return stats["items"]


def test_items_carry_prefix_results_and_rescenario_never_looks_up(loose, monkeypatch):
    df = _structured_df()
    cached_items, plain_items = _items(df, StructureCache(10)), _items(df, None)
    assert set(cached_items[0].prefix_results) == {unit.name for unit in structure.PREFIX_UNITS}
    assert plain_items[0].prefix_results is None

    def no_lookup(*args, **kwargs):
        raise AssertionError("rescenario must not look the cache up")

    monkeypatch.setattr(structure, "ticker_prefixes", no_lookup)
    for cached, plain in zip(cached_items, plain_items):
        for price in (cached.scan_price, cached.scan_price * 1.01):
            a, b = analyze.rescenario(cached, df, price), analyze.rescenario(plain, df, price)
            assert (a is None) == (b is None)
            if a is not None:
                assert (a.direction, a.entry, a.stop_loss, a.take_profit) == \
                    (b.direction, b.entry, b.stop_loss, b.take_profit)
                assert cached.level_map == plain.level_map


@pytest.mark.parametrize("mode,expect", [("off", False), ("shadow", True), ("on", True)])
def test_analysis_cache_follows_the_mode(mode, expect, monkeypatch):
    fresh = StructureCache(5)
    monkeypatch.setattr(structure, "STRUCTURE_CACHE", fresh)
    monkeypatch.setattr(config, "ANALYSIS_CACHE", mode)
    got_mode, cache = scan_run._analysis_cache()
    assert got_mode == mode and (cache is fresh) == expect


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """test_mtf_gate.py's isolate_data_dir, requested explicitly."""
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    seed_store("account", {
        "balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0, "sizing_mode": "risk_pct",
        "balance_history": [{"ts": "2026-08-01T00:00:00+00:00", "balance": 10000.0}],
    })


@pytest.mark.parametrize("mode", ["off", "on"])
def test_base_lane_passes_the_cache_and_one_now(mode, data_dir, monkeypatch):
    fresh = StructureCache(10)
    monkeypatch.setattr(structure, "STRUCTURE_CACHE", fresh)
    monkeypatch.setattr(config, "ANALYSIS_CACHE", mode)
    seen = []
    real = analyze._scan_one

    def spy(*args, **kwargs):
        seen.append((kwargs.get("structure"), kwargs.get("now")))
        return real(*args, **kwargs)

    monkeypatch.setattr(analyze, "_scan_one", spy)
    _scan_with_funnel("bullish")
    assert seen
    assert all(s is (fresh if mode == "on" else None) for s, _ in seen)
    assert len({n for _, n in seen}) == 1 and seen[0][1].tzinfo is not None


def test_extra_lane_passes_its_context_cache_and_no_now(monkeypatch):
    seen = {}

    def spy(*args, **kwargs):
        seen.update(kwargs)
        return {"newly_closed": [], "near_close_warnings": [], "funnel_events": [], "items": []}

    monkeypatch.setattr(analyze, "_scan_one", spy)
    monkeypatch.setattr(analyze, "align_completed", lambda frame, spy_df, _x, _now: (frame, spy_df, None))
    cache = StructureCache(1)
    ctx = analyze.ExtraScanContext(regime=None, min_confluence=0, min_confidence=0, rs_cache=None,
                                   spy_df=None, live_prices={}, hard_filters=None, opex_tier=None,
                                   io=HERMETIC_IO, structure=cache)
    analyze.scan_extra_candidate(SimpleNamespace(ticker="XYZ", source="s", mode="m"), object(), ctx, ["4w"])
    assert seen["structure"] is cache and "now" not in seen


def test_replay_contexts_carry_no_cache():
    ctx = analyze.ExtraScanContext(regime=None, min_confluence=0, min_confidence=0, rs_cache=None,
                                   spy_df=None, live_prices={}, hard_filters=None, opex_tier=None)
    assert ctx.structure is None


def test_short_lane_context_takes_the_scan_cache(monkeypatch):
    cache = StructureCache(1)
    monkeypatch.setattr(scan_run, "_analysis_cache", lambda: ("on", cache))
    monkeypatch.setattr(short_run.opex, "current_tier", lambda: None)
    monkeypatch.setattr(short_run.opex, "effective_min_confluence", lambda n, tier: n)
    monkeypatch.setattr(short_run.opex, "effective_min_confidence_level", lambda tier: 0)
    monkeypatch.setattr(scan_run, "_hard_filters_snapshot", lambda params=None: {})
    reference = SimpleNamespace(reference_rels=[], spy=None, now=None)
    ctx = short_run._scan_context(reference, SimpleNamespace(min_target_confluence_count=2), {}, None)
    assert ctx.structure is cache
