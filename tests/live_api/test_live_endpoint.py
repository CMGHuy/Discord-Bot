"""v202: GET /api/v1/live -- auth, shape, ?limit=, sections, DB-only."""
from tests.store_seed import seed_store
import pytest

from tests.admin.api_v1_contract import NULLABLE_NUMBER, NULLABLE_STR, assert_error, assert_shape
SECTION = {"availability": str, "as_of": str, "reason": NULLABLE_STR}
HEAT = {**SECTION, "open_pct": NULLABLE_NUMBER, "cap_pct": NULLABLE_NUMBER,
        "utilisation_pct": NULLABLE_NUMBER, "open_amount": NULLABLE_NUMBER,
        "cap_amount": NULLABLE_NUMBER, "headroom_pct": NULLABLE_NUMBER,
        "headroom_amount": NULLABLE_NUMBER, "balance": NULLABLE_NUMBER,
        "includes_resting": bool}
AWAITING = {**SECTION, "count": (int, type(None)), "next_expiry": NULLABLE_STR}
KILLSWITCH = {**SECTION, "engaged": (bool, type(None)), "since": NULLABLE_STR,
              "detail": NULLABLE_STR}


def _live(client, query=""):
    response = client.get(f"/api/v1/live{query}")
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


def test_requires_auth(client):
    assert_error(client.get("/api/v1/live"), "auth", 401)


def test_live_top_level_and_heat_shape(logged_in):
    body = _live(logged_in)
    assert_shape(body, {"heat": dict, "awaiting": dict, "killswitch": dict,
                        "events": list, "events_meta": dict})
    assert_shape(body["heat"], HEAT, where="heat")


@pytest.mark.parametrize("raw, expected", [
    (None, 8), ("", 8), ("1", 1), ("8", 8), ("50", 50), ("51", 50), ("1000", 50),
    ("0", None), ("-3", None), ("abc", None), ("2.5", None),
])
def test_parse_limit(admin_app, raw, expected):
    from swingbot.admin.api_v1 import live
    assert live.parse_limit(raw) == expected


@pytest.mark.parametrize("query", ["?limit=0", "?limit=-1", "?limit=abc", "?limit=2.5"])
def test_a_bad_limit_is_a_400(logged_in, query):
    assert_error(logged_in.get(f"/api/v1/live{query}"), "invalid", 400)


def test_events_are_not_wired_until_v202_3(logged_in):
    body = _live(logged_in)
    assert body["events"] == []
    assert body["events_meta"]["availability"] == "unavailable"
    assert body["events_meta"]["reason"] == "not wired"


OPEN_TRADE = {"id": "t1", "ticker": "AAPL", "status": "open", "direction": "bullish",
              "strategy": "VWAP", "horizon_key": "1m", "entry": 100.0, "stop_loss": 95.0,
              "take_profit": 120.0, "shares": 10, "opened_at": "2026-10-28T12:00:00+00:00"}


def _plan(plan_id, status, valid_session=None):
    return {"plan_id": plan_id, "ticker": "MSFT", "strategy": "VWAP", "horizon_key": "1m",
            "status": status, "created_at": "2026-10-28T13:00:00+00:00",
            "valid_session": valid_session, "direction": "bullish",
            "entry_price": 418.5, "status_history": []}


def _boom():
    raise RuntimeError("db down")


def test_awaiting_and_killswitch_shape(logged_in):
    body = _live(logged_in)
    assert_shape(body["awaiting"], AWAITING, where="awaiting")
    assert_shape(body["killswitch"], KILLSWITCH, where="killswitch")


def test_awaiting_counts_pending_plans_and_the_soonest_exact_expiry(logged_in):
    seed_store("plans", [
        _plan("p1", "PENDING", "2030-01-17"),
        _plan("p2", "PENDING", "2030-01-15"),
        _plan("p3", "PENDING"),                  # bar-count expiry: no exact time, no guess
        _plan("p4", "PENDING", "2020-01-02"),    # already past: not the "next" expiry
        _plan("p5", "ACTIVE", "2030-01-14"),     # filled: not awaiting an order
        _plan("p6", "CANCELLED", "2030-01-14"),
    ])
    awaiting = _live(logged_in)["awaiting"]

    assert awaiting["availability"] == "ok"
    assert awaiting["count"] == 4
    assert awaiting["next_expiry"] == "2030-01-15T21:00:00+00:00"   # 16:00 ET close, EST


