"""v171 D2: the trade and plan detail carry the quote a posted plan was built from; n/a before v171."""
import pytest

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
