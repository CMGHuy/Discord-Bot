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
    # Whether this row's CURRENT status was entered today (Europe/Berlin
    # calendar day) -- the Dashboard lifecycle strip's date scope, applied
    # uniformly across all five statuses rather than hardcoded to
    # CLOSED/CANCELLED. See `_row_from_plan`'s `today` field.
    "today": bool,
    # SR53 — the plan's own numbers, so a row that has not filled is not
    # mostly nulls. `created_at` is the only time an unfilled plan has;
    # `trigger_price` is its only actionable price; `follow_score` is the
    # plans board's ranking column, which was not on the wire at all.
    # All three on both origins: a legacy row emits nulls rather than omitting
    # the keys, so there is one row shape rather than two.
    "created_at": NULLABLE_STR,
    "trigger_price": NULLABLE_NUMBER,
    "follow_score": NULLABLE_NUMBER,
    # SR7 -- the status bar. All five on every row, terminal ones included: a
    # cell that must check whether a field exists has a second render path,
    # and the second one only runs on data nobody tests with.
    "progress_pct": NULLABLE_NUMBER,
    "entry_pct": NULLABLE_NUMBER,
    "progress_band": NULLABLE_STR,
    "blink_seconds": NULLABLE_NUMBER,
    "status_label": str,
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


# --- SR52: the filters that had no control --------------------------------
#
# The parity audit found five list filters the Jinja UI had and the SPA did
# not. Three -- strategy, horizon, tier -- were already accepted here and
# merely had nothing sending them. Two were accepted by neither side.
#
# `tag` is the one deliberately left out: journal tags are not on a trade row
# at all, so filtering by one needs the journal endpoint SR55 adds. Recorded
# here so its absence reads as a decision rather than an oversight.


def test_strategy_filter(seed, logged_in):
    """Already in FILTERS before SR52; pinned now that a control sends it."""
    seed(plans=[
        _plan("11111111-1111-4111-8111-111111111111", strategy="RSI Divergence"),
        _plan("22222222-2222-4222-8222-222222222222", strategy="VWAP"),
    ])
    body = logged_in.get("/api/v1/trades?strategy=VWAP").get_json()
    assert body["total"] == 1
    assert body["items"][0]["strategy"] == "VWAP"


def test_horizon_filter(seed, logged_in):
    seed(plans=[
        {**_plan("11111111-1111-4111-8111-111111111111"), "horizon_key": "2w"},
        {**_plan("22222222-2222-4222-8222-222222222222"), "horizon_key": "6m"},
    ])
    body = logged_in.get("/api/v1/trades?horizon=6m").get_json()
    assert body["total"] == 1
    assert body["items"][0]["horizon"] == "6m"


def test_tier_filter(seed, logged_in):
    seed(plans=[
        {**_plan("11111111-1111-4111-8111-111111111111"), "tier": "A"},
        {**_plan("22222222-2222-4222-8222-222222222222"), "tier": "C"},
    ])
    body = logged_in.get("/api/v1/trades?tier=C").get_json()
    assert body["total"] == 1
    assert body["items"][0]["tier"] == "C"


def test_badge_filter(seed, logged_in):
    """New in SR52 -- the plans board had it and this endpoint did not."""
    seed(plans=[
        {**_plan("11111111-1111-4111-8111-111111111111"), "badge": "VALIDATED"},
        {**_plan("22222222-2222-4222-8222-222222222222"), "badge": "WEAK"},
    ])
    body = logged_in.get("/api/v1/trades?badge=WEAK").get_json()
    assert body["total"] == 1
    assert body["items"][0]["badge"] == "WEAK"


@pytest.mark.parametrize("value", ["weak", "WEAK", "Weak"])
def test_badge_filter_is_case_insensitive(seed, logged_in, value):
    """NG54's shape, pre-empted. A `?badge=weak` that quietly matched nothing
    would read as "no weak-badged trades", which is a perfectly ordinary thing
    for this UI to say -- and is how the status chips stayed broken for a
    phase."""
    seed(plans=[{**_plan("22222222-2222-4222-8222-222222222222"), "badge": "WEAK"}])
    assert logged_in.get(f"/api/v1/trades?badge={value}").get_json()["total"] == 1


