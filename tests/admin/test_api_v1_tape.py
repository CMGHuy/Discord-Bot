"""GET /api/v1/market/tape -- the Lane B feed."""
from unittest.mock import patch

import pytest

_LOGIN = {"username": "admin", "password": "admin"}


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


def test_tape_empty_symbols_returns_no_rows(logged_in):
    resp = logged_in.get("/api/v1/market/tape?symbols=")
    assert resp.status_code == 200
    assert resp.get_json()["rows"] == []


def test_tape_prices_only_requested_symbols(logged_in):
    with patch("swingbot.core.marketdata.data.get_current_price_batch",
               return_value={"NVDA": 182.4}) as batch:
        resp = logged_in.get("/api/v1/market/tape?symbols=NVDA")
    assert resp.status_code == 200
    body = resp.get_json()
    assert [r["symbol"] for r in body["rows"]] == ["NVDA"]
    assert body["rows"][0]["price"] == 182.4
    # The endpoint must never price the whole watchlist.
    assert batch.call_args[0][0] == ["NVDA"]


def test_tape_symbols_are_deduped_uppercased_and_capped(logged_in):
    with patch("swingbot.core.marketdata.data.get_current_price_batch",
               return_value={}) as batch:
        logged_in.get("/api/v1/market/tape?symbols=nvda,NVDA,amd")
    assert batch.call_args[0][0] == ["NVDA", "AMD"]


def test_tape_open_position_outranks_plan(logged_in):
    trades = [{"ticker": "NVDA", "status": "open", "entry": 170.0,
               "stop_loss": 160.0}]
    with patch("swingbot.core.marketdata.data.get_current_price_batch",
               return_value={"NVDA": 182.0}), \
         patch("swingbot.core.tracking.performance.TradeLog.get_trades",
               return_value=trades):
        row = logged_in.get("/api/v1/market/tape?symbols=NVDA").get_json()["rows"][0]
    assert row["context_kind"] == "position"
    assert row["sort_rank"] == 0
    assert row["context_label"] == "+1.2R"


def test_tape_unpriced_symbol_still_returns_a_row(logged_in):
    """A flagged name must never silently vanish from the tape."""
    with patch("swingbot.core.marketdata.data.get_current_price_batch",
               return_value={}):
        row = logged_in.get("/api/v1/market/tape?symbols=ZZZZ").get_json()["rows"][0]
    assert row["symbol"] == "ZZZZ"
    assert row["price"] is None
    assert row["change_pct"] is None


def test_tape_as_of_is_iso_utc(logged_in):
    resp = logged_in.get("/api/v1/market/tape?symbols=")
    assert resp.get_json()["as_of"].endswith("+00:00")
