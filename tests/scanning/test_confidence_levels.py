import pytest
from swingbot.core.scanning.confidence import (
    LEVELS, honesty_cap, level_for_score,
)


def test_levels_table_has_five_contiguous_bands():
    """v32 Task 9: Level 6 ("Elite") was conditional on TRAIN clearing
    n>=100, point estimate >=90%, Wilson lower bound >=80% and above Level
    5's own point estimate. It didn't -- n=0, structurally unreachable
    once the quality-points pool emptied (the +1 nudge that could reach it
    never fires). Removed; back to the exact pre-v32 5-band edges."""
    assert [lvl for lvl, _label, _lo, _hi in LEVELS] == [1, 2, 3, 4, 5]
    for (_l, _lab, _lo, hi), (_l2, _lab2, lo2, _hi2) in zip(LEVELS, LEVELS[1:]):
        assert lo2 == hi + 1, "level bands must be contiguous with no gap"


@pytest.mark.parametrize("methods,expected_cap", [
    (0, 1), (1, 3), (2, 4), (3, 5), (4, 5), (9, 5),
])
def test_honesty_cap_by_method_count(methods, expected_cap):
    """One method can never exceed Lv3, two never Lv4. Three or more
    methods all reach the same ceiling, Lv5, now that Lv6 is removed."""
    assert honesty_cap(methods) == expected_cap


def test_high_score_cannot_beat_the_cap():
    """A perfect 100 on one confirming method still caps at Level 3. This is
    the whole point of the honesty property."""
    level, _label = level_for_score(100, target_count=1)
    assert level == 3


def test_three_and_four_methods_reach_the_same_ceiling_now():
    """Lv6 used to distinguish 3 vs 4+ methods; with it removed both cap at
    Lv5."""
    assert level_for_score(100, target_count=3)[0] == 5
    assert level_for_score(100, target_count=4)[0] == 5


def test_many_methods_set_a_high_base_level_even_with_weak_quality():
    """v32 Task 9 fix: method count sets the BASE level (honesty_cap), and
    weak quality can only demote it by one level from there -- it can never
    override method count down to Level 1 the way a pure score-band lookup
    would. This corrects a Task 5 gap: deriving level purely from the 0-100
    score (using honesty_cap only as an upper ceiling) meant method count
    had NO influence on level unless the quality-points pool also scored
    high -- which would have pinned every alert at Level 1 the moment
    Task 9's TRAIN evidence emptied that pool (15 of 15 measured quality
    factors were Wilson-overlapping or wrong-signed), making Task 10's
    VALIDATION run fail by construction rather than test anything real."""
    level, _label = level_for_score(5, target_count=9)
    assert level == 4   # honesty_cap(9)=5, quality<=30 -> -1 nudge -> 4


def test_weak_quality_demotes_but_only_by_one_level():
    level, _label = level_for_score(5, target_count=2)
    assert level == 3   # honesty_cap(2)=4, quality<=30 -> -1 nudge -> 3


def test_unremarkable_quality_leaves_the_base_level_untouched():
    level, _label = level_for_score(50, target_count=2)
    assert level == 4   # honesty_cap(2)=4, 30 < quality < 70 -> no nudge


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
    assert 1 <= result.level <= 5
    assert 0 <= result.score <= 100
    assert isinstance(result.breakdown, dict)


def test_macro_verdict_kwarg_reaches_the_breakdown(monkeypatch, sample_scenario):
    """v33 Task 5: score_confidence()'s **kwargs is filtered through a fixed
    whitelist tuple (confidence.py) before it reaches FactorContext -- a
    kwarg missing from that tuple is silently dropped, never raised. Every
    factor-level test in test_factors.py builds FactorContext directly via
    _ctx(), which bypasses that whitelist entirely and so can't catch a
    reverted/typo'd tuple entry. This test goes through the real
    score_confidence() call the way engine.py does, so it fails if
    "macro_verdict" ever falls out of the whitelist tuple."""
    monkeypatch.setattr(config, "UNIFIED_CONFIDENCE", True)
    result = score_confidence(
        sample_scenario, regime_trend="bullish", df=None,
        macro_verdict={"status": "aligned", "reason": "bullish trend agrees",
                       "trend": "bullish"},
    )
    assert "Macro trend (6m)" in result.breakdown
