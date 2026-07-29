import numpy as np

from swingbot.core.gate.atr_regime import check_atr_normal
from swingbot.core.gate.registry import CHECKS
from tests.conftest import make_ohlcv
from tests.fixtures.gate.plans import make_plan


def _vol_path(early_move, late_move, n=300, late=25):
    """Alternating +/- daily moves: early_move for n-late bars, late_move after."""
    closes = [100.0]
    for i in range(n):
        m = early_move if i < n - late else late_move
        closes.append(closes[-1] * (1 + (m if i % 2 == 0 else -m)))
    return make_ohlcv(np.asarray(closes[1:]), spread_pct=0.2)


PLAN = make_plan()


def test_normal_band_passes():
    result = check_atr_normal(_vol_path(0.01, 0.01), PLAN, None)
    assert result.status == "pass"
    assert 20 <= result.evidence["percentile"] <= 80


def test_compression_warns():
    assert check_atr_normal(_vol_path(0.02, 0.002), PLAN, None).status == "warn"


def test_spike_fails():
    result = check_atr_normal(_vol_path(0.004, 0.05), PLAN, None)
    assert result.status == "fail"
    assert result.evidence["percentile"] > 95


def test_short_history_unknown():
    df = _vol_path(0.01, 0.01, n=40, late=5)
    assert check_atr_normal(df, PLAN, None).status == "unknown"


def test_registered():
    assert CHECKS["atr_normal"].threshold("pct_spike") == 95.0
