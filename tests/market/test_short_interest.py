"""V183-10: the short-interest cache -- parse yfinance .info, refresh off the
scan path, read disk only, never fabricate a value."""
import datetime as dt
import json
import logging
import threading

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

    assert si.refresh_short_interest(["gme", "BAD"], now=NOW, fetch=fetch) == {
        "updated": 1, "failed": ["BAD"], "retried": 1, "recovered": 0}
    assert si.cached_short_interest("GME")["short_pct_float"] == 18.2
    assert si.cached_short_interest("BAD") is None

    assert si.refresh_short_interest(["GME"], now=NOW, fetch=lambda t: 1 / 0) == {
        "updated": 0, "failed": ["GME"], "retried": 1, "recovered": 0}
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


def test_open_short_tickers_reads_bearish_plans_and_open_trades(monkeypatch):
    """Exercises the real imports: the trade-log import once pointed at a module
    that does not exist, so this source raised on every refresh in production."""
    from types import SimpleNamespace
    from swingbot.core.planning import plan_store
    from swingbot.core.tracking import performance
    plans = [SimpleNamespace(ticker="TSLA", direction="bearish"),
             SimpleNamespace(ticker="AAPL", direction="bullish")]
    trades = [{"ticker": "RIVN", "direction": "bearish"},
              {"ticker": "MSFT", "direction": "bullish"}]
    calls = {}

    class _Plans:
        def open_plans(self):
            return plans

    class _Trades:
        def get_trades(self, **kwargs):
            calls.update(kwargs)
            return trades

    monkeypatch.setattr(plan_store, "PlanStore", _Plans)
    monkeypatch.setattr(performance, "TradeLog", _Trades)
    assert si._open_short_tickers() == ["TSLA", "RIVN"]
    assert calls == {"status": "open", "limit": None}


def test_open_short_tickers_empty_book(monkeypatch):
    from swingbot.core.planning import plan_store
    from swingbot.core.tracking import performance
    monkeypatch.setattr(plan_store, "PlanStore",
                        lambda: type("P", (), {"open_plans": lambda self: []})())
    monkeypatch.setattr(performance, "TradeLog",
                        lambda: type("T", (), {"get_trades": lambda self, **k: []})())
    assert si._open_short_tickers() == []


def _info_entry(fetched_at=NOW):
    from swingbot.core.marketdata.shared.kinds import Entry
    return Entry({k: INFO.get(k) for k in si.INFO_KEYS}, fetched_at, "yfinance", "fetched")


def test_fetch_reads_only_the_parsed_info_keys_through_the_shared_layer(monkeypatch):
    from swingbot.core.marketdata import data
    asked = []
    monkeypatch.setattr(data, "get_info_fields",
                        lambda t, keys, *, variant: asked.append((t, keys, variant)) or _info_entry())
    out = si.fetch_short_interest("gme")
    assert asked == [("gme", si.INFO_KEYS, "short_interest")]
    assert {k: v for k, v in out.items() if k != "fetched_at"} == {
        k: v for k, v in si.parse_info(INFO, today=dt.date.today()).items() if k != "fetched_at"}
    assert set(si.INFO_KEYS) >= {"shortPercentOfFloat", "exDividendDate", "lastDividendValue"}


def test_fetch_stamps_when_the_value_was_fetched_not_when_it_was_read(monkeypatch):
    """A budget-deferred layer serves an older cached doc; its age is not hidden."""
    from swingbot.core.marketdata import data
    old = dt.datetime(2026, 10, 1, 21, 40, tzinfo=dt.timezone.utc)
    monkeypatch.setattr(data, "get_info_fields", lambda t, keys, *, variant: _info_entry(old))
    assert si.fetch_short_interest("GME")["fetched_at"] == old.isoformat()


def test_fetch_with_no_layer_answer_is_a_failure_not_an_empty_entry(_data_dir, monkeypatch):
    from swingbot.core.marketdata import data
    monkeypatch.setattr(data, "get_info_fields", lambda t, keys, *, variant: None)
    with pytest.raises(si.ShortInterestUnavailable):
        si.fetch_short_interest("GME")
    assert si.refresh_short_interest(["GME"], now=NOW) == {
        "updated": 0, "failed": ["GME"], "retried": 1, "recovered": 0}


