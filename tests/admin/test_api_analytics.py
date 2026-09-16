"""SR54 — the derived analytics figures, and the date range that scopes them.

`stats.html` computed all of this in browser JS. The load-bearing assertions
here are the two that would let the old behaviour creep back:

* `test_empty_window_reports_none_for_every_derived_figure` — a range that
  selects nothing must not render as a wall of zeroes, which is what a naive
  `sum([]) == 0` port produces and what makes a dead account look flat rather
  than empty.
* `test_range_actually_narrows_the_figures` — proves the range parameter
  reaches the arithmetic instead of being accepted and ignored, the failure
  mode that made the Trades filters page-scoped before SR52.
"""
import json

import pytest

from tests.admin.api_v1_contract import NULLABLE_NUMBER, assert_error, assert_shape

_LOGIN = {"username": "admin", "password": "admin"}

_DERIVED_KEYS = {
    "avg_win_pct": NULLABLE_NUMBER,
    "avg_loss_pct": NULLABLE_NUMBER,
    "total_return_pct": NULLABLE_NUMBER,
    "annualised_return_pct": NULLABLE_NUMBER,
    "calmar": NULLABLE_NUMBER,
    "volatility_ann_pct": NULLABLE_NUMBER,
    "trades_per_month": NULLABLE_NUMBER,
    "pct_in_market": NULLABLE_NUMBER,
    "sharpe_ann": NULLABLE_NUMBER,
    "sortino_ann": NULLABLE_NUMBER,
    # Scoped copies of the two top-level figures. The top-level ones stay
    # all-time so the pre-SR54 contract is unchanged; these are what the range
    # control drives, so a user narrowing to March sees March's win rate.
    "win_rate": NULLABLE_NUMBER,
    "expectancy_r": NULLABLE_NUMBER,
}


def _closed(trade_id, *, opened, closed_at, entry, exit_price, status="win",
            strategy="RSI", horizon_key="1m"):
    """A closed trade with only the fields the derived figures actually read."""
    return {
        "id": trade_id, "plan_id": None, "ticker": "AAPL", "strategy": strategy,
        "horizon_key": horizon_key, "direction": "bullish", "confidence_level": 4,
        "confidence_label": "High", "confidence_score": 81.0,
        "entry": entry, "stop_loss": entry * 0.95, "take_profit": entry * 1.1,
        "target2": None, "risk_reward_ratio": 1.8, "tier": "A",
        "badge": "VALIDATED", "quality_score": 72, "source": "strategy",
        "legs": [], "opened_at": opened, "status": status, "closed_at": closed_at,
        "exit_price": exit_price,
        "realized_pnl_amount": (exit_price - entry) * 10,
        "shares": 10, "position_value": entry * 10, "target_sources": [],
        "stop_sources": [], "target2_sources": [], "confirmed_by": [],
        "explanation": None, "confidence_breakdown": None,
    }


def _year():
    """+10%, -5%, +20%, -10% across 2024 — the same shape as the pure-metric
    fixture, so a divergence between layers shows up as a value mismatch."""
    return [
        _closed("a" * 16, opened="2024-01-01T10:00:00+00:00",
                closed_at="2024-01-11T15:00:00+00:00", entry=100.0, exit_price=110.0),
        _closed("b" * 16, opened="2024-04-01T10:00:00+00:00",
                closed_at="2024-04-11T15:00:00+00:00", entry=100.0, exit_price=95.0,
                status="loss"),
        _closed("c" * 16, opened="2024-07-01T10:00:00+00:00",
                closed_at="2024-07-21T15:00:00+00:00", entry=100.0, exit_price=120.0,
                strategy="MACD"),
        _closed("d" * 16, opened="2024-12-22T10:00:00+00:00",
                closed_at="2025-01-01T15:00:00+00:00", entry=100.0, exit_price=90.0,
                status="loss", strategy="MACD"),
    ]


