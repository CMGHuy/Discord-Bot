import numpy as np

from swingbot.core.gate.risk_def import check_stop_structural
from tests.conftest import make_ohlcv
from tests.fixtures.gate.plans import make_plan


def _support_touches(support=100.0, top=110.0, n=120):
    """Three clean touches of a support at ~100 (valleys unique)."""
    closes = []
    for _ in range(3):
        closes += list(np.linspace(top, support, 15)) + list(np.linspace(support, top, 15))[1:]
    closes += list(np.linspace(top, top * 1.01, n - len(closes)))
    return make_ohlcv(np.asarray(closes), spread_pct=0.5)


def test_beyond_and_wide_passes():
    # support (with spread) ~99.75; stop 98.4 is >0.5 ATR beyond, off-level
    plan = make_plan(direction="bullish", trigger_price=104.0, entry_price=104.0,
                     stop_loss=98.4, tp1=112.0)
    result = check_stop_structural(_support_touches(), plan, None)
    assert result.status == "pass"
    assert result.evidence["margin_atr"] >= 0.5


def test_at_level_or_too_tight_warns():
    plan = make_plan(direction="bullish", trigger_price=104.0, entry_price=104.0,
                     stop_loss=99.7, tp1=112.0)      # a hair beyond the structure
    assert check_stop_structural(_support_touches(), plan, None).status == "warn"


def test_inside_structure_fails():
    plan = make_plan(direction="bullish", trigger_price=104.0, entry_price=104.0,
                     stop_loss=101.0, tp1=112.0)     # above the support = inside
    assert check_stop_structural(_support_touches(), plan, None).status == "fail"
