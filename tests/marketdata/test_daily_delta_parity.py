"""v171 D4 parity: cache + delta equals a full fresh download bar for bar,
Volume included, on both bases (a)-(d); and frames never cross caches."""
import dataclasses
import logging
import os
from datetime import date

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.marketdata import daily_delta as dd, data_store
from swingbot.core.marketdata.shared.kinds import Asker
from tests.marketdata.daily_fakes import OHLCV, Market

T0, TMID, T1 = date(2026, 9, 30), date(2026, 10, 9), date(2026, 10, 16)
BASES = [dd.BASIS_ALPACA, dd.BASIS_YF]


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "ALPACA_ANCHOR_DATE", "2026-01-05")
    monkeypatch.setattr(config, "DELTA_WINDOW_MAX_DAYS", 30)
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "off")
    data_store.clear_normalized_frame_cache()


def _run(monkeypatch, market, basis, as_of):
    monkeypatch.setattr(dd, "basis_for", lambda t: basis)
    window, full = market.providers(as_of)
    return dd.delta_update(["AAPL"], asker=Asker.SCAN, today=as_of,
                           fetch_window=window, fetch_full=full)["AAPL"]


def _assert_parity(market, basis, as_of, got):
    want = market.frame(basis, as_of)[OHLCV]
    pd.testing.assert_frame_equal(got[OHLCV], want, check_freq=False, check_names=False, rtol=1e-12)
    disk = dd.read_daily("AAPL", basis)
    pd.testing.assert_frame_equal(disk, want[want.index.date < as_of], check_freq=False,
                                  check_names=False, rtol=1e-12)


@pytest.mark.parametrize("basis", BASES)
def test_parity_dividend_older_than_overlap(monkeypatch, caplog, basis):
    """A 0.3% dividend, ex-date 2026-09-15, published only on 2026-10-14: the
    overlap bars after the ex-date agree exactly and the window holds no
    action, so only the anchor bar can see it."""
    m = Market(divs=[("2026-09-15", 0.30, date(2026, 10, 14))])
    _assert_parity(m, basis, T0, _run(monkeypatch, m, basis, T0))
    _assert_parity(m, basis, TMID, _run(monkeypatch, m, basis, TMID))
    assert [c[0] for c in m.calls].count("full") == 1
    with caplog.at_level(logging.INFO, logger=dd.log.name):
        got = _run(monkeypatch, m, basis, T1)
    assert "full refetch (anchor)" in caplog.text
    _assert_parity(m, basis, T1, got)


@pytest.mark.parametrize("basis", BASES)
def test_parity_dividend_inside_window(monkeypatch, caplog, basis):
    m = Market(divs=[("2026-10-13", 0.30, date(2026, 10, 13))])
    _run(monkeypatch, m, basis, T0)
    with caplog.at_level(logging.INFO, logger=dd.log.name):
        got = _run(monkeypatch, m, basis, T1)
    assert ("full refetch (event)" if basis == dd.BASIS_YF else "full refetch (anchor)") in caplog.text
    _assert_parity(m, basis, T1, got)


@pytest.mark.parametrize("basis", BASES)
def test_parity_split(monkeypatch, caplog, basis):
    m = Market(splits=[("2026-10-08", 2.0, date(2026, 10, 8))])
    _run(monkeypatch, m, basis, T0)
    with caplog.at_level(logging.INFO, logger=dd.log.name):
        got = _run(monkeypatch, m, basis, T1)
    assert "full refetch (" in caplog.text
    _assert_parity(m, basis, T1, got)


@pytest.mark.parametrize("basis", BASES)
def test_parity_fewer_than_three_overlap_bars(monkeypatch, caplog, basis):
    m = Market()
    _run(monkeypatch, m, basis, T0)
    disk = dd.read_daily("AAPL", basis)
    data_store.atomic_write_csv(disk[disk.index <= "2026-09-23"], dd.cache_file("AAPL", basis))
    meta = dd.read_meta("AAPL", basis)
    dd._write_meta("AAPL", basis, dataclasses.replace(meta, anchor_checked=T1.isoformat()))
    with caplog.at_level(logging.INFO, logger=dd.log.name):
        got = _run(monkeypatch, m, basis, T1)
    assert "full refetch (overlap-short)" in caplog.text
    _assert_parity(m, basis, T1, got)


def test_alpaca_frame_never_written_to_yfinance_cache(monkeypatch):
    m = Market()
    with pytest.raises(ValueError, match="cannot be written"):
        dd.write_daily("AAPL", m.frame(dd.BASIS_ALPACA, T0), basis=dd.BASIS_YF, full=True, today=T0)
    assert not os.path.exists(dd.cache_file("AAPL", dd.BASIS_YF))
    m.missing.add(("full", dd.BASIS_ALPACA))         # Alpaca misses the cold symbol
    got = _run(monkeypatch, m, dd.BASIS_ALPACA, T0)
    assert got.attrs["source"] == "yfinance-fallback"
    assert not os.path.exists(dd.cache_file("AAPL", dd.BASIS_ALPACA))
    assert dd.read_meta("AAPL", dd.BASIS_YF).basis == dd.BASIS_YF


def test_yfinance_frame_never_written_to_alpaca_cache():
    m = Market()
    with pytest.raises(ValueError, match="cannot be written"):
        dd.write_daily("AAPL", m.frame(dd.BASIS_YF, T0), basis=dd.BASIS_ALPACA, full=True, today=T0)
    untagged = m.frame(dd.BASIS_ALPACA, T0)
    untagged.attrs = {}
    with pytest.raises(ValueError, match="cannot be written"):
        dd.write_daily("AAPL", untagged, basis=dd.BASIS_ALPACA, full=True, today=T0)
    assert not os.path.exists(dd.cache_file("AAPL", dd.BASIS_ALPACA))
