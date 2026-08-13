"""NG5 — GET /api/v1/trades, the unified collection.

Spec v11 Decision 2 **and its NG1 amendment**. The amendment is the part
that matters here: the two stores OVERLAP. When a plan fills, it stays in
plans.json as ACTIVE while log_trade() writes a linked row into
trades.json. Concatenating the two row sets would list one real position
twice, and `test_a_filled_plan_appears_exactly_once` is the regression
test for precisely that.

The union is therefore a join:

    all plans (authoritative for the five statuses)
      each enriched by its trades.json row, matched on plan_id
    + trades where plan_id is None  (legacy v1, in no other store)

Legacy trades carry open/win/loss/closed rather than the plan vocabulary,
so they are mapped -- open -> ACTIVE, win|loss|closed -> CLOSED -- and get
no PENDING/PARTIAL/CANCELLED, because they have no such states to report.
"""
import json

import pytest

from tests.admin.api_v1_contract import (
    NULLABLE_NUMBER,
    NULLABLE_STR,
    assert_collection,
    assert_error,
)

_LOGIN = {"username": "admin", "password": "admin"}

# The full row contract: spec 3's seven default columns plus the eleven
# fields row expansion reveals. Declared once; every response is checked
# against it, so an endpoint that grows or drops a field fails here.
TRADE_ROW = {
    "id": str,
    "origin": str,               # "plan" | "legacy" -- which store it came from
    "status": str,
    # NG54. The RAW trade status, untranslated -- win/loss/open/closed, or
    # None for a plan with no trade behind it. `status` normalises win and
    # loss to CLOSED, so this is the only field that can tell them apart, and
    # the Trades workspace's Win/Loss chips filter on it.
    "outcome": NULLABLE_STR,
    "ticker": str,
    "direction": str,
    "strategy": NULLABLE_STR,
    "horizon": NULLABLE_STR,
    "tier": NULLABLE_STR,
    "badge": NULLABLE_STR,
    "confidence_level": NULLABLE_NUMBER,
    "confidence_score": NULLABLE_NUMBER,
    "quality_score": NULLABLE_NUMBER,
    "entry": NULLABLE_NUMBER,
    "stop_loss": NULLABLE_NUMBER,
    "target": NULLABLE_NUMBER,
    "target2": NULLABLE_NUMBER,
    "risk_reward": NULLABLE_NUMBER,
    "shares": NULLABLE_NUMBER,
    "position_value": NULLABLE_NUMBER,
    "current_price": NULLABLE_NUMBER,
    "exit_price": NULLABLE_NUMBER,
    "realized_pnl_amount": NULLABLE_NUMBER,
    "pnl_pct": NULLABLE_NUMBER,
    "r_multiple": NULLABLE_NUMBER,
    "held_hours": NULLABLE_NUMBER,
    "opened_at": NULLABLE_STR,
    "closed_at": NULLABLE_STR,
    "has_note": bool,
}


# --- fixtures ------------------------------------------------------------

def _plan(plan_id, *, ticker="AAPL", status="PENDING", strategy="RSI Divergence"):
    """A minimal plans.json record. Only the fields the endpoint reads."""
    return {
        "plan_id": plan_id, "ticker": ticker, "created_at": "2026-08-01T10:00:00+00:00",
        "source": "strategy", "strategy": strategy, "horizon_key": "1m",
        "direction": "bullish", "entry_type": "stop_entry", "trigger_price": 100.0,
        "entry_price": 101.0, "expiry_bars": 5, "stop_loss": 95.0, "tp1": 110.0,
        "tp1_fraction": 0.5, "tp2": 120.0, "breakeven_trigger_fraction": 0.5,
        "trail_atr_mult": 1.5, "quality_score": 72, "quality_breakdown": [],
        "tier": "A", "badge": "VALIDATED", "badge_stats": {}, "status": status,
        "status_history": [], "legs_realized": [],
    }


