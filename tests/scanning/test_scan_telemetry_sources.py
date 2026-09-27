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
