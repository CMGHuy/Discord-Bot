from swingbot import config
from swingbot.core.marketdata import data
from swingbot.core.marketdata.shared.admin_refresh import QUEUE_KIND_QUOTE
from tests.admin.test_api_v1_trades import _open_pair
from tests.store_seed import seed_store


def _seed_msft():
    plan, trade = _open_pair(ticker="MSFT", entry=100.0)
    seed_store("plans", [plan])
    seed_store("trades", [trade])


def test_dashboard_prices_open_positions_from_the_cache(on_client, market):
    _seed_msft()
    market.quote("MSFT", 110.0, age_s=5)
    body = on_client.get("/api/v1/dashboard?mode=today").get_json()
    assert body["open_pnl_pct"] == 10.0
    meta = body["market_meta"]
    assert meta["as_of"] is not None and meta["missing_count"] == 0
    assert meta["incomplete"] is False and meta["source"] == "request"


def test_dashboard_kpis_incomplete_when_a_position_is_unpriced(on_client, market):
    _seed_msft()                                    # no cached quote at all
    body = on_client.get("/api/v1/dashboard?mode=today").get_json()
    assert body["open_pnl_pct"] is None and body["open_pnl_amount"] is None
    meta = body["market_meta"]
    assert meta["missing_count"] == 1 and meta["incomplete"] is True and meta["refreshing"] is True
    assert (QUEUE_KIND_QUOTE, "MSFT") in market.queue.pending


def test_refresher_off_restores_the_request_time_fetch(client, auth, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_REFRESHER", "off")
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    calls = []

    def fake(tickers, *, asker, max_age_s=None, fresh_only=False):
        calls.append(list(tickers))
        return {}
    monkeypatch.setattr(data, "get_quote_batch", fake)
    _seed_msft()
    body = client.get("/api/v1/dashboard?mode=today", headers=auth).get_json()
    assert calls == [["MSFT"]]
    assert body["market_meta"]["missing_count"] == 1 and body["market_meta"]["as_of"] is None
