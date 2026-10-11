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
from tests.store_seed import seed_store

_LOGIN = {"username": "admin", "password": "admin"}

_PLAN_ID = "44444444-4444-4444-8444-444444444444"
_TRADE_ID = "aaaaaaaaaaaaaaaa"

# The detail response is the list row plus exactly one key.
DETAIL_ROW = {**TRADE_ROW, "detail": dict}


@pytest.fixture
def seed(admin_app, tmp_path):
    def _seed(plans=(), trades=()):
        seed_store("plans", list(plans))
        seed_store("trades", list(trades))
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


# --- v151: the Why panel's detail keys ------------------------------------

import datetime as dt  # noqa: E402

from swingbot import config  # noqa: E402
from swingbot.admin import trade_why  # noqa: E402

WHY_KEYS = {
    "entry_context", "risk_features", "cohort_label", "confidence_points",
    "confidence_unevaluated", "gates", "sessions_since_created", "expires_on",
    "time_exit_on", "calendar", "hold_cap_bars", "acceptance_level",
}
_MONDAY = "2026-09-14T14:00:00+00:00"      # 10:00 ET, Monday 14 Sep 2026
_TODAY = dt.date(2026, 9, 21)               # five sessions later


@pytest.fixture
def fixed_today(monkeypatch):
    monkeypatch.setattr(trade_why, "_today", lambda: _TODAY)
    return _TODAY


def _why_plan(**overrides):
    plan = {**_plan(_PLAN_ID, status="PENDING"), "created_at": _MONDAY, "horizon_key": "2w",
            "direction": "bearish", "cohort_label": "BEAR_VOL-SHORT",
            "entry_context": {"rs_combined": 18.0, "rs_pctile": 20.0, "sector_pctile": 30.0,
                              "regime2_state": "BEAR_VOL", "gap_p90_pct": 2.4,
                              "gap_fragile": True, "htf_aligned": True, "atr_pct": 3.1},
            "risk_features": {"days_to_earnings": None, "atr_pct": 3.1},
            "hold_cap_bars": None, "acceptance_level": 99.5}
    plan.update(overrides)
    return plan


def _detail(client, ident):
    response = client.get(f"/api/v1/trades/{ident}")
    assert response.status_code == 200
    return response.get_json()["detail"]


def test_plan_backed_detail_carries_every_why_key(seed, logged_in, fixed_today):
    seed(plans=[_why_plan()], trades=[_trade(_TRADE_ID, plan_id=_PLAN_ID)])
    detail = _detail(logged_in, _PLAN_ID)
    assert WHY_KEYS <= set(detail)
    assert detail["cohort_label"] == "BEAR_VOL-SHORT"
    assert detail["acceptance_level"] == 99.5
    assert detail["hold_cap_bars"] is None


def test_plan_entry_context_wins_and_is_filtered_to_the_wire_keys(seed, logged_in, fixed_today):
    trade = {**_trade(_TRADE_ID, plan_id=_PLAN_ID), "entry_context": {"rs_combined": 90.0}}
    seed(plans=[_why_plan()], trades=[trade])
    ctx = _detail(logged_in, _PLAN_ID)["entry_context"]
    assert ctx["rs_combined"] == 18.0
    assert "atr_pct" not in ctx
    assert set(ctx) <= set(trade_why.WIRE_CONTEXT_KEYS)


def test_an_empty_plan_context_falls_back_to_the_trades(seed, logged_in, fixed_today):
    trade = {**_trade(_TRADE_ID, plan_id=_PLAN_ID), "entry_context": {"rs_combined": 90.0},
             "risk_features": {"days_to_earnings": 4}}
    seed(plans=[_why_plan(entry_context={}, risk_features={})], trades=[trade])
    detail = _detail(logged_in, _PLAN_ID)
    assert detail["entry_context"] == {"rs_combined": 90.0}
    assert detail["risk_features"] == {"days_to_earnings": 4}


def test_confidence_keys_absent_are_none_and_empty(seed, logged_in, fixed_today):
    seed(plans=[_why_plan()], trades=[_trade(_TRADE_ID, plan_id=_PLAN_ID)])
    detail = _detail(logged_in, _PLAN_ID)
    assert detail["confidence_points"] is None
    assert detail["confidence_unevaluated"] == []


