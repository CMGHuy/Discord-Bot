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


# --- V109-2: ratio and scaling ---------------------------------------------
import pickle

import pandas as pd

READING = sm.SpotRatio("XAUUSD", 4151.70, "GC=F", 4175.30, 4151.70 / 4175.30)


def _gc():
    df = pd.DataFrame({"Open": [4000.0, 4010.0], "High": [4020.0, 4030.0],
                       "Low": [3990.0, 4000.0], "Close": [4010.0, 4020.0],
                       "Volume": [1000.0, 1200.0]},
                      index=pd.DatetimeIndex(["2026-09-24", "2026-09-25"]))
    df.attrs["source"] = "yfinance"
    return df


def test_ratio_is_spot_over_the_live_future(monkeypatch):
    _serve(monkeypatch, _body())
    asked = []
    monkeypatch.setattr(sm, "_futures_price", lambda s: asked.append(s) or 4175.30)
    reading, reason = sm.spot_ratio_detail("XAUUSD", now=NOW)
    assert (reading, reason) == (READING, "")
    assert asked == ["GC=F"]
    assert f"{reading.ratio:.5f}" == "0.99435"
    assert sm.spot_ratio("XAUUSD", now=NOW) == READING.ratio


def test_missing_quote_never_asks_for_the_future(monkeypatch):
    _serve(monkeypatch, OSError("down"))
    monkeypatch.setattr(sm, "_futures_price", lambda s: pytest.fail("no futures read"))
    assert sm.spot_ratio_detail("XAUUSD", now=NOW) == (None, "spot quote missing")


@pytest.mark.parametrize("futures", [None, 0.0, -1.0])
def test_missing_future_is_none(monkeypatch, futures):
    _serve(monkeypatch, _body())
    monkeypatch.setattr(sm, "_futures_price", lambda s: futures)
    assert sm.spot_ratio_detail("XAUUSD", now=NOW) == (None, "GC=F live price unavailable")


@pytest.mark.parametrize("futures", [3000.0, 4500.0])
def test_ratio_outside_the_sanity_band_is_rejected_and_logged(monkeypatch, caplog, futures):
    _serve(monkeypatch, _body())
    monkeypatch.setattr(sm, "_futures_price", lambda s: futures)
    caplog.set_level(logging.WARNING, logger="swing-bot.spot_metals")
    reading, reason = sm.spot_ratio_detail("XAUUSD", now=NOW)
    assert reading is None and "outside" in reason
    assert any("outside" in r.getMessage() for r in caplog.records)
    assert sm.spot_ratio("XAUUSD", now=NOW) is None


def test_futures_price_is_a_trading_grade_read(monkeypatch):
    from swingbot.core.marketdata import data as data_mod
    seen = {}

    def fake(tickers, *, allow_stale=True):
        seen.update(tickers=list(tickers), allow_stale=allow_stale)
        return {"GC=F": 4175.30}
    monkeypatch.setattr(data_mod, "get_current_price_batch", fake)
    assert sm._futures_price("GC=F") == 4175.30
    assert seen == {"tickers": ["GC=F"], "allow_stale": False}


def test_scale_frame_multiplies_prices_only():
    raw = _gc()
    out = sm.scale_frame(raw, READING)
    for col in ("Open", "High", "Low", "Close"):
        assert out[col].tolist() == pytest.approx((raw[col] * READING.ratio).tolist())
    assert out["Volume"].tolist() == [1000.0, 1200.0]
    assert raw["Close"].tolist() == [4010.0, 4020.0]          # input untouched
    assert raw.attrs == {"source": "yfinance"}
    assert out.attrs["source"] == "spot-scaled:GC=F"
    assert out.attrs["spot_ratio"] == READING.ratio
    assert out.attrs["spot_price"] == 4151.70
    assert out.attrs["futures_price"] == 4175.30
    assert out.attrs["spot_underlying"] == "GC=F"


def test_scaled_attrs_survive_the_spawn_pickle():
    out = sm.scale_frame(_gc(), READING)
    assert pickle.loads(pickle.dumps(out)).attrs == out.attrs


def test_scale_underlying_checks_bars_before_any_network(monkeypatch):
    monkeypatch.setattr(sm, "spot_ratio_detail", lambda *a, **k: pytest.fail("no ratio read"))
    assert sm.scale_underlying("XAUUSD", None) == (None, "no GC=F bars")
    assert sm.scale_underlying("XAUUSD", _gc().iloc[0:0]) == (None, "no GC=F bars")


def test_scale_underlying_passes_the_ratio_reason_through(monkeypatch):
    monkeypatch.setattr(sm, "spot_ratio_detail", lambda *a, **k: (None, "spot quote stale (1200s old)"))
    assert sm.scale_underlying("XAUUSD", _gc()) == (None, "spot quote stale (1200s old)")


def test_scale_underlying_scales(monkeypatch):
    monkeypatch.setattr(sm, "spot_ratio_detail", lambda *a, **k: (READING, ""))
    df, reason = sm.scale_underlying("XAUUSD", _gc())
    assert reason == "" and df.attrs["source"] == "spot-scaled:GC=F"
    assert df["Close"].iloc[-1] == pytest.approx(4020.0 * READING.ratio)
