import pandas as pd
import pytest

from swingbot.admin import watchlist_rows
from swingbot.core.marketdata import data_store
from swingbot.core.marketdata.shared.kinds import DataKind

ROW_QUOTE_FIELDS = {"current_price", "current_price_stale", "price_as_of", "price_age_s",
                    "price_refreshing", "price_error"}


@pytest.fixture
def disk(monkeypatch):
    frames = {}
    monkeypatch.setattr(data_store, "load_normalized", lambda sym, tf: frames.get(sym))
    return frames


def _rows(client, symbols):
    body = client.get(f"/api/v1/market/tape?symbols={symbols}").get_json()
    return {r["symbol"]: r for r in body["rows"]}


def test_tape_rows_carry_cached_quotes_and_their_age(on_client, market, disk):
    market.quote("MSFT", 110.0, age_s=8)
    market.quote("^GSPC", 5000.0, age_s=8, kind=DataKind.INDEX_QUOTE)
    disk["MSFT"] = pd.DataFrame({"Close": [100.0, 100.0]})
    rows = _rows(on_client, "MSFT,%5EGSPC")
    assert ROW_QUOTE_FIELDS <= set(rows["MSFT"])
    assert rows["MSFT"]["price"] == 110.0 and rows["MSFT"]["change_pct"] == 10.0
    assert rows["MSFT"]["price_refreshing"] is False and rows["MSFT"]["price_as_of"]
    assert rows["^GSPC"]["price"] == 5000.0 and rows["^GSPC"]["age_s"] >= 7


def test_tape_never_seen_symbol_is_null_and_refreshing(on_client, market, disk):
    row = _rows(on_client, "NEWX")["NEWX"]
    assert row["price"] is None and row["price_refreshing"] is True


def test_watchlist_overlays_cached_quotes_in_session(refresher_on, market, session_is,
                                                     disk, monkeypatch):
    monkeypatch.setattr(watchlist_rows, "is_us_market_active", lambda *a, **k: True)
    monkeypatch.setattr(watchlist_rows, "_cached_daily",
                        lambda t: pd.DataFrame({"Close": [100.0, 101.0]}))
    market.quote("MSFT", 110.0, age_s=5)
    row = watchlist_rows.build_market_rows(["MSFT"])["MSFT"]
    assert row["price"] == 110.0 and row["price_source"] == "alpaca"
    assert row["price_refreshing"] is False and row["price_age_s"] is not None


def test_watchlist_cold_symbol_reads_disk_of_any_age(refresher_on, market, session_is,
                                                     disk, monkeypatch):
    monkeypatch.setattr(watchlist_rows, "is_us_market_active", lambda *a, **k: False)
    monkeypatch.setattr(watchlist_rows, "_cached_daily", lambda t: None)   # stale file
    disk["NVDA"] = pd.DataFrame({"Close": [90.0, 95.0]},
                                index=pd.to_datetime(["2026-10-27", "2026-10-28"]))
    row = watchlist_rows.build_market_rows(["NVDA"])["NVDA"]
    assert row["price"] == 95.0 and row["as_of"] == "2026-10-28"
    assert market.queue.pending == {}            # closed market: last close, no enqueue
