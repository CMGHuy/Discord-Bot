"""v245 V245-7: the analysis prefix cache, its key and its invalidation."""
import logging
import threading

import pandas as pd
import pytest

from swingbot import bot_core, config
from swingbot.core.infra import store_generation
from swingbot.core.scanning import structure
from swingbot.core.scanning.structure import StructureCache, prefix_fingerprint


def _frame(n: int = 40, start: str = "2024-01-02") -> pd.DataFrame:
    idx = pd.bdate_range(start, periods=n)
    close = pd.Series([100.0 + i for i in range(n)], index=idx)
    return pd.DataFrame({"Open": close - 0.5, "High": close + 1.0, "Low": close - 1.0,
                         "Close": close, "Volume": 1_000_000.0}, index=idx)


@pytest.fixture
def fresh(monkeypatch):
    cache = StructureCache(3)
    monkeypatch.setattr(structure, "STRUCTURE_CACHE", cache)
    monkeypatch.setattr(config, "STRUCTURE_CACHE_MAX", 3, raising=False)
    return cache


# --- key -------------------------------------------------------------------

def test_fingerprint_ignores_rows_after_the_prefix():
    df = _frame()
    moved = df.copy()
    moved.iloc[-1, moved.columns.get_loc("Close")] += 5.0     # the forming bar moves
    assert prefix_fingerprint(df, 39) == prefix_fingerprint(moved, 39)


@pytest.mark.parametrize("change", ["new_bar", "restated_history", "revised_volume", "trim_start"])
def test_fingerprint_changes_with_the_prefix(change):
    df = _frame(41)
    base = prefix_fingerprint(df.iloc[:40], 39)
    if change == "new_bar":
        other = prefix_fingerprint(df, 40)
    elif change == "restated_history":                       # a split adjusts the whole series
        other = prefix_fingerprint(df.iloc[:40] * 0.5, 39)
    elif change == "revised_volume":
        revised = df.iloc[:40].copy()
        revised.iloc[38, revised.columns.get_loc("Volume")] = 1_234_567.0
        other = prefix_fingerprint(revised, 39)
    else:                                                    # the 1500-bar trim moved one session
        other = prefix_fingerprint(df.iloc[1:41], 39)
    assert other != base


def test_fingerprint_of_an_empty_prefix():
    assert prefix_fingerprint(_frame(), 0) == (0,)


def test_fingerprint_without_volume_column():
    fp = prefix_fingerprint(_frame().drop(columns=["Volume"]), 10)
    assert fp[0] == 10 and fp[-1] is None


# --- cache -----------------------------------------------------------------

def test_hit_on_the_same_key_and_miss_counts():
    cache = StructureCache(4)
    key = ("AAA", "trendline:support", (1,))
    assert cache.get(key) is None
    cache.put(key, ("value",))
    assert cache.get(key) == ("value",)
    assert cache.stats() == {"cache_hits": 1, "cache_misses": 1, "cache_evictions": 0, "cache_entries": 1}


def test_miss_on_a_changed_fingerprint_and_on_an_absent_horizon():
    cache = StructureCache(4)
    cache.put(("AAA", "unit:4w", (1,)), "4w")
    assert cache.get(("AAA", "unit:4w", (2,))) is None       # new prefix
    assert cache.get(("AAA", "unit:2w", (1,))) is None       # horizon not in the entry
    assert cache.get(("BBB", "unit:4w", (1,))) is None       # other ticker


def test_lru_eviction_drops_the_least_recently_used():
    cache = StructureCache(2)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.get("a")                                            # a is now most recent
    cache.put("c", 3)
    assert cache.get("b") is None and cache.get("a") == 1 and cache.get("c") == 3
    assert cache.stats()["cache_evictions"] == 1


def test_none_is_never_stored():
    cache = StructureCache(2)
    cache.put("a", None)
    assert cache.stats()["cache_entries"] == 0


def test_get_or_build_builds_once_then_hits():
    cache = StructureCache(2)
    calls = []

    def build():
        calls.append(1)
        return ("built",)

    assert cache.get_or_build("k", build, ticker="AAA") == ("built",)
    assert cache.get_or_build("k", build, ticker="AAA") == ("built",)
    assert len(calls) == 1
    assert cache.prefix_build_s >= 0.0