def _trade(trade_id, *, plan_id=None, ticker="AAPL", status="open"):
    """A minimal trades.json record."""
    return {
        "id": trade_id, "plan_id": plan_id, "ticker": ticker,
        "strategy": "RSI Divergence", "horizon_key": "1m", "direction": "bullish",
        "confidence_level": 4, "confidence_label": "High", "confidence_score": 81.0,
        "entry": 101.0, "stop_loss": 95.0, "take_profit": 110.0, "target2": None,
        "risk_reward_ratio": 1.8, "tier": "A", "badge": "VALIDATED",
        "quality_score": 72, "source": "strategy", "legs": [],
        "opened_at": "2026-08-01T10:00:00+00:00", "status": status,
        "closed_at": "2026-08-04T15:00:00+00:00" if status != "open" else None,
        "exit_price": 108.0 if status != "open" else None,
        "realized_pnl_amount": 70.0 if status != "open" else None,
        "shares": 10, "position_value": 1010.0,
        "target_sources": [], "stop_sources": [], "target2_sources": [],
        "confirmed_by": [], "explanation": None, "confidence_breakdown": None,
    }


@pytest.fixture
def seed(admin_app, tmp_path):
    """Write plans.json / trades.json directly. The stores read them fresh on
    construction, so no reload is needed after this."""
    def _seed(plans=(), trades=()):
        (tmp_path / "plans.json").write_text(json.dumps(list(plans)), encoding="utf-8")
        (tmp_path / "trades.json").write_text(json.dumps(list(trades)), encoding="utf-8")
    return _seed


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


# --- auth ----------------------------------------------------------------

def test_requires_auth(client):
    assert_error(client.get("/api/v1/trades"), "auth", 401)


# --- the join ------------------------------------------------------------

def test_empty_stores_give_an_empty_collection(seed, logged_in):
    seed()
    body = logged_in.get("/api/v1/trades").get_json()
    assert_collection(body, TRADE_ROW)
    assert body == {"items": [], "total": 0, "page": 1, "per_page": 25}


def test_a_pending_plan_appears_with_its_plan_status(seed, logged_in):
    seed(plans=[_plan("11111111-1111-4111-8111-111111111111")])
    body = logged_in.get("/api/v1/trades").get_json()
    assert_collection(body, TRADE_ROW)
    assert body["total"] == 1
    row = body["items"][0]
    assert row["id"] == "11111111-1111-4111-8111-111111111111"
    assert row["status"] == "PENDING"
    assert row["origin"] == "plan"


def test_a_filled_plan_appears_exactly_once(seed, logged_in):
    """THE regression NG1 found.

    A filled plan lives in BOTH stores -- plans.json as ACTIVE, trades.json
    as an open row linked by plan_id. Concatenating the two row sets would
    show this single position twice.
    """
    pid = "22222222-2222-4222-8222-222222222222"
    seed(plans=[_plan(pid, status="ACTIVE")],
         trades=[_trade("aaaaaaaaaaaaaaaa", plan_id=pid)])

    body = logged_in.get("/api/v1/trades").get_json()
    assert body["total"] == 1, "the plan and its linked trade are ONE position"
    assert body["items"][0]["id"] == pid, "the plan id is the identity, not the trade id"


def test_a_filled_plan_is_enriched_by_its_trade_row(seed, logged_in):
    """The join has to actually carry the trade's data across, or the plan
    row would report no sizing and no realised P&L."""
    pid = "33333333-3333-4333-8333-333333333333"
    seed(plans=[_plan(pid, status="CLOSED")],
         trades=[_trade("bbbbbbbbbbbbbbbb", plan_id=pid, status="win")])

    row = logged_in.get("/api/v1/trades").get_json()["items"][0]
    assert row["shares"] == 10
    assert row["exit_price"] == 108.0
    assert row["realized_pnl_amount"] == 70.0
    assert row["closed_at"] == "2026-08-04T15:00:00+00:00"


