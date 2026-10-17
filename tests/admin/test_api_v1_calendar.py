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
from tests.store_seed import seed_store

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
        seed_store("trades", list(trades))
        seed_store("journal", [{"created_at": "2026-01-01T00:00:00+00:00", **entry} for entry in entries])
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
        "as_of": str, "month": str, "days": list, "totals": dict, "day_of_week": list,
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
    assert_shape(body, {
        "as_of": str, "date": str, "trades": list, "trade_count": int, "winners": int,
        "losers": int, "total_r": NULLABLE_NUMBER,
        "total_ccy": NULLABLE_NUMBER, "win_rate": NULLABLE_NUMBER,
        "avg_trade_r": NULLABLE_NUMBER,
        "worst_drawdown_r": NULLABLE_NUMBER, "contributors": list,
        "detractors": list,
        # v165 D2 / D3.
        "context": dict, "breakdown": dict,
    })
    assert_shape(body["context"], {
        "percentile": NULLABLE_NUMBER, "history_days": int,
        "vs_avg_day": dict, "vs_weekday_avg": dict,
    }, where="context")
    for side in ("vs_avg_day", "vs_weekday_avg"):
        assert_shape(body["context"][side], {"pnl_amount": NULLABLE_NUMBER, "r": NULLABLE_NUMBER},
                     where=f"context.{side}")
    # Set, not order: Flask's default JSON provider sorts keys on the wire.
    assert set(body["breakdown"]) == {"strategy", "horizon", "direction", "exit_reason"}
    assert_shape(body["breakdown"]["strategy"][0], {
        "key": str, "n": int, "pnl_amount": NULLABLE_NUMBER,
        "r": NULLABLE_NUMBER, "win_rate": NULLABLE_NUMBER,
    }, where="breakdown.strategy[0]")
    assert_shape(body["trades"][0], {
        "trade_id": str, "ticker": str, "strategy": str,
        "plan_id": NULLABLE_STR, "opened_at": NULLABLE_STR,
        "horizon": NULLABLE_STR, "direction": NULLABLE_STR, "day": str,
        "closed_at": NULLABLE_STR, "outcome": NULLABLE_STR,
        "pnl_amount": NULLABLE_NUMBER, "r_multiple": NULLABLE_NUMBER,
        "mfe_r": NULLABLE_NUMBER, "mae_r": NULLABLE_NUMBER,
        "exit_efficiency": NULLABLE_NUMBER, "tags": list,
        "auto_lesson": NULLABLE_STR, "leg_index": int, "leg_total": int,
        # v165 D1.
        "entry_price": NULLABLE_NUMBER, "exit_price": NULLABLE_NUMBER,
        "stop_price": NULLABLE_NUMBER, "tp1": NULLABLE_NUMBER, "tp2": NULLABLE_NUMBER,
        "shares": NULLABLE_NUMBER, "held_hours": NULLABLE_NUMBER,
        "return_pct": NULLABLE_NUMBER, "exit_reason": str,
    }, where="trades[0]")
    assert body["trades"][0]["tags"] == ["clean-exit"]
    assert body["trades"][0]["auto_lesson"] == "Held to target."


def test_day_detail_summarises_its_existing_trade_rows(seed, logged_in):
    seed(trades=[
        _trade("a" * 16, pnl=50.0),
        _trade("b" * 16, closed_at="2026-08-03T21:00:00+00:00", pnl=-25.0,
               status="loss", exit_price=97.5),
    ], entries=[
        _entry("a" * 16, r=2.0),
        _entry("b" * 16, r=-1.0),
    ])
    body = logged_in.get("/api/v1/calendar/pnl/day?date=2026-08-03").get_json()
    assert body["trade_count"] == 2
    assert body["winners"] == 1
    assert body["losers"] == 1
    assert body["total_r"] == 1.0
    assert body["avg_trade_r"] == 0.5
    assert body["worst_drawdown_r"] == 1.0
    assert body["contributors"] == [{"ticker": "AAPL", "r": 2.0}]
    assert body["detractors"] == [{"ticker": "AAPL", "r": -1.0}]


