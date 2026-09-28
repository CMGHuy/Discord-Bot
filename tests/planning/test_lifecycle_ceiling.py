"""v104 Part 0: lifecycle widening is bounded by the stop ceiling, not max_risk_pct."""
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.market import levels_lifecycle
from swingbot.core.planning import lifecycle


@pytest.fixture
def tested_anchor(monkeypatch):
    """One tested support at 95.0 behind a 2% stop at 98.0 (entry 100)."""
    monkeypatch.setattr(config, "LEVEL_LIFECYCLE_STOPS_ENABLED", True, raising=False)
    monkeypatch.setattr(config, "MIN_RISK_REWARD_RATIO", 1.5, raising=False)
    monkeypatch.setattr(config, "MAX_RISK_REWARD_RATIO", 2.5, raising=False)
    monkeypatch.setattr(lifecycle, "_lifecycle_levels", lambda *a, **k: ["level"])
    monkeypatch.setattr(
        levels_lifecycle,
        "preferred_stop_anchor",
        lambda levels, direction: SimpleNamespace(price=95.0, state="tested", touches=1),
    )


def _apply(scope, monkeypatch):
    monkeypatch.setattr(config, "STRUCTURAL_STOP_SCOPE", scope, raising=False)
    return lifecycle.apply_level_lifecycle(
        None, 0, entry=100.0, stop=98.0, tp1=104.0, atr_val=1.0, direction="bullish",
        strategy="Fibonacci", horizon_key="4w", candidate_levels=[112.0])


def test_out_of_scope_never_widens_past_two_percent(tested_anchor, monkeypatch):
    stop, tp1, _ = _apply("", monkeypatch)
    assert (stop, tp1) == (98.0, 104.0)


def test_in_scope_widens_to_the_tested_level(tested_anchor, monkeypatch):
    stop, tp1, meta = _apply("Fibonacci:bullish", monkeypatch)
    assert stop == pytest.approx(94.75)
    assert tp1 == 112.0
    assert meta["lifecycle_stop"]["state"] == "tested"