@pytest.fixture
def seed(admin_app, tmp_path):
    def _seed(trades=()):
        (tmp_path / "plans.json").write_text("[]", encoding="utf-8")
        (tmp_path / "trades.json").write_text(json.dumps(list(trades)), encoding="utf-8")
        (tmp_path / "account.json").write_text(json.dumps({"base_balance": 1000.0, "balance": 1150.0, "risk_pct": 1.0, "max_position_pct": 20.0, "sizing_mode": "risk_pct", "balance_history": []}), encoding="utf-8")
    return _seed


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


def _perf(client, query=""):
    return client.get("/api/v1/analytics/performance" + query).get_json()


def test_derived_block_declares_every_figure(seed, logged_in):
    seed(trades=_year())
    assert_shape(_perf(logged_in)["derived"], _DERIVED_KEYS, where="derived")


def test_derived_values_match_the_hand_computed_answers(seed, logged_in):
    seed(trades=_year())
    derived = _perf(logged_in)["derived"]
    assert derived["avg_win_pct"] == pytest.approx(15.0)
    assert derived["avg_loss_pct"] == pytest.approx(-7.5)
    assert derived["total_return_pct"] == pytest.approx(15.0)
    # These records open 10:00 and close 15:00, so each holding period is
    # 10 (or 20) days PLUS five hours, and the span is 366 days plus five.
    # Spelled out rather than rounded to whole days: the five hours are what
    # a whole-day approximation would quietly swallow.
    held = 3 * (10 + 5 / 24) + (20 + 5 / 24)
    span = 366 + 5 / 24
    assert derived["pct_in_market"] == pytest.approx(held / span * 100, abs=0.01)


def test_range_actually_narrows_the_figures(seed, logged_in):
    """The parameter must reach the arithmetic, not just be accepted."""
    seed(trades=_year())
    whole = _perf(logged_in)["derived"]
    winners_only = _perf(logged_in, "?from=2024-01-01&to=2024-01-31")["derived"]
    assert winners_only["total_return_pct"] == pytest.approx(10.0)
    assert winners_only["total_return_pct"] != whole["total_return_pct"]
    # A window containing no losers has no average loss to report.
    assert winners_only["avg_loss_pct"] is None


def test_range_is_echoed_back_with_the_sample_size(seed, logged_in):
    seed(trades=_year())
    body = _perf(logged_in, "?from=2024-01-01&to=2024-07-31")
    assert_shape(body["range"], {
        "from": (str, type(None)), "to": (str, type(None)),
        "span_years": NULLABLE_NUMBER, "n": int,
    }, where="range")
    assert body["range"]["n"] == 3
    assert body["range"]["from"] == "2024-01-01"


def test_empty_window_reports_none_for_every_derived_figure(seed, logged_in):
    """The whole point of the None convention: an empty range must not render
    as a wall of confident zeroes."""
    seed(trades=_year())
    derived = _perf(logged_in, "?from=2030-01-01&to=2030-12-31")["derived"]
    for key in _DERIVED_KEYS:
        assert derived[key] is None, f"{key} should be None on an empty window"


def test_no_trades_at_all_still_returns_the_full_shape(seed, logged_in):
    seed()
    body = _perf(logged_in)
    assert_shape(body["derived"], _DERIVED_KEYS, where="derived")
    assert body["range"]["n"] == 0


def test_malformed_date_is_a_400_not_a_silently_ignored_filter(seed, logged_in):
    seed(trades=_year())
    assert_error(logged_in.get("/api/v1/analytics/performance?from=last-tuesday"),
                 "invalid", 400)
    assert_error(logged_in.get("/api/v1/analytics/performance?to=2024-13-45"),
                 "invalid", 400)


def test_unknown_performance_parameter_is_rejected(seed, logged_in):
    seed()
    assert_error(logged_in.get("/api/v1/analytics/performance?form=all"), "invalid", 400)


