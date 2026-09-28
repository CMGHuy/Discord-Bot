"""v109: spot gold/silver -- pair table, quote client, staleness."""
import json
import logging
from datetime import datetime, timedelta, timezone

import pytest

from swingbot import config
from swingbot.core.marketdata import spot_metals as sm

NOW = datetime(2026, 9, 28, 9, 45, tzinfo=timezone.utc)


def _body(price=4151.70, updated=NOW):
    return json.dumps({"name": "Gold", "price": price, "symbol": "XAU",
                       "updatedAt": updated.isoformat().replace("+00:00", "Z")})


def _serve(monkeypatch, *bodies):
    """Stub the HTTP GET: the Nth call gets bodies[N] (the last repeats);
    an Exception instance is raised instead of returned."""
    calls = []

    def fake(url):
        calls.append(url)
        body = bodies[min(len(calls) - 1, len(bodies) - 1)]
        if isinstance(body, Exception):
            raise body
        return body
    monkeypatch.setattr(sm, "_raw_get", fake)
    return calls


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    sm.reset()
    monkeypatch.setattr(config, "SPOT_QUOTE_MAX_AGE_SECONDS", 900)
    clock = [1000.0]
    monkeypatch.setattr(sm, "_now_mono", lambda: clock[0])
    yield clock
    sm.reset()


def test_config_field_declared_in_data_sources():
    keys = {f.key: f for f in config.FIELDS}
    field = keys["SPOT_QUOTE_MAX_AGE_SECONDS"]
    assert field.section == "Data Sources"
    assert field.type == "number" and field.default == "900"


def test_source_tags():
    from swingbot.core.marketdata.providers import base
    assert base.SOURCE_SPOT == "spot"
    assert base.SOURCE_SPOT_SCALED == "spot-scaled"


def test_pair_table_and_membership():
    assert sm.SPOT_PAIRS == {"XAUUSD": ("XAU", "GC=F"), "XAGUSD": ("XAG", "SI=F")}
    assert sm.is_spot_metal("XAUUSD") and sm.is_spot_metal(" xagusd ")
    for other in ("GC=F", "SI=F", "GOLD", "XAU", "AAPL", "", None):
        assert not sm.is_spot_metal(other)
    assert sm.underlying("xauusd") == "GC=F" and sm.underlying("XAGUSD") == "SI=F"
    with pytest.raises(KeyError):
        sm.underlying("AAPL")


def test_cache_symbols_map_spot_to_its_future():
    assert sm.cache_symbol("XAUUSD") == "GC=F"
    assert sm.cache_symbol("AAPL") == "AAPL"
    assert sm.cache_symbols(["XAUUSD", "GC=F", "AAPL", "XAGUSD"]) == ["GC=F", "AAPL", "SI=F"]


def test_split_spot_preserves_order():
    assert sm.split_spot(["AAPL", "XAUUSD", "SI=F", "XAGUSD"]) == (
        ["XAUUSD", "XAGUSD"], ["AAPL", "SI=F"])


def test_quote_parsed_from_the_gold_api_payload(monkeypatch):
    calls = _serve(monkeypatch, _body())
    quote = sm.spot_quote("XAUUSD", now=NOW + timedelta(seconds=30))
    assert quote == sm.SpotQuote(4151.70, NOW)
    assert calls == ["https://api.gold-api.com/price/XAU"]


def test_silver_asks_for_xag(monkeypatch):
    calls = _serve(monkeypatch, _body(price=48.12))
    assert sm.spot_quote("XAGUSD", now=NOW).price == 48.12
    assert calls == ["https://api.gold-api.com/price/XAG"]


def test_non_spot_symbol_never_fetches(monkeypatch):
    calls = _serve(monkeypatch, _body())
    assert sm.quote_with_reason("AAPL", now=NOW) == (None, "AAPL is not a spot metal")
    assert calls == []


def test_quote_cached_for_fifteen_seconds(monkeypatch, _clean):
    clock = _clean
    calls = _serve(monkeypatch, _body(), _body(price=4160.0))
    first = sm.spot_quote("XAUUSD", now=NOW)
    clock[0] += 14
    assert sm.spot_quote("XAUUSD", now=NOW) == first and len(calls) == 1
    clock[0] += 2
    assert sm.spot_quote("XAUUSD", now=NOW).price == 4160.0 and len(calls) == 2


def test_stale_quote_is_treated_as_missing(monkeypatch):
    _serve(monkeypatch, _body())
    assert sm.spot_quote("XAUUSD", now=NOW + timedelta(seconds=900)) is not None
    quote, reason = sm.quote_with_reason("XAUUSD", now=NOW + timedelta(seconds=901))
    assert quote is None and reason.startswith("spot quote stale")


def test_staleness_reads_the_config_at_call_time(monkeypatch):
    _serve(monkeypatch, _body())
    monkeypatch.setattr(config, "SPOT_QUOTE_MAX_AGE_SECONDS", 60)
    assert sm.spot_quote("XAUUSD", now=NOW + timedelta(seconds=61)) is None


@pytest.mark.parametrize("body", [
    "not json",
    json.dumps({"price": 0, "updatedAt": "2026-09-28T09:45:00Z"}),
    json.dumps({"price": -3.0, "updatedAt": "2026-09-28T09:45:00Z"}),
    json.dumps({"updatedAt": "2026-09-28T09:45:00Z"}),
    json.dumps({"price": 4151.7}),
])
def test_bad_payloads_are_none_never_raised(monkeypatch, body):
    _serve(monkeypatch, body)
    quote, reason = sm.quote_with_reason("XAUUSD", now=NOW)
    assert quote is None and reason == "spot quote missing"


def test_http_error_logged_once_per_failure_streak(monkeypatch, caplog, _clean):
    clock = _clean
    _serve(monkeypatch, OSError("boom"), OSError("boom"), _body())
    caplog.set_level(logging.INFO, logger="swing-bot.spot_metals")
    assert sm.spot_quote("XAUUSD", now=NOW) is None
    clock[0] += 20
    assert sm.spot_quote("XAUUSD", now=NOW) is None
    assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 1
    clock[0] += 20
    assert sm.spot_quote("XAUUSD", now=NOW).price == 4151.70
    assert any("recovered" in r.getMessage() for r in caplog.records)


def test_a_failure_is_cached_too(monkeypatch, _clean):
    """An outage must not turn every caller into a 10 s blocking GET."""
    calls = _serve(monkeypatch, OSError("boom"))
    sm.spot_quote("XAUUSD", now=NOW)
    sm.spot_quote("XAUUSD", now=NOW)
    assert len(calls) == 1
