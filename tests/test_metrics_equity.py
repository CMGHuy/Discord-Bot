from swingbot.core.analytics.metrics import equity_curve, drawdown_series, max_drawdown_pct


def _t(closed_at, pnl, opened_at="2026-01-02T10:00:00+00:00"):
    return {"status": "win" if pnl >= 0 else "loss", "opened_at": opened_at,
            "closed_at": closed_at, "realized_pnl_amount": pnl}


def test_equity_curve_walks_balance():
    curve = equity_curve([_t("2026-01-05T10:00:00+00:00", 50.0),
                          _t("2026-01-03T10:00:00+00:00", -20.0)], 1000.0)
    pts = curve["points"]
    assert [p["balance"] for p in pts] == [1000.0, 980.0, 1030.0]  # sorted by close date
    assert curve["skipped_n"] == 0
    assert pts[0]["date"] == "2026-01-02"  # earliest opened_at, not the first close


def test_equity_curve_skips_unsized_trades():
    curve = equity_curve([{"status": "win", "closed_at": "2026-01-03T00:00:00+00:00",
                           "opened_at": "2026-01-02T00:00:00+00:00"}], 500.0)
    assert curve["skipped_n"] == 1 and len(curve["points"]) == 1


def test_equity_curve_empty_input():
    curve = equity_curve([], 1000.0)
    assert curve == {"points": [], "skipped_n": 0}


def test_equity_curve_baseline_falls_back_to_closed_at_when_opened_at_missing():
    """Baseline date should fall back to earliest closed_at when opened_at is missing."""
    trades = [
        {"status": "win", "closed_at": "2026-01-05T10:00:00+00:00", "realized_pnl_amount": 50.0},
        {"status": "loss", "closed_at": "2026-01-03T10:00:00+00:00", "realized_pnl_amount": -20.0}
    ]
    curve = equity_curve(trades, 1000.0)
    pts = curve["points"]
    assert len(pts) >= 1, "Baseline point should be present"
    assert pts[0]["date"] == "2026-01-03", "Baseline should be dated at earliest closed_at"
    assert pts[0]["balance"] == 1000.0, "Baseline balance should be starting balance"
    assert pts[0]["pnl"] == 0.0, "Baseline pnl should be 0.0"
    assert curve["skipped_n"] == 0
    # Verify full curve: baseline + 2 trades in close order
    assert [p["balance"] for p in pts] == [1000.0, 980.0, 1030.0]


def _pts(balances):
    return [{"date": f"2026-01-{i+1:02d}", "balance": b, "pnl": 0.0} for i, b in enumerate(balances)]


def test_drawdown_series_and_max():
    pts = _pts([1000, 1100, 990, 1200])
    dd = drawdown_series(pts)
    assert [round(d["dd_pct"], 4) for d in dd] == [0.0, 0.0, 10.0, 0.0]
    assert max_drawdown_pct(pts) == 10.0


def test_max_drawdown_pct_needs_two_points():
    assert max_drawdown_pct([]) is None
    assert max_drawdown_pct(_pts([1000])) is None


def test_drawdown_series_monotonic_up_is_all_zero():
    pts = _pts([1000, 1050, 1100, 1150])
    assert all(d["dd_pct"] == 0.0 for d in drawdown_series(pts))