def test_distributions_and_series_are_present_and_scoped(seed, logged_in):
    seed(trades=_year())
    body = _perf(logged_in)
    assert_shape(body["distributions"], {"returns": list, "r_multiples": list},
                 where="distributions")
    assert sum(b["count"] for b in body["distributions"]["returns"]) == 4
    assert_shape(body, {
        "totals": dict, "relocated": dict, "win_rate": NULLABLE_NUMBER, "win_rate_n": int,
        "expectancy_r": NULLABLE_NUMBER, "expectancy_n": int, "by_confidence": dict, "derived": dict,
        "range": dict, "distributions": dict, "rolling_returns": list,
        "holding_period_split": list, "risk_reward_split": list, "calendar": list,
        "cumulative_by_strategy": dict, "benchmark": dict,
    })


def test_calendar_and_by_strategy_carry_the_seeded_shape(seed, logged_in):
    seed(trades=_year())
    body = _perf(logged_in)
    months = {c["month"] for c in body["calendar"]}
    assert months == {"2024-01", "2024-04", "2024-07", "2025-01"}
    assert set(body["cumulative_by_strategy"]) == {"RSI", "MACD"}


def test_holding_split_reports_every_bucket_even_when_empty(seed, logged_in):
    seed(trades=_year())
    buckets = {b["bucket"] for b in _perf(logged_in)["holding_period_split"]}
    assert buckets == {"0h-2h", "2h-4h", "4h-8h", "8h-24h", "1d-2d", "2d+"}


def test_benchmark_block_is_present_even_when_yfinance_is_unavailable(seed, logged_in):
    """spy_cum is best-effort — the network call may return nothing. The key
    must still exist, or the workspace has to special-case its absence."""
    seed(trades=_year())
    assert_shape(_perf(logged_in)["benchmark"], {"spy_cum": dict}, where="benchmark")


def test_range_requires_auth_like_every_other_analytics_route(client):
    assert client.get("/api/v1/analytics/performance?from=2024-01-01").status_code == 401


# --- R9-01: GET /analytics/equity-curve --------------------------------

def _closed_r(trade_id, *, closed_at, r, strategy="RSI", horizon="1m"):
    """A closed trade whose `core.analytics.metrics.r_multiple()` evaluates
    to exactly `r`, built through `_closed()`'s fixed entry=100/
    stop_loss=95 (risk=5): exit = 100 + r*5.

    `r=None` builds a zero-risk trade (stop_loss forced equal to entry) --
    the one case `r_multiple()` itself treats as unmeasurable and returns
    None for, rather than a trade missing some field outright. That is the
    real "null, not zero" case this endpoint has to skip.
    """
    entry = 100.0
    if r is None:
        t = _closed(trade_id, opened=closed_at, closed_at=closed_at,
                     entry=entry, exit_price=entry, strategy=strategy,
                     horizon_key=horizon)
        t["stop_loss"] = entry
        return t
    exit_price = entry + r * (entry - entry * 0.95)
    return _closed(trade_id, opened=closed_at, closed_at=closed_at,
                   entry=entry, exit_price=exit_price, strategy=strategy,
                   horizon_key=horizon)


def _curve(client, query=""):
    return client.get("/api/v1/analytics/equity-curve" + query).get_json()


def test_the_curve_accumulates_r_in_close_order(seed, logged_in):
    seed(trades=[
        _closed_r("a" * 16, closed_at="2026-04-03T16:00:00+00:00", r=2.0),
        _closed_r("b" * 16, closed_at="2026-04-01T16:00:00+00:00", r=1.0),
    ])
    pts = _curve(logged_in)["points"]
    assert [p["cum_r"] for p in pts] == [1.0, 3.0]


def test_drawdown_is_measured_from_the_running_peak(seed, logged_in):
    seed(trades=[
        _closed_r("a" * 16, closed_at="2026-04-01T16:00:00+00:00", r=3.0),
        _closed_r("b" * 16, closed_at="2026-04-02T16:00:00+00:00", r=-1.0),
    ])
    pts = _curve(logged_in)["points"]
    assert pts[0]["drawdown_r"] == 0.0
    assert pts[1]["drawdown_r"] == 1.0


def test_drawdown_is_never_negative(seed, logged_in):
    seed(trades=[
        _closed_r(chr(ord("a") + i) * 16,
                  closed_at=f"2026-04-0{i + 1}T16:00:00+00:00", r=1.0)
        for i in range(4)
    ])
    pts = _curve(logged_in)["points"]
    assert all(p["drawdown_r"] >= 0 for p in pts)


