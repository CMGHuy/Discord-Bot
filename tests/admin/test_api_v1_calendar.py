"""v53 -- /api/v1/calendar/pnl and /api/v1/calendar/pnl/day.

Data is seeded by WRITING trades.json and journal.json into the tmp_path
`admin_app` points config.DATA_DIR at, rather than by monkeypatching the
stores -- the same posture as tests/admin/test_api_v1_analytics.py. Note
`admin_app` seeds trades.json/account.json/plans.json but NOT journal.json;
JournalStore reads a missing file as [], so the unjournaled case is the
default here and has to be asserted deliberately.
"""
import json

import pytest

from tests.admin.api_v1_contract import (NULLABLE_NUMBER, NULLABLE_STR,
                                         assert_error, assert_shape)

_LOGIN = {"username": "admin", "password": "admin"}


def _trade(trade_id, *, closed_at="2026-08-03T20:00:00+00:00", status="win",
           pnl=50.0, exit_price=110.0, horizon="4w", sources=("EMA20",)):
    return {
        "id": trade_id, "plan_id": None, "ticker": "AAPL",
        "strategy": "S/R Confluence", "horizon_key": horizon,
        "direction": "bullish", "confidence_level": 4,
        "confidence_label": "High", "confidence_score": 81.0,
        "entry": 100.0, "stop_loss": 95.0, "take_profit": 120.0,
        "target2": None, "risk_reward_ratio": 2.0, "badge": "VALIDATED",
        "quality_score": 72, "source": "confluence", "legs": [],
        "opened_at": "2026-08-01T14:00:00+00:00", "status": status,
        "closed_at": closed_at, "exit_price": exit_price,
        "realized_pnl_amount": pnl, "shares": 10, "position_value": 1000.0,
        "target_sources": list(sources), "stop_sources": [],
        "target2_sources": [], "confirmed_by": [], "explanation": None,
        "confidence_breakdown": None,
    }


@pytest.fixture
def seed(admin_app, tmp_path):
    def _seed(trades=(), entries=()):
        (tmp_path / "trades.json").write_text(json.dumps(list(trades)), encoding="utf-8")
        (tmp_path / "journal.json").write_text(json.dumps(list(entries)), encoding="utf-8")
    return _seed


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


def test_requires_auth(client):
    assert_error(client.get("/api/v1/calendar/pnl?month=2026-08"), "auth", 401)


def test_works_on_an_empty_store(seed, logged_in):
    """A fresh install has no trades and no journal. The page must render."""
    seed()
    body = logged_in.get("/api/v1/calendar/pnl?month=2026-08").get_json()
    assert body["days"] == []
    assert body["totals"]["trade_count"] == 0
    assert body["filters"] == {"strategies": [], "horizons": []}
    assert body["best_day"] is None
    assert body["streak"] == {"direction": None, "days": 0}


def test_response_shape(seed, logged_in):
    seed(trades=[_trade("a" * 16)])
    body = logged_in.get("/api/v1/calendar/pnl?month=2026-08").get_json()
    assert_shape(body, {
        "month": str, "days": list, "totals": dict, "day_of_week": list,
        "best_day": (dict, type(None)), "worst_day": (dict, type(None)),
        "streak": dict, "filters": dict,
    })
    assert_shape(body["days"][0], {
        "date": str, "net_pnl_amount": NULLABLE_NUMBER,
        "net_r": NULLABLE_NUMBER, "trade_count": int,
        "win_rate": NULLABLE_NUMBER,
    }, where="days[0]")
    assert_shape(body["totals"], {
        "net_pnl_amount": NULLABLE_NUMBER, "net_r": NULLABLE_NUMBER,
        "trade_count": int, "win_rate": NULLABLE_NUMBER,
    }, where="totals")
    assert_shape(body["day_of_week"][0], {
        "weekday": str, "avg_pnl_amount": NULLABLE_NUMBER,
        "avg_r": NULLABLE_NUMBER, "win_rate": NULLABLE_NUMBER,
        "trade_count": int,
    }, where="day_of_week[0]")
    assert_shape(body["streak"], {"direction": NULLABLE_STR, "days": int},
                 where="streak")
    assert_shape(body["filters"], {"strategies": list, "horizons": list},
                 where="filters")
    assert len(body["day_of_week"]) == 5


def test_scopes_to_the_requested_month(seed, logged_in):
    seed(trades=[
        _trade("a" * 16, closed_at="2026-07-20T20:00:00+00:00"),
        _trade("b" * 16, closed_at="2026-08-03T20:00:00+00:00"),
    ])
    body = logged_in.get("/api/v1/calendar/pnl?month=2026-08").get_json()
    assert [d["date"] for d in body["days"]] == ["2026-08-03"]


def test_a_malformed_month_is_a_400_not_a_silent_whole_history(seed, logged_in):
    seed(trades=[_trade("a" * 16)])
    assert_error(logged_in.get("/api/v1/calendar/pnl?month=August"), "invalid", 400)
    assert_error(logged_in.get("/api/v1/calendar/pnl?month=2026-13"), "invalid", 400)
    assert_error(logged_in.get("/api/v1/calendar/pnl?month=2026-1"), "invalid", 400)


def test_month_defaults_to_the_current_month_when_omitted(seed, logged_in):
    import datetime as dt
    seed(trades=[_trade("a" * 16)])
    body = logged_in.get("/api/v1/calendar/pnl").get_json()
    assert body["month"] == dt.date.today().strftime("%Y-%m")


