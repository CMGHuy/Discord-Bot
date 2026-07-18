"""Auto-cache-on-add: caching logic + that each watchlist add surface
triggers a background fetch. No real network -- fetch is always monkeypatched."""
import pandas as pd
import pytest

from swingbot.core import backtest_cache as bc


def _make_df(nbars: int) -> pd.DataFrame:
    idx = pd.date_range("2020-01-01", periods=nbars, freq="B", name="Date")
    return pd.DataFrame(
        {"Open": 1.0, "High": 2.0, "Low": 0.5, "Close": 1.5, "Volume": 100},
        index=idx,
    )


@pytest.fixture(autouse=True)
def _tmp_cache(tmp_path, monkeypatch):
    """Point the cache at a temp dir so tests never touch data/backtest_cache/."""
    monkeypatch.setattr(bc, "CACHE_DIR", tmp_path / "backtest_cache")
    return tmp_path


def test_cache_path_sanitizes_symbols():
    assert bc.cache_path("GC=F").name == "GC_F.csv"
    assert bc.cache_path("^GSPC").name == "_GSPC.csv"
    assert bc.cache_path("BRK/B").name == "BRK_B.csv"


def test_normalize_flattens_multiindex_and_selects_columns():
    raw = _make_df(3).copy()
    raw.columns = pd.MultiIndex.from_product([raw.columns, ["AAPL"]])
    out = bc.normalize_ohlcv(raw)
    assert list(out.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert out.index.name == "Date"


def test_normalize_none_and_empty():
    assert bc.normalize_ohlcv(None) is None
    assert bc.normalize_ohlcv(pd.DataFrame()) is None


def test_ensure_cached_writes_csv(monkeypatch):
    monkeypatch.setattr(bc, "fetch", lambda t: _make_df(500))
    res = bc.ensure_cached("AAPL")
    assert res.status == "ok"
    assert res.bars == 500
    assert bc.cache_path("AAPL").exists()


def test_ensure_cached_skips_when_present(monkeypatch):
    calls = []
    monkeypatch.setattr(bc, "fetch", lambda t: calls.append(t) or _make_df(500))
    bc.ensure_cached("AAPL")
    res = bc.ensure_cached("AAPL")  # second call must not refetch
    assert res.status == "skipped"
    assert calls == ["AAPL"]  # fetched exactly once


def test_ensure_cached_force_refetches(monkeypatch):
    calls = []
    monkeypatch.setattr(bc, "fetch", lambda t: calls.append(t) or _make_df(500))
    bc.ensure_cached("AAPL")
    bc.ensure_cached("AAPL", force=True)
    assert calls == ["AAPL", "AAPL"]


def test_ensure_cached_short_history_still_cached_but_noted(monkeypatch):
    monkeypatch.setattr(bc, "fetch", lambda t: _make_df(30))
    res = bc.ensure_cached("NEWIPO")
    assert res.status == "ok"
    assert "too short" in res.note
    assert bc.cache_path("NEWIPO").exists()


def test_ensure_cached_failure_does_not_raise(monkeypatch):
    def _boom(t):
        raise RuntimeError("network down")

    monkeypatch.setattr(bc, "fetch", _boom)
    res = bc.ensure_cached("SPCX")
    assert res.status == "failed"
    assert not bc.cache_path("SPCX").exists()


def test_ensure_cached_empty_response_fails(monkeypatch):
    monkeypatch.setattr(bc, "fetch", lambda t: None)
    res = bc.ensure_cached("SPCX")
    assert res.status == "failed"
    assert not bc.cache_path("SPCX").exists()


def test_ensure_cached_background_writes_file(monkeypatch):
    monkeypatch.setattr(bc, "fetch", lambda t: _make_df(500))
    t = bc.ensure_cached_background("AAPL")
    t.join(timeout=5)
    assert bc.cache_path("AAPL").exists()


def test_ensure_cached_background_skips_cached_without_fetch(monkeypatch):
    monkeypatch.setattr(bc, "fetch", lambda t: _make_df(500))
    bc.ensure_cached("AAPL")  # pre-cache
    calls = []
    monkeypatch.setattr(bc, "fetch", lambda t: calls.append(t))
    t = bc.ensure_cached_background("AAPL")
    t.join(timeout=5)
    assert calls == []  # already cached -> no background fetch
