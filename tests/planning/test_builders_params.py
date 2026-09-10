"""The shared target builders accept an explicit scan decision surface."""
import dataclasses

from swingbot.core.planning.builders import _atr_plan
from swingbot.scan_params import ScanParams


def test_params_none_matches_the_config_globals():
    params = ScanParams.from_config()
    plain = _atr_plan(100.0, 2.0, "bullish", "4w", "RSI", candidate_levels=[110.0])
    explicit = _atr_plan(100.0, 2.0, "bullish", "4w", "RSI",
                          candidate_levels=[110.0], params=params)
    assert plain == explicit


def test_wider_rr_band_changes_target_selection():
    base = ScanParams.from_config()
    wide = dataclasses.replace(base, min_risk_reward_ratio=0.1,
                               max_risk_reward_ratio=10.0)
    assert _atr_plan(100.0, 2.0, "bullish", "4w", "RSI",
                     candidate_levels=[101.0], params=base) is None
    assert _atr_plan(100.0, 2.0, "bullish", "4w", "RSI",
                     candidate_levels=[101.0], params=wide) is not None
