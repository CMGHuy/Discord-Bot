"""V183-10: the short-interest cache -- parse yfinance .info, refresh off the
scan path, read disk only, never fabricate a value."""
import datetime as dt
import json

import pytest

from swingbot import config
from swingbot.core.market import short_interest as si

TODAY = dt.date(2026, 10, 21)
NOW = dt.datetime(2026, 10, 21, 21, 40, tzinfo=dt.timezone.utc)


def _epoch(day: str) -> int:
    return int(dt.datetime.fromisoformat(day).replace(tzinfo=dt.timezone.utc).timestamp())


INFO = {"shortPercentOfFloat": 0.182, "shortRatio": 4.08, "floatShares": 45_300_000,
        "sharesShort": 8_244_600, "dateShortInterest": _epoch("2026-10-15"),
        "exDividendDate": _epoch("2026-10-24"), "lastDividendValue": 0.42,
        "lastDividendDate": _epoch("2026-07-24")}


@pytest.fixture(autouse=True)
def _data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    return tmp_path


def _parsed(ticker):
    return si.parse_info(INFO, today=TODAY)


def test_parse_info_converts_fraction_and_epoch_fields():
    out = si.parse_info(INFO, today=TODAY)
    assert out["short_pct_float"] == 18.2                 # never 0.2
    assert out["days_to_cover"] == 4.1
    assert out["float_shares"] == 45_300_000.0
    assert out["si_date"] == "2026-10-15"                  # never a raw integer
    assert out["ex_div_date"] == "2026-10-24"
    assert out["div_per_share"] == 0.42 and out["div_estimated"] is True
    assert dt.datetime.fromisoformat(out["fetched_at"]).tzinfo is not None


def test_parse_info_falls_back_to_shares_short_over_float():
    out = si.parse_info({**INFO, "shortPercentOfFloat": None}, today=TODAY)
    assert out["short_pct_float"] == 18.2


def test_announced_dividend_is_not_an_estimate():
    out = si.parse_info({**INFO, "lastDividendDate": INFO["exDividendDate"]}, today=TODAY)
    assert out["div_estimated"] is False


@pytest.mark.parametrize("bad", [None, "n/a", float("nan"), 0, -1, True])
def test_every_missing_or_unusable_field_is_none_never_zero(bad):
    out = si.parse_info({key: bad for key in INFO}, today=TODAY)
    for key in ("short_pct_float", "days_to_cover", "float_shares", "si_date",
                "ex_div_date", "div_per_share"):
        assert out[key] is None, key
    assert out["div_estimated"] is False


def test_refresh_writes_the_cache_and_keeps_old_entries_on_failure():
    def fetch(ticker):
        if ticker == "BAD":
            raise RuntimeError("yahoo 429")
        return _parsed(ticker)

    assert si.refresh_short_interest(["gme", "BAD"], now=NOW, fetch=fetch) == {"updated": 1, "failed": ["BAD"]}
    assert si.cached_short_interest("GME")["short_pct_float"] == 18.2
    assert si.cached_short_interest("BAD") is None

    assert si.refresh_short_interest(["GME"], now=NOW, fetch=lambda t: 1 / 0) == {"updated": 0, "failed": ["GME"]}
    assert si.cached_short_interest("gme")["short_pct_float"] == 18.2        # kept, case-insensitive


def test_cached_read_is_none_on_a_miss_and_raises_on_a_corrupt_file(_data_dir):
    assert si.cached_short_interest("GME") is None                          # no file yet
    (_data_dir / si.CACHE_NAME).write_text("{half-written", encoding="utf-8")
    with pytest.raises(si.ShortInterestCacheError):
        si.cached_short_interest("GME")


def test_a_corrupt_cache_does_not_stop_the_refresh(_data_dir):
    (_data_dir / si.CACHE_NAME).write_text("[]", encoding="utf-8")         # wrong shape
    assert si.refresh_short_interest(["GME"], now=NOW, fetch=_parsed)["updated"] == 1
    assert si.cached_short_interest("GME") is not None


def test_cached_read_never_fetches(monkeypatch):
    monkeypatch.setattr(si, "fetch_short_interest", lambda t: pytest.fail("network on the alert path"))
    assert si.cached_short_interest("GME") is None


def test_a_miss_is_queued_and_cleared_by_the_next_refresh(_data_dir, monkeypatch):
    monkeypatch.setattr(si, "_watchlist", lambda: ["AAPL"])
    monkeypatch.setattr(si, "_short_universe", lambda today: ["XOM"])
    monkeypatch.setattr(si, "_open_short_tickers", lambda: ["TSLA", "AAPL"])
    si.request_refresh("rivn")
    assert si.refresh_symbols() == ["AAPL", "RIVN", "TSLA", "XOM"]
    si.refresh_short_interest(["RIVN"], now=NOW, fetch=_parsed)
    assert "RIVN" not in json.loads((_data_dir / si.QUEUE_NAME).read_text(encoding="utf-8"))


def test_request_refresh_never_raises(monkeypatch):
    def boom(*args):
        raise OSError("disk full")
    monkeypatch.setattr(si, "atomic_write_json", boom)
    si.request_refresh("GME")                                               # no exception


def test_refresh_symbols_survives_a_failing_source(monkeypatch):
    def boom():
        raise RuntimeError("db down")
    monkeypatch.setattr(si, "_watchlist", boom)
    monkeypatch.setattr(si, "_short_universe", lambda today: ["XOM"])
    monkeypatch.setattr(si, "_open_short_tickers", lambda: [])
    assert si.refresh_symbols() == ["XOM"]
