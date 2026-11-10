"""v211 V211-1: BREADTH_ATR1.csv and ^VIX.csv sit in the cache dir beside the
ticker CSVs (the context loader reads <cache_dir>/<stem>.csv literally), so
every ticker listing must skip them. SPY/TLT/UUP stay tickers."""
import re
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
for _sub in ("backtest", "data"):
    if str(ROOT / "scripts" / _sub) not in sys.path:
        sys.path.insert(0, str(ROOT / "scripts" / _sub))

import cache_dir_source as cds  # noqa: E402
import fetch_earnings_dates as fed  # noqa: E402
from swingbot.core.backtesting.screen import context as screen_context  # noqa: E402
from swingbot.core.marketdata import backtest_cache, training_data  # noqa: E402

STEMS = ("AAA", "BREADTH_ATR1", "SPY", "TLT", "UUP", "^VIX")


def _cache_dir(tmp_path: Path) -> Path:
    frame = pd.DataFrame({"Open": [1.0], "High": [1.0], "Low": [1.0], "Close": [1.0],
                          "Volume": [0.0]}, index=pd.DatetimeIndex(["2010-01-04"], name="Date"))
    for stem in STEMS:
        frame.to_csv(tmp_path / f"{stem}.csv")
    return tmp_path


def test_the_context_only_set_is_exactly_the_two_new_files():
    assert screen_context.CONTEXT_ONLY_STEMS == frozenset({"BREADTH_ATR1", "^VIX"})
    assert screen_context.is_context_only("BREADTH_ATR1")
    assert screen_context.is_context_only("^VIX")
    for ticker in ("SPY", "TLT", "UUP", "_VIX", "VIX", "AAA"):
        assert not screen_context.is_context_only(ticker), ticker


def test_directory_readers_skip_context_stems_and_keep_spy(tmp_path):
    cache_dir = _cache_dir(tmp_path)
    assert cds.listing(cache_dir) == ["AAA", "SPY", "TLT", "UUP"]
    assert cds.cache_files(cache_dir) == ["AAA.csv", "SPY.csv", "TLT.csv", "UUP.csv"]
    assert sorted(cds.load_all(cache_dir)) == ["AAA", "SPY", "TLT", "UUP"]


def test_load_all_filters_before_the_limit(tmp_path):
    # Unfiltered, the sorted paths start AAA.csv, BREADTH_ATR1.csv: the
    # limit must count tickers, never a context file.
    assert sorted(cds.load_all(_cache_dir(tmp_path), limit=2)) == ["AAA", "SPY"]


def test_switch_readers_drop_context_stems_too(monkeypatch):
    # The yfinance source with BACKTEST_CACHE_DIR at the ext dir globs the same files.
    monkeypatch.setattr(cds.training_data, "available_tickers",
                        lambda: ["AAA", "BREADTH_ATR1", "SPY", "^VIX"])
    monkeypatch.setattr(cds.training_data, "load_daily",
                        lambda t: pd.DataFrame({"Close": [1.0]}))
    assert cds.listing(None) == ["AAA", "SPY"]
    assert cds.cache_files(None) == ["AAA.csv", "SPY.csv"]
    assert sorted(cds.load_all(None)) == ["AAA", "SPY"]
    assert sorted(cds.load_all(None, limit=1)) == ["AAA"]


def test_earnings_fetch_never_asks_for_a_context_stem(tmp_path):
    assert fed.cached_symbols(_cache_dir(tmp_path)) == ["AAA", "SPY", "TLT", "UUP"]


@pytest.fixture
def yfinance_dir(tmp_path, monkeypatch):
    """The yfinance switch reading tmp_path as backtest_cache.CACHE_DIR."""
    monkeypatch.setattr(backtest_cache, "CACHE_DIR", tmp_path)
    training_data.reset()
    training_data.select("yfinance")
    yield tmp_path
    training_data.reset()


def test_yfinance_switch_on_an_ext_dir_never_lists_context_stems(yfinance_dir):
    _cache_dir(yfinance_dir)
    assert training_data.available_tickers() == ["AAA", "SPY", "TLT", "UUP"]


def test_yfinance_switch_on_a_normal_dir_lists_as_before(yfinance_dir):
    for stem in ("AAA", "SPY", "ZZZ", "_VIX"):      # _VIX is cache_path's spelling, a ticker file
        (yfinance_dir / f"{stem}.csv").write_text("Date,Close\n", encoding="utf-8")
    assert training_data.available_tickers() == sorted(p.stem for p in yfinance_dir.glob("*.csv"))
    assert training_data.available_tickers() == ["AAA", "SPY", "ZZZ", "_VIX"]


def test_training_data_mirrors_the_screen_set():
    # marketdata may not import the screen (test_import_guard.py), so it keeps a copy.
    assert training_data._CONTEXT_ONLY_STEMS == screen_context.CONTEXT_ONLY_STEMS


#: Every script that globs *.csv, and why it is safe. A new glob over a cache
#: dir fails here until it filters with is_context_only or is listed with a reason.
KNOWN_CSV_GLOBS = {
    "scripts/backtest/cache_dir_source.py": "filters is_context_only (V211-1)",
    "scripts/data/fetch_earnings_dates.py": "filters is_context_only (V211-1)",
    "scripts/data/snapshot_backtest_cache.py": "byte copy of the whole dir, context included",
    "scripts/backtest/measure_fvg_bullish_diagnostic.py": "globs the earnings dir, not a cache dir",
    "scripts/backtest/measure_giveback_levels.py": "globs the earnings dir, not a cache dir",
    "scripts/data/fetch_intraday_cache.py": "reads backtest_cache.CACHE_DIR (data/backtest_cache by default)",
    "scripts/reports/audit_quality_score.py": "reads backtest_cache.CACHE_DIR (data/backtest_cache by default)",
    "scripts/reports/parity_sizing.py": "reads backtest_cache.CACHE_DIR (data/backtest_cache by default)",
    "scripts/reports/runner_headroom.py": "reads backtest_cache.CACHE_DIR (data/backtest_cache by default)",
}
_GLOB = re.compile(r"""r?glob\(\s*["']\*\.csv["']\s*\)""")


def test_every_csv_glob_in_scripts_is_known():
    found = {path.relative_to(ROOT).as_posix()
             for path in sorted((ROOT / "scripts").rglob("*.py"))
             if _GLOB.search(path.read_text(encoding="utf-8"))}
    assert found == set(KNOWN_CSV_GLOBS)