def test_confidence_filter(seed, logged_in):
    """`confidence` in the URL, `confidence_level` on the row.

    The parameter is named for what the chip row calls it; the row field keeps
    its own name. The alias is what makes both true at once.
    """
    seed(trades=[
        {**_trade("aaaaaaaaaaaaaaaa"), "confidence_level": 5},
        {**_trade("bbbbbbbbbbbbbbbb"), "confidence_level": 2},
    ])
    body = logged_in.get("/api/v1/trades?confidence=5").get_json()
    assert body["total"] == 1
    assert body["items"][0]["confidence_level"] == 5


def test_an_unsatisfiable_new_filter_is_empty_not_an_error(seed, logged_in):
    """Same convention as `outcome`: unsatisfiable is not malformed."""
    seed(plans=[_plan("11111111-1111-4111-8111-111111111111")])
    resp = logged_in.get("/api/v1/trades?badge=NOSUCHBADGE")
    assert resp.status_code == 200
    assert resp.get_json()["total"] == 0


def test_tag_is_not_a_trade_filter(seed, logged_in):
    """Deliberately rejected rather than silently ignored.

    A journal tag is not a field on a trade row, and `FILTERS` exists so that a
    parameter this endpoint cannot honour is a 400 rather than a filter that
    appears to work and returns everything.
    """
    seed()
    assert_error(logged_in.get("/api/v1/trades?tag=revenge"), "invalid", 400)


def test_a_pending_plan_carries_its_creation_time_and_trigger(seed, logged_in):
    """SR53. The row a PENDING plan produces used to be mostly nulls.

    `opened_at`, `held_hours` and `entry` all describe an execution that has
    not happened. What the plan HAS is when it was created and the price it is
    waiting for, and the plans board showed both.
    """
    seed(plans=[_plan("11111111-1111-4111-8111-111111111111", status="PENDING")])
    row = logged_in.get("/api/v1/trades").get_json()["items"][0]

    assert row["created_at"] == "2026-08-01T10:00:00+00:00"
    assert row["trigger_price"] == 100.0


def test_a_plan_row_is_ranked(seed, logged_in):
    """follow_score is a composite over the plan population, so it is attached
    for the whole set in one pass rather than scored per row."""
    seed(plans=[_plan("11111111-1111-4111-8111-111111111111")])
    row = logged_in.get("/api/v1/trades").get_json()["items"][0]

    assert row["follow_score"] is not None
    assert 0 <= row["follow_score"] <= 100


def test_a_legacy_row_has_no_plan_numbers_but_still_has_the_keys(seed, logged_in):
    """One row shape for both origins. A client that had to check whether a key
    exists would have a second render path, and the second one only runs on
    data nobody tests with."""
    seed(trades=[_trade("aaaaaaaaaaaaaaaa")])
    row = logged_in.get("/api/v1/trades").get_json()["items"][0]

    assert row["origin"] == "legacy"
    assert row["trigger_price"] is None
    assert row["follow_score"] is None
    # A legacy trade has no creation apart from its open, which is what it gets.
    assert row["created_at"] == row["opened_at"]


def test_sorting_by_follow_score_sinks_the_unranked(seed, logged_in):
    """Valueless rows last in BOTH directions.

    A descending sort that floated every unranked legacy row to the top would
    make "best-ranked first" show a screenful of rows with no ranking.
    """
    seed(
        plans=[_plan("11111111-1111-4111-8111-111111111111")],
        trades=[_trade("aaaaaaaaaaaaaaaa")],
    )
    items = logged_in.get("/api/v1/trades?sort=-follow_score").get_json()["items"]

    assert items[0]["follow_score"] is not None
    assert items[-1]["follow_score"] is None


def test_new_filters_narrow_the_total_not_just_the_page(seed, logged_in):
    """`total` stays post-filter, pre-slice for the new filters too."""
    seed(plans=(
        [{**_plan(f"{i:08d}-1111-4111-8111-111111111111"), "tier": "A"} for i in range(12)]
        + [{**_plan(f"{i:08d}-2222-4222-8222-222222222222"), "tier": "C"} for i in range(8)]
    ))
    body = logged_in.get("/api/v1/trades?tier=C&per_page=5").get_json()
    assert body["total"] == 8
    assert len(body["items"]) == 5


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


# --- today (Dashboard lifecycle-strip parity) -----------------------------
# Before this, clicking any of the strip's five statuses always landed here
# with only a `status` filter -- no date scope at all, regardless of the
# page's own Today+open/Today/All days toggle. Those first two modes were
# then merged into one "Today", defined as: a row opened today, OR it has
# not closed yet AT ALL -- so PENDING/ACTIVE/PARTIAL stay in Today no matter
# how old they are (matching the strip's own all-time counts for those three,
# SR53), and only CLOSED/CANCELLED are actually date-restricted, by when
# they opened.