def test_a_legacy_trade_appears_on_its_own(seed, logged_in):
    """plan_id is None means it exists in no other store."""
    seed(trades=[_trade("cccccccccccccccc", plan_id=None)])
    row = logged_in.get("/api/v1/trades").get_json()["items"][0]
    assert row["id"] == "cccccccccccccccc"
    assert row["origin"] == "legacy"


def test_an_orphaned_linked_trade_is_not_dropped(seed, logged_in):
    """A trade whose plan_id names a plan that no longer exists must still
    appear. Silently dropping it would lose real trading history, which is
    a worse failure than showing it unjoined."""
    seed(plans=[], trades=[_trade("dddddddddddddddd", plan_id="gone")])
    body = logged_in.get("/api/v1/trades").get_json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == "dddddddddddddddd"


# --- legacy status mapping -----------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("open", "ACTIVE"), ("win", "CLOSED"), ("loss", "CLOSED"), ("closed", "CLOSED"),
])
def test_legacy_statuses_map_onto_the_plan_vocabulary(seed, logged_in, raw, expected):
    seed(trades=[_trade("eeeeeeeeeeeeeeee", plan_id=None, status=raw)])
    assert logged_in.get("/api/v1/trades").get_json()["items"][0]["status"] == expected


# --- filtering, sorting, paging ------------------------------------------

def test_status_filter(seed, logged_in):
    seed(plans=[
        _plan("11111111-1111-4111-8111-111111111111", status="PENDING"),
        _plan("22222222-2222-4222-8222-222222222222", status="CANCELLED"),
    ])
    body = logged_in.get("/api/v1/trades?status=PENDING").get_json()
    assert body["total"] == 1
    assert body["items"][0]["status"] == "PENDING"


# --- NG54: the status vocabulary the UI actually sends -------------------
#
# Every one of these failed before NG54, which is how five of the six status
# chips came to return an empty list that read as "no trades in that state".
# The gate's browser walk found it; nothing in either suite could have.

def _lifecycle(seed):
    """One plan per status, plus the two legacy shapes."""
    seed(
        plans=[
            _plan("11111111-1111-4111-8111-111111111111", status="PENDING"),
            _plan("22222222-2222-4222-8222-222222222222", status="ACTIVE"),
            _plan("33333333-3333-4333-8333-333333333333", status="PARTIAL"),
            _plan("44444444-4444-4444-8444-444444444444", status="CANCELLED"),
        ],
        trades=[
            _trade("t-open", ticker="SPY", status="open"),
            _trade("t-win", ticker="AMD", status="win"),
            _trade("t-loss", ticker="COIN", status="loss"),
        ],
    )


@pytest.mark.parametrize("value", ["CANCELLED", "cancelled", "Cancelled"])
def test_status_matches_whatever_case_it_arrives_in(seed, logged_in, value):
    """The chips send lowercase; the rows hold uppercase. An exact compare
    made every lowercase chip match nothing."""
    _lifecycle(seed)
    body = logged_in.get(f"/api/v1/trades?status={value}").get_json()
    assert body["total"] == 1
    assert body["items"][0]["status"] == "CANCELLED"


def test_status_open_means_active_or_partial(seed, logged_in):
    """`open` is an alias, not a status. A partially-realised position is
    still open, and the user should not have to know that to see it."""
    _lifecycle(seed)
    body = logged_in.get("/api/v1/trades?status=open").get_json()

    # Two plans (ACTIVE, PARTIAL) plus the legacy open trade, which maps to
    # ACTIVE. Not the win or the loss.
    assert body["total"] == 3
    assert {r["status"] for r in body["items"]} == {"ACTIVE", "PARTIAL"}


