"""v204: snapshot bars come from the yfinance-basis daily file only; never fetched, never written."""
import os

import pandas as pd
import pytest

from swingbot.admin import freshness
from swingbot.core.edge import portfolio_state
from swingbot.core.marketdata import daily_readonly, data, data_refresh, data_store
from swingbot.core.marketdata.daily_readonly import (
    DailyCacheUnavailable, ReadOnlyBars, RecordingReader, read_cached_daily)


def frame(days=30, start="2026-08-03"):
    close = [100.0 + i for i in range(days)]
    return pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close,
                         "Volume": [1000.0] * days}, index=pd.bdate_range(start, periods=days))


@pytest.fixture
def disk(tmp_path, monkeypatch):
    root = tmp_path / "market_data"
    daily = root / data_store.timeframe_name("daily")
    daily.mkdir(parents=True)
    monkeypatch.setattr(data_store, "DATA_DIR", str(root))

    def boom(*a, **k):
        raise AssertionError("read-only bars reached a fetch or a cache write")
    for mod, name in ((data, "get_daily_data"), (data, "get_daily_data_batch"),
                      (data_refresh, "refresh_symbol"), (data_store, "update_cache"),
                      (data_store, "save_to_disk"), (freshness, "_daily_for")):
        monkeypatch.setattr(mod, name, boom, raising=False)

    def write(sym, df):
        df.to_csv(daily / f"{data_store.safe_symbol(sym)}.csv")
    return write, daily


def test_cached_symbols_are_read_and_absent_ones_listed_missing(disk):
    write, _ = disk
    write("AAPL", frame())
    got = read_cached_daily(["aapl", " MSFT ", "AAPL"])
    assert isinstance(got, ReadOnlyBars)
    assert list(got.frames) == ["AAPL"] and got.missing == {"MSFT": "no_file"}
    assert got.frames["AAPL"]["Close"].iloc[-1] == 129.0


def test_fingerprint_names_the_yfinance_basis_file(disk):
    write = disk[0]
    write("AAPL", frame(days=40))
    _, daily = disk
    fp = read_cached_daily(["AAPL"], period="6mo").fingerprints["AAPL"]
    assert os.path.normcase(fp["path"]) == os.path.normcase(
        os.path.abspath(daily / f"{data_store.safe_symbol('AAPL')}.csv"))
    assert fp["rows"] == 40 and fp["last_bar"] == "2026-09-25" and fp["mtime"] > 0


def test_period_trims_to_the_window_but_rows_count_the_file(disk):
    write, _ = disk
    write("AAPL", frame(days=600, start="2024-03-01"))
    got = read_cached_daily(["AAPL"], period="1y")
    kept = got.frames["AAPL"]
    assert (kept.index[-1] - kept.index[0]).days <= daily_readonly.PERIOD_DAYS["1y"]
    assert got.fingerprints["AAPL"]["rows"] == 600


def test_short_frame_is_missing_with_its_row_count_never_returned(disk):
    write, _ = disk
    write("AAPL", frame(days=12))
    got = read_cached_daily(["AAPL"], min_rows=21)
    assert got.frames == {} and got.missing == {"AAPL": "short:12/21"}
    assert got.fingerprints["AAPL"]["rows"] == 12


def test_empty_and_unreadable_files_are_missing_with_a_reason(disk):
    _, daily = disk
    (daily / f"{data_store.safe_symbol('AAA')}.csv").write_text("")
    (daily / f"{data_store.safe_symbol('BBB')}.csv").write_text("not,a,bar file\n1,2,3\n")
    got = read_cached_daily(["AAA", "BBB"])
    assert got.frames == {} and got.missing == {"AAA": "empty", "BBB": "unreadable"}


def test_spot_metal_is_missing_never_fetched(disk):
    got = read_cached_daily(["XAUUSD"])
    assert got.frames == {} and got.missing == {"XAUUSD": "spot_metal"} and got.fingerprints == {}


def test_unmounted_cache_dir_raises(tmp_path, monkeypatch):
    absent = tmp_path / "not-mounted"
    monkeypatch.setattr(data_store, "DATA_DIR", str(absent))
    with pytest.raises(DailyCacheUnavailable, match="not mounted"):
        read_cached_daily(["AAPL"])
    assert not absent.exists()


def test_recording_reader_returns_frames_and_remembers_every_call(disk):
    write, _ = disk
    write("AAPL", frame())
    reader = RecordingReader(min_rows=5)
    assert list(reader(["AAPL"])) == ["AAPL"]
    assert reader(["MSFT"]) == {}
    seen = reader.seen
    assert list(seen.frames) == ["AAPL"] and seen.missing == {"MSFT": "no_file"}
    assert set(seen.fingerprints) == {"AAPL"}


def test_page_daily_read_only_reads_disk_and_never_refreshes(disk):
    write, _ = disk
    write("AAPL", frame())
    assert set(freshness.page_daily(["AAPL", "MSFT", "XAUUSD"], read_only=True)) == {"AAPL"}


def test_cluster_bars_go_through_the_reader_keyed_by_trade_ticker(disk):
    frames, missing = portfolio_state._daily_frames(
        [{"ticker": "aapl"}, {"ticker": "MSFT"}], bars_reader=lambda syms: {"AAPL": frame()})
    assert list(frames) == ["aapl"] and missing == 1


def test_missing_volume_escapes_the_collector(monkeypatch):
    def unmounted(syms):
        raise DailyCacheUnavailable("daily bar cache /x is not mounted")
    trades = [{"ticker": "AAPL", "direction": "bullish", "entry": 100.0, "stop_loss": 95.0,
               "shares": 10.0}]
    monkeypatch.setattr(portfolio_state, "_trades", lambda: trades)
    monkeypatch.setattr(portfolio_state, "_load_sector_map", lambda: {"AAPL": "Tech"})
    monkeypatch.setattr(portfolio_state.account_module, "load_account_config",
                        lambda: {"base_balance": 10_000.0})
    with pytest.raises(DailyCacheUnavailable):
        portfolio_state.collect_portfolio_state(bars_reader=unmounted)


def test_collector_without_a_reader_still_swallows_cluster_fetch_errors(monkeypatch):
    def down(ticker):
        raise RuntimeError("provider down")
    monkeypatch.setattr(data, "get_daily_data", down)
    frames, missing = portfolio_state._daily_frames([{"ticker": "AAPL"}])
    assert frames == {} and missing == 1