def test_day_detail_orders_leaders_by_r_magnitude_and_keeps_empty_side(seed, logged_in):
    trades = [
        _trade(chr(97 + i) * 16, closed_at=f"2026-08-03T{12 + i:02}:00:00+00:00")
        for i in range(6)
    ]
    entries = [_entry(trade["id"], r=float(i + 1)) for i, trade in enumerate(trades)]
    seed(trades=trades, entries=entries)
    body = logged_in.get("/api/v1/calendar/pnl/day?date=2026-08-03").get_json()
    assert [row["r"] for row in body["contributors"]] == [6.0, 5.0, 4.0, 3.0, 2.0]
    assert body["detractors"] == []


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


def test_a_banked_tp1_partial_counts_on_the_day_it_closed(seed, logged_in):
    """The Dashboard's Trades table shows a TP1 partial as its own CLOSED
    row on the day it banked, even while the runner is still open. The
    calendar must count the same row, or the two pages disagree on how many
    trades closed that day."""
    runner = {**_trade("m" * 16, status="open", closed_at=None, exit_price=None, pnl=None),
              "ticker": "MSFT",
              "legs": [{"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1",
                        "closed_at": "2026-08-03T15:00:00+00:00"}]}
    seed(trades=[_trade("a" * 16), runner])

    grid = logged_in.get("/api/v1/calendar/pnl?month=2026-08").get_json()
    day = next(d for d in grid["days"] if d["date"] == "2026-08-03")
    assert day["trade_count"] == 2
    # +$50 whole trade, + 10 shares x 0.5 x +$10 = +$50 on the TP1 leg.
    assert day["net_pnl_amount"] == 100.0

    body = logged_in.get("/api/v1/calendar/pnl/day?date=2026-08-03").get_json()
    leg = next(t for t in body["trades"] if t["trade_id"] == "m" * 16)
    assert (leg["leg_index"], leg["leg_total"]) == (0, 2)
    assert leg["r_multiple"] == pytest.approx(2.0)


# --- v165: day context and breakdown on the day route ----------------------


def _context_book():
    """08-03 (Mon): EMA20 +50 (r +2.0), VWAP -20.  08-04 (Tue): EMA20 +30
    (r +1.2).  08-05 (Wed): EMA20 -10 (r -0.4), VWAP +100. No journal, so
    every R is metrics.r_multiple off entry 100 / stop 95."""
    return [
        _trade("a" * 16, closed_at="2026-08-03T20:00:00+00:00", pnl=50.0,
               exit_price=110.0, sources=("EMA20",)),
        _trade("b" * 16, closed_at="2026-08-03T21:00:00+00:00", pnl=-20.0,
               exit_price=96.0, status="loss", sources=("VWAP",)),
        _trade("c" * 16, closed_at="2026-08-04T20:00:00+00:00", pnl=30.0,
               exit_price=106.0, sources=("EMA20",)),
        _trade("d" * 16, closed_at="2026-08-05T20:00:00+00:00", pnl=-10.0,
               exit_price=98.0, status="loss", sources=("EMA20",)),
        _trade("e" * 16, closed_at="2026-08-05T21:00:00+00:00", pnl=100.0,
               exit_price=120.0, sources=("VWAP",)),
    ]


def test_day_context_compares_against_the_other_days_under_the_filter(seed, logged_in):
    seed(trades=_context_book())
    body = logged_in.get(
        "/api/v1/calendar/pnl/day?date=2026-08-03&strategy=EMA20").get_json()
    # Other EMA20 days: 08-04 (+30, 1.2R) and 08-05 (-10, -0.4R).
    # Means +10 and 0.4R -> deltas +40 and 2.0 - 0.4 = 1.6R. No other Monday.
    assert body["context"] == {
        "percentile": None, "history_days": 2,
        "vs_avg_day": {"pnl_amount": 40.0, "r": 1.6},
        "vs_weekday_avg": {"pnl_amount": None, "r": None},
    }


