"""v32 Task 6, Step 6: engine.py's post-HTF-penalty rebucket must go through
level_for_score() (the single source of truth for the v32 honesty-cap-based
level, updated by Task 9 -- see confidence.py's level_for_score docstring)
when UNIFIED_CONFIDENCE is on, and must keep the exact pre-v32 hardcoded
formula when it's off -- the legacy score is still positioned inside the
OLD 5-equal-band scale, so "default off means nothing changes" has to hold
for this rebucket too, not just inside score_confidence() itself."""
from swingbot import config
from swingbot.core.scanning.confidence import ConfidenceResult
from swingbot.core.scanning.engine import _rebucket_after_htf_penalty


def test_unified_rebucket_uses_honesty_cap_not_the_old_hardcoded_bands(monkeypatch):
    """target_count=4 -> honesty_cap=5 (Level 6 removed on a negative TRAIN
    result, Task 9 -- see confidence.py's LEVELS comment); score=78 clears
    the quality-boost threshold (70) so the +1 nudge applies, clamped back
    to the cap -> 5. The old hardcoded `1 + 78 // 20` gives 4 -- the exact
    divergence this fix exists to close (engine.py used to silently
    recompute the wrong level for the unified path)."""
    monkeypatch.setattr(config, "UNIFIED_CONFIDENCE", True)
    conf = ConfidenceResult(level=5, label="Very High", score=98, breakdown={})
    result = _rebucket_after_htf_penalty(conf, new_score=78, target_count=4, penalty=20)
    assert result.level == 5
    assert result.score == 78
    assert result.breakdown["htf_counter_trend_penalty"] == -20


def test_legacy_rebucket_keeps_the_old_hardcoded_formula(monkeypatch):
    """Same score, flag off: must land on Level 4, exactly as the
    unmodified `1 + 78 // 20` formula always did -- proves the legacy path
    did not silently start using the new bands."""
    monkeypatch.setattr(config, "UNIFIED_CONFIDENCE", False)
    conf = ConfidenceResult(level=5, label="Very High", score=98, breakdown={})
    result = _rebucket_after_htf_penalty(conf, new_score=78, target_count=4, penalty=20)
    assert result.level == 4


def test_unified_rebucket_honors_the_honesty_cap(monkeypatch):
    """A high post-penalty score with only one confirming method still
    lands at Level 3 (honesty_cap(1)=3; the +1 quality nudge is absorbed by
    the clamp), same as everywhere else level_for_score is used."""
    monkeypatch.setattr(config, "UNIFIED_CONFIDENCE", True)
    conf = ConfidenceResult(level=5, label="Very High", score=98, breakdown={})
    result = _rebucket_after_htf_penalty(conf, new_score=95, target_count=1, penalty=3)
    assert result.level == 3
