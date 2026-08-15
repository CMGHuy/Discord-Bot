"""FMP client: URL/key building, error classification, and crawl isolation.
Fully mocked -- no network. _raw_get is monkeypatched to simulate responses."""
import json
import urllib.error

import pytest

from swingbot.core import fmp_client as fc
from swingbot.core.fmp_client import (
    FMPClient, FMPAccessError, FMPError, FMPRateLimitError, VALID_INTERVALS,
)


def _client(**kw):
    # no throttle in tests; a dummy key so _get doesn't short-circuit
    return FMPClient(api_key="TESTKEY", min_interval_s=0.0, **kw)


# ------------------------------------------------------------------ url/key

def test_build_url_injects_key_and_drops_none():
    c = _client()
    url = c._build_url("income-statement", {"symbol": "AAPL", "period": None, "limit": 5})
    assert url.startswith("https://financialmodelingprep.com/stable/income-statement?")
    assert "symbol=AAPL" in url and "limit=5" in url
    assert "period=" not in url          # None dropped
    assert "apikey=TESTKEY" in url


def test_missing_key_is_gated():
    c = FMPClient(api_key="", min_interval_s=0.0)
    # env/config may or may not supply one; force empty to test the guard
    c.api_key = ""
    with pytest.raises(FMPAccessError):
        c._get("profile", symbol="AAPL")


# ---------------------------------------------------------- error mapping

def test_402_maps_to_access_error(monkeypatch):
    c = _client()

    def raise_402(url):
        raise urllib.error.HTTPError(url, 402, "Payment Required", {}, None)

    monkeypatch.setattr(c, "_raw_get", raise_402)
    with pytest.raises(FMPAccessError):
        c._get("ratios", symbol="AAPL")


def test_429_retries_then_rate_limit_error(monkeypatch):
    c = _client(max_retries=2)
    calls = {"n": 0}

    def raise_429(url):
        calls["n"] += 1
        raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, None)

    monkeypatch.setattr(c, "_raw_get", raise_429)
    monkeypatch.setattr(fc.time, "sleep", lambda *_: None)  # no real backoff wait
    with pytest.raises(FMPRateLimitError):
        c._get("quote", symbol="AAPL")
    assert calls["n"] == 3   # initial + 2 retries


def test_premium_message_in_200_body_is_gated(monkeypatch):
    c = _client()
    monkeypatch.setattr(c, "_raw_get",
                        lambda url: (200, json.dumps({"Error Message": "Exclusive to premium members"})))
    with pytest.raises(FMPAccessError):
        c._get("earnings-call-transcript", symbol="AAPL", year=2024, quarter=1)


def test_generic_error_message_is_plain_error(monkeypatch):
    c = _client()
    monkeypatch.setattr(c, "_raw_get",
                        lambda url: (200, json.dumps({"Error Message": "Invalid symbol XYZ"})))
    with pytest.raises(FMPError) as ei:
        c._get("profile", symbol="XYZ")
    assert not isinstance(ei.value, FMPAccessError)


def test_non_json_body_is_error(monkeypatch):
    c = _client()
    monkeypatch.setattr(c, "_raw_get", lambda url: (200, "<html>oops</html>"))
    with pytest.raises(FMPError):
        c._get("profile", symbol="AAPL")


def test_ok_list_passes_through(monkeypatch):
    c = _client()
    monkeypatch.setattr(c, "_raw_get", lambda url: (200, json.dumps([{"symbol": "AAPL"}])))
    assert c.profile("AAPL") == [{"symbol": "AAPL"}]


# ------------------------------------------------------------ interval guard

def test_intraday_rejects_bad_interval():
    c = _client()
    with pytest.raises(ValueError):
        c.intraday("AAPL", "3min")


def test_intraday_accepts_valid_intervals(monkeypatch):
    c = _client()
    seen = {}
    monkeypatch.setattr(c, "_get", lambda path, **p: seen.setdefault("path", path))
    c.intraday("AAPL", "15min")
    assert seen["path"] == "historical-chart/15min"


# --------------------------------------------------------- crawl isolation

def test_crawl_all_isolates_failures(monkeypatch):
    """A gated/error endpoint must not abort the crawl; every endpoint gets a
    result with the right status."""
    c = _client()

    def fake_get(path, **params):
        if "ratios" in path:
            raise FMPAccessError("gated")
        if "grades" in path:
            raise FMPError("boom")
        if path == "quote":
            return []                       # empty
        return [{"x": 1}]                   # ok

    monkeypatch.setattr(c, "_get", fake_get)
    results = c.crawl_all("aapl", intervals=("1hour",))

    assert results["profile"].status == "ok" and results["profile"].n == 1
    assert results["quote"].status == "empty"
    assert results["ratios"].status == "gated"
    assert results["grades"].status == "error"
    assert results["intraday_1hour"].status == "ok"
    # crawl covered every registered endpoint plus the one interval
    assert len(results) == len(c._endpoints("AAPL", intervals=("1hour",)))


def test_probe_strips_payload(monkeypatch):
    c = _client()
    monkeypatch.setattr(c, "_get", lambda path, **p: [{"a": 1}])
    rows = c.probe("AAPL", intervals=("1hour",))
    assert all(r.data is None for r in rows)
    assert all(r.status == "ok" for r in rows)


def test_default_intervals_are_valid():
    assert all(iv in VALID_INTERVALS for iv in fc.DEFAULT_INTRADAY)
