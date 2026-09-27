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
        "alpaca": 1, "yfinance": 1, "yfinance-fallback": 0, "none": 1}


def test_a_failed_chunk_counts_its_tickers_as_none(monkeypatch):
    from swingbot.core.scanning import fetch

    def boom(tickers):
        raise RuntimeError("worker died")
    monkeypatch.setattr(fetch, "ProcessPoolExecutor", _InlinePool)
    monkeypatch.setattr(fetch, "get_current_price_batch", boom)
    fetch.reset_fetch_stats()
    assert fetch._fetch_live_prices(["AAPL", "MSFT"]) == {}
    assert fetch.fetch_stats()["price_sources"]["none"] == 2