def test_the_sample_size_is_reported_beside_the_curve(seed, logged_in):
    seed(trades=[_closed_r("a" * 16, closed_at="2026-04-01T16:00:00+00:00", r=1.0)])
    assert _curve(logged_in)["n"] == 1


def test_an_empty_book_returns_no_points_rather_than_a_flat_line(seed, logged_in):
    seed(trades=[])
    body = _curve(logged_in)
    assert body["points"] == []
    assert body["n"] == 0
    assert body["as_of"] is None


def test_a_trade_without_an_r_multiple_is_skipped_not_counted_as_zero(seed, logged_in):
    seed(trades=[
        _closed_r("a" * 16, closed_at="2026-04-01T16:00:00+00:00", r=1.0),
        _closed_r("b" * 16, closed_at="2026-04-02T16:00:00+00:00", r=None),
    ])
    body = _curve(logged_in)
    assert body["n"] == 1
    assert [p["cum_r"] for p in body["points"]] == [1.0]


def test_the_strategy_filter_narrows_the_curve(seed, logged_in):
    seed(trades=[
        _closed_r("a" * 16, closed_at="2026-04-01T16:00:00+00:00", r=1.0, strategy="RSI"),
        _closed_r("b" * 16, closed_at="2026-04-02T16:00:00+00:00", r=5.0, strategy="Fib"),
    ])
    body = _curve(logged_in, "?strategy=RSI")
    assert body["n"] == 1


def test_equity_curve_requires_auth_like_every_other_analytics_route(client):
    assert client.get("/api/v1/analytics/equity-curve").status_code == 401


def test_equity_curve_range_narrows_like_performance_does(seed, logged_in):
    seed(trades=[
        _closed_r("a" * 16, closed_at="2026-04-01T16:00:00+00:00", r=1.0),
        _closed_r("b" * 16, closed_at="2026-07-01T16:00:00+00:00", r=5.0),
    ])
    body = _curve(logged_in, "?from=2026-04-01&to=2026-04-30")
    assert body["n"] == 1
    assert body["points"][0]["cum_r"] == 1.0


def test_equity_curve_unknown_parameter_is_rejected(logged_in):
    assert_error(logged_in.get("/api/v1/analytics/equity-curve?strat=RSI"),
                 "invalid", 400)


# --- R9-02: GET /analytics/by-dimension --------------------------------

@pytest.fixture
def registry(tmp_path):
    """Seeds a test-isolated registry: writes a fixture JSON to `tmp_path`
    (never the real committed `validation_registry.json`) and loads it
    through `load_registry(path)`, which bypasses the module's own `_PATH`
    entirely -- the same mechanism `tests/backtesting/test_registry_decay.py`
    already uses. `reload_registry()` on teardown clears the module-global
    `_CACHE` so this fixture never leaks its rows into a later test.
    """
    from swingbot.core.backtesting import registry as reg

    def _registry(badges: dict[str, str]):
        rows = [
            {"source": "strategy", "strategy": strategy, "horizon": None,
             "status": status, "n": 10, "win_rate": 50.0, "expectancy_r": 0.1}
            for strategy, status in badges.items()
        ]
        path = tmp_path / "by_dimension_registry.json"
        path.write_text(json.dumps(rows), encoding="utf-8")
        reg.load_registry(path)

    yield _registry
    reg.reload_registry()


def _by_dim(client, dim, query=""):
    return client.get(f"/api/v1/analytics/by-dimension?dim={dim}" + query).get_json()


def test_strategy_rows_carry_both_measures(seed, logged_in):
    seed(trades=[
        _closed_r("a" * 16, closed_at="2026-04-01T16:00:00+00:00", r=1.0),
        _closed_r("b" * 16, closed_at="2026-04-02T16:00:00+00:00", r=-1.0),
        _closed_r("c" * 16, closed_at="2026-04-03T16:00:00+00:00", r=2.0),
    ])
    row = _by_dim(logged_in, "strategy")["rows"][0]
    assert row["exp_r"] == pytest.approx(2.0 / 3)
    assert row["total_r"] == pytest.approx(2.0)
    assert row["n"] == 3


