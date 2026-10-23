"""v183 / v171 D1: selected yfinance ``.info`` fields (the short-interest
refresh's lookup) go through the shared layer like every other provider call."""
from datetime import datetime, timezone

import pytest

from swingbot import config
from swingbot.core.marketdata import data
from swingbot.core.marketdata.shared import layer
from swingbot.core.marketdata.shared.kinds import PROVIDER_YF, Asker, DataKind, Entry

KEYS = ("shortRatio", "floatShares", "dateShortInterest")


class FakeTicker:
    reads = []

    def __init__(self, symbol):
        self.symbol = symbol

    @property
    def info(self):
        FakeTicker.reads.append(self.symbol)
        return {"shortRatio": 4.08, "floatShares": float("nan"), "longBusinessSummary": "x" * 500}


def test_fetch_keeps_only_the_asked_keys_and_drops_non_finite_numbers(monkeypatch):
    FakeTicker.reads = []
    monkeypatch.setattr(data.yf, "Ticker", FakeTicker)
    tokens = []
    monkeypatch.setattr(data.yf_safe, "_take_yf_token", lambda: tokens.append(1))
    out = data._fetch_info_fields(["GME", "AMC"], keys=KEYS)
    assert out == {s: {"shortRatio": 4.08, "floatShares": None, "dateShortInterest": None}
                   for s in ("GME", "AMC")}
    assert FakeTicker.reads == ["GME", "AMC"] and len(tokens) == 2      # one budget token each


def test_fetch_of_an_empty_info_is_a_doc_of_nones(monkeypatch):
    class Empty:
        def __init__(self, s):
            self.info = None
    monkeypatch.setattr(data.yf, "Ticker", Empty)
    monkeypatch.setattr(data.yf_safe, "_take_yf_token", lambda: None)
    assert data._fetch_info_fields(["ZZZZ"], keys=KEYS) == {"ZZZZ": dict.fromkeys(KEYS)}


def test_fetch_error_propagates_so_the_caller_counts_a_failure(monkeypatch):
    class Broken:
        def __init__(self, s):
            pass

        @property
        def info(self):
            raise RuntimeError("yahoo")
    monkeypatch.setattr(data.yf, "Ticker", Broken)
    monkeypatch.setattr(data.yf_safe, "_take_yf_token", lambda: None)
    with pytest.raises(RuntimeError):
        data._fetch_info_fields(["ZZZZ"], keys=KEYS)


def test_get_info_fields_asks_the_layer_as_background_metadata_never_cached(monkeypatch):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    calls = []
    entry = Entry({"shortRatio": 4.08}, datetime(2026, 10, 21, tzinfo=timezone.utc), "yfinance", "fetched")

    def fake_get(kind, symbols, fetch, **kw):
        calls.append({"kind": kind, "symbols": list(symbols), "keys": fetch.keywords["keys"], **kw})
        return {"GME": entry}
    monkeypatch.setattr(layer, "get", fake_get)
    assert data.get_info_fields("GME", KEYS, variant="short_interest") is entry
    assert calls == [{"kind": DataKind.METADATA, "symbols": ["GME"], "keys": KEYS,
                      "asker": Asker.BACKGROUND, "provider": PROVIDER_YF,
                      "params": "short_interest", "max_age_s": 0.0}]


def test_get_info_fields_is_none_when_the_layer_has_nothing(monkeypatch):
    monkeypatch.setattr(layer, "get", lambda *a, **k: {})
    assert data.get_info_fields("GME", KEYS, variant="short_interest") is None


def test_off_mode_fetches_directly(monkeypatch):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "off")
    FakeTicker.reads = []
    monkeypatch.setattr(data.yf, "Ticker", FakeTicker)
    entry = data.get_info_fields("GME", KEYS, variant="short_interest")
    assert entry.value["shortRatio"] == 4.08 and FakeTicker.reads == ["GME"]
