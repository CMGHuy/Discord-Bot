"""v32 Task 6, Step 6: engine.py's post-HTF-penalty rebucket must go through
level_for_score() (the single source of truth for the v32 6-band table)
when UNIFIED_CONFIDENCE is on, and must keep the exact pre-v32 hardcoded
formula when it's off -- the legacy score is still positioned inside the
OLD 5-equal-band scale, so "default off means nothing changes" has to hold
for this rebucket too, not just inside score_confidence() itself."""
from swingbot import config
from swingbot.core.scanning.confidence import ConfidenceResult
from swingbot.core.scanning.engine import _rebucket_after_htf_penalty


def test_unified_rebucket_uses_the_new_uneven_bands(monkeypatch):
    """78 is Level 5 under the v32 table (76-90) but Level 4 under the old
    hardcoded `1 + score // 20` -- the exact divergence this fix exists to
    close."""
    monkeypatch.setattr(config, "UNIFIED_CONFIDENCE", True)
    conf = ConfidenceResult(level=6, label="Elite", score=98, breakdown={})
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
    caps at Level 3, same as everywhere else level_for_score is used."""
    monkeypatch.setattr(config, "UNIFIED_CONFIDENCE", True)
    conf = ConfidenceResult(level=6, label="Elite", score=98, breakdown={})
    result = _rebucket_after_htf_penalty(conf, new_score=95, target_count=1, penalty=3)
    assert result.level == 3
