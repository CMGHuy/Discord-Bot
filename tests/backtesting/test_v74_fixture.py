"""The committed fixture used by v74 observability and parity tests."""
from pathlib import Path

import pandas as pd

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "v74"
TICKERS = ("AAPL", "XOM")


def load_v74_fixture() -> dict[str, pd.DataFrame]:
    return {symbol: pd.read_csv(FIXTURE_DIR / f"{symbol}.csv", index_col=0, parse_dates=True)
            for symbol in TICKERS}


def test_fixture_files_exist_and_have_the_expected_shape():
    for frame in load_v74_fixture().values():
        assert len(frame) >= 500
        assert list(frame.columns) == ["Open", "High", "Low", "Close", "Volume"]
        assert frame.index.is_monotonic_increasing
        assert not frame.isna().any().any()


def test_fixture_is_deterministic_on_disk():
    first, second = load_v74_fixture(), load_v74_fixture()
    for symbol in TICKERS:
        pd.testing.assert_frame_equal(first[symbol], second[symbol])
