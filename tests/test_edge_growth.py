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
