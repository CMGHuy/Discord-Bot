"""v47: a cached frame must be indistinguishable from a live-download frame.

The whole cache-first design rests on this. fetch_interval_data() resolves
symbols through the same candidate_symbols() helper as get_daily_data(), uses
the same auto_adjust=True, and for daily requests period="max" -- a superset of
the 10y get_daily_data asks for. So the DATA is equivalent by construction; what
is NOT guaranteed is the shape after a to_csv/read_csv round-trip.
"""
import pandas as pd
import pytest

from swingbot.core.marketdata import data_store
from tests.helpers import make_ohlcv


@pytest.fixture
def cache_dir(tmp_path):
    return str(tmp_path / "market_data")


def test_round_trip_preserves_columns_dtypes_and_index(cache_dir):
    live = make_ohlcv([100.0, 101.0, 102.0, 103.0])
    data_store.save_to_disk(live, "TEST", "daily", base_dir=cache_dir)

    loaded = data_store.load_normalized("TEST", "daily", base_dir=cache_dir)

    assert list(loaded.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert all(str(loaded[c].dtype) == "float64" for c in loaded.columns)
    assert isinstance(loaded.index, pd.DatetimeIndex)
    assert loaded.index.tz is None
    assert loaded.index.is_monotonic_increasing
    assert not loaded.index.has_duplicates
    # check_freq=False deliberately: make_ohlcv builds its index with
    # pd.bdate_range, which stamps freq=<BusinessDay>. A real yf.download()
    # frame has freq=None -- market holidays break the cadence, so pandas
    # infers nothing. The round-tripped frame matching None is the LIVE shape;
    # re-stamping a freq here would assert a regularity real data lacks.
    pd.testing.assert_frame_equal(loaded, live, check_dtype=True, check_freq=False)
    assert loaded.index.equals(live.index)


def test_tz_aware_cached_index_is_flattened(cache_dir):
    """A CSV written by an intraday refresh round-trips tz-aware. The scan's
    frames are compared against tz-naive daily frames downstream, so an
    unflattened index raises on comparison rather than silently misaligning."""
    live = make_ohlcv([100.0, 101.0, 102.0])
    live.index = live.index.tz_localize("UTC")
    data_store.save_to_disk(live, "TZT", "daily", base_dir=cache_dir)

    loaded = data_store.load_normalized("TZT", "daily", base_dir=cache_dir)

    assert loaded.index.tz is None


def test_missing_file_returns_none(cache_dir):
    assert data_store.load_normalized("NOPE", "daily", base_dir=cache_dir) is None


def test_unreadable_file_returns_none_rather_than_raising(cache_dir):
    """A truncated/corrupt CSV must degrade to a cache miss, not kill the scan."""
    path = data_store.cache_path("BAD", "daily", base_dir=cache_dir)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("this is not a csv\x00\x00")

    assert data_store.load_normalized("BAD", "daily", base_dir=cache_dir) is None
