from swingbot.core.analytics.metrics import rolling_expectancy_r


def _t(i, r):
    entry, stop = 100.0, 95.0                      # risk = 5 -> exit = entry + 5r
    return {"status": "win" if r > 0 else "loss", "direction": "bullish", "entry": entry,
            "stop_loss": stop, "exit_price": entry + 5 * r,
            "closed_at": f"2026-08-{i + 1:02d}T15:00:00+00:00"}


def test_rolling_expectancy_starts_at_five_trades_and_averages_the_window():
    closed = [_t(i, r) for i, r in enumerate([1, -1, 2, -1, 1, 3])]
    pts = rolling_expectancy_r(closed, window=3)
    assert [p["date"] for p in pts] == ["2026-08-05", "2026-08-06"]
    assert pts[0]["exp_r"] == round((2 - 1 + 1) / 3, 4)
    assert pts[1]["exp_r"] == round((-1 + 1 + 3) / 3, 4)


def test_rolling_expectancy_skips_uncomputable_and_undated():
    closed = [_t(i, 1) for i in range(5)] + [{"status": "win", "entry": 1, "stop_loss": 1}]
    assert len(rolling_expectancy_r(closed, window=50)) == 1
