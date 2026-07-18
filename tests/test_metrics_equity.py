from swingbot.core.analytics.metrics import equity_curve


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
