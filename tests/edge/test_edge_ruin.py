import pytest

from swingbot.core.edge.ruin import simulate

# Positive-expectancy but loss-heavy mix: 8 wins of +0.4R, 2 losses of -1R
# -> expectancy +0.12R. Realistic shape for this bot's strategies.
R_MIX = [0.4] * 8 + [-1.0] * 2


def test_deterministic_under_seed():
    a = simulate(R_MIX, risk_pct=1.0)
    b = simulate(R_MIX, risk_pct=1.0)
    assert a == b


def test_risk_scales_drawdown_and_ruin():
    low = simulate(R_MIX, risk_pct=1.0)
    high = simulate(R_MIX, risk_pct=5.0)
    assert high["max_dd_p95"] > low["max_dd_p95"]
    assert high["p_ruin"] >= low["p_ruin"]
    assert low["p_ruin"] < 0.01  # 1% risk on a +0.12R edge basically never halves


def test_positive_edge_compounds_at_median():
    out = simulate(R_MIX, risk_pct=1.0)
    assert out["p50_final_multiple"] > 1.0
    assert 0.0 <= out["p_10x"] <= 1.0


def test_empty_history_raises():
    with pytest.raises(ValueError):
        simulate([], risk_pct=1.0)
