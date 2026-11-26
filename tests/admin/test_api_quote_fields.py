"""v171 D2: the trade and plan detail carry the quote a posted plan was built from; n/a before v171."""
import copy

import pytest

from swingbot.admin import market_values
from swingbot.admin.api_v1 import trade_progress as tp
from swingbot.admin.api_v1 import trades as trades_api
from swingbot.admin.market_values import MarketQuote
from tests.admin.test_api_v1_trades import _plan, _trade
from tests.store_seed import seed_store

_LOGIN = {"username": "admin", "password": "admin"}
_PLAN_ID = "55555555-5555-4555-8555-555555555555"
_TRADE_ID = "bbbbbbbbbbbbbbbb"
_AT = "2026-10-15T13:00:01+00:00"
_PLAN_QUOTE = {"quote_at": _AT, "quote_kind": "mid", "quote_age_s": 1.7,
               "quote_session": "pre-market", "price_confirmed": True}
_TRADE_QUOTE = {"at": _AT, "kind": "trade", "age_s": 2.4, "session": "regular", "confirmed": True}


@pytest.fixture
def seed(admin_app):
    def _seed(plans=(), trades=()):
        seed_store("plans", list(plans))
        seed_store("trades", list(trades))
    return _seed


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


def _quote(client, row_id):
    return client.get(f"/api/v1/trades/{row_id}").get_json()["detail"]["quote"]


def test_plan_without_a_trade_row_reads_the_plan_fields(seed, logged_in):
    seed(plans=[{**_plan(_PLAN_ID), **_PLAN_QUOTE}])
    assert _quote(logged_in, _PLAN_ID) == {"at": _AT, "kind": "mid", "age_s": 1.7,
                                           "session": "pre-market", "confirmed": True}


def test_the_trade_record_quote_wins_over_the_plan_fields(seed, logged_in):
    seed(plans=[{**_plan(_PLAN_ID, status="ACTIVE"), **_PLAN_QUOTE}],
         trades=[{**_trade(_TRADE_ID, plan_id=_PLAN_ID), "quote": _TRADE_QUOTE}])
    assert _quote(logged_in, _PLAN_ID) == _TRADE_QUOTE


def test_legacy_trade_carries_its_quote(seed, logged_in):
    seed(trades=[{**_trade(_TRADE_ID), "quote": _TRADE_QUOTE}])
    assert _quote(logged_in, _TRADE_ID) == _TRADE_QUOTE


def test_unconfirmed_price_is_passed_through(seed, logged_in):
    seed(plans=[{**_plan(_PLAN_ID), **_PLAN_QUOTE, "quote_kind": "scan", "price_confirmed": False}])
    quote = _quote(logged_in, _PLAN_ID)
    assert (quote["kind"], quote["confirmed"]) == ("scan", False)


@pytest.mark.parametrize("row_id, plans, trades", [
    (_PLAN_ID, [_plan(_PLAN_ID)], []),
    (_TRADE_ID, [], [_trade(_TRADE_ID)]),
])
def test_pre_v171_rows_carry_no_quote(seed, logged_in, row_id, plans, trades):
    seed(plans=plans, trades=trades)
    assert _quote(logged_in, row_id) is None


_AS_OF = "2026-11-25T14:40:00+00:00"
_ERR_AT = "2026-11-25T14:41:00+00:00"


def _held(ticker, *, status="ACTIVE", **extra):
    row = {"id": ticker, "ticker": ticker, "status": status, "direction": "bullish",
           "entry": 100.0, "stop_loss": 90.0, "target": 120.0, "risk_stop": 90.0,
           "bar_kind": "none", "open_shares": None}
    row.update(extra)
    return row


def _live(sym, price, *, error=None, error_at=None):
    return MarketQuote(symbol=sym, price=price, as_of=_AS_OF, age_s=30.0, refreshing=False,
                       error=error, source="alpaca-iex", error_at=error_at)


def _bid_ask_only(sym):
    """DOCU before the open: Alpaca has bid/ask (76.57 / 84.18) but no trade."""
    return MarketQuote(symbol=sym, price=None, as_of="2026-11-24T21:00:00+00:00",
                       age_s=63_600.0, refreshing=False, error="no quote",
                       source="alpaca-iex", error_at=_ERR_AT)


@pytest.fixture
def door(monkeypatch):
    """The refresher-on door with a fake cache: quotes and daily closes by symbol."""
    from swingbot.core.market import session
    from swingbot.core.marketdata.shared import admin_refresh
    state = {"quotes": {}, "closes": {}, "close_reads": []}
    monkeypatch.setattr(admin_refresh, "refresher_on", lambda: True)
    monkeypatch.setattr(session, "session_state", lambda now=None: "extended")

    def read_quotes(symbols, **_kw):
        return {s.upper(): state["quotes"][s.upper()] for s in symbols
                if s.upper() in state["quotes"]}

    def last_close_fields(symbols):
        state["close_reads"].append(sorted(s.upper() for s in symbols))
        return {s.upper(): state["closes"][s.upper()] for s in symbols
                if s.upper() in state["closes"]}

    monkeypatch.setattr(market_values, "read_quotes", read_quotes)
    monkeypatch.setattr(market_values, "last_close_fields", last_close_fields)
    monkeypatch.setattr(trades_api, "convert_amount",
                        lambda amount, ticker, on, **_kw: (amount, False))
    return state


