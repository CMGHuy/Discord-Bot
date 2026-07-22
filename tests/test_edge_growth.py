"""Growth math: the honest 10x arithmetic. Golden numbers derived by hand
in the docstrings of swingbot/core/edge/growth.py."""
import pytest

from swingbot.core.edge.growth import (
    eta_days, growth_table, per_trade_growth, trades_to_multiple,
)


def test_ten_x_trade_count_golden():
    # 1% risk, +0.10R expectancy -> 0.1% growth per closed trade.
    # ln(10)/ln(1.001) = 2303.7 -> floor 2303 (the trade DURING which the
    # target is crossed is #2304; 2303 full trades come before it).
    assert trades_to_multiple(10, 1.0, 0.10) == 2303
    assert per_trade_growth(1.0, 0.10) == pytest.approx(0.001)


def test_negative_expectancy_never_compounds():
    assert trades_to_multiple(10, 1.0, -0.05) is None
    assert trades_to_multiple(10, 1.0, 0.0) is None


def test_already_there():
    assert trades_to_multiple(1.0, 1.0, 0.10) == 0


def test_eta_days_golden():
    # 2303 trades at 60/month = 38.383 months * 30.44 = 1168.4 -> ceil 1169
    assert eta_days(2303, 60) == 1169
    assert eta_days(2303, 0) is None
    assert eta_days(None, 60) is None


def test_growth_table_shape():
    rows = growth_table()
    assert len(rows) == 16  # 4 expectancies x 4 risks
    assert set(rows[0]) == {"risk_pct", "expectancy_r", "growth_per_trade", "trades_to_10x"}
    # higher expectancy at same risk always needs fewer trades
    at_1pct = {r["expectancy_r"]: r["trades_to_10x"] for r in rows if r["risk_pct"] == 1.0}
    assert at_1pct[0.20] < at_1pct[0.05]


def test_growth_report_contains_trades_and_eta():
    from swingbot.core.edge.growth import growth_report
    stats = {"expectancy_r": 0.10, "trades_per_month": 60,
             "risk_pct": 1.0, "current_multiple": 1.0, "n_closed": 120}
    out = growth_report(stats, target=10.0)
    assert "2303" in out              # trades to 10x at current settings
    assert "1169" in out or "1,169" in out  # ETA days
    assert "+0.05R" in out            # sensitivity row header
    assert "not financial advice" in out.lower() or "will differ" in out.lower()


def test_growth_report_handles_no_edge():
    from swingbot.core.edge.growth import growth_report
    out = growth_report({"expectancy_r": -0.02, "trades_per_month": 10,
                         "risk_pct": 1.0, "n_closed": 15})
    assert "never" in out.lower() or "no positive edge" in out.lower()
    assert "N=15" in out              # sample size always shown


def test_growth_path_fixture():
    from swingbot.core.edge.growth import growth_path
    import math
    # 365 days from 10k to 15k -> 1.5x
    points = [("2025-07-12", 10_000.0), ("2026-07-12", 15_000.0)]
    gp = growth_path(points, start_balance=10_000.0)
    assert gp["current_multiple"] == pytest.approx(1.5)
    # log progress: ln(1.5)/ln(10) = 17.6%
    assert gp["pct_to_target"] == pytest.approx(17.6, abs=0.1)
    # required daily growth for 10x-in-3y from 1.5x: (10/1.5)^(1/1095.75)-1
    want = (10 / 1.5) ** (1 / (3 * 365.25)) - 1
    assert gp["required_daily_growth"][3] == pytest.approx(want, rel=1e-6)
    # realized: 1.5^(1/365) - 1 per day ≈ 0.111%/day
    assert gp["realized_daily_growth"] == pytest.approx(1.5 ** (1 / 365) - 1, rel=1e-4)
    assert gp["on_track_vs"][8] in (True, False)


def test_growth_path_empty_curve():
    from swingbot.core.edge.growth import growth_path
    gp = growth_path([], start_balance=10_000.0)
    assert gp["current_multiple"] == 1.0 and gp["realized_daily_growth"] is None


def test_collect_stats_threads_target_into_growth_path(monkeypatch):
    # Regression: _collect_stats() used to always call growth_path() with its
    # hardcoded default target_multiple=10.0, so `!growth 5` (or any non-10
    # target) computed pct_to_target/on_track_vs against 10x instead of the
    # user's requested target -- inconsistent with the main growth_report()
    # line a few feet away, which DID honor `target`.
    from swingbot.commands import growth as growth_cmd
    from swingbot.core import account as account_module

    points = [("2025-07-12", 10_000.0), ("2026-07-12", 15_000.0)]  # 1.5x
    monkeypatch.setattr(account_module, "load_account_config",
                        lambda: {"risk_pct": 1.0, "base_balance": 10_000.0, "balance": 15_000.0})
    monkeypatch.setattr(account_module, "get_balance_history_points", lambda: points)

    stats_default = growth_cmd._collect_stats()
    stats_5x = growth_cmd._collect_stats(target=5.0)

    assert stats_default["growth_path"]["pct_to_target"] == pytest.approx(17.6, abs=0.1)  # vs 10x
    # Same current_multiple (1.5x), but measured against a 5x target instead
    # of the hardcoded 10x -- pct_to_target and on_track_vs must both differ.
    import math
    want_5x = math.log(1.5) / math.log(5.0) * 100
    assert stats_5x["growth_path"]["pct_to_target"] == pytest.approx(want_5x, abs=0.01)
    assert stats_5x["growth_path"]["pct_to_target"] != stats_default["growth_path"]["pct_to_target"]
    assert stats_5x["growth_path"]["required_daily_growth"] != stats_default["growth_path"]["required_daily_growth"]