def test_confidence_keys_present_pass_through_untouched(seed, logged_in, fixed_today):
    trade = {**_trade(_TRADE_ID, plan_id=_PLAN_ID),
             "confidence_points": {"trend": 15, "regime": 7},
             "confidence_unevaluated": ["regime"]}
    seed(plans=[_why_plan()], trades=[trade])
    detail = _detail(logged_in, _PLAN_ID)
    assert detail["confidence_points"] == {"trend": 15, "regime": 7}
    assert detail["confidence_unevaluated"] == ["regime"]


def test_pending_plan_timing_and_calendar(seed, logged_in, fixed_today):
    seed(plans=[_why_plan()])            # expiry_bars=5 from _plan()
    detail = _detail(logged_in, _PLAN_ID)
    assert detail["sessions_since_created"] == 5
    assert detail["expires_on"] == "2026-09-21"
    assert detail["time_exit_on"] is None
    assert detail["calendar"] == [{"date": "2026-09-18", "kind": "opex_monthly", "label": "Monthly OPEX"}]


def test_filled_plan_with_a_hold_cap_has_a_time_exit_day(seed, logged_in, fixed_today):
    history = [{"status": "PENDING", "reason": None, "at": _MONDAY},
               {"status": "ACTIVE", "reason": "trigger_hit", "at": "2026-09-15T14:00:00+00:00"}]
    seed(plans=[_why_plan(status="ACTIVE", status_history=history, hold_cap_bars=10)],
         trades=[_trade(_TRADE_ID, plan_id=_PLAN_ID)])
    detail = _detail(logged_in, _PLAN_ID)
    assert detail["expires_on"] is None                 # not PENDING
    assert detail["time_exit_on"] == "2026-09-28"       # fill 15 Sep is session 1 of 10
    assert detail["hold_cap_bars"] == 10
    assert [r["date"] for r in detail["calendar"]] == ["2026-09-18"]


def test_active_plan_without_a_hold_cap_uses_the_horizon_window(seed, logged_in, fixed_today):
    # 2w: max_holding_days 14 -> 14 Sep .. 28 Sep.
    seed(plans=[_why_plan(status="ACTIVE")], trades=[_trade(_TRADE_ID, plan_id=_PLAN_ID)])
    detail = _detail(logged_in, _PLAN_ID)
    assert detail["time_exit_on"] is None
    assert [r["date"] for r in detail["calendar"]] == ["2026-09-18"]


def test_gates_present_on_a_plan_backed_row(seed, logged_in, fixed_today):
    seed(plans=[_why_plan()])
    gates = _detail(logged_in, _PLAN_ID)["gates"]
    assert [g["key"] for g in gates] == ["rs", "regime", "earnings"]
    rs = gates[0]
    assert rs["value"] == 18.0
    assert rs["threshold"] == config.RS_LAGGARD_PERCENTILE
    assert gates[1]["note"] == "BEAR_VOL-SHORT"


def test_legacy_row_has_the_same_keys_with_plan_only_fields_empty(seed, logged_in, fixed_today):
    trade = {**_trade(_TRADE_ID, plan_id=None, status="win"), "opened_at": _MONDAY,
             "entry_context": {"rs_pctile": 22.0, "atr_pct": 1.0},
             "confidence_points": {"trend": 15}}
    seed(trades=[trade])
    detail = _detail(logged_in, _TRADE_ID)
    assert WHY_KEYS <= set(detail)
    assert detail["cohort_label"] is None
    assert detail["calendar"] == []
    assert detail["expires_on"] is None and detail["time_exit_on"] is None
    assert detail["hold_cap_bars"] is None and detail["acceptance_level"] is None
    assert detail["entry_context"] == {"rs_pctile": 22.0}
    assert detail["confidence_points"] == {"trend": 15}
    assert detail["confidence_unevaluated"] == []
    assert detail["sessions_since_created"] == 5
    assert [g["key"] for g in detail["gates"]] == ["rs", "regime", "earnings"]


def test_a_minimal_legacy_trade_still_gets_every_key(seed, logged_in, fixed_today):
    seed(trades=[_trade(_TRADE_ID, plan_id=None, status="win")])
    detail = _detail(logged_in, _TRADE_ID)
    assert WHY_KEYS <= set(detail)
    assert detail["entry_context"] == {} and detail["risk_features"] == {}
    assert detail["gates"][0]["note"] == "exempt"


# --- trade_why helpers, no HTTP --------------------------------------------

@pytest.mark.parametrize("stamp, expected", [
    ("2026-09-14", dt.date(2026, 9, 14)),
    ("2026-09-14T14:00:00+00:00", dt.date(2026, 9, 14)),
    ("2026-09-15T02:00:00+00:00", dt.date(2026, 9, 14)),   # 22:00 ET the evening before
    ("not a date", None),
    (None, None),
    ("", None),
])
def test_session_day_parses_dates_and_aware_datetimes(stamp, expected):
    assert trade_why._session_day(stamp) == expected


