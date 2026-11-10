import pytest

from swingbot.admin import market_values as mv
from swingbot.core.marketdata import data
from swingbot.core.marketdata.shared import kinds
from swingbot.core.marketdata.shared.admin_refresh import (
    PRIORITY_FRESH_HINT, PRIORITY_MISSING, PRIORITY_USER, QUEUE_KIND_QUOTE)
from swingbot.core.marketdata.shared.kinds import DataKind

ROW_QUOTE_FIELDS = {"current_price", "current_price_stale", "price_as_of", "price_age_s",
                    "price_refreshing", "price_error"}
META_KEYS = {"as_of", "refreshing", "stale_count", "missing_count", "incomplete",
             "computed_at", "stale_inputs", "source", "error"}


@pytest.fixture(autouse=True)
def _no_provider(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("the door fetched")
    monkeypatch.setattr(data, "get_quote_batch", boom)


def test_cached_quote_is_read_with_its_age_and_no_fetch(market, session_is):
    market.quote("MSFT", 110.0, age_s=12)
    q = mv.read_quotes(["msft"])["MSFT"]
    assert q.price == 110.0 and q.refreshing is False and q.error is None
    assert 11 <= q.age_s <= 15 and q.as_of.startswith("20") and q.source == "alpaca-iex"
    assert market.queue.pending == {}


def test_never_seen_symbol_is_null_refreshing_and_enqueued_once(market, session_is):
    first = mv.read_quotes(["NEWX"])["NEWX"]
    mv.read_quotes(["NEWX"])
    assert first.price is None and first.refreshing is True
    assert market.queue.pending == {(QUEUE_KIND_QUOTE, "NEWX"): PRIORITY_MISSING}


def test_stale_symbol_is_enqueued_unless_in_flight(market, session_is):
    market.quote("OLD", 5.0, age_s=600)
    market.quote("BUSY", 6.0, age_s=600)
    market.marks.in_flight.add("quote:BUSY")
    got = mv.read_quotes(["OLD", "BUSY"])
    assert got["OLD"].refreshing is False and got["BUSY"].refreshing is True
    assert market.queue.pending == {(QUEUE_KIND_QUOTE, "OLD"): PRIORITY_MISSING}


def test_closed_market_never_requeues_old_quotes(market, session_is):
    session_is("closed")
    market.quote("MSFT", 110.0, age_s=2 * 86400)
    assert mv.read_quotes(["MSFT"])["MSFT"].price == 110.0
    assert market.queue.pending == {}


def test_fresh_hint_enqueues_every_symbol(market, session_is):
    market.quote("MSFT", 110.0, age_s=1)
    with kinds.fresh_request():
        mv.read_quotes(["MSFT", "NVDA"])
    assert market.queue.pending == {(QUEUE_KIND_QUOTE, "MSFT"): PRIORITY_FRESH_HINT,
                                    (QUEUE_KIND_QUOTE, "NVDA"): PRIORITY_FRESH_HINT}


def test_enqueue_false_never_writes_the_queue(market, session_is):
    mv.read_quotes(["NEWX"], enqueue=False)
    assert market.queue.pending == {}


def test_index_quotes_read_their_own_kind(market, session_is):
    market.quote("^GSPC", 5000.0, age_s=5, kind=DataKind.INDEX_QUOTE)
    assert mv.read_quotes(["^GSPC"], kind=DataKind.INDEX_QUOTE)["^GSPC"].price == 5000.0


def test_mark_error_is_reported_and_stops_refreshing(market, session_is):
    market.quote("BAD", 7.0, age_s=30)
    market.marks.errors_by_key["quote:BAD"] = "provider 503"
    q = mv.read_quotes(["BAD"])["BAD"]
    assert q.error == "provider 503" and q.refreshing is False


def test_repository_failure_fails_open(market, session_is, monkeypatch):
    def broken(*a, **k):
        raise RuntimeError("db down")
    monkeypatch.setattr(market.marks, "active", broken)
    monkeypatch.setattr(market.queue, "enqueue", broken)
    market.quote("MSFT", 110.0, age_s=5)
    assert mv.read_quotes(["MSFT", "NEWX"])["MSFT"].price == 110.0


def test_quote_fields_are_exactly_the_row_quote_fields(market, session_is):
    market.quote("MSFT", 110.0, age_s=5)
    fields = mv.quote_fields(mv.read_quotes(["MSFT"])["MSFT"])
    assert set(fields) == ROW_QUOTE_FIELDS and fields["current_price_stale"] is False
    assert set(mv.quote_fields(None)) == ROW_QUOTE_FIELDS
    assert mv.quote_fields(None)["price_refreshing"] is False


def test_total_meta_takes_the_oldest_input_and_counts_stale(market, session_is):
    market.quote("A", 1.0, age_s=10)
    market.quote("B", 2.0, age_s=200)                 # regular: stale after 120 s
    quotes = mv.read_quotes(["A", "B"])
    meta = mv.total_meta(quotes.values())
    assert meta["as_of"] == quotes["B"].as_of
    assert meta["stale_count"] == 1 and meta["missing_count"] == 0
    assert meta["incomplete"] is False and meta["source"] == "request"


def test_total_with_unknown_currency_counts_missing_not_zero(market, session_is):
    market.quote("A", 1.0, age_s=10)
    quotes = mv.read_quotes(["A", "NEWX"])
    meta = mv.total_meta(quotes.values(), extra_missing=1)    # 1 unknown-currency position
    assert meta["missing_count"] == 2 and meta["incomplete"] is True
    assert meta["refreshing"] is True


def test_total_meta_closed_session_counts_nothing_stale(market, session_is):
    session_is("closed")
    market.quote("A", 1.0, age_s=3 * 86400)
    assert mv.total_meta(mv.read_quotes(["A"]).values())["stale_count"] == 0


def test_market_meta_always_has_every_key():
    meta = mv.total_meta([])
    assert set(meta) == META_KEYS
    assert (meta["computed_at"], meta["stale_inputs"], meta["source"]) == (None, False, "request")


def test_request_refresh_enqueues_at_user_priority(market):
    assert mv.request_refresh(["msft", "MSFT", "nvda"]) == 2
    assert market.queue.pending == {(QUEUE_KIND_QUOTE, "MSFT"): PRIORITY_USER,
                                    (QUEUE_KIND_QUOTE, "NVDA"): PRIORITY_USER}


def test_request_refresh_with_no_symbols_enqueues_nothing(market):
    assert mv.request_refresh([]) == 0
    assert market.queue.pending == {}


def test_last_close_fields_reads_the_cached_daily_bar(monkeypatch):
    import pandas as pd
    from swingbot.core.marketdata import daily_readonly
    frame = pd.DataFrame({"Close": [10.0, 12.5]}, index=pd.to_datetime(["2026-11-06", "2026-11-09"]))
    monkeypatch.setattr(daily_readonly, "read_cached_daily",
                        lambda syms, period="2y", min_rows=1: daily_readonly.ReadOnlyBars(
                            {"ASTS": frame}, {"ARM": "no_file"}, {}))
    got = mv.last_close_fields(["asts", "ARM"])
    assert got == {"ASTS": {"last_close": 12.5, "last_close_date": "2026-11-09"}}


def test_last_close_fields_is_empty_when_the_cache_is_not_mounted(monkeypatch):
    from swingbot.core.marketdata import daily_readonly

    def down(*a, **k):
        raise daily_readonly.DailyCacheUnavailable("not mounted")
    monkeypatch.setattr(daily_readonly, "read_cached_daily", down)
    assert mv.last_close_fields(["ASTS"]) == {}
    assert mv.last_close_fields([]) == {}
