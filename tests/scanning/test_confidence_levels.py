import pytest
from swingbot.core.scanning.confidence import (
    LEVELS, honesty_cap, level_for_score,
)


def test_levels_table_has_six_contiguous_bands():
    assert [lvl for lvl, _label, _lo, _hi in LEVELS] == [1, 2, 3, 4, 5, 6]
    for (_l, _lab, _lo, hi), (_l2, _lab2, lo2, _hi2) in zip(LEVELS, LEVELS[1:]):
        assert lo2 == hi + 1, "level bands must be contiguous with no gap"


@pytest.mark.parametrize("methods,expected_cap", [
    (0, 1), (1, 3), (2, 4), (3, 5), (4, 6), (9, 6),
])
def test_honesty_cap_by_method_count(methods, expected_cap):
    """One method can never exceed Lv3, two never Lv4, three never Lv5.
    Level 6 additionally requires a FOURTH independent method -- stricter
    than Lv5's 3, per the spec."""
    assert honesty_cap(methods) == expected_cap


def test_high_score_cannot_beat_the_cap():
    """A perfect 100 on one confirming method still caps at Level 3. This is
    the whole point of the honesty property."""
    level, _label = level_for_score(100, target_count=1)
    assert level == 3


def test_level_six_needs_four_methods_even_at_full_score():
    assert level_for_score(100, target_count=3)[0] == 5
    assert level_for_score(100, target_count=4)[0] == 6


def test_low_score_is_not_rescued_by_many_methods():
    """The cap only ever lowers a level, never raises one."""
    level, _label = level_for_score(5, target_count=9)
    assert level == 1


# --- Task 6: score_confidence() runs the registry behind the flag -----

from swingbot import config  # noqa: E402
from swingbot.core.scanning.confidence import score_confidence  # noqa: E402

# Captured by running the pre-Task-6 (legacy) score_confidence directly
# against sample_scenario (regime_trend="bullish", df=None) before this
# task touched the function -- see the Task 6 commit message.
LEGACY_EXPECTED_LEVEL = 4
LEGACY_EXPECTED_SCORE = 73


def test_legacy_path_is_bit_identical_when_flag_off(monkeypatch, sample_scenario):
    """Default-OFF must mean *nothing changes*. This is the safety property
    the whole rollout depends on."""
    monkeypatch.setattr(config, "UNIFIED_CONFIDENCE", False)
    result = score_confidence(sample_scenario, regime_trend="bullish", df=None)
    assert result.level == LEGACY_EXPECTED_LEVEL
    assert result.score == LEGACY_EXPECTED_SCORE


def test_unified_path_returns_same_result_shape(monkeypatch, sample_scenario):
    monkeypatch.setattr(config, "UNIFIED_CONFIDENCE", True)
    result = score_confidence(sample_scenario, regime_trend="bullish", df=None)
    assert 1 <= result.level <= 6
    assert 0 <= result.score <= 100
    assert isinstance(result.breakdown, dict)
