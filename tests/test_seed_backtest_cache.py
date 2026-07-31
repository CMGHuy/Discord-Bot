"""scripts/seed_backtest_cache.py -- market_data/daily -> data/backtest_cache
bridge. No real market_data on disk in this repo checkout; every case uses
synthetic fixture CSVs under tmp_path so the test never touches the live
94MB dataset (which only exists on the deployed server)."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from seed_backtest_cache import bridge_one  # noqa: E402


def _write_market_data_csv(path: Path, ticker: str, nbars: int, start="2000-01-03"):
    """market_data's on-disk shape: Date,Close,High,Low,Open,Volume -- note
    the column ORDER differs from backtest_cache's canonical Open/High/Low/
    Close/Volume, which is exactly what bridge_one must tolerate."""
    idx = pd.date_range(start, periods=nbars, freq="B", name="Date")
    df = pd.DataFrame({
        "Close": 1.5, "High": 2.0, "Low": 0.5, "Open": 1.0, "Volume": 100,
    }, index=idx)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path)


def test_bridges_and_reorders_columns(tmp_path):
    market_dir, cache_dir = tmp_path / "market_data", tmp_path / "backtest_cache"
    _write_market_data_csv(market_dir / "AAPL.csv", "AAPL", 500)

    r = bridge_one("AAPL", market_dir, cache_dir)

    assert r["status"] == "ok"
    assert r["bars"] == 500
    written = pd.read_csv(cache_dir / "AAPL.csv", index_col="Date", parse_dates=True)
    assert list(written.columns) == ["Open", "High", "Low", "Close", "Volume"]


def test_sanitizes_ticker_symbol_both_directions(tmp_path):
    """GC=F on the watchlist must read GC_F.csv and write GC_F.csv, matching
    data_store.safe_symbol / backtest_cache.cache_path's shared scheme."""
    market_dir, cache_dir = tmp_path / "market_data", tmp_path / "backtest_cache"
    _write_market_data_csv(market_dir / "GC_F.csv", "GC=F", 6000)

    r = bridge_one("GC=F", market_dir, cache_dir)

    assert r["status"] == "ok"
    assert (cache_dir / "GC_F.csv").exists()


def test_flags_short_history_but_still_writes(tmp_path):
    """Below BACKTEST_MIN_BARS (260): still written (matches
    backtest_cache.ensure_cached's own convention), but flagged."""
    market_dir, cache_dir = tmp_path / "market_data", tmp_path / "backtest_cache"
    _write_market_data_csv(market_dir / "SKHY.csv", "SKHY", 15)

    r = bridge_one("SKHY", market_dir, cache_dir)

    assert r["status"] == "short"
    assert "too short" in r["note"]
    assert (cache_dir / "SKHY.csv").exists()


def test_missing_source_file_reported_not_raised(tmp_path):
    market_dir, cache_dir = tmp_path / "market_data", tmp_path / "backtest_cache"

    r = bridge_one("NOPE", market_dir, cache_dir)

    assert r["status"] == "missing"
    assert not (cache_dir / "NOPE.csv").exists()


def test_empty_source_file_reported_not_raised(tmp_path):
    market_dir, cache_dir = tmp_path / "market_data", tmp_path / "backtest_cache"
    market_dir.mkdir(parents=True)
    pd.DataFrame(columns=["Close", "High", "Low", "Open", "Volume"]).to_csv(
        market_dir / "EMPTY.csv", index_label="Date"
    )

    r = bridge_one("EMPTY", market_dir, cache_dir)

    assert r["status"] == "missing"


def test_refuses_to_shrink_existing_cache(tmp_path):
    """The V43 never-shrink rule: a destination with MORE bars than the
    source would produce must not be silently overwritten."""
    market_dir, cache_dir = tmp_path / "market_data", tmp_path / "backtest_cache"
    _write_market_data_csv(market_dir / "NVDA.csv", "NVDA", 300)
    # Seed a destination that already has more history than the source has.
    _write_market_data_csv(cache_dir / "NVDA.csv", "NVDA", 500)

    r = bridge_one("NVDA", market_dir, cache_dir)

    assert r["status"] == "refused_shrink"
    still_there = pd.read_csv(cache_dir / "NVDA.csv", index_col="Date", parse_dates=True)
    assert len(still_there) == 500  # untouched


def test_force_allows_shrink(tmp_path):
    market_dir, cache_dir = tmp_path / "market_data", tmp_path / "backtest_cache"
    _write_market_data_csv(market_dir / "NVDA.csv", "NVDA", 300)
    _write_market_data_csv(cache_dir / "NVDA.csv", "NVDA", 500)

    r = bridge_one("NVDA", market_dir, cache_dir, force=True)

    assert r["status"] == "ok"
    assert r["bars"] == 300


def test_dry_run_writes_nothing(tmp_path):
    market_dir, cache_dir = tmp_path / "market_data", tmp_path / "backtest_cache"
    _write_market_data_csv(market_dir / "AAPL.csv", "AAPL", 500)

    r = bridge_one("AAPL", market_dir, cache_dir, dry_run=True)

    assert r["status"] == "ok"
    assert not cache_dir.exists()


def test_growing_source_extends_existing_cache(tmp_path):
    """Non-shrink case: source has MORE bars than an existing destination --
    this must proceed and overwrite with the larger set."""
    market_dir, cache_dir = tmp_path / "market_data", tmp_path / "backtest_cache"
    _write_market_data_csv(market_dir / "NVDA.csv", "NVDA", 600)
    _write_market_data_csv(cache_dir / "NVDA.csv", "NVDA", 500)

    r = bridge_one("NVDA", market_dir, cache_dir)

    assert r["status"] == "ok"
    assert r["bars"] == 600
