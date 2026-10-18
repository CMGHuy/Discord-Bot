"""v171 D8: refresh_all batches stale warm symbols per timeframe chunk; layer
off, force and cold symbols keep today's per-symbol path."""
import os
import time

import numpy as np
import pandas as pd
import pytest

from swingbot import config
from swingbot.core.marketdata import data_refresh as rf, data_store, yf_safe
from swingbot.core.marketdata.providers import router
from swingbot.core.marketdata.shared.kinds import Asker


def _frame(start, periods):
    idx = pd.bdate_range(start, periods=periods)
    v = 100.0 + np.arange(periods, dtype=float)
    return pd.DataFrame({"Open": v, "High": v + 1, "Low": v - 1, "Close": v, "Volume": 1e6}, index=idx)


@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "count")
    monkeypatch.setattr(config, "BATCH_FETCH_CHUNK_SIZE", 2)
    for s in ("AAA", "BBB", "CCC"):
        data_store.save_to_disk(_frame("2026-09-01", 20), s, "daily", base_dir=str(tmp_path))
        old = time.time() - 13 * 3600
        os.utime(data_store.cache_path(s, "daily", base_dir=str(tmp_path)), (old, old))
    return str(tmp_path)


@pytest.fixture
def downloads(monkeypatch):
    calls = []
    fresh = _frame("2026-09-28", 3)                     # Sep 28 (= last cached bar), 29, 30

    def download(tickers, **kw):
        syms = tickers.split()
        calls.append((syms, kw, router.current_asker()))
        return pd.concat({s: fresh for s in syms}, axis=1)
    monkeypatch.setattr(yf_safe, "download", download)
    return calls


@pytest.fixture
def per_symbol(monkeypatch):
    calls = []

    def fake(symbol, timeframe, base_dir=None, force=False, state=None):
        calls.append(symbol)
        return {"symbol": symbol, "timeframe": "daily", "rows": 0, "added": 0, "status": "fresh"}
    monkeypatch.setattr(rf, "refresh_symbol", fake)
    return calls


def _run(base, symbols=("AAA", "BBB", "CCC"), **kw):
    return rf.refresh_all(list(symbols), ["daily"], base_dir=base, state={}, persist_state=False, **kw)


def test_one_download_per_chunk_with_refresh_symbol_shaped_results(base, downloads, per_symbol):
    out = _run(base)
    assert [c[0] for c in downloads] == [["AAA", "BBB"], ["CCC"]] and per_symbol == []
    kw = downloads[0][1]
    assert (kw["start"], kw["interval"], kw["group_by"], kw["auto_adjust"]) == ("2026-09-28", "1d", "ticker", True)
    assert out["summary"]["daily"]["incremental"] == 3 and out["summary"]["daily"]["added"] == 6
    assert len(data_store.load_from_disk("AAA", "daily", base_dir=base)) == 22


def test_layer_off_keeps_the_per_symbol_path(monkeypatch, base, downloads, per_symbol):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "off")
    _run(base)
    assert per_symbol == ["AAA", "BBB", "CCC"] and downloads == []


def test_force_and_cold_symbols_take_the_per_symbol_path(base, downloads, per_symbol):
    _run(base, symbols=("AAA", "DDD"))
    assert per_symbol == ["DDD"]
    per_symbol.clear()
    _run(base, force=True)
    assert per_symbol == ["AAA", "BBB", "CCC"]


def test_a_failed_batch_falls_back_per_symbol(monkeypatch, base, per_symbol):
    monkeypatch.setattr(yf_safe, "download", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    _run(base)
    assert per_symbol == ["AAA", "BBB", "CCC"]


def test_budget_deferred_fails_the_chunk_without_per_symbol_retries(monkeypatch, base, per_symbol):
    def deferred(*a, **k):
        raise yf_safe.BudgetDeferred("tier 4")
    monkeypatch.setattr(yf_safe, "download", deferred)
    out = _run(base)
    assert per_symbol == []
    assert out["summary"]["daily"]["failed"] == 3
    assert {e for _, _, e in out["failures"]} == {"budget-deferred"}


def test_batched_pairs_are_not_paced_and_run_at_background_tier(monkeypatch, base, downloads, per_symbol):
    slept = []
    monkeypatch.setattr(rf.time, "sleep", lambda s: slept.append(s))
    _run(base, sleep_seconds=5.0)
    assert slept == [] and {c[2] for c in downloads} == {Asker.BACKGROUND}


def test_a_pair_inside_its_window_is_not_batched(base, downloads, per_symbol):
    now = time.time()
    os.utime(data_store.cache_path("BBB", "daily", base_dir=base), (now, now))
    _run(base)
    assert [c[0] for c in downloads] == [["AAA", "CCC"]] and per_symbol == ["BBB"]
