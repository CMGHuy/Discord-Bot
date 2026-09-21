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
    "/api/v1/analytics/heat-grid",
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


def test_heat_grid_folds_thin_strategies_and_nulls_thin_cells(seed, logged_in):
    fat = [
        _closed(f"{i:016d}", strategy="MACD", horizon_key="4w",
                closed_at=f"2026-08-{(i % 28) + 1:02d}T15:00:00+00:00")
        for i in range(21)
    ]
    thin = [_closed("z" * 16, strategy="Volume Profile", horizon_key="4w")]
    seed(trades=fat + thin)

    body = logged_in.get("/api/v1/analytics/heat-grid").get_json()
    assert body["rows"] == ["MACD"] and body["cols"][0] == "2w"
    macd_4w = next(cell for cell in body["cells"]
                   if cell["r"] == 0 and body["cols"][cell["c"]] == "4w")
    assert macd_4w["n"] == 21 and macd_4w["win_rate"] == 100.0
    assert body["folded"]["n_strategies"] == 1
    other_4w = next(cell for cell in body["folded"]["cells"]
                    if body["cols"][cell["c"]] == "4w")
    assert other_4w["n"] == 1 and other_4w["win_rate"] is None
    assert body["n"] == 22 and body["min_cell_n"] == 20


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


def test_performance_window_balance_is_the_real_unscoped_account_balance(seed, tmp_path, logged_in):
    """A scoped request must not compute `window_balance` from just the
    scoped subset's own P&L -- there is exactly one real pooled account
    balance, with no per-strategy meaning (metrics.balance_at's docstring).

    Two strategies: MACD closes $500 and RSI closes $200, both before the
    `from` cutoff, then RSI closes $300 after it. Scoping to `?strategy=RSI`
    drops the MACD trade and the early RSI trade from `scoped`/`closed`, but
    `window_balance` -- the base for `total_return_pct` -- must still count
    BOTH pre-cutoff closes (base 1000 + 500 + 200 = 1700), not just RSI's
    own pre-cutoff close (a buggy 1000 + 0 = 1000, since the only RSI trade
    before the cutoff was itself excluded by the date filter along with
    MACD's). 300 realised on top of 1700 is +17.6471%; on top of the buggy
    1000 it would read as +30%.
    """
    (tmp_path / "account.json").write_text(json.dumps({
        "base_balance": 1000.0, "balance": 1000.0, "risk_pct": 1.0,
        "max_position_pct": 20.0, "sizing_mode": "risk_pct", "balance_history": [],
    }), encoding="utf-8")
    seed(trades=[
        _closed("a" * 16, strategy="MACD", opened_at="2024-01-01T10:00:00+00:00",
                closed_at="2024-01-05T15:00:00+00:00", realized_pnl_amount=500.0),
        _closed("b" * 16, strategy="RSI", opened_at="2024-01-02T10:00:00+00:00",
                closed_at="2024-01-06T15:00:00+00:00", realized_pnl_amount=200.0),
        _closed("c" * 16, strategy="RSI", opened_at="2024-02-01T10:00:00+00:00",
                closed_at="2024-02-05T15:00:00+00:00", realized_pnl_amount=300.0),
    ])
    body = logged_in.get("/api/v1/analytics/performance?from=2024-01-10&strategy=RSI").get_json()
    assert body["n"] == 1   # only trade c is in scope (RSI, closed on/after the cutoff)
    assert body["derived"]["total_return_pct"] == pytest.approx(17.6471)


def test_calibration_shape(seed, logged_in):
    seed()
    assert_shape(logged_in.get("/api/v1/analytics/calibration").get_json(),
                 {"deciles": list, "levels": list, "drift": list})


def test_exit_quality_is_scoped_and_echoes(seed, logged_in):
    seed(trades=[
        _closed("a" * 16),
        _closed("b" * 16, closed_at="2026-07-01T15:00:00+00:00"),
    ])
    body = logged_in.get("/api/v1/analytics/exit-quality?from=2026-08-01").get_json()
    assert body["n"] == 1 and body["scope"]["from"] == "2026-08-01"
    assert body["hold_by_outcome"]["n_winners"] == 1
    assert body["min_cell_n"] == 20


def test_exit_quality_rejects_non_scope_parameters(logged_in):
    assert_error(logged_in.get("/api/v1/analytics/exit-quality?bins=3"), "invalid", 400)


def test_journal_is_scoped_and_keeps_lessons_param(seed, logged_in):
    seed(trades=[_closed("a" * 16)])
    body = logged_in.get("/api/v1/analytics/journal?lessons=2&direction=bearish").get_json()
    assert body["n"] == 0 and body["entries_n"] == 0
    assert body["scope"]["direction"] == "bearish"
    assert_error(logged_in.get("/api/v1/analytics/journal?lessons=0"), "invalid", 400)


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


def test_by_dimension_accepts_every_dimension_and_nulls_thin_rates(seed, logged_in):
    seed(trades=[_closed("a" * 16), _closed("b" * 16, status="loss", direction="bearish")])
    for dim in ("strategy", "horizon", "badge", "confidence", "direction", "dow", "month", "ticker", "source"):
        body = logged_in.get(f"/api/v1/analytics/by-dimension?dim={dim}").get_json()
        assert body["min_cell_n"] == 20 and body["n"] == 2, dim
        for row in body["rows"]:
            assert row["n"] < 20
            assert row["win_rate"] is None and row["exp_r"] is None and row["avg_win_r"] is None, (dim, row)
            assert isinstance(row["total_pnl"], (int, float))


def test_by_dimension_is_scoped(seed, logged_in):
    seed(trades=[_closed("a" * 16), _closed("b" * 16, direction="bearish")])
    body = logged_in.get("/api/v1/analytics/by-dimension?dim=direction&direction=bearish").get_json()
    assert [r["key"] for r in body["rows"]] == ["bearish"] and body["n"] == 1


def test_by_dimension_rejects_unknown_dim(logged_in):
    assert_error(logged_in.get("/api/v1/analytics/by-dimension?dim=tier"), "invalid", 400)


def test_by_dimension_strategy_rows_carry_soak_key(seed, logged_in):
    """v93 Task 13 attaches `soak` to every dim=strategy row; this rewrite
    must not drop it. No plans are seeded, so the value itself is None
    (verdict['n_closed'] == 0) -- what matters here is that the key
    survived the rewrite, not its computed meaning."""
    seed(trades=[_closed("a" * 16)])
    row = logged_in.get("/api/v1/analytics/by-dimension?dim=strategy").get_json()["rows"][0]
    assert "soak" in row