# --- v248 § 6: the job fits its pool -----------------------------------------------

@pytest.mark.parametrize("limits, workers", [((1, 1), 2), ((1, 0), 1), ((0, 0), 1)])
def test_workers_equal_the_side_pool_capacity(monkeypatch, limits, workers):
    from swingbot.core.db import side_engine
    monkeypatch.setattr(side_engine, "pool_limits", lambda: limits)
    assert si._worker_count() == workers


def test_the_parallel_pass_uses_the_pool_capacity(monkeypatch):
    from swingbot.core.db import side_engine
    monkeypatch.setattr(side_engine, "pool_limits", lambda: (1, 1))
    seen = []
    real = si.ThreadPoolExecutor

    def recording(max_workers=None, **kw):
        seen.append(max_workers)
        return real(max_workers=max_workers, **kw)

    monkeypatch.setattr(si, "ThreadPoolExecutor", recording)
    si.refresh_short_interest(["GME", "TSLA"], now=NOW, fetch=_parsed)
    assert seen == [2]


def test_a_failed_first_pass_is_retried_once_serially(monkeypatch):
    main = threading.get_ident()
    calls, retry_threads = [], []

    def flaky(ticker):
        calls.append(ticker)
        if ticker == "FLAKY" and calls.count("FLAKY") == 1:
            raise RuntimeError("QueuePool limit of size 1 overflow 1 reached")
        if ticker == "DEAD":
            if calls.count("DEAD") == 2:
                retry_threads.append(threading.get_ident())
            raise RuntimeError("no .info")
        if calls.count(ticker) == 2:
            retry_threads.append(threading.get_ident())
        return _parsed(ticker)

    result = si.refresh_short_interest(["GME", "FLAKY", "DEAD"], now=NOW, fetch=flaky)
    assert result == {"updated": 2, "failed": ["DEAD"], "retried": 2, "recovered": 1}
    assert sorted(calls) == ["DEAD", "DEAD", "FLAKY", "FLAKY", "GME"]    # each failure retried once
    assert calls[-2:] in (["FLAKY", "DEAD"], ["DEAD", "FLAKY"])           # the retry pass runs last
    assert retry_threads == [main, main]                                  # ... on the calling thread
    assert si.cached_short_interest("FLAKY") is not None


def test_nothing_is_retried_when_the_first_pass_succeeds():
    calls = []
    result = si.refresh_short_interest(["GME", "TSLA"], now=NOW,
                                       fetch=lambda t: calls.append(t) or _parsed(t))
    assert result == {"updated": 2, "failed": [], "retried": 0, "recovered": 0}
    assert sorted(calls) == ["GME", "TSLA"]


@pytest.mark.parametrize("result, total, level, text", [
    ({"updated": 65, "failed": ["X"] * 27, "retried": 30, "recovered": 3}, 92, logging.WARNING,
     "65 updated, 27 failed of 92 symbols, retried 30, recovered 3"),
    ({"updated": 83, "failed": ["X"] * 9, "retried": 12, "recovered": 3}, 92, logging.INFO,
     "83 updated, 9 failed of 92 symbols, retried 12, recovered 3"),       # 9.8 %: not above 10 %
    ({"updated": 9, "failed": ["X"], "retried": 1, "recovered": 0}, 10, logging.INFO,
     "9 updated, 1 failed of 10 symbols, retried 1, recovered 0"),         # exactly 10 %: not above
    ({"updated": 0, "failed": [], "retried": 0, "recovered": 0}, 0, logging.INFO,
     "0 updated, 0 failed of 0 symbols, retried 0, recovered 0"),          # no symbols: no division
    ({"updated": 2, "failed": []}, 2, logging.INFO,
     "2 updated, 0 failed of 2 symbols, retried 0, recovered 0"),          # an older result shape
])
def test_summary_line(result, total, level, text):
    assert si.summary_line(result, total) == (level, text)
