"""v175: GET /api/v1/analytics/variance-band -- the whole-book losing-run band.

No store is seeded and no database is read: `_closed_book` (and, for the
loader's own test, `_all_trades`) is monkeypatched. The band is the real
`variance_band`, run with fewer paths so the shape test stays fast; the
statistics themselves are tested in tests/analytics/test_variance_band_*.py.
"""
import datetime as dt
import functools

import pytest

from tests.admin.api_v1_contract import NULLABLE_NUMBER, NULLABLE_STR, NUMBER, assert_error, assert_shape

_LOGIN = {"username": "admin", "password": "admin"}
_URL = "/api/v1/analytics/variance-band"
_R_CYCLE = (1.5, -1.0, -1.0, 2.0, -1.0, 0.5)     # R per close day, repeated
_NULLABLE_INT = (int, type(None))

_FULL_KEYS = {"status", "scope", "asof", "days", "weeks", "pool", "composition",
              "horizons", "current", "expr"}
_CURRENT = {"run": int, "run_age_days": _NULLABLE_INT, "drawdown": NUMBER,
            "drawdown_age_days": _NULLABLE_INT, "run_zone": str, "drawdown_zone": str,
            "zone": str}
_EXPR = {"value": NULLABLE_NUMBER, "n": int, "start": NULLABLE_STR, "end": NULLABLE_STR,
         "ci": (list, type(None)), "not_positive": bool}
_HORIZON = {"horizon": int, "weeks_span": NUMBER, "run": dict, "drawdown": dict}
_RUN_Q = {"p80": int, "p95": int, "p95_lo": int, "p95_hi": int}
_DD_Q = {"p80": NUMBER, "p95": NUMBER, "p95_lo": NUMBER, "p95_hi": NUMBER}


def _trade(i: int, day: dt.date, r: float, *, shares=10.0, plan_id="p", status=None):
    """One closed bullish trade, entry 100 / stop 95 (risk 5), closing at
    15:00 UTC (11:00 New York), so its ET close date is `day`."""
    return {
        "id": f"t{i}", "ticker": "AAPL", "direction": "bullish",
        "entry": 100.0, "stop_loss": 95.0, "exit_price": 100.0 + 5.0 * r,
        "status": status or ("win" if r > 0 else "loss"),
        "closed_at": f"{day.isoformat()}T15:00:00+00:00",
        "plan_id": f"{plan_id}{i}" if plan_id else None,
        "shares": shares, "horizon_key": "4w", "ledger": "main",
    }


def _book(days: int = 130, *, shares=10.0) -> list[dict]:
    """One trade per weekday from Mon 2026-01-05: 130 days = 26 ISO weeks."""
    out, day = [], dt.date(2026, 1, 5)
    while len(out) < days:
        if day.weekday() < 5:
            out.append(_trade(len(out), day, _R_CYCLE[len(out) % len(_R_CYCLE)], shares=shares))
        day += dt.timedelta(days=1)
    return out


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


@pytest.fixture
def book(monkeypatch):
    """Serve `trades` as the closed book, through a fast real `variance_band`."""
    import swingbot.admin.api_v1.analytics as analytics_api
    from swingbot.core.analytics import variance_band as vb

    fast = functools.partial(vb.variance_band, paths=500, outer=20, outer_paths=200)
    monkeypatch.setattr(vb, "variance_band", fast)

    def _serve(trades):
        monkeypatch.setattr(analytics_api, "_closed_book", lambda: list(trades))
    return _serve


def test_requires_auth(client):
    assert_error(client.get(_URL), "auth", 401)


def test_any_query_parameter_is_rejected(logged_in, book):
    book(_book())
    assert_error(logged_in.get(_URL + "?strategy=RSI"), "invalid", 400)
    body = logged_in.get(_URL + "?ledger=main").get_json()
    assert "unknown parameter 'ledger'; allowed: []" in str(body)


def test_full_band_shape_is_whole_book(logged_in, book):
    book(_book())
    resp = logged_in.get(_URL)
    assert resp.status_code == 200
    body = resp.get_json()
    assert set(body) == _FULL_KEYS | {"dollars"}
    assert body["status"] == "ok" and body["scope"] == "whole_book"
    assert body["pool"] == "v2"
    assert body["days"] == 130 and body["weeks"] == 26
    assert [h["horizon"] for h in body["horizons"]] == [20, 50]
    for i, entry in enumerate(body["horizons"]):
        assert_shape(entry, _HORIZON, where=f"horizons[{i}]")
        assert_shape(entry["run"], _RUN_Q, where=f"horizons[{i}].run")
        assert_shape(entry["drawdown"], _DD_Q, where=f"horizons[{i}].drawdown")
    assert_shape(body["current"], _CURRENT, where="current")
    assert body["current"]["zone"] in ("normal", "rough", "outside")
    assert_shape(body["expr"], _EXPR, where="expr")
    assert body["expr"]["n"] == 130
    assert_shape(body["dollars"], {"median_risk": NUMBER, "drawdown_usd": NUMBER}, where="dollars")
    assert body["dollars"]["median_risk"] == 50.0          # 10 shares x |100 - 95|
    assert set(body["composition"]) == {"days_by_era", "trades_by_horizon"}
    assert body["composition"]["days_by_era"] == {"v2": 130, "legacy": 0}


def test_dollars_key_is_omitted_when_no_trade_has_shares(logged_in, book):
    book(_book(shares=None))
    body = logged_in.get(_URL).get_json()
    assert body["status"] == "ok"
    assert "dollars" not in body
    assert set(body) == _FULL_KEYS


def test_small_book_is_insufficient_with_exact_shape(logged_in, book):
    book([_trade(i, dt.date(2026, 1, 5 + i), -1.0) for i in range(3)])
    body = logged_in.get(_URL).get_json()
    assert body == {"status": "insufficient", "scope": "whole_book", "days": 3, "weeks": 1}


def test_empty_book_is_insufficient_not_an_error(logged_in, book):
    book([])
    resp = logged_in.get(_URL)
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "insufficient", "scope": "whole_book", "days": 0, "weeks": 0}


def test_closed_book_keeps_every_ledger_and_drops_open_trades(monkeypatch):
    import swingbot.admin.api_v1.analytics as analytics_api

    day = dt.date(2026, 1, 5)
    rows = [dict(_trade(0, day, 1.0), ledger="main"),
            dict(_trade(1, day, -1.0), ledger="weak"),
            dict(_trade(2, day, 0.0, status="closed"), ledger="main"),
            dict(_trade(3, day, 0.0), status="open", closed_at=None)]
    seen = {}

    def fake_all_trades(tl):
        seen["called"] = True
        return rows

    monkeypatch.setattr(analytics_api, "_all_trades", fake_all_trades)
    monkeypatch.setattr(analytics_api, "TradeLog", lambda: object())
    closed = analytics_api._closed_book()
    assert seen == {"called": True}
    assert [t["id"] for t in closed] == ["t0", "t1", "t2"]
