"""v171 D1/D2: ticker metadata (persistent) and intraday bars through the layer."""
import contextlib
import os
import time
from datetime import datetime, timezone

import pytest

from swingbot import config
from swingbot.core.marketdata import data, data_store
from swingbot.core.marketdata.shared import counters, kinds, layer
from swingbot.core.marketdata.shared.kinds import PROVIDER_YF, Asker, DataKind, Entry
from tests.helpers import make_ohlcv

META = {"ASML.AS": {"name": "ASML Holding N.V.", "currency": "EUR"}}


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(data, "_company_name_cache", {})
    monkeypatch.setattr(data, "_currency_cache", {})
    saved = []
    monkeypatch.setattr(data, "_save_ticker_meta_cache", lambda: saved.append(1))
    monkeypatch.setattr("swingbot.core.marketdata.ticker_directory.lookup_name", lambda key: None)
    monkeypatch.setattr(data, "candidate_symbols", lambda t: [t])
    return saved


@pytest.fixture
def on_layer(monkeypatch):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    calls = []

    def fake_get(kind, symbols, fetch, **kw):
        calls.append({"kind": kind, "symbols": list(symbols), **kw})
        return {s: Entry(META[s], datetime.now(timezone.utc), "yfinance", "hit")
                for s in symbols if s in META}
    monkeypatch.setattr(layer, "get", fake_get)
    return calls


class FakeTicker:
    reads = []

    def __init__(self, symbol):
        self.symbol = symbol

    @property
    def info(self):
        FakeTicker.reads.append(("info", self.symbol))
        return {"longName": "ASML Holding N.V."}            # no currency: fast_info fills it

    @property
    def fast_info(self):
        FakeTicker.reads.append(("fast_info", self.symbol))
        return {"currency": "eur"}


def test_intraday_window_matches_data_store():
    assert kinds.INTRADAY_MAX_AGE_S == data_store.INTRADAY_MAX_AGE_SECONDS


def test_on_mode_name_and_currency_come_from_one_persistent_meta_doc(on_layer, isolated):
    assert data.get_company_name("asml.as") == "ASML Holding N.V."
    assert data.get_currency_symbol("ASML.AS") == "€"
    assert data.get_company_name("ASML.AS") == "ASML Holding N.V."      # in-process hit
    assert [c["kind"] for c in on_layer] == [DataKind.METADATA] * 2
    assert all(c["asker"] is Asker.BACKGROUND and c["provider"] == PROVIDER_YF for c in on_layer)
    assert len(isolated) == 2                                           # both persisted


def test_an_unanswered_lookup_is_not_cached_as_no_name(on_layer, isolated):
    assert data.get_company_name("NEWCO") is None
    assert "NEWCO" not in data._company_name_cache and isolated == []
    assert data.get_currency_symbol("NEWCO", default_symbol="€") == "€"
    assert "NEWCO" not in data._currency_cache


def test_directory_names_never_reach_the_layer(on_layer, monkeypatch):
    monkeypatch.setattr("swingbot.core.marketdata.ticker_directory.lookup_name", lambda key: "Apple Inc.")
    assert data.get_company_name("AAPL") == "Apple Inc." and on_layer == []


def test_off_mode_keeps_the_legacy_slow_path(monkeypatch):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "off")
    monkeypatch.setattr(layer, "get", lambda *a, **k: pytest.fail("layer used in off mode"))
    FakeTicker.reads = []
    monkeypatch.setattr(data.yf, "Ticker", FakeTicker)
    assert data.get_company_name("ASML.AS") == "ASML Holding N.V."
    assert FakeTicker.reads == [("info", "ASML.AS")]


def test_count_mode_counts_each_metadata_fetch(monkeypatch):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "count")
    monkeypatch.setattr(data.yf, "Ticker", FakeTicker)
    seen = []
    monkeypatch.setattr(counters, "count", lambda *a, **k: seen.append(a[:2] + a[3:]))
    data.get_company_name("ASML.AS")
    data.get_currency_symbol("ASML.AS")
    assert seen == [(PROVIDER_YF, DataKind.METADATA, "fetched")] * 2


def test_meta_fetch_reads_info_once_and_falls_back_to_fast_info(monkeypatch):
    FakeTicker.reads = []
    monkeypatch.setattr(data.yf, "Ticker", FakeTicker)
    tokens = []
    monkeypatch.setattr(data.yf_safe, "_take_yf_token", lambda: tokens.append(1))
    assert data._fetch_ticker_meta(["ASML.AS"]) == {"ASML.AS": {"name": "ASML Holding N.V.", "currency": "EUR"}}
    assert FakeTicker.reads == [("info", "ASML.AS"), ("fast_info", "ASML.AS")] and tokens


def test_meta_fetch_failure_is_a_miss(monkeypatch):
    class Broken:
        def __init__(self, s):
            pass

        @property
        def info(self):
            raise RuntimeError("yahoo")
    monkeypatch.setattr(data.yf, "Ticker", Broken)
    monkeypatch.setattr(data.yf_safe, "_take_yf_token", lambda: None)
    assert data._fetch_ticker_meta(["ZZZZ"]) == {"ZZZZ": None}


# --- intraday ---------------------------------------------------------------

def _stale_file(tmp_path, symbol="AAPL"):
    data_store.save_to_disk(make_ohlcv([10.0, 11.0]), symbol, "1h", base_dir=str(tmp_path))
    path = data_store.cache_path(symbol, "1h", base_dir=str(tmp_path))
    old = time.time() - data_store.INTRADAY_MAX_AGE_SECONDS - 60
    os.utime(path, (old, old))
    return path


def _lease_recorder(monkeypatch, held=True, on_enter=None):
    taken = []

    @contextlib.contextmanager
    def fake_lease(kind, symbol, *, asker, deadline_s=30.0):
        taken.append((kind, symbol, asker))
        if on_enter:
            on_enter()
        yield held
    monkeypatch.setattr(layer, "lease", fake_lease)
    return taken


def test_on_mode_intraday_fetches_once_under_the_lease(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    _stale_file(tmp_path)
    taken = _lease_recorder(monkeypatch)
    fetched = []
    out = data_store.get_intraday("AAPL", "1h", base_dir=str(tmp_path),
                                  fetch_fn=lambda s, i: fetched.append(s) or make_ohlcv([12.0, 13.0]))
    assert fetched == ["AAPL"] and out is not None
    assert taken == [(DataKind.INTRADAY_BARS, "AAPL:1h", Asker.SCAN)]


def test_a_file_written_by_the_other_holder_is_read_not_refetched(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    path = _stale_file(tmp_path)
    _lease_recorder(monkeypatch, held=False, on_enter=lambda: os.utime(path, None))
    out = data_store.get_intraday("AAPL", "1h", base_dir=str(tmp_path),
                                  fetch_fn=lambda s, i: pytest.fail("refetched"))
    assert out is not None and len(out) == 2


def test_off_mode_intraday_takes_no_lease(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "off")
    _stale_file(tmp_path)
    monkeypatch.setattr(layer, "lease", lambda *a, **k: pytest.fail("lease in off mode"))
    out = data_store.get_intraday("AAPL", "1h", base_dir=str(tmp_path),
                                  fetch_fn=lambda s, i: make_ohlcv([12.0, 13.0]))
    assert out is not None
