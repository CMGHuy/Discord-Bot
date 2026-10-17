"""v148 OH13: remaining marketdata handlers count under their tags."""
import time
from concurrent.futures import Future

import pytest

from swingbot.core.infra import swallowed as sw
from swingbot.core.marketdata import backtest_cache, data_store, export_data, spot_metals, ticker_directory
from swingbot.core.marketdata.providers import router


def _boom(*a, **k):
    raise RuntimeError("probe")


@pytest.fixture(autouse=True)
def _clean():
    sw.reset()
    yield
    sw.reset()


def test_router_wait_counts_and_hands_exception_back():
    failed = Future()
    failed.set_exception(RuntimeError("probe"))
    result, exc = router._wait(failed, time.monotonic() + 1)
    assert result is None and isinstance(exc, RuntimeError)
    assert sw.snapshot()["marketdata.router.wait"]["count"] == 1


def test_ticker_directory_download_counts_both_listings(monkeypatch):
    monkeypatch.setattr(ticker_directory, "_download", _boom)
    assert ticker_directory._build_directory() == []
    assert sw.snapshot()["marketdata.ticker_directory.download"]["count"] == 2


def test_spot_quote_counts_and_still_notes_failure(monkeypatch):
    monkeypatch.setattr(spot_metals, "_raw_get", _boom)
    key = next(iter(spot_metals.SPOT_PAIRS))
    assert spot_metals._fetch_quote(key) is None
    assert sw.snapshot()["marketdata.spot_quote"]["last_error"] == "RuntimeError: probe"
    assert key in spot_metals._failing
    spot_metals._failing.discard(key)


def test_ensure_cached_counts_and_reports_failed(monkeypatch, tmp_path):
    monkeypatch.setattr(backtest_cache, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(backtest_cache, "fetch", _boom)
    assert backtest_cache.ensure_cached("AAA").status == "failed"
    assert sw.snapshot()["marketdata.backtest_cache.ensure"]["count"] == 1


def test_ranged_fetch_counts_and_returns_none(monkeypatch):
    monkeypatch.setattr(data_store.yf_safe, "download", _boom)
    assert data_store._default_ranged_fetch("AAA", "2024-01-01", "1d") is None
    assert sw.snapshot()["marketdata.ranged_fetch"]["count"] == 1


def test_export_data_has_logger():
    import logging
    assert isinstance(export_data.log, logging.Logger)
