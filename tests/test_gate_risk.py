import numpy as np

from swingbot.core.gate.risk_def import check_stop_structural, check_rr_realistic
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


def _resistance_touches(level=110.0, base=100.0, n=120):
    closes = []
    for _ in range(3):
        closes += list(np.linspace(base, level, 15)) + list(np.linspace(level, base, 15))[1:]
    closes += list(np.linspace(base, base * 1.04, n - len(closes)))
    return make_ohlcv(np.asarray(closes), spread_pct=0.5)


def test_wall_capped_rr_fails_despite_nominal_2to1():
    # nominal RR = (115-104)/5.5 = 2.0, but the ~110 wall caps it at ~1.15
    plan = make_plan(direction="bullish", trigger_price=104.0, entry_price=104.0,
                     stop_loss=98.5, tp1=115.0)
    result = check_rr_realistic(_resistance_touches(), plan, None)
    assert result.status == "fail"
    assert result.evidence["nominal_rr"] >= 1.9
    assert result.evidence["capped_rr"] < 1.2


def test_clear_sky_passes():
    # entry above the wall: nothing caps TP1
    plan = make_plan(direction="bullish", trigger_price=111.0, entry_price=111.0,
                     stop_loss=107.0, tp1=119.0)
    result = check_rr_realistic(_resistance_touches(), plan, None)
    assert result.status == "pass" and result.evidence["capped_rr"] >= 1.5