def test_day_net_equals_the_grid_cell_and_the_breakdown_sums_to_the_tiles(seed, logged_in):
    seed(trades=_context_book())
    for query in ("", "&strategy=EMA20", "&strategy=VWAP"):
        grid = logged_in.get(f"/api/v1/calendar/pnl?month=2026-08{query}").get_json()
        cell = next(d for d in grid["days"] if d["date"] == "2026-08-03")
        body = logged_in.get(f"/api/v1/calendar/pnl/day?date=2026-08-03{query}").get_json()
        assert body["total_ccy"] == cell["net_pnl_amount"], query
        assert body["trade_count"] == cell["trade_count"], query
        for dimension, groups in body["breakdown"].items():
            assert sum(g["n"] for g in groups) == body["trade_count"], (query, dimension)
            assert sum(g["pnl_amount"] for g in groups if g["pnl_amount"] is not None) \
                == pytest.approx(body["total_ccy"]), (query, dimension)
            assert sum(g["r"] for g in groups if g["r"] is not None) \
                == pytest.approx(body["total_r"]), (query, dimension)


def test_day_breakdown_is_built_from_exactly_the_days_trades(seed, logged_in):
    seed(trades=_context_book())
    body = logged_in.get("/api/v1/calendar/pnl/day?date=2026-08-03").get_json()
    # R: (110-100)/5 = 2.0 and (96-100)/5 = -0.8.
    assert body["breakdown"]["strategy"] == [
        {"key": "EMA20", "n": 1, "pnl_amount": 50.0, "r": 2.0, "win_rate": 100.0},
        {"key": "VWAP", "n": 1, "pnl_amount": -20.0, "r": -0.8, "win_rate": 0.0},
    ]
    # Unfiltered: this day nets 50 - 20 = +30; the other days are 08-04 (+30)
    # and 08-05 (-10 + 100 = +90), mean +60 -> delta -30.
    assert body["context"]["history_days"] == 2
    assert body["context"]["vs_avg_day"]["pnl_amount"] == -30.0


def test_a_leg_row_on_the_day_route_carries_its_own_d1_fields(seed, logged_in):
    runner = {**_trade("m" * 16, status="open", closed_at=None, exit_price=None, pnl=None),
              "legs": [{"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1",
                        "closed_at": "2026-08-03T15:00:00+00:00"}]}
    seed(trades=[runner])
    body = logged_in.get("/api/v1/calendar/pnl/day?date=2026-08-03").get_json()
    leg = body["trades"][0]
    assert (leg["exit_reason"], leg["shares"], leg["exit_price"], leg["return_pct"]) == (
        "tp1", 5.0, 110.0, 10.0)
    # 2026-08-01T14:00Z -> 2026-08-03T15:00Z.
    assert leg["held_hours"] == 49.0
    assert body["breakdown"]["exit_reason"] == [
        {"key": "tp1", "n": 1, "pnl_amount": 50.0, "r": 2.0, "win_rate": 100.0}]


def test_the_day_route_still_404s_before_computing_context(seed, logged_in):
    seed(trades=_context_book())
    assert_error(logged_in.get("/api/v1/calendar/pnl/day?date=2026-08-09&strategy=EMA20"),
                 "not_found", 404)


# ---- v165 D4: GET /calendar/pnl/day/sparklines -----------------------------

_SPARK = "/api/v1/calendar/pnl/day/sparklines"


@pytest.fixture
def bars(monkeypatch):
    """Cached daily bars: AAPL has 30 flat bars from Mon 2026-07-20 (close
    100, High 101, Low 99); every other ticker is an uncached miss. Returns
    the list of (ticker, interval) loads the route made."""
    from swingbot.core.marketdata import data_store
    from tests.helpers import make_ohlcv

    calls = []

    def _load(ticker, interval):
        calls.append((ticker, interval))
        return make_ohlcv([100.0] * 30, start="2026-07-20") if ticker == "AAPL" else None

    def _never(*args, **kwargs):
        pytest.fail("the sparklines route may read bars only through load_normalized")

    monkeypatch.setattr(data_store, "load_normalized", _load)
    monkeypatch.setattr(data_store, "load_from_disk", _never)
    monkeypatch.setattr(data_store, "fetch_interval_data", _never)
    return calls


