from tests.fake_feed import FakePriceFeed


def test_per_ticker_ordering_and_isolation():
    feed = FakePriceFeed([("AAPL", 100.0), ("MSFT", 50.0), ("AAPL", 101.0)])
    assert feed.get_price("AAPL") == 100.0
    assert feed.get_price("MSFT") == 50.0
    assert feed.get_price("AAPL") == 101.0


def test_exhaustion_repeats_last():
    feed = FakePriceFeed()
    feed.set_series("AAPL", [100.0, 105.0])
    assert [feed.get_price("AAPL") for _ in range(4)] == [100.0, 105.0, 105.0, 105.0]


def test_unknown_ticker_raises():
    import pytest
    with pytest.raises(KeyError):
        FakePriceFeed().get_price("GHOST")
