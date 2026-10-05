import pandas as pd

from tests.helpers import make_ohlcv


def test_make_ohlcv_floats():
    df = make_ohlcv([100, 101, 102])
    assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert len(df) == 3
    assert df["Close"].iloc[1] == 101
    assert df["High"].iloc[1] == 101 * 1.01
    assert isinstance(df.index, pd.DatetimeIndex)


def test_make_ohlcv_tuples():
    df = make_ohlcv([(100, 105, 99, 104)])
    assert df["High"].iloc[0] == 105 and df["Low"].iloc[0] == 99
