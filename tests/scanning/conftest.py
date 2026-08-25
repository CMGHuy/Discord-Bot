import pytest

from swingbot.core.market.levels import Scenario
from swingbot.core.scanning import engine as scan_engine


class _InlineProcessPool:
    """Stands in for ProcessPoolExecutor: runs fn(*args) directly, in-process
    -- no subprocess, no pickling constraints, no network. For tests that
    drive _sync_run_scan/_crawl_latest_data end-to-end but don't care about
    the real batching/bounded-pool machinery itself (see stub_batch_fetch
    below). Tests that DO exercise that machinery use their own fake pool --
    see tests/scanning/test_cold_fetch_pool.py and
    test_no_cross_ticker_mixing.py.
    """

    def __init__(self, max_workers=None, mp_context=None):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def submit(self, fn, *args):
        from concurrent.futures import Future
        fut = Future()
        try:
            fut.set_result(fn(*args))
        except Exception as exc:
            fut.set_exception(exc)
        return fut


@pytest.fixture
def stub_batch_fetch(monkeypatch):
    """v55: a test driving _sync_run_scan/_crawl_latest_data end-to-end while
    controlling fetch behaviour via get_daily_data()/a live-price expectation
    would otherwise hit the real, batched get_daily_data_batch()/
    get_current_price_batch() -- real network -- through a real
    ProcessPoolExecutor -- a real subprocess. This fixture forces both batch
    calls to resolve empty, so _fetch_cold_frames falls through to the
    single-ticker get_daily_data() fallback (which the test already mocks)
    and _fetch_live_prices resolves no live price for anyone (the same "no
    live price -> falls back to today's daily close" behavior the old
    per-ticker get_current_price()->None mock used to produce), and swaps in
    an in-process fake pool so _run_bounded never touches a real subprocess.
    """
    monkeypatch.setattr(scan_engine, "get_daily_data_batch", lambda tickers, period=None: {})
    monkeypatch.setattr(scan_engine, "get_current_price_batch", lambda tickers: {})
    monkeypatch.setattr(scan_engine, "ProcessPoolExecutor", _InlineProcessPool)


@pytest.fixture
def sample_scenario():
    """A representative bullish scenario with real Scenario field values --
    used to compare the legacy and unified score_confidence() paths (v32
    Task 6) without either path having to special-case a mock."""
    return Scenario(
        direction="bullish",
        entry=100.0,
        market_price=100.0,
        stop_loss=98.0,
        stop_sources=["EMA", "VWAP"],
        stop_distance_pct=2.0,
        tight_stop=False,
        atr_floor_pct=1.5,
        take_profit=106.0,
        target_distance_pct=6.0,
        target_sources=["EMA", "VWAP", "Fibonacci"],
        target2_price=None,
        target2_distance_pct=None,
        target2_sources=None,
    )