def test_sparklines_require_auth(client):
    assert_error(client.get(f"{_SPARK}?date=2026-08-03"), "auth", 401)


def test_sparklines_response_shape(seed, logged_in, bars):
    """`_trade` opens Sat 08-01 (entry bar Mon 08-03 = i10) and closes 08-03
    (exit bar i10): window i7..i13 = Wed 07-29..Thu 08-06."""
    seed(trades=[_trade("a" * 16)])
    body = logged_in.get(f"{_SPARK}?date=2026-08-03").get_json()
    assert_shape(body, {"as_of": str, "date": str, "truncated": bool, "series": dict})
    assert body["date"] == "2026-08-03"
    assert body["truncated"] is False
    series = body["series"]["a" * 16 + ":0"]
    assert_shape(series, {
        "closes": list, "exit_bar": int, "last_bar": str, "stale": bool,
        "entry": NULLABLE_NUMBER, "stop": NULLABLE_NUMBER, "tp1": NULLABLE_NUMBER,
        "tp2": NULLABLE_NUMBER, "exit": NULLABLE_NUMBER, "exit_date": str,
    }, where="series")
    assert_shape(series["closes"][0], {"date": str, "close": NULLABLE_NUMBER},
                 where="close")
    assert series["closes"][0]["date"] == "2026-07-29"
    assert series["closes"][-1]["date"] == "2026-08-06"
    assert (series["exit_bar"], series["exit_date"]) == (3, "2026-08-03")
    assert (series["entry"], series["stop"], series["tp1"], series["tp2"],
            series["exit"]) == (100.0, 95.0, 120.0, None, 110.0)
    assert series["stale"] is False
    assert bars == [("AAPL", "daily")]


def test_a_spot_metal_sparkline_is_null_without_a_load(seed, logged_in, bars):
    seed(trades=[{**_trade("a" * 16), "ticker": "XAUUSD"}])
    body = logged_in.get(f"{_SPARK}?date=2026-08-03").get_json()
    assert body["series"] == {"a" * 16 + ":0": None}
    assert bars == []


def test_an_uncached_ticker_sparkline_is_null(seed, logged_in, bars):
    seed(trades=[{**_trade("a" * 16), "ticker": "MSFT"}])
    body = logged_in.get(f"{_SPARK}?date=2026-08-03").get_json()
    assert body["series"] == {"a" * 16 + ":0": None}
    assert bars == [("MSFT", "daily")]


def test_sparklines_respect_the_strategy_filter(seed, logged_in, bars):
    seed(trades=[
        _trade("a" * 16, sources=("EMA20",)),
        _trade("b" * 16, closed_at="2026-08-03T21:00:00+00:00", sources=("VWAP",)),
    ])
    body = logged_in.get(f"{_SPARK}?date=2026-08-03&strategy=VWAP").get_json()
    assert list(body["series"]) == ["b" * 16 + ":0"]


def test_sparklines_for_a_day_with_no_closes_are_an_empty_200(seed, logged_in, bars):
    seed(trades=[_trade("a" * 16)])
    response = logged_in.get(f"{_SPARK}?date=2026-08-09")
    assert response.status_code == 200
    body = response.get_json()
    assert (body["series"], body["truncated"]) == ({}, False)
    assert bars == []


def test_sparklines_reject_a_bad_date_or_an_unknown_parameter(seed, logged_in, bars):
    seed(trades=[_trade("a" * 16)])
    assert_error(logged_in.get(_SPARK), "invalid", 400)
    assert_error(logged_in.get(f"{_SPARK}?date=2026-08"), "invalid", 400)
    assert_error(logged_in.get(f"{_SPARK}?date=2026-02-30"), "invalid", 400)
    assert_error(logged_in.get(f"{_SPARK}?date=2026-08-03&tickr=AAPL"), "invalid", 400)
