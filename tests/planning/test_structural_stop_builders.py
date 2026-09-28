"""v104 §2.2: builders cap out of scope and retain or drop structural stops in scope."""
import pytest

from swingbot import config
from swingbot.core.planning import builders as b
from swingbot.core.planning.targets import atr_target_candidates


@pytest.fixture
def rr(monkeypatch):
    monkeypatch.setattr(config, "MIN_RISK_REWARD_RATIO", 1.5, raising=False)
    monkeypatch.setattr(config, "MAX_RISK_REWARD_RATIO", 2.5, raising=False)


def _scope(monkeypatch, raw):
    monkeypatch.setattr(config, "STRUCTURAL_STOP_SCOPE", raw, raising=False)


def test_fibonacci_out_of_scope_is_capped_at_two_percent(rr, monkeypatch):
    _scope(monkeypatch, "")
    stop, _ = b._fibonacci_plan(100.0, 1.0, 120.0, 95.0, "bullish", "4w", candidate_levels=[110.0])
    assert stop == pytest.approx(98.0)


def test_fibonacci_in_scope_keeps_the_swing_stop(rr, monkeypatch):
    _scope(monkeypatch, "Fibonacci:bullish")
    stop, tp1 = b._fibonacci_plan(100.0, 1.0, 120.0, 95.0, "bullish", "4w", candidate_levels=[110.0])
    assert stop == pytest.approx(94.75)
    assert tp1 == 110.0


def test_fibonacci_in_scope_beyond_the_ceiling_drops(rr, monkeypatch):
    _scope(monkeypatch, "Fibonacci:bullish")
    assert b._fibonacci_plan(100.0, 1.0, 120.0, 90.0, "bullish", "4w", candidate_levels=[130.0]) is None


def test_atr_plan_in_scope_keeps_two_atr(rr, monkeypatch):
    candidates = atr_target_candidates(100.0, 3.0, "bullish")
    _scope(monkeypatch, "")
    assert b._atr_plan(100.0, 3.0, "bullish", "4w", "MACD", candidate_levels=candidates)[0] == pytest.approx(98.0)
    _scope(monkeypatch, "MACD:bullish")
    assert b._atr_plan(100.0, 3.0, "bullish", "4w", "MACD", candidate_levels=candidates)[0] == pytest.approx(94.0)


def test_sr_plan_in_scope_uses_sr_stop_pct(rr, monkeypatch):
    _scope(monkeypatch, "")
    assert b._sr_plan(100.0, 2.0, "bullish", "2m", candidate_levels=[115.0])[0] == pytest.approx(98.0)
    _scope(monkeypatch, "Support/Resistance:bullish")
    stop, tp1 = b._sr_plan(100.0, 2.0, "bullish", "2m", candidate_levels=[115.0])
    assert stop == pytest.approx(92.0) and tp1 == 115.0


def test_elliott_in_scope_keeps_the_wave_two_stop(rr, monkeypatch):
    _scope(monkeypatch, "Elliott Wave:bullish")
    stop, _ = b._elliott_plan(100.0, 1.0, 95.0, "bullish", "4w", candidate_levels=[110.0])
    assert stop == pytest.approx(94.75)


def test_bearish_mirror_in_scope(rr, monkeypatch):
    _scope(monkeypatch, "Fibonacci:bearish")
    stop, _ = b._fibonacci_plan(100.0, 1.0, 105.0, 80.0, "bearish", "4w", candidate_levels=[90.0])
    assert stop == pytest.approx(105.25)