def test_outcome_separates_a_win_from_a_loss(seed, logged_in):
    """`status` normalises both to CLOSED, so this is the only field that
    can tell them apart — and the Jinja UI filtered on exactly it."""
    _lifecycle(seed)

    won = logged_in.get("/api/v1/trades?outcome=win").get_json()
    lost = logged_in.get("/api/v1/trades?outcome=loss").get_json()

    assert [r["ticker"] for r in won["items"]] == ["AMD"]
    assert [r["ticker"] for r in lost["items"]] == ["COIN"]
    # Both are CLOSED by status, which is why status could not do this.
    assert won["items"][0]["status"] == lost["items"][0]["status"] == "CLOSED"


def test_a_plan_with_no_trade_has_no_outcome(seed, logged_in):
    """None, not "open". A PENDING plan has not had an outcome yet; saying it
    is open would make it match a filter for live positions."""
    seed(plans=[_plan("11111111-1111-4111-8111-111111111111", status="PENDING")])
    row = logged_in.get("/api/v1/trades").get_json()["items"][0]
    assert row["outcome"] is None


def test_an_unknown_outcome_is_an_empty_set_not_an_error(seed, logged_in):
    """Unsatisfiable is not malformed. 400 is reserved for the latter."""
    _lifecycle(seed)
    resp = logged_in.get("/api/v1/trades?outcome=banana")
    assert resp.status_code == 200
    assert resp.get_json()["total"] == 0


def test_ticker_filter(seed, logged_in):
    seed(plans=[
        _plan("11111111-1111-4111-8111-111111111111", ticker="AAPL"),
        _plan("22222222-2222-4222-8222-222222222222", ticker="MSFT"),
    ])
    body = logged_in.get("/api/v1/trades?ticker=MSFT").get_json()
    assert body["total"] == 1
    assert body["items"][0]["ticker"] == "MSFT"


def test_total_is_the_prefilter_count_not_the_page_length(seed, logged_in):
    """`total` is post-filter, pre-slice. Returning len(items) here would
    silently collapse a multi-page result to one page."""
    seed(plans=[_plan(f"{i:08d}-1111-4111-8111-111111111111") for i in range(30)])
    body = logged_in.get("/api/v1/trades?per_page=10").get_json()
    assert body["total"] == 30
    assert len(body["items"]) == 10
    assert body["per_page"] == 10


def test_second_page_returns_different_rows(seed, logged_in):
    seed(plans=[_plan(f"{i:08d}-1111-4111-8111-111111111111") for i in range(30)])
    first = logged_in.get("/api/v1/trades?per_page=10&page=1").get_json()["items"]
    second = logged_in.get("/api/v1/trades?per_page=10&page=2").get_json()["items"]
    assert {r["id"] for r in first}.isdisjoint({r["id"] for r in second})


def test_unknown_filter_is_rejected(seed, logged_in):
    seed()
    assert_error(logged_in.get("/api/v1/trades?tikcer=AAPL"), "invalid", 400)


def test_unsortable_field_is_rejected(seed, logged_in):
    seed()
    assert_error(logged_in.get("/api/v1/trades?sort=nonsense"), "invalid", 400)


def test_sort_by_opened_at_descending_is_the_default(seed, logged_in):
    seed(trades=[
        dict(_trade("aaaaaaaaaaaaaaaa", plan_id=None), opened_at="2026-08-01T10:00:00+00:00"),
        dict(_trade("bbbbbbbbbbbbbbbb", plan_id=None), opened_at="2026-08-05T10:00:00+00:00"),
    ])
    items = logged_in.get("/api/v1/trades").get_json()["items"]
    assert [r["id"] for r in items] == ["bbbbbbbbbbbbbbbb", "aaaaaaaaaaaaaaaa"]


def test_sort_ascending(seed, logged_in):
    seed(trades=[
        dict(_trade("aaaaaaaaaaaaaaaa", plan_id=None), opened_at="2026-08-01T10:00:00+00:00"),
        dict(_trade("bbbbbbbbbbbbbbbb", plan_id=None), opened_at="2026-08-05T10:00:00+00:00"),
    ])
    items = logged_in.get("/api/v1/trades?sort=opened_at").get_json()["items"]
    assert [r["id"] for r in items] == ["aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb"]


