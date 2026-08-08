"""NG6 — GET /api/v1/trades/{id}.

Answers spec v11's open question 1 (does detail extend the list row, or is
it a distinct shape?): **it extends it.** The response is exactly the list
row plus one extra key, `detail`, holding the heavy fields nobody scans
down a column — status history, legs, quality and confidence breakdowns,
the source lists, and the plan's execution parameters.

Why that way round: the SPA's TradesStore already holds list rows, and a
detail response with a *different* shape for the same seven columns would
force it to reconcile two representations of one position. Nesting the
heavy fields keeps the row contract byte-identical between list and detail
while still letting detail carry an order of magnitude more data.

Routing exploits NG1's invariant: a 36-char four-dash id is a plan, so the
right store is chosen without a prefix and without loading the other one.
"""
import json

import pytest

from tests.admin.api_v1_contract import assert_shape
from tests.admin.test_api_v1_trades import TRADE_ROW, _plan, _trade

_LOGIN = {"username": "admin", "password": "admin"}

_PLAN_ID = "44444444-4444-4444-8444-444444444444"
_TRADE_ID = "aaaaaaaaaaaaaaaa"

# The detail response is the list row plus exactly one key.
DETAIL_ROW = {**TRADE_ROW, "detail": dict}


@pytest.fixture
def seed(admin_app, tmp_path):
    def _seed(plans=(), trades=()):
        (tmp_path / "plans.json").write_text(json.dumps(list(plans)), encoding="utf-8")
        (tmp_path / "trades.json").write_text(json.dumps(list(trades)), encoding="utf-8")
    return _seed


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


# --- auth and misses -----------------------------------------------------

def test_requires_auth(client):
    from tests.admin.api_v1_contract import assert_error
    assert_error(client.get(f"/api/v1/trades/{_TRADE_ID}"), "auth", 401)


def test_unknown_plan_shaped_id_is_404(seed, logged_in):
    from tests.admin.api_v1_contract import assert_error
    seed()
    assert_error(logged_in.get(f"/api/v1/trades/{_PLAN_ID}"), "not_found", 404)


def test_unknown_trade_shaped_id_is_404(seed, logged_in):
    from tests.admin.api_v1_contract import assert_error
    seed()
    assert_error(logged_in.get("/api/v1/trades/zzzzzzzzzzzzzzzz"), "not_found", 404)


# --- shape ---------------------------------------------------------------

def test_detail_is_the_list_row_plus_detail(seed, logged_in):
    seed(plans=[_plan(_PLAN_ID)])
    body = logged_in.get(f"/api/v1/trades/{_PLAN_ID}").get_json()
    assert_shape(body, DETAIL_ROW)


def test_detail_row_fields_match_the_list_exactly(seed, logged_in):
    """The same position, fetched both ways, must agree on every list field.

    This is the property that lets the SPA drop a detail response straight
    into the store beside list rows.
    """
    seed(plans=[_plan(_PLAN_ID, status="ACTIVE")],
         trades=[_trade(_TRADE_ID, plan_id=_PLAN_ID)])

    from_list = logged_in.get("/api/v1/trades").get_json()["items"][0]
    from_detail = logged_in.get(f"/api/v1/trades/{_PLAN_ID}").get_json()

    # held_hours is excluded because it is genuinely time-varying: an OPEN
    # position measures to now, so two requests milliseconds apart differ by
    # milliseconds. That is correct behaviour -- the Held column has to tick
    # for a position still running -- so it is compared with tolerance rather
    # than pinned. Every other field must match exactly.
    volatile = {"held_hours"}
    assert (
        {k: v for k, v in from_detail.items() if k != "detail" and k not in volatile}
        == {k: v for k, v in from_list.items() if k not in volatile}
    )
    assert from_detail["held_hours"] == pytest.approx(from_list["held_hours"], abs=1.0)


# --- plan detail ---------------------------------------------------------

def test_plan_detail_carries_plan_execution_parameters(seed, logged_in):
    seed(plans=[_plan(_PLAN_ID)])
    detail = logged_in.get(f"/api/v1/trades/{_PLAN_ID}").get_json()["detail"]
    assert detail["entry_type"] == "stop_entry"
    assert detail["trigger_price"] == 100.0
    assert detail["tp1_fraction"] == 0.5
    assert detail["expiry_bars"] == 5
    assert detail["created_at"] == "2026-08-01T10:00:00+00:00"
    assert detail["status_history"] == []


def test_plan_detail_includes_the_linked_trades_execution_detail(seed, logged_in):
    seed(plans=[_plan(_PLAN_ID, status="CLOSED")],
         trades=[_trade(_TRADE_ID, plan_id=_PLAN_ID, status="win")])
    detail = logged_in.get(f"/api/v1/trades/{_PLAN_ID}").get_json()["detail"]
    assert detail["legs"] == []
    assert detail["trade_id"] == _TRADE_ID, (
        "the underlying trade id must be reachable -- the plan id is the "
        "public identity, but close/delete act on the trade record"
    )


def test_plan_with_no_trade_yet_still_has_a_detail_object(seed, logged_in):
    """A PENDING plan has never filled, so there is no trade to join. The
    detail object must still be present and typed, not None."""
    seed(plans=[_plan(_PLAN_ID, status="PENDING")])
    detail = logged_in.get(f"/api/v1/trades/{_PLAN_ID}").get_json()["detail"]
    assert isinstance(detail, dict)
    assert detail["trade_id"] is None
    assert detail["legs"] == []


# --- legacy detail -------------------------------------------------------

def test_legacy_trade_detail(seed, logged_in):
    seed(trades=[_trade(_TRADE_ID, plan_id=None, status="win")])
    body = logged_in.get(f"/api/v1/trades/{_TRADE_ID}").get_json()
    assert_shape(body, DETAIL_ROW)
    assert body["origin"] == "legacy"
    assert body["detail"]["trade_id"] == _TRADE_ID


def test_legacy_detail_carries_the_alert_provenance(seed, logged_in):
    """explanation / confirmed_by / *_sources are what make a trade page
    show what you saw when the alert fired, rather than a reconstruction."""
    seed(trades=[dict(
        _trade(_TRADE_ID, plan_id=None, status="win"),
        explanation="RSI reclaim at support",
        confirmed_by=["RSI Divergence/1m"],
        target_sources=["EMA50", "Fib 0.618"],
        stop_sources=["swing low"],
    )])
    detail = logged_in.get(f"/api/v1/trades/{_TRADE_ID}").get_json()["detail"]
    assert detail["explanation"] == "RSI reclaim at support"
    assert detail["confirmed_by"] == ["RSI Divergence/1m"]
    assert detail["target_sources"] == ["EMA50", "Fib 0.618"]
    assert detail["stop_sources"] == ["swing low"]


def test_orphaned_linked_trade_is_reachable_by_its_own_id(seed, logged_in):
    """Its plan is gone, so it appears as a legacy row -- and must still be
    openable, or the list would show a row that 404s when clicked."""
    seed(plans=[], trades=[_trade(_TRADE_ID, plan_id="gone")])
    assert logged_in.get(f"/api/v1/trades/{_TRADE_ID}").status_code == 200
