"""v106: each scan's telemetry row counts where its daily frames came from.
The source tag rides on frame.attrs, so it must survive the spawned-process
pickle round trip every cold fetch goes through."""
import pandas as pd


def _tagged():
    df = pd.DataFrame({"Close": [1.0]})
    df.attrs["source"] = "alpaca"
    return df


def test_attrs_survive_spawn_round_trip():
    from swingbot.core.scanning.fetch import _run_bounded
    out = _run_bounded(_tagged, (), 30, "attrs-probe")
    assert out.attrs.get("source") == "alpaca"


def _frame(source=None):
    df = pd.DataFrame({"Close": [1.0]})
    if source:
        df.attrs["source"] = source
    return df


def test_count_sources_buckets_untagged_as_cache():
    from swingbot.core.scanning.scan_run import _count_sources
    frames = {"AAPL": _frame("alpaca"), "SAP.DE": _frame("yfinance"), "X": _frame()}
    assert _count_sources(frames) == {
        "alpaca": 1, "yfinance": 1, "yfinance-fallback": 0, "cache": 1}


def test_single_ticker_yfinance_path_is_tagged(monkeypatch):
    """get_daily_data's candidate loop (the cold-fetch remainder path) must
    tag its frame, or a network fetch is counted as a disk-cache hit."""
    from swingbot import config
    from swingbot.core.marketdata import data as data_mod
    monkeypatch.setattr(config, "ALPACA_ENABLED", False)
    monkeypatch.setattr(data_mod.yf, "download", lambda *a, **k: _frame())
    assert data_mod.get_daily_data("SAP.DE").attrs["source"] == "yfinance"


# --- v106 soak telemetry: cold_fetch_s and price_sources ---------------------

class _InlinePool:
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


def test_cold_fetch_records_one_timing_per_chunk(monkeypatch):
    from swingbot import config
    from swingbot.core.scanning import fetch
    monkeypatch.setattr(fetch, "ProcessPoolExecutor", _InlinePool)
    monkeypatch.setattr(config, "BATCH_FETCH_CHUNK_SIZE", 2)
    monkeypatch.setattr(fetch, "get_daily_data_batch",
                        lambda tickers, period=None: {t: _frame("alpaca") for t in tickers})
    fetch.reset_fetch_stats()
    pairs = fetch._fetch_cold_frames(["A", "B", "C"])
    stats = fetch.fetch_stats()
    assert [t for t, df in pairs if df is not None] == ["A", "B", "C"]
    assert len(stats["cold_fetch_s"]) == 2
    assert all(isinstance(s, float) and s >= 0 for s in stats["cold_fetch_s"])


def test_live_prices_count_each_tickers_provider(monkeypatch):
    from swingbot.core.marketdata.providers import router
    from swingbot.core.scanning import fetch
    monkeypatch.setattr(fetch, "ProcessPoolExecutor", _InlinePool)
    monkeypatch.setattr(fetch, "get_current_price_batch",
                        lambda tickers: {"AAPL": 190.0, "SAP.DE": 50.0})
    monkeypatch.setattr(router, "last_source",
                        lambda t: {"AAPL": "alpaca", "SAP.DE": "yfinance"}.get(t))
    fetch.reset_fetch_stats()
    prices = fetch._fetch_live_prices(["AAPL", "SAP.DE", "MSFT"])
    assert prices == {"AAPL": 190.0, "SAP.DE": 50.0}
    assert fetch.fetch_stats()["price_sources"] == {
        "alpaca": 1, "yfinance": 1, "yfinance-fallback": 0,
        "yfinance-old-print": 0, "none": 1}


def test_a_failed_chunk_counts_its_tickers_as_none(monkeypatch):
    from swingbot.core.scanning import fetch

    def boom(tickers):
        raise RuntimeError("worker died")
    monkeypatch.setattr(fetch, "ProcessPoolExecutor", _InlinePool)
    monkeypatch.setattr(fetch, "get_current_price_batch", boom)
    fetch.reset_fetch_stats()
    assert fetch._fetch_live_prices(["AAPL", "MSFT"]) == {}
    assert fetch.fetch_stats()["price_sources"]["none"] == 2
    assert set(fetch.fetch_stats()["price_sources"]) == {
        "alpaca", "yfinance", "yfinance-fallback", "yfinance-old-print", "none"}


