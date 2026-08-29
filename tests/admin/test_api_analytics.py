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
            strategy="RSI"):
    """A closed trade with only the fields the derived figures actually read."""
    return {
        "id": trade_id, "plan_id": None, "ticker": "AAPL", "strategy": strategy,
        "horizon_key": "1m", "direction": "bullish", "confidence_level": 4,
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
    assert derived["total_return_pct"] == pytest.approx(12.86, abs=0.01)
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
        "totals": dict, "relocated": dict, "win_rate": NULLABLE_NUMBER,
        "expectancy_r": NULLABLE_NUMBER, "by_confidence": dict, "derived": dict,
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