# --- derived values ------------------------------------------------------

def test_closed_row_carries_derived_pnl_and_r(seed, logged_in):
    """Reuses dashboard.closed_pnl / closed_r rather than recomputing --
    the admin already has one definition of these and a second would drift."""
    seed(trades=[_trade("ffffffffffffffff", plan_id=None, status="win")])
    row = logged_in.get("/api/v1/trades").get_json()["items"][0]
    # entry 101, exit 108, bullish -> +6.93%; risk |101-95| = 6 -> +1.17R
    assert row["pnl_pct"] == pytest.approx(6.93, abs=0.01)
    assert row["r_multiple"] == pytest.approx(1.17, abs=0.01)
    assert row["held_hours"] == pytest.approx(77.0, abs=0.1)


def test_numbers_are_numbers_not_preformatted_strings(seed, logged_in):
    """Spec v11: formatting is sub-project 3's decision, and a server that
    ships "+6.93%" has taken it away."""
    seed(trades=[_trade("ffffffffffffffff", plan_id=None, status="win")])
    row = logged_in.get("/api/v1/trades").get_json()["items"][0]
    assert isinstance(row["pnl_pct"], float)
    assert isinstance(row["entry"], float)


# --- has_note (NG18) -----------------------------------------------------
# The route audit found this missing. Spec v11's mapping table replaces
# `GET /journal` and `GET /api/journal` with `GET /api/v1/trades?has_note=1`,
# and `has_note` was emitted on every row but absent from FILTERS -- so the
# documented replacement 400'd as an unknown parameter, and the Notes
# workspace (spec v14, "was Journal") had no way to list its own rows.

def _with_note(trade_id, tmp_path):
    (tmp_path / "journal.json").write_text(
        json.dumps([{"trade_id": trade_id, "note": "watched the open"}]),
        encoding="utf-8")


def test_has_note_filters_to_noted_trades(seed, logged_in, tmp_path):
    seed(trades=[_trade("aaaaaaaaaaaaaaaa"), _trade("bbbbbbbbbbbbbbbb")])
    _with_note("aaaaaaaaaaaaaaaa", tmp_path)

    items = logged_in.get("/api/v1/trades?has_note=1").get_json()["items"]
    assert [r["id"] for r in items] == ["aaaaaaaaaaaaaaaa"]


def test_has_note_false_returns_the_others(seed, logged_in, tmp_path):
    seed(trades=[_trade("aaaaaaaaaaaaaaaa"), _trade("bbbbbbbbbbbbbbbb")])
    _with_note("aaaaaaaaaaaaaaaa", tmp_path)

    items = logged_in.get("/api/v1/trades?has_note=0").get_json()["items"]
    assert [r["id"] for r in items] == ["bbbbbbbbbbbbbbbb"]


def test_has_note_is_compared_as_a_bool_not_a_string(seed, logged_in, tmp_path):
    """The generic filter stringifies both sides, so `?has_note=1` would test
    "1" == "True" and match nothing -- a filter that silently returns an empty
    list rather than erroring."""
    seed(trades=[_trade("aaaaaaaaaaaaaaaa")])
    _with_note("aaaaaaaaaaaaaaaa", tmp_path)

    for truthy in ("1", "true", "True", "yes"):
        assert logged_in.get(f"/api/v1/trades?has_note={truthy}").get_json()["total"] == 1


def test_has_note_total_is_the_post_filter_count(seed, logged_in, tmp_path):
    seed(trades=[_trade("aaaaaaaaaaaaaaaa"), _trade("bbbbbbbbbbbbbbbb")])
    _with_note("aaaaaaaaaaaaaaaa", tmp_path)
    assert logged_in.get("/api/v1/trades?has_note=1").get_json()["total"] == 1
