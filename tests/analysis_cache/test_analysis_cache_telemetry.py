"""v245 V245-12: analysis-cache telemetry -- cache_* counters,
phases_s.analysis_prefix, rss_mb and the Scan pass summary."""
import logging
import sys

import pytest

from swingbot import config
from swingbot.core.scanning import scan_run, structure, telemetry
from swingbot.core.scanning.structure import StructureCache
from tests.scanning.test_mtf_gate import _scan_with_funnel
from tests.store_seed import seed_store

COUNTERS = ("cache_hits", "cache_misses", "cache_evictions", "cache_entries")


def test_rss_mb_reads_vmrss_in_megabytes(tmp_path):
    status = tmp_path / "status"
    status.write_text("Name:\tpython\nVmPeak:\t  999999 kB\nVmRSS:\t  409600 kB\nThreads:\t4\n",
                      encoding="ascii")
    assert structure.rss_mb(str(status)) == 400.0


@pytest.mark.parametrize("body", ["Name:\tpython\n", "VmRSS:\tlots kB\n", "VmRSS:\n"])
def test_rss_mb_is_none_without_a_readable_vmrss(tmp_path, body):
    status = tmp_path / "status"
    status.write_text(body, encoding="ascii")
    assert structure.rss_mb(str(status)) is None


def test_rss_mb_is_none_where_the_file_is_missing(tmp_path):
    assert structure.rss_mb(str(tmp_path / "missing")) is None


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="/proc/self/status is Linux-only")
def test_rss_mb_reads_this_process_on_linux():
    value = structure.rss_mb()
    assert isinstance(value, float) and value > 0


def _warm(cache: StructureCache) -> StructureCache:
    cache.put(("T", "u", (1,)), ("v",))
    cache.get(("T", "u", (1,)))          # one hit
    cache.get(("T", "u", (2,)))          # one miss
    return cache


def test_cache_telemetry_with_a_cache(monkeypatch):
    monkeypatch.setattr(structure, "rss_mb", lambda: 321.5)
    assert scan_run._cache_telemetry("on", _warm(StructureCache(5))) == {
        "cache_mode": "on", "cache_hits": 1, "cache_misses": 1, "cache_evictions": 0,
        "cache_entries": 1, "rss_mb": 321.5}


def test_cache_telemetry_without_a_cache(monkeypatch):
    monkeypatch.setattr(structure, "rss_mb", lambda: None)
    assert scan_run._cache_telemetry("off", None) == {
        "cache_mode": "off", **dict.fromkeys(COUNTERS), "rss_mb": None}


def test_start_resets_the_counters_and_the_build_timer(monkeypatch):
    cache = _warm(StructureCache(5))
    cache.prefix_build_s = 1.5
    monkeypatch.setattr(scan_run, "_analysis_cache", lambda: ("on", cache))
    assert scan_run._start_analysis_cache() == ("on", cache)
    assert cache.stats() == {"cache_hits": 0, "cache_misses": 0, "cache_evictions": 0, "cache_entries": 1}
    assert cache.prefix_build_s == 0.0


def test_start_without_a_cache(monkeypatch):
    monkeypatch.setattr(scan_run, "_analysis_cache", lambda: ("off", None))
    assert scan_run._start_analysis_cache() == ("off", None)


def test_analysis_prefix_seconds():
    cache = StructureCache(5)
    cache.prefix_build_s = 0.12345
    assert scan_run._analysis_prefix_s(cache) == 0.123
    assert scan_run._analysis_prefix_s(None) == 0.0


def test_cache_summary_text():
    assert scan_run._cache_summary("shadow", _warm(StructureCache(5))) == \
        "analysis cache shadow: 1 hit(s), 1 miss(es)"
    assert scan_run._cache_summary("off", None) == "analysis cache off"


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """test_mtf_gate.py's isolate_data_dir, requested explicitly."""
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    seed_store("account", {
        "balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0, "sizing_mode": "risk_pct",
        "balance_history": [{"ts": "2026-08-01T00:00:00+00:00", "balance": 10000.0}],
    })


def _rows(monkeypatch) -> list:
    rows: list = []
    monkeypatch.setattr(telemetry, "log_scan_telemetry", lambda stats, path=None: rows.append(stats))
    monkeypatch.setattr(telemetry, "scan_slowdown", lambda *args, **kwargs: False)
    return rows


def test_scan_rows_carry_the_cache_fields_cold_then_warm(data_dir, monkeypatch, caplog):
    monkeypatch.setattr(structure, "STRUCTURE_CACHE", StructureCache(50))
    monkeypatch.setattr(config, "ANALYSIS_CACHE", "on")
    rows = _rows(monkeypatch)
    with caplog.at_level(logging.INFO, logger=scan_run.log.name):
        _scan_with_funnel("bullish")
        _scan_with_funnel("bullish")             # same frame: every unit hits
    assert len(rows) == 2, caplog.text           # a swallowed telemetry error shows up here
    cold, warm = rows
    assert cold["cache_mode"] == "on" and cold["cache_hits"] == 0 and cold["cache_misses"] > 0
    assert (warm["cache_hits"], warm["cache_misses"]) == (cold["cache_misses"], 0)
    assert warm["cache_entries"] == cold["cache_entries"] > 0
    assert cold["phases_s"]["analysis_prefix"] >= 0.0 and warm["phases_s"]["analysis_prefix"] == 0.0
    assert "rss_mb" in warm and "analysis" in warm["phases_s"]
    assert "analysis cache on: 0 hit(s)" in caplog.text
    assert f"analysis cache on: {cold['cache_misses']} hit(s), 0 miss(es)" in caplog.text


def test_scan_rows_without_a_cache(data_dir, monkeypatch):
    monkeypatch.setattr(config, "ANALYSIS_CACHE", "off")
    rows = _rows(monkeypatch)
    _scan_with_funnel("bullish")
    (row,) = rows
    assert row["cache_mode"] == "off" and all(row[key] is None for key in COUNTERS)
    assert row["phases_s"]["analysis_prefix"] == 0.0
