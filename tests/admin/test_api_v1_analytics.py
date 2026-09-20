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
    "/api/v1/analytics/plans",
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
    """The NG11 contract, extended by SR54's range-scoped blocks and by v94 D5.

    `win_rate` and `expectancy_r` now follow the `BookScope` population like
    every other block (spec v94 D5) rather than staying all-time -- see
    `tests/admin/test_api_analytics.py` for the range-narrowing assertions.
    """
    seed()
    assert_shape(logged_in.get("/api/v1/analytics/performance").get_json(), {
        "totals": dict, "relocated": dict, "win_rate": NULLABLE_NUMBER, "win_rate_n": int,
        "expectancy_r": NULLABLE_NUMBER, "expectancy_n": int, "by_confidence": dict,
        # v93 -- the weak ledger's own separate, never-summed record (weak_summary()).
        "weak": dict,
        "range": dict, "derived": dict, "distributions": dict,
        "rolling_returns": list, "holding_period_split": list, "risk_reward_split": list,
        "calendar": list, "cumulative_by_strategy": dict, "benchmark": dict,
        # v94 D5/D9 -- BookScope echo and the two rolling series.
        "rolling_wr": list, "rolling_exp_r": list, "scope": dict, "n": int,
        "weak": dict,
    })


def _closed(trade_id, *, status="win", closed_at="2026-08-04T15:00:00+00:00", **over):
    t = _trade(trade_id, plan_id=None, status=status)
    t["closed_at"] = closed_at
    t.update(over)
    return t


def test_performance_is_scoped_and_echoes_scope(seed, logged_in):
    # `_trade`'s default horizon_key ("1m") isn't in the real HORIZONS
    # vocabulary (2w/4w/2m.../9m -- strategy_types.py), so the in-scope
    # trades are pinned to "4w" here rather than the brief's "1m", which
    # `_scope()`'s validation would reject as an unknown horizon.
    seed(trades=[
        _closed("a" * 16, closed_at="2026-07-10T15:00:00+00:00", horizon_key="4w"),
        _closed("b" * 16, status="loss", horizon_key="4w"),
        _closed("c" * 16, horizon_key="2w"),
    ])
    body = logged_in.get("/api/v1/analytics/performance?from=2026-08-01&horizon=4w").get_json()
    assert body["scope"] == {"from": "2026-08-01", "to": None, "ledger": "main",
                             "strategy": None, "horizon": "4w", "direction": None}
    assert body["n"] == 1
    assert body["win_rate_n"] == 1 and body["win_rate"] == 0.0
    assert body["rolling_wr"] == [] and body["rolling_exp_r"] == []
    assert body["totals"]["closed"] == 1


def test_performance_rejects_bad_scope(logged_in):
    assert_error(logged_in.get("/api/v1/analytics/performance?ledger=shadow"), "invalid", 400)
    assert_error(logged_in.get("/api/v1/analytics/performance?bogus=1"), "invalid", 400)


def test_calibration_shape(seed, logged_in):
    seed()
    assert_shape(logged_in.get("/api/v1/analytics/calibration").get_json(),
                 {"deciles": list, "levels": list, "drift": list})


def test_exit_quality_rejects_unknown_parameters(logged_in):
    assert logged_in.get("/api/v1/analytics/exit-quality?from=2026-01-01").status_code == 400


def test_plans_shape(seed, logged_in):
    seed()
    assert_shape(logged_in.get("/api/v1/analytics/plans").get_json(), {
        "funnel": dict, "in_flight": int, "fill_rate": dict,
        "badges": dict, "confidence_levels": dict,
    })


def test_plans_serves_the_lifecycle_aggregation_over_real_plans(logged_in, monkeypatch):
    """`seed()`'s plans.json is always empty (it exists to seed trades); this
    checks the route actually forwards PlanStore().all() through
    _plan_lifecycle rather than an empty list, by patching PlanStore at its
    origin module -- the same target the route itself resolves lazily. """
    import swingbot.core.planning.plan_store as plan_store_mod

    class FakePlan:
        def __init__(self, status, badge, confidence_level):
            self.status = status
            self.status_history = []
            self.created_at = "2026-01-01"
            self.badge = badge
            self.confidence_level = confidence_level

    class FakeStore:
        def all(self):
            return [
                FakePlan("PENDING", "VALIDATED", 5),
                FakePlan("PENDING", "WEAK", 1),
            ]

    monkeypatch.setattr(plan_store_mod, "PlanStore", FakeStore)
    body = logged_in.get("/api/v1/analytics/plans").get_json()
    assert body["funnel"]["posted"] == 2
    assert body["in_flight"] == 2
    assert body["badges"] == {"VALIDATED": 1, "WEAK": 1}
    assert body["confidence_levels"] == {"5": 1, "1": 1}


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


def test_equity_curve_carries_currency_and_percent_and_scope(seed, logged_in):
    seed(trades=[
        _closed("a" * 16, closed_at="2026-08-02T15:00:00+00:00", realized_pnl_amount=70.0),
        _closed("b" * 16, status="loss", closed_at="2026-08-03T15:00:00+00:00",
                exit_price=98.0, realized_pnl_amount=-30.0),
    ])
    body = logged_in.get("/api/v1/analytics/equity-curve?ledger=both").get_json()
    assert [p["cum_pnl"] for p in body["points"]] == [70.0, 40.0]
    assert all(isinstance(p["cum_pct"], (int, float)) or p["cum_pct"] is None for p in body["points"])
    assert body["scope"]["ledger"] == "both" and body["n"] == 2
    assert "spy_indexed" in body["benchmark"]


def test_index_benchmark_rebases_to_first_point_in_range():
    from swingbot.admin.api_v1.analytics import _index_benchmark
    out = _index_benchmark({"2026-08-01": 100.0, "2026-08-02": 102.0, "2026-08-03": 99.0}, "2026-08-02")
    assert out == [{"date": "2026-08-02", "pct": 0.0}, {"date": "2026-08-03", "pct": round((99 / 102 - 1) * 100, 4)}]
    assert _index_benchmark({}, None) == []
    # `spy_cum`'s only real producer (the pre-refactor `get_detailed_stats`,
    # dropped in 4ae117dc) was itself a {date: value} dict -- no list-of-rows
    # shape has ever existed for this key (`get_extended_stats`, what today's
    # route actually reads, doesn't populate `spy_cum` at all). So this covers
    # the dict shape more thoroughly instead: a `None` reading is filtered out
    # (a real gap, not a zero), and when the exact `start` has no entry (here
    # because it was filtered as `None`) the series rebases to the next
    # available date at/after it, not to the nearest one before.
    assert _index_benchmark({"2026-08-01": 100.0, "2026-08-02": None, "2026-08-03": 105.0},
                             "2026-08-02") == [{"date": "2026-08-03", "pct": 0.0}]