def test_build_failure_warns_with_the_ticker_and_stores_nothing(caplog):
    cache = StructureCache(2)

    def boom():
        raise ValueError("bad frame")

    with caplog.at_level(logging.WARNING, logger=structure.__name__):
        assert cache.get_or_build(("AAA", "trendline:support", (1,)), boom, ticker="AAA") is None
    assert "AAA" in caplog.text and "trendline:support" in caplog.text
    assert cache.stats()["cache_entries"] == 0


def test_clear_resize_and_reset_counters():
    cache = StructureCache(5)
    for k in "abcde":
        cache.put(k, k)
    cache.resize(2)
    assert cache.stats()["cache_entries"] == 2 and cache.max_entries == 2
    assert cache.get("e") == "e" and cache.get("a") is None
    cache.clear()
    assert cache.stats()["cache_entries"] == 0
    cache.reset_counters()
    assert cache.stats() == {"cache_hits": 0, "cache_misses": 0, "cache_evictions": 0, "cache_entries": 0}
    assert cache.prefix_build_s == 0.0


def test_concurrent_get_and_put_from_two_threads():
    cache = StructureCache(50)
    errors = []

    def worker(offset):
        try:
            for i in range(2000):
                key = (offset + i) % 120
                cache.put(key, (key,))
                value = cache.get(key)
                assert value is None or value == (key,)
        except Exception as exc:          # surfaced below; a thread cannot fail the test itself
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n * 7,)) for n in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    stats = cache.stats()
    assert not errors
    assert stats["cache_entries"] <= 50
    assert stats["cache_hits"] + stats["cache_misses"] == 4000


# --- mode, config, reload ---------------------------------------------------

def test_cache_for_mode(fresh):
    assert structure.cache_for_mode("off") is None
    assert structure.cache_for_mode("shadow") is fresh
    assert structure.cache_for_mode("on") is fresh


def test_config_fields_parse_and_fall_back():
    fields = {f.attr: f for f in config.FIELDS}
    assert config._cast(fields["ANALYSIS_CACHE"], "ON") == "on"
    assert config._cast(fields["ANALYSIS_CACHE"], "bogus") == "off"
    assert fields["ANALYSIS_CACHE"].default == "off"
    assert isinstance(config._cast(fields["STRUCTURE_CACHE_MAX"], "250"), int)
    assert fields["ANALYSIS_CACHE"].hot_reloadable and fields["STRUCTURE_CACHE_MAX"].hot_reloadable


def test_a_moved_settings_generation_clears_on_the_next_scan(fresh):
    structure.cache_for_mode("on")
    fresh.put("a", 1)
    store_generation.bump("settings")              # any reload path that changed a value
    assert structure.cache_for_mode("on").stats()["cache_entries"] == 0


def test_a_new_cap_resizes_on_the_next_scan(fresh, monkeypatch):
    structure.cache_for_mode("on")
    for k in "abc":
        fresh.put(k, k)
    monkeypatch.setattr(config, "STRUCTURE_CACHE_MAX", 1)
    assert structure.cache_for_mode("on").stats()["cache_entries"] == 1


def test_apply_config_change_clears_and_resizes(fresh, monkeypatch):
    fresh.put("a", 1)
    structure.apply_config_change({})
    assert fresh.stats()["cache_entries"] == 1                # nothing changed: kept
    monkeypatch.setattr(config, "STRUCTURE_CACHE_MAX", 7)
    structure.apply_config_change({"STRUCTURE_CACHE_MAX": (3, 7)})
    assert fresh.stats()["cache_entries"] == 0 and fresh.max_entries == 7


def test_sighup_clears_through_the_loops_callback(fresh, monkeypatch):
    from swingbot.commands.scanning import loops
    assert loops._apply_structure_cache_change in bot_core._reload_callbacks
    monkeypatch.setattr(bot_core, "_reload_callbacks", [loops._apply_structure_cache_change])
    monkeypatch.setattr(bot_core.config, "reload", lambda: {"MIN_RISK_REWARD_RATIO": (1.5, 2.0)})
    fresh.put("a", 1)
    bot_core._handle_reload_signal()
    assert fresh.stats()["cache_entries"] == 0
