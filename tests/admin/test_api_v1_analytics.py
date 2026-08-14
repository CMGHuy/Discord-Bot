"""NG11 — GET /api/v1/analytics/*.

Backs the four Analytics tabs (spec v14 Decision 6). The load-bearing
assertion is `test_performance_carries_the_six_relocated_metrics`: spec 3
moved wins, losses, avg realised P&L, best trade, worst trade and avg
holding period off the Dashboard header on the promise that they would be
one click away, and if they never actually arrive here that trade was a
straight loss.
"""
import json

import pytest

from tests.admin.api_v1_contract import NULLABLE_NUMBER, assert_error, assert_shape
from tests.admin.test_api_v1_trades import _trade

_LOGIN = {"username": "admin", "password": "admin"}

_PATHS = [
    "/api/v1/analytics/snapshot",
    "/api/v1/analytics/performance",
    "/api/v1/analytics/strategies",
    "/api/v1/analytics/calibration",
    "/api/v1/analytics/registry",
]


@pytest.fixture
def seed(admin_app, tmp_path):
    def _seed(trades=()):
        (tmp_path / "plans.json").write_text("[]", encoding="utf-8")
        (tmp_path / "trades.json").write_text(json.dumps(list(trades)), encoding="utf-8")
    return _seed


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


@pytest.mark.parametrize("path", _PATHS)
def test_every_analytics_route_requires_auth(client, path):
    assert_error(client.get(path), "auth", 401)


@pytest.mark.parametrize("path", _PATHS)
def test_every_analytics_route_works_on_an_empty_store(seed, logged_in, path):
    """A fresh install has no trades and no snapshot. Every tab must render
    rather than 500 -- the snapshot self-heals on the request."""
    seed()
    assert logged_in.get(path).status_code == 200


def test_performance_carries_the_six_relocated_metrics(seed, logged_in):
    seed(trades=[
        _trade("aaaaaaaaaaaaaaaa", plan_id=None, status="win"),
        _trade("bbbbbbbbbbbbbbbb", plan_id=None, status="loss"),
    ])
    relocated = logged_in.get("/api/v1/analytics/performance").get_json()["relocated"]
    assert_shape(relocated, {
        "wins": NULLABLE_NUMBER,
        "losses": NULLABLE_NUMBER,
        "avg_realized_pct": NULLABLE_NUMBER,
        "best_trade_pct": NULLABLE_NUMBER,
        "worst_trade_pct": NULLABLE_NUMBER,
        "avg_holding_days": NULLABLE_NUMBER,
    }, where="relocated")
    assert relocated["wins"] == 1
    assert relocated["losses"] == 1


def test_performance_top_level_shape(seed, logged_in):
    """The NG11 contract, extended by SR54 with the range-scoped blocks.

    `win_rate` and `expectancy_r` stay here and stay all-time: pre-SR54
    clients read them as the account's overall record. Their range-scoped
    counterparts live in `derived`, and `tests/admin/test_api_analytics.py`
    owns the assertions about them.
    """
    seed()
    assert_shape(logged_in.get("/api/v1/analytics/performance").get_json(), {
        "totals": dict, "relocated": dict, "win_rate": NULLABLE_NUMBER,
        "expectancy_r": NULLABLE_NUMBER, "by_confidence": dict,
        "range": dict, "derived": dict, "distributions": dict,
        "rolling_returns": list, "holding_period_split": list,
        "calendar": list, "cumulative_by_strategy": dict, "benchmark": dict,
    })


def test_calibration_shape(seed, logged_in):
    seed()
    assert_shape(logged_in.get("/api/v1/analytics/calibration").get_json(),
                 {"deciles": list, "tiers": list, "drift": list})


def test_strategies_ships_series_not_svg(seed, logged_in):
    """The Jinja page renders this same data as an inline SVG. Sub-project 3
    owns how a sparkline looks, so the SPA gets numbers."""
    seed()
    body = logged_in.get("/api/v1/analytics/strategies").get_json()
    assert_shape(body, {"strategies": list, "heatmap": dict})
    assert_shape(body["heatmap"],
                 {"strategies": list, "horizons": list, "cells": list},
                 where="heatmap")
    for row in body["strategies"]:
        assert "sparkline_svg" not in row
        assert isinstance(row["win_rate_series"], list)


def test_snapshot_fresh_param_is_accepted(seed, logged_in):
    seed()
    assert logged_in.get("/api/v1/analytics/snapshot?fresh=1").status_code == 200