def test_strategy_rows_carry_the_registry_badge(seed, logged_in, registry):
    registry({"RSI": "WEAK"})
    seed(trades=[_closed_r("a" * 16, closed_at="2026-04-01T16:00:00+00:00", r=1.0)])
    row = _by_dim(logged_in, "strategy")["rows"][0]
    assert row["badge"] == "WEAK"


def test_horizon_rows_carry_no_badge_field(seed, logged_in):
    seed(trades=[_closed_r("a" * 16, closed_at="2026-04-01T16:00:00+00:00",
                           r=1.0, horizon="4w")])
    row = _by_dim(logged_in, "horizon")["rows"][0]
    assert "badge" not in row


def test_horizon_rows_use_the_real_horizon_vocabulary(seed, logged_in):
    from swingbot.core.market.strategy_types import HORIZONS

    horizons = list(HORIZONS)[:3]
    seed(trades=[
        _closed_r(chr(ord("a") + i) * 16,
                  closed_at=f"2026-04-0{i + 1}T16:00:00+00:00", r=1.0, horizon=h)
        for i, h in enumerate(horizons)
    ])
    keys = [r["key"] for r in _by_dim(logged_in, "horizon")["rows"]]
    assert set(keys) <= set(HORIZONS)


def test_as_of_ignores_a_trade_dropped_for_an_unrecognized_horizon(seed, logged_in):
    """A trade with a legacy/unrecognized horizon_key never becomes a row
    under dim=horizon (test_horizon_rows_use_the_real_horizon_vocabulary),
    so it must not be allowed to set `as_of` either -- otherwise the
    freshness stamp would claim the shown rows are more current than any
    of them actually are."""
    seed(trades=[
        _closed_r("a" * 16, closed_at="2026-04-01T16:00:00+00:00", r=1.0, horizon="4w"),
        # Closes two months later but under a horizon that isn't real
        # HORIZONS vocabulary -- dropped from grouping entirely.
        _closed_r("b" * 16, closed_at="2026-06-01T16:00:00+00:00", r=1.0, horizon="6w"),
    ])
    body = _by_dim(logged_in, "horizon")
    assert {r["key"] for r in body["rows"]} == {"4w"}
    assert body["as_of"] == "2026-04-01"


def test_total_r_is_not_expectancy_times_n_when_some_trades_lack_an_r(seed, logged_in):
    seed(trades=[
        _closed_r("a" * 16, closed_at="2026-04-01T16:00:00+00:00", r=2.0),
        _closed_r("b" * 16, closed_at="2026-04-02T16:00:00+00:00", r=None),
    ])
    row = _by_dim(logged_in, "strategy")["rows"][0]
    assert row["n"] == 1
    assert row["total_r"] == pytest.approx(2.0)


def test_profit_factor_is_null_when_there_are_no_losers(seed, logged_in):
    seed(trades=[_closed_r("a" * 16, closed_at="2026-04-01T16:00:00+00:00", r=1.0)])
    row = _by_dim(logged_in, "strategy")["rows"][0]
    assert row["profit_factor"] is None


def test_an_unknown_dimension_is_a_bad_request(seed, logged_in):
    seed(trades=[])
    assert_error(logged_in.get("/api/v1/analytics/by-dimension?dim=phase-of-moon"),
                 "invalid", 400)


def test_a_dimension_with_no_trades_returns_no_rows_not_a_row_of_zeroes(seed, logged_in):
    seed(trades=[])
    assert _by_dim(logged_in, "strategy")["rows"] == []


def test_by_dimension_requires_auth_like_every_other_analytics_route(client):
    assert client.get("/api/v1/analytics/by-dimension?dim=strategy").status_code == 401


def test_by_dimension_unknown_parameter_is_rejected(logged_in):
    assert_error(logged_in.get("/api/v1/analytics/by-dimension?dim=strategy&strat=RSI"),
                 "invalid", 400)
