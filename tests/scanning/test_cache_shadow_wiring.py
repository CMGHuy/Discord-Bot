"""v245 V245-14: the shadow comparison wired into the base-lane scan."""
import logging
import zlib
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.infra import swallowed as sw
from swingbot.core.scanning import analyze, cache_shadow, scan_run, structure, telemetry
from swingbot.core.scanning.structure import StructureCache
from tests.scanning import v245_golden_cases as golden
from tests.scanning.test_mtf_gate import _scan_with_funnel
from tests.store_seed import seed_store

NOW = datetime(2026, 11, 23, 15, 0, tzinfo=timezone.utc)
SEQ = zlib.crc32(b"T") % 3            # the scan number on which ticker "T" is sampled
KWARGS = {"horizons_to_scan": ["4w"], "progress": "PROGRESS", "regime": None,
          "effective_min_confluence": 0, "effective_min_confidence": 0, "live_prices": {"T": 101.0}}


def _stats(entry=100.0):
    item = SimpleNamespace(
        result=SimpleNamespace(horizon_key="4w"),
        plan=SimpleNamespace(direction="bullish", entry=entry, stop_loss=95.0, take_profit=110.0),
        conf=SimpleNamespace(level=3, score=60), requirements=[], target_confluence=(2, ()),
        stop_confluence=(1, ()), trendline_candidates=[], all_requirements_met=True)
    return {"items": [item]}


@pytest.fixture
def calls(monkeypatch):
    """A fake `_scan_one` recording each call's kwargs; an uncached call
    (structure None) returns `calls.uncached_entry` as its entry."""
    seen = SimpleNamespace(log=[], uncached_entry=100.0)

    def fake(ticker, df, **kwargs):
        seen.log.append(kwargs)
        return _stats(seen.uncached_entry if kwargs.get("structure") is None else 100.0)

    monkeypatch.setattr(analyze, "_scan_one", fake)
    monkeypatch.setattr(cache_shadow, "write_diffs", lambda diffs, path: seen.log.append({"written": diffs}))
    return seen


def _ctx(mode, seq=SEQ):
    return scan_run._AnalysisCtx(mode, None if mode == "off" else StructureCache(4), NOW, seq)


def test_on_scans_once_with_the_cache_and_the_scan_clock(calls):
    ctx = _ctx("on")
    scan_run._scan_ticker("T", object(), KWARGS, ctx)
    (kwargs,) = calls.log
    assert kwargs["structure"] is ctx.cache and kwargs["now"] is NOW and kwargs["progress"] == "PROGRESS"
    assert "io" not in kwargs and ctx.compared == 0


def test_shadow_reruns_a_sampled_ticker_uncached_without_side_effects(calls):
    ctx = _ctx("shadow")
    stats = scan_run._scan_ticker("T", object(), KWARGS, ctx)
    cached, uncached, written = calls.log
    assert cached["structure"] is ctx.cache and cached["progress"] == "PROGRESS"
    assert uncached["structure"] is None and uncached["progress"] is None
    assert cached["now"] is uncached["now"] is NOW and uncached["live_prices"] is cached["live_prices"]
    assert uncached["io"].monitor_scan("T", None, 1.0) == ([], [])
    assert stats["items"][0].plan.entry == 100.0 and written == {"written": []}
    assert (ctx.compared, ctx.diffs) == (1, 0)


@pytest.mark.parametrize("seq, df", [(SEQ + 1, object()), (SEQ, None)])
def test_shadow_skips_unsampled_tickers_and_missing_frames(calls, seq, df):
    ctx = _ctx("shadow", seq=seq)
    scan_run._scan_ticker("T", df, KWARGS, ctx)
    assert len(calls.log) == 1 and ctx.compared == 0