def test_awaiting_without_session_plans_has_no_expiry(logged_in):
    seed_store("plans", [_plan("p3", "PENDING")])
    awaiting = _live(logged_in)["awaiting"]
    assert (awaiting["count"], awaiting["next_expiry"]) == (1, None)


def test_awaiting_with_nothing_pending_is_zero_not_unavailable(logged_in):
    awaiting = _live(logged_in)["awaiting"]
    assert (awaiting["availability"], awaiting["count"], awaiting["next_expiry"]) == ("ok", 0, None)


def test_a_failed_plans_read_is_unavailable_not_zero(logged_in, monkeypatch):
    monkeypatch.setattr("swingbot.core.db.repositories.plans.plans_repo", _boom)
    body = _live(logged_in)

    assert body["awaiting"]["availability"] == "unavailable"
    assert body["awaiting"]["reason"] == "awaiting_unavailable"
    assert body["awaiting"]["count"] is None
    assert body["heat"]["availability"] == "ok"
    assert body["killswitch"]["availability"] == "ok"


def test_killswitch_engaged_reports_since_and_detail(logged_in):
    seed_store("killswitch", {"on": True, "reason": "daily loss",
                              "at": "2026-10-29T07:31:00+00:00"})
    kill = _live(logged_in)["killswitch"]
    assert kill["availability"] == "ok"
    assert kill["engaged"] is True
    assert kill["since"] == "2026-10-29T07:31:00+00:00"
    assert kill["detail"] == "daily loss"


def test_a_released_killswitch_has_no_since(logged_in):
    """release() overwrites engaged_at: that time is never an engagement."""
    seed_store("killswitch", {"on": False, "reason": None, "manual_release": True,
                              "at": "2026-10-29T09:00:00+00:00"})
    kill = _live(logged_in)["killswitch"]
    assert kill["engaged"] is False
    assert kill["since"] is None


def test_no_killswitch_row_reads_the_configured_default(logged_in):
    from swingbot import config
    kill = _live(logged_in)["killswitch"]
    assert kill["engaged"] is bool(config.KILLSWITCH_DEFAULT_ON)
    assert kill["since"] is None


def test_a_failed_killswitch_read_is_unavailable(logged_in, monkeypatch):
    monkeypatch.setattr("swingbot.core.db.repositories.killswitch.killswitch_repo", _boom)
    kill = _live(logged_in)["killswitch"]
    assert (kill["availability"], kill["reason"]) == ("unavailable", "killswitch_unavailable")
    assert kill["engaged"] is None


def test_utc_text_normalises_offsets(admin_app):
    from datetime import datetime, timezone
    from swingbot.admin.api_v1 import live
    assert live._utc_text(None) is None
    assert live._utc_text("2026-10-29T09:31:00+02:00") == "2026-10-29T07:31:00+00:00"
    assert live._utc_text(datetime(2026, 10, 29, 7, 31, tzinfo=timezone.utc)) \
        == "2026-10-29T07:31:00+00:00"


def test_live_is_postgres_only(logged_in, no_network, monkeypatch):
    """Never a provider, never the slow Risk collector (spec section 5)."""
    collector = []
    monkeypatch.setattr("swingbot.core.edge.portfolio_state.collect_portfolio_state",
                        lambda *a, **k: collector.append(1) or {})
    seed_store("trades", [OPEN_TRADE])
    seed_store("plans", [_plan("p1", "PENDING", "2030-01-15")])
    body = _live(logged_in)

    assert {body[s]["availability"] for s in ("heat", "awaiting", "killswitch")} == {"ok"}
    assert no_network == []
    assert collector == []