def _today_iso():
    """Today in Europe/Berlin, which is what `is_today_berlin` compares to."""
    from datetime import datetime, timedelta
    from datetime import timezone as tz

    from swingbot.admin.dashboard import is_today_berlin
    now = datetime.now(tz.utc)
    for delta in (0, 1, -1):
        candidate = (now + timedelta(hours=delta)).isoformat()
        if is_today_berlin(candidate):
            return candidate
    return now.isoformat()


_OLD_ISO = "2026-08-01T10:00:00+00:00"


@pytest.mark.parametrize("status", ["PENDING", "ACTIVE", "PARTIAL"])
def test_today_includes_a_still_open_plan_no_matter_how_old(seed, logged_in, status):
    """Not yet closed at all -- included regardless of `created_at`. This is
    the "if trades are not yet closed, also show in Today view" half."""
    plan = _plan("11111111-1111-4111-8111-111111111111", status=status)
    plan["created_at"] = _OLD_ISO
    seed(plans=[plan])

    items = logged_in.get(f"/api/v1/trades?status={status}&today=1").get_json()["items"]
    assert [r["id"] for r in items] == [plan["plan_id"]]


def test_today_filters_a_closed_plan_by_when_it_opened(seed, logged_in):
    """CLOSED (and CANCELLED) are the only statuses this actually narrows --
    to whichever day the plan was created/opened on."""
    old = _plan("11111111-1111-4111-8111-111111111111", status="CLOSED")
    old["created_at"] = _OLD_ISO
    fresh = _plan("22222222-2222-4222-8222-222222222222", status="CLOSED")
    fresh["created_at"] = _today_iso()
    seed(plans=[old, fresh])

    items = logged_in.get("/api/v1/trades?status=CLOSED&today=1").get_json()["items"]
    assert [r["id"] for r in items] == [fresh["plan_id"]]


def test_today_includes_a_still_open_legacy_trade_no_matter_how_old(seed, logged_in):
    trade = _trade("aaaaaaaaaaaaaaaa", status="open")
    trade["opened_at"] = _OLD_ISO
    seed(trades=[trade])

    items = logged_in.get("/api/v1/trades?status=ACTIVE&today=1").get_json()["items"]
    assert [r["id"] for r in items] == ["aaaaaaaaaaaaaaaa"]


def test_today_filters_a_closed_legacy_trade_by_when_it_opened(seed, logged_in):
    """A legacy row has no separate creation moment -- `opened_at` doubles
    as both, so `today` reads the same field a plan row's `created_at`
    equivalent does."""
    old = _trade("aaaaaaaaaaaaaaaa", status="win")
    old["opened_at"] = _OLD_ISO
    fresh = _trade("bbbbbbbbbbbbbbbb", status="win")
    fresh["opened_at"] = _today_iso()
    seed(trades=[old, fresh])

    items = logged_in.get("/api/v1/trades?status=CLOSED&today=1").get_json()["items"]
    assert [r["id"] for r in items] == ["bbbbbbbbbbbbbbbb"]


def test_today_false_returns_the_others(seed, logged_in):
    old = _plan("11111111-1111-4111-8111-111111111111", status="CLOSED")
    old["created_at"] = _OLD_ISO
    fresh = _plan("22222222-2222-4222-8222-222222222222", status="CLOSED")
    fresh["created_at"] = _today_iso()
    seed(plans=[old, fresh])

    items = logged_in.get("/api/v1/trades?status=CLOSED&today=0").get_json()["items"]
    assert [r["id"] for r in items] == [old["plan_id"]]


# --- SR7: the status-bar fields ------------------------------------------
# Spec v18 Decision 5. Five fields on every row, so SR11's StatusCell can draw
# a position bar without doing arithmetic of its own -- and so the arithmetic
# happens once, next to the bot's own near-close alerts, rather than twice.

def _open_pair(ticker="MSFT", direction="bullish", entry=100.0, sl=90.0, tp=120.0):
    """An ACTIVE plan and its linked open trade -- the shape a live position
    actually has in this store, not a synthetic single row."""
    plan = _plan("22222222-2222-4222-8222-222222222222", ticker=ticker, status="ACTIVE")
    plan.update({"direction": direction, "entry_price": entry,
                 "stop_loss": sl, "tp1": tp})
    trade = _trade("t-open", plan_id=plan["plan_id"], ticker=ticker, status="open")
    trade.update({"direction": direction, "entry": entry,
                  "stop_loss": sl, "take_profit": tp})
    return plan, trade


