"""v111 §3/§4: fetch misses and fallbacks are DEBUG, per symbol, never INFO."""
import logging

import pandas as pd

from swingbot.core.marketdata import yf_safe
from swingbot.core.marketdata.providers import alpaca_provider, router
from swingbot.core.marketdata.providers.alpaca_provider import AlpacaMiss
from tests.marketdata.test_alpaca_provider import NOW, FakeClient, _prov, _snap
from tests.marketdata.test_provider_router import FakeProvider, _use, enabled  # noqa: F401


def _records(caplog, logger):
    return [r for r in caplog.records if r.name == logger.name]


def test_empty_yfinance_download_is_a_debug_line(monkeypatch, caplog):
    monkeypatch.setattr("yfinance.download", lambda *a, **k: pd.DataFrame())
    with caplog.at_level(logging.DEBUG, logger=yf_safe.log.name):
        yf_safe.download(tickers="ZZZZ", period="5d")
    [record] = _records(caplog, yf_safe.log)
    assert record.levelno == logging.DEBUG and "ZZZZ" in record.getMessage()


def test_none_yfinance_download_is_a_debug_line(monkeypatch, caplog):
    monkeypatch.setattr("yfinance.download", lambda *a, **k: None)
    with caplog.at_level(logging.DEBUG, logger=yf_safe.log.name):
        assert yf_safe.download("QQQQ", period="5d") is None
    [record] = _records(caplog, yf_safe.log)
    assert "QQQQ" in record.getMessage()


def test_nonempty_yfinance_download_is_silent(monkeypatch, caplog):
    frame = pd.DataFrame({"Close": [1.0]})
    monkeypatch.setattr("yfinance.download", lambda *a, **k: frame)
    with caplog.at_level(logging.DEBUG, logger=yf_safe.log.name):
        assert yf_safe.download(tickers="AAPL") is frame
    assert not _records(caplog, yf_safe.log)


def test_alpaca_miss_is_debug_not_info(enabled, monkeypatch, caplog):
    _use(monkeypatch, FakeProvider(exc=AlpacaMiss("boom")))
    with caplog.at_level(logging.DEBUG, logger=router.log.name):
        router.daily_bars(["AAPL"], "2y", lambda tickers, period: {})
    misses = [r for r in _records(caplog, router.log) if "miss" in r.getMessage()]
    assert misses and all(r.levelno == logging.DEBUG for r in misses)


def test_per_symbol_fallback_names_the_symbols(enabled, monkeypatch, caplog):
    _use(monkeypatch, FakeProvider(daily={"AAPL"}))
    with caplog.at_level(logging.DEBUG, logger=router.log.name):
        router.daily_bars(["AAPL", "MSFT"], "2y", lambda tickers, period: {})
    assert "Alpaca daily_bars fallback to yfinance for 1 symbol(s): MSFT" in [
        r.getMessage() for r in _records(caplog, router.log)]


def test_no_fallback_no_line(enabled, monkeypatch, caplog):
    _use(monkeypatch, FakeProvider(daily={"AAPL"}))
    with caplog.at_level(logging.DEBUG, logger=router.log.name):
        router.daily_bars(["AAPL"], "2y", lambda tickers, period: {})
    assert not any("fallback" in r.getMessage() for r in _records(caplog, router.log))


def test_latest_prices_fallback_names_the_symbols(enabled, monkeypatch, caplog):
    _use(monkeypatch, FakeProvider(prices={"AAPL": 190.0}))
    with caplog.at_level(logging.DEBUG, logger=router.log.name):
        router.latest_prices(["AAPL", "MSFT"], lambda ts: {t: 1.0 for t in ts})
    assert "Alpaca latest_prices fallback to yfinance for 1 symbol(s): MSFT" in [
        r.getMessage() for r in _records(caplog, router.log)]


def test_intraday_fallback_names_the_ticker(enabled, monkeypatch, caplog):
    _use(monkeypatch, FakeProvider())
    with caplog.at_level(logging.DEBUG, logger=router.log.name):
        router.intraday_bars("AAPL", "1h", lambda t, iv: pd.DataFrame())
    assert "Alpaca intraday_bars fallback to yfinance for 1 symbol(s): AAPL" in [
        r.getMessage() for r in _records(caplog, router.log)]


def test_stale_snapshot_names_the_symbol(caplog):
    client = FakeClient(snaps={"AAPL": _snap(190.0, NOW - pd.Timedelta(minutes=20))})
    with caplog.at_level(logging.DEBUG, logger=alpaca_provider.log.name):
        assert _prov(client).latest_prices(["AAPL"], 300) == {}
    assert ["Alpaca snapshot: no fresh price for AAPL"] == [
        r.getMessage() for r in _records(caplog, alpaca_provider.log)]


def test_fresh_snapshot_is_silent(caplog):
    client = FakeClient(snaps={"AAPL": _snap(190.0, NOW)})
    with caplog.at_level(logging.DEBUG, logger=alpaca_provider.log.name):
        assert _prov(client).latest_prices(["AAPL"], 300) == {"AAPL": 190.0}
    assert not _records(caplog, alpaca_provider.log)
