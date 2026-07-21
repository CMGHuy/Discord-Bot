import pytest

from swingbot.core.edge.sizing import (
    KELLY_FRACTION_CAP, RISK_CEILING_PCT, RISK_FLOOR_PCT,
    kelly_fraction, kelly_risk_pct,
)


def test_kelly_fraction_golden():
    # f* = p - q/b with b = avg_win/avg_loss.
    # WR 0.80, avg win 0.4R, avg loss 1.0R: b = 0.4 -> f* = 0.8 - 0.2/0.4 = 0.30
    assert kelly_fraction(0.80, 0.4, 1.0) == pytest.approx(0.30)


def test_kelly_zero_when_no_edge():
    # WR 0.70 at b = 0.4 -> f* = 0.7 - 0.3/0.4 = -0.05 -> clamp to 0
    assert kelly_fraction(0.70, 0.4, 1.0) == 0.0
    assert kelly_fraction(0.50, 0.0, 1.0) == 0.0   # degenerate avg win


def test_quarter_kelly_capped_to_ceiling():
    # f* = 0.30 -> quarter-Kelly = 7.5% of equity -> way past the 2% ceiling
    stats = {"win_rate": 0.80, "avg_win_r": 0.4, "avg_loss_r": 1.0, "n": 200}
    assert kelly_risk_pct(stats) == RISK_CEILING_PCT


def test_zero_edge_floors():
    stats = {"win_rate": 0.60, "avg_win_r": 0.3, "avg_loss_r": 1.0, "n": 200}
    # f* = 0.6 - 0.4/0.3 = negative -> floor
    assert kelly_risk_pct(stats) == RISK_FLOOR_PCT


def test_small_sample_floors():
    stats = {"win_rate": 0.90, "avg_win_r": 0.5, "avg_loss_r": 1.0, "n": 12}
    assert kelly_risk_pct(stats) == RISK_FLOOR_PCT


def test_constants_frozen():
    assert KELLY_FRACTION_CAP == 0.25
    assert RISK_FLOOR_PCT == 0.25 and RISK_CEILING_PCT == 2.0