@pytest.fixture
def priced(monkeypatch):
    """Pin the live price. The real one is a network call, and the whole
    point of these fields is what they do WITH a price."""
    def _at(value):
        import swingbot.core.marketdata.data as data
        monkeypatch.setattr(data, "prefetch_prices", lambda tickers: None)
        monkeypatch.setattr(data, "get_current_price", lambda t: value)
    return _at


def test_open_trade_row_carries_the_status_bar_fields(seed, logged_in, priced):
    plan, trade = _open_pair()
    seed(plans=[plan], trades=[trade])
    priced(110.0)                      # between entry and target

    row = logged_in.get("/api/v1/trades?status=open").get_json()["items"][0]

    assert 0.0 <= row["progress_pct"] <= 100.0
    assert 0.0 <= row["entry_pct"] <= 100.0
    assert row["progress_band"] in {"toward_stop", "neutral", "toward_target"}
    assert 0.6 <= row["blink_seconds"] <= 2.2
    assert isinstance(row["status_label"], str) and row["status_label"]


def test_status_fields_are_null_without_a_live_price(seed, logged_in, priced):
    plan, trade = _open_pair()
    seed(plans=[plan], trades=[trade])
    priced(None)                       # the network is down; the list must still render

    row = logged_in.get("/api/v1/trades?status=open").get_json()["items"][0]

    assert row["progress_pct"] is None
    assert row["progress_band"] is None
    assert row["blink_seconds"] is None
    # The label always exists -- it is what the degraded cell shows.
    assert row["status_label"]


def test_a_short_reaching_its_target_reads_100_not_0(seed, logged_in, priced):
    """Direction handling is the one thing a naive implementation gets wrong:
    for a short the target is BELOW entry, so a falling price is progress."""
    plan, trade = _open_pair(direction="bearish", entry=100.0, sl=110.0, tp=80.0)
    seed(plans=[plan], trades=[trade])
    priced(81.0)                       # all but at the target

    row = logged_in.get("/api/v1/trades?status=open").get_json()["items"][0]

    assert row["progress_pct"] > 95.0
    assert row["progress_band"] == "toward_target"


def test_a_terminal_row_has_no_position_only_a_label(seed, logged_in):
    """A cancelled plan never opened; there is no position to place on a bar.
    The label still has to say something, because the cell still renders."""
    seed(plans=[_plan("44444444-4444-4444-8444-444444444444", status="CANCELLED")])

    row = logged_in.get("/api/v1/trades?status=CANCELLED").get_json()["items"][0]

    assert row["progress_pct"] is None
    assert row["entry_pct"] is None
    assert row["blink_seconds"] is None
    assert row["status_label"] == "CANCELLED"


# --- SR16: sorting by status means sorting by progress --------------------

def test_status_sort_orders_by_progress_not_alphabetically(seed, logged_in, priced):
    """Alphabetical status is meaningless to a trader; how close a position is
    to its target is what the column draws."""
    near, near_t = _open_pair(ticker="NEAR")
    far, far_t = _open_pair(ticker="FAR")
    far["plan_id"] = far_t["plan_id"] = "33333333-3333-4333-8333-333333333333"
    seed(plans=[near, far], trades=[near_t, far_t])
    priced(118.0)                      # same price; both progress equally

    body = logged_in.get("/api/v1/trades?sort=status").get_json()
    assert body["total"] == 2
    # Both priced, so both carry progress -- the point is that neither is
    # dropped and the sort does not 400.
    assert all(r["progress_pct"] is not None for r in body["items"])


@pytest.mark.parametrize("direction", ["status", "-status"])
def test_rows_without_progress_sort_last_in_both_directions(seed, logged_in, priced,
                                                            direction):
    """`reverse=True` on a plain key flips the is-None flag too, floating every
    priceless row to the TOP on descending -- a user asking for "closest to
    target" would get a screen of rows with no price."""
    live, live_t = _open_pair(ticker="LIVE")
    seed(plans=[live, _plan("44444444-4444-4444-8444-444444444444",
                            ticker="DEAD", status="CANCELLED")],
         trades=[live_t])
    priced(110.0)

    items = logged_in.get(f"/api/v1/trades?sort={direction}").get_json()["items"]

    assert items[-1]["progress_pct"] is None, "a row with no progress must sort last"
    assert items[0]["progress_pct"] is not None
