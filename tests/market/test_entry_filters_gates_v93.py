import pandas as pd
import pytest

from swingbot.core.market import entry_filters as ef
from swingbot.core.market.strategy_types import STRATEGY_GATES
from tests.helpers import make_ohlcv


@pytest.fixture
def frame(monkeypatch):
    df = make_ohlcv([100.0] * 300, start="2025-01-02")
    on = pd.Series(True, index=df.index)
    monkeypatch.setitem(ef.ENTRY_FUNCS, "Fake", lambda d, hk, params=None: (on.copy(), on.copy()))
    monkeypatch.setattr(ef, "apply_regime_gate", lambda bull, bear, strategy, regimes: (bull, bear))
    return df


def test_horizons_by_direction_overrides_only_that_direction(frame, monkeypatch):
    monkeypatch.setitem(STRATEGY_GATES, "Fake", {"directions": ("bullish", "bearish"), "horizons": ("2m",),
                                                   "horizons_by_direction": {"bearish": ("4w", "2m")}})
    bull, bear = ef.entries_for("Fake", frame, "4w", regimes=pd.Series("x", index=frame.index))
    assert not bull.any() and bear.all()
    bull, bear = ef.entries_for("Fake", frame, "2m", regimes=pd.Series("x", index=frame.index))
    assert bull.all() and bear.all()
    bull, bear = ef.entries_for("Fake", frame, "9m", regimes=pd.Series("x", index=frame.index))
    assert not bull.any() and not bear.any()


def test_direction_mask_and_gate_override_restore(frame, monkeypatch):
    monkeypatch.setitem(STRATEGY_GATES, "Fake", {"directions": ("bullish",)})
    bull, bear = ef.entries_for("Fake", frame, "4w", regimes=pd.Series("x", index=frame.index))
    assert bull.all() and not bear.any()
    with ef.gate_override("Fake", {"directions": ("bullish", "bearish")}):
        assert STRATEGY_GATES["Fake"] == {"directions": ("bullish", "bearish")}
    assert STRATEGY_GATES["Fake"] == {"directions": ("bullish",)}
    with ef.gate_override("Fake", None):
        assert "Fake" not in STRATEGY_GATES
    assert STRATEGY_GATES["Fake"] == {"directions": ("bullish",)}


def test_gate_override_restores_after_exception(monkeypatch):
    monkeypatch.setitem(STRATEGY_GATES, "Fake", {"directions": ("bullish",)})
    with pytest.raises(RuntimeError):
        with ef.gate_override("Fake", {}):
            raise RuntimeError("boom")
    assert STRATEGY_GATES["Fake"] == {"directions": ("bullish",)}