def test_a_diff_is_counted_written_and_warned(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(analyze, "_scan_one",
                        lambda t, df, **kw: _stats(100.5 if kw.get("structure") is None else 100.0))
    path = tmp_path / "shadow.jsonl"
    monkeypatch.setattr(cache_shadow, "SHADOW_LOG_PATH", str(path))
    ctx = _ctx("shadow")
    with caplog.at_level(logging.WARNING, logger=scan_run.log.name):
        stats = scan_run._scan_ticker("T", object(), KWARGS, ctx)
    cache_shadow.close_writers()
    assert stats["items"][0].plan.entry == 100.0           # the cached result stays authoritative
    assert (ctx.compared, ctx.diffs) == (1, 1)
    (line,) = path.read_text(encoding="utf-8").splitlines()
    assert '"field": "entry"' in line
    assert "analysis cache shadow: T: 1 diff(s)" in caplog.text


def test_a_comparator_failure_is_swallowed(calls, monkeypatch):
    sw.reset()

    def boom(*args):
        raise RuntimeError("comparator")

    monkeypatch.setattr(cache_shadow, "compare_stats", boom)
    ctx = _ctx("shadow")
    stats = scan_run._scan_ticker("T", object(), KWARGS, ctx)
    assert stats["items"][0].plan.entry == 100.0 and (ctx.compared, ctx.diffs) == (0, 0)
    assert sw.snapshot()["scan.analysis_cache_shadow"]["count"] == 1
    sw.reset()


def test_the_rerun_logs_at_debug_only(calls, monkeypatch, caplog):
    def fake(ticker, df, **kwargs):
        analyze.log.info("plan rejected (%s)", "uncached" if kwargs["structure"] is None else "cached")
        return _stats()

    monkeypatch.setattr(analyze, "_scan_one", fake)
    with caplog.at_level(logging.INFO):
        scan_run._scan_ticker("T", object(), KWARGS, _ctx("shadow"))
    assert [r.getMessage() for r in caplog.records if "plan rejected" in r.getMessage()] == [
        "plan rejected (cached)"]


def test_new_ctx_and_shadow_telemetry(monkeypatch):
    monkeypatch.setattr(cache_shadow, "next_scan_seq", lambda: 7)
    assert scan_run._new_analysis_ctx("shadow", None).scan_seq == 7
    on = scan_run._new_analysis_ctx("on", None)
    assert on.scan_seq == 0 and on.scan_now.tzinfo is not None and (on.compared, on.diffs) == (0, 0)
    shadow = _ctx("shadow")
    shadow.compared, shadow.diffs = 31, 0
    assert scan_run._shadow_telemetry(shadow) == {"cache_compared": 31, "cache_diffs": 0}
    assert scan_run._shadow_telemetry(on) == {"cache_compared": None, "cache_diffs": None}


@pytest.mark.parametrize("name", ["wave_forming", "wave_completed_gate", "long_forming", "down_completed"])
def test_real_analysis_cached_and_uncached_agree_cold_and_warm(name, monkeypatch):
    case = golden.CASE_BY_NAME[name]
    df = case.frame()
    live = case.live_price(df)
    kwargs = {"horizons_to_scan": list(case.horizons), "regime": None,
              "effective_min_confluence": golden.MIN_CONFLUENCE,
              "effective_min_confidence": golden.MIN_CONFIDENCE,
              "live_prices": {golden.TICKER: live} if live else None,
              "hard_filters": {**golden.GOLDEN_HARD_FILTERS, "mtf_adjacent_gate": case.mtf_adjacent_gate,
                               "confluence_atr_stop_floor": case.atr_stop_floor},
              "allowed_directions": case.allowed_directions}
    monkeypatch.setattr(analyze, "LIVE_IO", golden.HERMETIC_IO)
    monkeypatch.setattr(cache_shadow, "write_diffs", lambda diffs, path: None)
    golden._pin_config_defaults(monkeypatch)
    seq = zlib.crc32(golden.TICKER.encode()) % 3
    shadow = scan_run._AnalysisCtx("shadow", StructureCache(20), golden.GOLDEN_NOW, seq)
    on = scan_run._AnalysisCtx("on", StructureCache(20), golden.GOLDEN_NOW, 0)
    shadow_progress, on_progress = scan_run.ScanProgress(), scan_run.ScanProgress()
    for _ in range(2):                                         # cold, then warm
        stats = scan_run._scan_ticker(golden.TICKER, df, {**kwargs, "progress": shadow_progress}, shadow)
        scan_run._scan_ticker(golden.TICKER, df, {**kwargs, "progress": on_progress}, on)
    assert (shadow.compared, shadow.diffs) == (2, 0)
    assert shadow_progress.done == on_progress.done           # the rerun never writes progress
    assert golden.first_diff(golden.snapshot(stats), golden.run_case(case)) is None
    if name == "wave_forming":
        assert stats["items"], "the comparison must cover real scenarios"


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """test_mtf_gate.py's isolate_data_dir, requested explicitly."""
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    seed_store("account", {
        "balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0, "sizing_mode": "risk_pct",
        "balance_history": [{"ts": "2026-08-01T00:00:00+00:00", "balance": 10000.0}],
    })


def _rows(monkeypatch, mode) -> list:
    rows: list = []
    monkeypatch.setattr(structure, "STRUCTURE_CACHE", StructureCache(50))
    monkeypatch.setattr(config, "ANALYSIS_CACHE", mode)
    monkeypatch.setattr(telemetry, "log_scan_telemetry", lambda stats, path=None: rows.append(stats))
    monkeypatch.setattr(telemetry, "scan_slowdown", lambda *args, **kwargs: False)
    return rows


def test_shadow_scan_rows_carry_compared_and_zero_diffs(data_dir, monkeypatch, tmp_path, caplog):
    rows = _rows(monkeypatch, "shadow")
    monkeypatch.setattr(cache_shadow, "in_sample", lambda ticker, seq: True)
    monkeypatch.setattr(cache_shadow, "SHADOW_LOG_PATH", str(tmp_path / "shadow.jsonl"))
    with caplog.at_level(logging.INFO):
        _scan_with_funnel("bullish")
        _scan_with_funnel("bullish")                           # cold, then warm
    assert len(rows) == 2, caplog.text                         # a swallowed telemetry error shows here
    assert [(r["cache_mode"], r["cache_compared"], r["cache_diffs"]) for r in rows] == [
        ("shadow", 1, 0), ("shadow", 1, 0)]
    assert not (tmp_path / "shadow.jsonl").exists()


def test_on_scan_rows_have_no_shadow_counts(data_dir, monkeypatch):
    rows = _rows(monkeypatch, "on")
    _scan_with_funnel("bullish")
    (row,) = rows
    assert (row["cache_compared"], row["cache_diffs"]) == (None, None)
