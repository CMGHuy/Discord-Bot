"""v209: stamp_entry_context merges shock_state beside the feature dict.

Never a FEATURE_KEYS member; absent (not None) without a label, so
MARKET_SHOCK_MODE=off stays byte-identical; survives a feature-build failure."""
import pytest

from swingbot.core.edge import context as edge_context
from swingbot.core.edge.context import FEATURE_KEYS
from swingbot.core.planning import params
from swingbot.core.planning.plan_types import PlanStatus, TradePlanV2
from tests.helpers import make_ohlcv

ASOF = {"regime2_state": "bear_volatile", "rs_pctile": 40.0, "sector_pctile": None,
        "rs_combined": 40.0}


def _plan():
    return TradePlanV2(plan_id="p", ticker="AAPL", created_at="2026-11-05", source="confluence",
                       strategy="MACD", horizon_key="3m", direction="bullish", entry_type="market",
                       trigger_price=100.0, entry_price=100.0, expiry_bars=5, stop_loss=98.5,
                       tp1=110.0, tp1_fraction=0.5, tp2=None, breakeven_trigger_fraction=0.5,
                       trail_atr_mult=2.0, quality_score=0, quality_breakdown=[], badge="WEAK",
                       badge_stats={}, status=PlanStatus.PENDING)


def _stamped(asof):
    plan = _plan()
    frame = make_ohlcv([100.0 + i * 0.1 for i in range(300)], start="2025-06-02")
    params.stamp_entry_context(plan, frame, asof)
    return plan.entry_context


def test_shock_state_is_never_a_feature_key():
    assert "shock_state" not in FEATURE_KEYS


def test_the_asof_fragment_is_empty_without_a_label():
    assert params.shock_asof(None) == {}
    assert params.shock_asof("SHOCK") == {"shock_state": "SHOCK"}


@pytest.mark.parametrize("label", ["NORMAL", "SHOCK", "RECOVERY"])
def test_the_label_is_merged_after_the_feature_dict(label):
    base = _stamped(ASOF)
    shocked = _stamped({**ASOF, "shock_state": label})
    assert shocked.pop("shock_state") == label
    assert shocked == base
    assert set(base) == set(FEATURE_KEYS)


@pytest.mark.parametrize("asof", [ASOF, {**ASOF, "shock_state": None}, None, {}])
def test_no_label_leaves_the_key_absent(asof):
    assert "shock_state" not in _stamped(asof)


def test_the_label_survives_a_feature_build_failure(monkeypatch):
    def boom(*args, **kwargs):
        raise ValueError("bad frame")

    monkeypatch.setattr(edge_context, "entry_context", boom)
    assert _stamped({**ASOF, "shock_state": "SHOCK"}) == {"shock_state": "SHOCK"}
    assert _stamped(ASOF) == {}