def _price(rows):
    trades_api._attach_current_prices(rows)
    trades_api._attach_status_fields(rows)
    trades_api._attach_unrealized_pnl(rows)
    return rows


def test_live_trade_wins_over_last_close(door):
    door["quotes"]["AAPL"] = _live("AAPL", 110.0)
    door["closes"]["AAPL"] = {"last_close": 95.0, "last_close_date": "2026-11-24"}
    [row] = _price([_held("AAPL")])
    assert row["current_price"] == 110.0 and row["price_kind"] == tp.PRICE_LIVE
    assert row["price_as_of"] == _AS_OF and "last_close" not in row
    assert row["status_label"] == "Trending toward target" and row["r_multiple"] == 1.0
    assert door["close_reads"] == [[]]


def test_bid_ask_only_quote_falls_back_to_prev_close_never_the_midpoint(door):
    door["quotes"]["DOCU"] = _bid_ask_only("DOCU")
    door["closes"]["DOCU"] = {"last_close": 95.0, "last_close_date": "2026-11-24"}
    [row] = _price([_held("DOCU")])
    assert row["current_price"] == 95.0                      # the close, not (76.57 + 84.18) / 2
    assert row["price_kind"] == tp.PRICE_PREV_CLOSE
    assert row["price_as_of"] is None and row["price_age_s"] is None
    assert row["current_price_stale"] is False
    assert (row["price_error"], row["price_error_at"]) == ("no quote", _ERR_AT)
    assert row["last_close_date"] == "2026-11-24"
    assert (row["progress_band"], row["blink_seconds"]) == ("neutral", None)
    assert row["status_label"] == tp.PREV_CLOSE_LABEL and row["progress_pct"] == 16.7
    assert row["pnl_pct"] == -5.0 and row["r_multiple"] == -0.5


def test_held_row_with_neither_price_stays_unpriced_without_a_kind(door):
    [row] = _price([_held("NEWX")])
    assert row["current_price"] is None and "price_kind" not in row
    assert row["progress_pct"] is None and row["status_label"] == "No live price"
    assert row.get("pnl_pct") is None and row.get("r_multiple") is None


def test_partial_is_held_and_pending_is_not(door):
    for sym in ("PART", "PEND"):
        door["closes"][sym] = {"last_close": 95.0, "last_close_date": "2026-11-24"}
    part, pend = _price([_held("PART", status="PARTIAL"), _held("PEND", status="PENDING")])
    assert part["price_kind"] == tp.PRICE_PREV_CLOSE and part["current_price"] == 95.0
    assert "price_kind" not in pend and pend["current_price"] is None
    assert pend["last_close"] == 95.0 and pend["status_label"] == "PENDING"


def test_pricing_twice_is_idempotent_and_never_overwrites_a_live_price(door):
    door["quotes"]["AAPL"] = _live("AAPL", 110.0)
    door["quotes"]["DOCU"] = _bid_ask_only("DOCU")
    door["closes"]["DOCU"] = {"last_close": 95.0, "last_close_date": "2026-11-24"}
    rows = _price([_held("AAPL"), _held("DOCU")])
    once = copy.deepcopy(rows)
    _price(rows)                                             # list_trades' sort-by-price branch
    assert rows == once
    assert rows[0]["current_price"] == 110.0 and rows[0]["price_kind"] == tp.PRICE_LIVE


def test_prev_close_counts_as_missing_in_the_page_meta(door):
    door["quotes"]["AAPL"] = _live("AAPL", 110.0)
    door["quotes"]["DOCU"] = _bid_ask_only("DOCU")
    door["closes"]["DOCU"] = {"last_close": 95.0, "last_close_date": "2026-11-24"}
    rows = _price([_held("AAPL"), _held("DOCU")])
    meta = trades_api._page_market_meta(rows)
    assert meta["missing_count"] == 1 and meta["incomplete"] is True
    assert meta["as_of"] == _AS_OF


def test_held_row_carries_the_full_quote_field_set(door):
    door["quotes"]["AAPL"] = _live("AAPL", 110.0, error="no quote", error_at=_ERR_AT)
    [row] = _price([_held("AAPL")])
    assert {"current_price", "current_price_stale", "price_as_of", "price_age_s",
            "price_refreshing", "price_error", "price_error_at", "price_kind"} <= set(row)
    assert row["price_error_at"] == _ERR_AT