def test_filters_narrow_the_grid_but_not_the_filter_vocabulary(seed, logged_in):
    """A dropdown that shrinks to only the selected option cannot be
    un-selected -- `filters` must stay the full vocabulary."""
    seed(trades=[
        _trade("a" * 16, sources=("EMA20",), horizon="4w"),
        _trade("b" * 16, closed_at="2026-08-04T20:00:00+00:00",
               sources=("VWAP",), horizon="3m"),
    ])
    body = logged_in.get(
        "/api/v1/calendar/pnl?month=2026-08&strategy=EMA20"
    ).get_json()
    assert [d["date"] for d in body["days"]] == ["2026-08-03"]
    assert body["filters"]["strategies"] == ["EMA20", "VWAP"]
    assert body["filters"]["horizons"] == ["3m", "4w"]


def test_an_unknown_query_parameter_is_rejected(seed, logged_in):
    seed()
    assert_error(logged_in.get("/api/v1/calendar/pnl?tickr=AAPL"), "invalid", 400)


def _entry(trade_id, *, r=2.0, tags=("clean-exit",)):
    return {
        "trade_id": trade_id, "ticker": "AAPL", "strategy": "S/R Confluence",
        "horizon_key": "4w", "direction": "bullish", "outcome": "win",
        "r_realized": r, "mfe_r": 2.4, "mae_r": -0.3,
        "exit_efficiency": 83.0, "holding_days": 2, "tags": list(tags),
        "auto_lesson": "Held to target.", "note": "",
        "opened_at": "2026-08-01T14:00:00+00:00",
        "closed_at": "2026-08-03T20:00:00+00:00",
    }


def test_day_requires_auth(client):
    assert_error(client.get("/api/v1/calendar/pnl/day?date=2026-08-03"),
                 "auth", 401)


def test_day_lists_every_trade_closed_that_day(seed, logged_in):
    seed(
        trades=[
            _trade("a" * 16, closed_at="2026-08-03T20:00:00+00:00"),
            _trade("b" * 16, closed_at="2026-08-03T21:00:00+00:00", pnl=-20.0,
                   status="loss", exit_price=96.0),
            _trade("c" * 16, closed_at="2026-08-04T20:00:00+00:00"),
        ],
        entries=[_entry("a" * 16)],
    )
    body = logged_in.get("/api/v1/calendar/pnl/day?date=2026-08-03").get_json()
    assert body["date"] == "2026-08-03"
    assert {t["trade_id"] for t in body["trades"]} == {"a" * 16, "b" * 16}


def test_day_trade_shape_carries_the_journal_join(seed, logged_in):
    seed(trades=[_trade("a" * 16)], entries=[_entry("a" * 16)])
    body = logged_in.get("/api/v1/calendar/pnl/day?date=2026-08-03").get_json()
    assert_shape(body, {"date": str, "trades": list})
    assert_shape(body["trades"][0], {
        "trade_id": str, "ticker": str, "strategy": str,
        "horizon": NULLABLE_STR, "direction": NULLABLE_STR, "day": str,
        "closed_at": NULLABLE_STR, "outcome": NULLABLE_STR,
        "pnl_amount": NULLABLE_NUMBER, "r_multiple": NULLABLE_NUMBER,
        "mfe_r": NULLABLE_NUMBER, "mae_r": NULLABLE_NUMBER,
        "exit_efficiency": NULLABLE_NUMBER, "tags": list,
        "auto_lesson": NULLABLE_STR,
    }, where="trades[0]")
    assert body["trades"][0]["tags"] == ["clean-exit"]
    assert body["trades"][0]["auto_lesson"] == "Held to target."


def test_day_survives_a_trade_with_no_journal_entry(seed, logged_in):
    """journal.json is not seeded by admin_app, so this is the common case
    on a fresh install -- the dollar figure must still arrive."""
    seed(trades=[_trade("a" * 16)])
    body = logged_in.get("/api/v1/calendar/pnl/day?date=2026-08-03").get_json()
    trade = body["trades"][0]
    assert trade["pnl_amount"] == 50.0
    assert trade["tags"] == []
    assert trade["auto_lesson"] is None


def test_day_respects_the_strategy_filter(seed, logged_in):
    seed(trades=[
        _trade("a" * 16, sources=("EMA20",)),
        _trade("b" * 16, closed_at="2026-08-03T21:00:00+00:00", sources=("VWAP",)),
    ])
    body = logged_in.get(
        "/api/v1/calendar/pnl/day?date=2026-08-03&strategy=VWAP"
    ).get_json()
    assert [t["trade_id"] for t in body["trades"]] == ["b" * 16]


def test_a_day_with_no_closes_is_404_not_an_empty_200(seed, logged_in):
    """Every date the grid returns has >=1 trade, so this is only reachable
    from a stale link -- and "the day you asked for is not in the book" is a
    different answer from "that day was flat"."""
    seed(trades=[_trade("a" * 16)])
    assert_error(logged_in.get("/api/v1/calendar/pnl/day?date=2026-08-09"),
                 "not_found", 404)


def test_a_missing_or_malformed_date_is_a_400(seed, logged_in):
    seed(trades=[_trade("a" * 16)])
    assert_error(logged_in.get("/api/v1/calendar/pnl/day"), "invalid", 400)
    assert_error(logged_in.get("/api/v1/calendar/pnl/day?date=2026-08"),
                 "invalid", 400)