def test_gate_thresholds_read_todays_config(monkeypatch):
    monkeypatch.setattr(config, "RS_GATE", False)
    monkeypatch.setattr(config, "RS_LAGGARD_PERCENTILE", 30.0)
    monkeypatch.setattr(config, "RS_LEADER_PERCENTILE", 55.0)
    monkeypatch.setattr(config, "REGIME_GATES_ENABLED", True)
    t = trade_why.gate_thresholds()
    assert (t.rs_gate, t.rs_laggard_pct, t.rs_leader_pct, t.regime_gates) == (False, 30.0, 55.0, True)


def test_plan_why_fields_without_a_created_at_degrades_to_none():
    fields = trade_why.plan_why_fields({"status": "PENDING", "expiry_bars": 5}, None,
                                       today=dt.date(2026, 9, 21))
    assert fields["sessions_since_created"] is None
    assert fields["expires_on"] is None
    assert fields["calendar"] == []
    assert fields["entry_context"] == {} and fields["risk_features"] == {}


@pytest.mark.parametrize("trade_points, trade_missing, expected_points, expected_missing", [
    (None, None, {"trend": 15}, ["regime"]),
    ({}, [], {}, []),
    ({"trend": 0}, ["rs"], {"trend": 0}, ["rs"]),
])
def test_plan_confidence_uses_first_non_none_logged_value(
        trade_points, trade_missing, expected_points, expected_missing):
    plan = _why_plan(confidence_points={"trend": 15}, confidence_unevaluated=["regime"])
    fields = trade_why.plan_why_fields(
        plan, {"confidence_points": trade_points, "confidence_unevaluated": trade_missing},
        today=_TODAY)
    assert fields["confidence_points"] == expected_points
    assert fields["confidence_unevaluated"] == expected_missing
    assert set(fields) == WHY_KEYS


def test_plan_risk_snapshot_wins_over_linked_trade():
    fields = trade_why.plan_why_fields(
        _why_plan(), {"risk_features": {"days_to_earnings": 4}}, today=_TODAY)
    assert fields["risk_features"] == {"days_to_earnings": None, "atr_pct": 3.1}
    assert fields["gates"][2]["value"] is None


@pytest.mark.parametrize("cap, history, expected", [
    (1, [{"status": "ACTIVE", "at": "2026-09-15T14:00:00+00:00"}], "2026-09-15"),
    (0, [{"status": "ACTIVE", "at": _MONDAY}], None),
    (-1, [{"status": "ACTIVE", "at": _MONDAY}], None),
    ("10", [{"status": "ACTIVE", "at": _MONDAY}], None),
    (10, [], None),
    (10, [{"status": "ACTIVE", "at": "invalid"}], None),
])
def test_time_exit_requires_a_valid_fill_and_positive_integer_cap(cap, history, expected):
    fields = trade_why.plan_why_fields(
        _why_plan(status="ACTIVE", hold_cap_bars=cap, status_history=history),
        None, today=_TODAY)
    assert fields["time_exit_on"] == expected


@pytest.mark.parametrize("stamp", [None, "invalid"])
def test_invalid_created_date_leaves_dates_and_calendar_empty(stamp):
    fields = trade_why.plan_why_fields(_why_plan(created_at=stamp), None, today=_TODAY)
    assert fields["sessions_since_created"] is None
    assert fields["expires_on"] is None
    assert fields["calendar"] == []


def test_unknown_horizon_without_an_expiry_has_no_calendar():
    fields = trade_why.plan_why_fields(
        _why_plan(status="CLOSED", horizon_key="unknown"), None, today=_TODAY)
    assert fields["calendar"] == []


def test_legacy_builder_ignores_plan_only_metadata():
    fields = trade_why.legacy_why_fields(
        {"opened_at": "invalid", "cohort_label": "BEAR_VOL-SHORT",
         "hold_cap_bars": 10, "acceptance_level": 99.5}, today=_TODAY)
    assert set(fields) == WHY_KEYS
    assert fields["sessions_since_created"] is None
    assert fields["cohort_label"] is None
    assert fields["hold_cap_bars"] is None
    assert fields["acceptance_level"] is None
    assert fields["expires_on"] is None
    assert fields["time_exit_on"] is None
    assert fields["calendar"] == []
