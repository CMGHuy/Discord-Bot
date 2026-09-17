import datetime as dt
from zoneinfo import ZoneInfo

from swingbot.core.scanning import strategy_pass as sp
from tests.helpers import make_ohlcv

ET = ZoneInfo("America/New_York")


def _frame_ending(day):
    df = make_ohlcv([100 + i for i in range(80)], start=(day - dt.timedelta(days=60)).isoformat())
    return df[df.index.date <= day]


def test_completed_frame_and_deduplication():
    day = dt.date(2026, 9, 17)
    df = _frame_ending(day)
    assert sp.completed_frame(df, dt.datetime(2026, 9, 17, 11, tzinfo=ET)).index[-1].date() == dt.date(2026, 9, 16)
    assert sp.completed_frame(df, dt.datetime(2026, 9, 17, 16, 5, tzinfo=ET)).index[-1].date() == day

    class P:
        source, ticker, strategy, horizon_key, created_at = "strategy", "AAPL", "MACD", "3m", "2026-09-16"
    class Store:
        def all(self): return [P()]
    assert sp.already_emitted(Store(), "AAPL", "MACD", "3m", "2026-09-16")
    assert not sp.already_emitted(Store(), "AAPL", "MACD", "4m", "2026-09-16")
