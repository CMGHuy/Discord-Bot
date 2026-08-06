"""Guards for scripts/extend_backtest_cache.py (plan v8, Task V24 Step 5).

The whole point of that script is that it must never corrupt history while
extending it, so the tests here pin the refusals, not just the happy path.
No network: `fetch_full` is monkeypatched with synthetic series.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import extend_backtest_cache as ext


def _series(start: str, periods: int, first_close: float = 100.0) -> pd.DataFrame:
    idx = pd.bdate_range(start, periods=periods, name="Date")
    close = pd.Series([first_close + i for i in range(periods)], index=idx, dtype=float)
    return pd.DataFrame({"Open": close, "High": close * 1.01, "Low": close * 0.99,
                         "Close": close, "Volume": 1_000_000}, index=idx)


@pytest.fixture
def cache(tmp_path, monkeypatch):
    """Redirect the script's cache_path at a tmp dir and return a writer."""
    monkeypatch.setattr(ext, "cache_path", lambda t: tmp_path / f"{t}.csv")

    def write(ticker, df):
        p = tmp_path / f"{ticker}.csv"
        df.to_csv(p)
        return p
    return write


def _run(monkeypatch, live, **kw):
    monkeypatch.setattr(ext, "fetch_full", lambda sym, adjusted: live if adjusted else None)
    return ext.process("T", "T", pd.Timestamp(kw.pop("end", "2026-08-03")),
                       kw.pop("apply", True), kw.pop("rebase", False))


def test_resolve_symbol_prefers_known_mapping():
    assert ext.resolve_symbol("_VIX", {"_VIX": "^VIX"}) == "^VIX"


def test_resolve_symbol_identity_when_unmangled():
    # cache_path only ever mangles INTO '_', so a stem without one is its own symbol.
    assert ext.resolve_symbol("QQQ", {}) == "QQQ"


def test_resolve_symbol_refuses_to_guess_mangled_stem():
    assert ext.resolve_symbol("_VIX", {}) is None


def test_append_extends_and_leaves_existing_rows_byte_identical(cache, monkeypatch):
    disk = _series("2026-01-01", 60)
    path = cache("T", disk)
    before = path.read_text()
    live = _series("2026-01-01", 70)  # same basis, 10 extra bars

    r = _run(monkeypatch, live)

    assert r["status"] == "ADDED"
    assert r["added"] == 10
    after = path.read_text()
    # Byte-level, not just numeric: the append path copies the original bytes
    # rather than re-serializing, so a pandas float round-trip
    # (108.07000000000001 -> 108.07) can never touch cached history.
    assert after.startswith(before), "existing rows must not be rewritten"
    out = pd.read_csv(path, index_col="Date", parse_dates=True)
    assert len(out) == 70
    assert out.index[-1] == live.index[-1]


def test_uniform_offset_is_refused_without_rebase(cache, monkeypatch):
    """The seam hazard: a ticker that went ex-dividend since caching comes back
    uniformly lower. Appending would splice in a gap-down that never happened."""
    disk = _series("2026-01-01", 60)
    path = cache("T", disk)
    before = path.read_text()
    live = _series("2026-01-01", 70)
    for c in ("Open", "High", "Low", "Close"):
        live[c] *= 0.99

    r = _run(monkeypatch, live)

    assert r["status"] == "SKIP"
    assert "--rebase" in r["note"]
    assert path.read_text() == before, "a refusal must leave the file untouched"


def test_rebase_rescales_and_preserves_returns(cache, monkeypatch):
    disk = _series("2026-01-01", 60)
    path = cache("T", disk)
    live = _series("2026-01-01", 70)
    for c in ("Open", "High", "Low", "Close"):
        live[c] *= 0.99

    r = _run(monkeypatch, live, rebase=True)

    assert r["status"] == "REBASED"
    assert r["added"] == 10
    out = pd.read_csv(path, index_col="Date", parse_dates=True)
    # A uniform rescale must leave every percentage return unchanged.
    pd.testing.assert_series_equal(
        out["Close"].pct_change().dropna().head(59).reset_index(drop=True),
        disk["Close"].pct_change().dropna().reset_index(drop=True),
        check_names=False, rtol=1e-9)


def test_rebase_does_not_prepend_older_history(cache, monkeypatch):
    """A period='max' refetch reaches back further than the cache deliberately
    does; rebase must extend forward only."""
    disk = _series("2026-01-01", 60)
    path = cache("T", disk)
    # Same price path as `disk` on the dates they share, but reaching back years
    # earlier and forward 10 bars -- i.e. what a period="max" refetch returns.
    full = pd.bdate_range("2020-01-01", periods=1700, name="Date")
    offset = full.get_loc(disk.index[0])
    close = pd.Series([100.0 + (i - offset) for i in range(len(full))],
                      index=full, dtype=float)
    live = pd.DataFrame({"Open": close, "High": close * 1.01, "Low": close * 0.99,
                         "Close": close, "Volume": 1_000_000}, index=full)
    for c in ("Open", "High", "Low", "Close"):
        live[c] *= 0.99
    assert live.index[-1] > disk.index[-1], "fixture must extend forward too"

    r = _run(monkeypatch, live, rebase=True)

    assert r["status"] == "REBASED"
    out = pd.read_csv(path, index_col="Date", parse_dates=True)
    assert out.index[0] == disk.index[0], "start date must not move backwards"


def test_non_uniform_mismatch_refused_even_with_rebase(cache, monkeypatch):
    """A varying ratio means a genuinely different convention (raw vs adjusted),
    not a rescale -- rebasing would silently change the price basis."""
    disk = _series("2026-01-01", 60)
    path = cache("T", disk)
    before = path.read_text()
    live = _series("2026-01-01", 70)
    live["Close"] = live["Close"] * pd.Series(
        [1 - 0.3 * (1 - i / len(live)) for i in range(len(live))], index=live.index)

    r = _run(monkeypatch, live, rebase=True)

    assert r["status"] == "SKIP"
    assert path.read_text() == before


def test_already_current_is_a_noop(cache, monkeypatch):
    disk = _series("2026-01-01", 60)
    path = cache("T", disk)
    before = path.read_text()

    r = _run(monkeypatch, _series("2026-01-01", 60), end=str(disk.index[-1].date()))

    assert r["status"] == "CURRENT"
    assert path.read_text() == before
