import pytest

from swingbot.core.backtesting.arms.engine import get_engine, run_arm
from tests.backtesting.test_v74_fixture import load_v74_fixture

WINDOW = ("1900-01-01", "2100-12-31")


@pytest.fixture(scope="module")
def frame():
    return load_v74_fixture()["AAPL"]


def test_confluence_trades_are_keyed_and_in_window(frame):
    trades = run_arm("AAPL", frame, ("confluence",), ("4w",), WINDOW, {})
    assert trades, "fixture should yield confluence trades on 4w"
    assert all(trade.source == "confluence" and trade.direction in ("bullish", "bearish")
               for trade in trades)
    assert len({trade.key for trade in trades}) == len(trades)
    assert all(trade.outcome in ("win", "loss", "scratch", "timeout") for trade in trades)


def test_signal_window_filters_by_entry_date(frame):
    trades = run_arm("AAPL", frame, ("confluence",), ("4w",),
                     ("2025-01-01", "2025-06-30"), {})
    assert all("2025-01-01" <= trade.entry_date <= "2025-06-30" for trade in trades)


def test_knob_delta_reaches_the_engine(frame):
    base = run_arm("AAPL", frame, ("confluence",), ("4w",), WINDOW, {})
    tight = run_arm("AAPL", frame, ("confluence",), ("4w",), WINDOW,
                    {"MIN_REWARD_PCT": 100.0})
    assert tight != base


def test_unknown_engine_is_an_error():
    with pytest.raises(ValueError):
        get_engine("nope")