def test_live_price_worker_counts_travel_back_to_the_parent(monkeypatch):
    from swingbot.core.marketdata.shared import counters
    from swingbot.core.scanning import fetch
    rows = [("2026-10-16T14:00:00+00:00", "alpaca", "quote", "SCAN", "fetched", 2)]
    merged = []
    monkeypatch.setattr(fetch, "ProcessPoolExecutor", _InlinePool)
    monkeypatch.setattr(fetch, "get_current_price_batch", lambda tickers: {"AAPL": 190.0})
    monkeypatch.setattr(counters, "snapshot_and_clear", lambda: list(rows))
    monkeypatch.setattr(counters, "merge", merged.extend)
    fetch.reset_fetch_stats()
    assert fetch._fetch_live_prices(["AAPL"]) == {"AAPL": 190.0}
    assert merged == rows
    assert "__counts__" not in fetch.fetch_stats()["price_sources"]


# --- v223: one live-price tag list -----------------------------------------------

def test_price_source_keys_are_the_provider_tags_plus_none():
    from swingbot.core.marketdata.providers.base import PRICE_SOURCES
    from swingbot.core.scanning import fetch
    assert PRICE_SOURCES == ("alpaca", "yfinance", "yfinance-fallback", "yfinance-old-print")
    assert fetch._PRICE_SOURCE_KEYS == PRICE_SOURCES + ("none",)


def test_an_old_print_answered_by_yfinance_gets_its_own_bucket(monkeypatch):
    from swingbot.core.marketdata.providers import router
    from swingbot.core.scanning import fetch
    monkeypatch.setattr(fetch, "ProcessPoolExecutor", _InlinePool)
    monkeypatch.setattr(fetch, "get_current_price_batch",
                        lambda tickers: {"AAPL": 190.0, "MSFT": 410.0, "NVDA": 120.0})
    monkeypatch.setattr(router, "last_source", lambda t: {
        "AAPL": "alpaca", "MSFT": "yfinance-old-print", "NVDA": "yfinance-fallback"}.get(t))
    fetch.reset_fetch_stats()
    fetch._fetch_live_prices(["AAPL", "MSFT", "NVDA"])
    assert fetch.fetch_stats()["price_sources"] == {
        "alpaca": 1, "yfinance": 0, "yfinance-fallback": 1,
        "yfinance-old-print": 1, "none": 0}


def test_an_old_print_yfinance_also_failed_for_lands_in_none(monkeypatch):
    """Spec item 7: no price at all -> "none" (empty_rate covers it), never
    an old print."""
    from swingbot.core.marketdata.providers import router
    from swingbot.core.scanning import fetch
    monkeypatch.setattr(fetch, "ProcessPoolExecutor", _InlinePool)
    monkeypatch.setattr(fetch, "get_current_price_batch", lambda tickers: {"AAPL": 190.0})
    monkeypatch.setattr(router, "last_source", lambda t: {
        "AAPL": "alpaca", "MSFT": "yfinance-old-print"}.get(t))
    fetch.reset_fetch_stats()
    assert fetch._fetch_live_prices(["AAPL", "MSFT"]) == {"AAPL": 190.0}
    counts = fetch.fetch_stats()["price_sources"]
    assert counts["none"] == 1 and counts["yfinance-old-print"] == 0


def test_daily_buckets_never_include_the_old_print_tag():
    """The daily path (_merge, daily_delta) has no freshness rule and never
    emits yfinance-old-print; its buckets are built from the same constants."""
    from swingbot.core.marketdata.providers.base import (
        SOURCE_ALPACA, SOURCE_FALLBACK, SOURCE_OLD_PRINT, SOURCE_YF)
    from swingbot.core.scanning.scan_run import _SOURCE_BUCKETS, _count_sources
    assert _SOURCE_BUCKETS == (SOURCE_ALPACA, SOURCE_YF, SOURCE_FALLBACK)
    counts = _count_sources({"AAPL": _frame("alpaca"), "X": _frame("yfinance-old-print")})
    assert SOURCE_OLD_PRINT not in counts
    assert counts == {"alpaca": 1, "yfinance": 0, "yfinance-fallback": 0, "cache": 1}
