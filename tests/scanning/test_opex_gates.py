"""The two alert gates tighten on an opex day and are untouched off one."""
import datetime as dt
import inspect

import pytest

from swingbot import config
from swingbot.core.market import opex
from swingbot.core.scanning import embeds


class _Conf:
    def __init__(self, level):
        self.level = level
        self.label = "High"
        self.score = 70
        self.breakdown = {}


class _Scenario:
    """Minimal stand-in -- only what _build_requirement_checks reads.

    An empty `constraints` dict makes every `c.get(key, True)` check pass, so
    the only two checks that can fail here are the two this task rewires.
    """
    def __init__(self):
        self.constraints = {}
        self.target_distance_pct = 5.0
        self.stop_distance_pct = 2.0
        self.risk_reward_ratio = 2.5


def _checks(conf_level, min_confluence, min_confidence, confluence=(3, ("EMA",)), opex_tier=None):
    # `target_confluence` is (count, families) -- the order
    # _build_requirement_checks unpacks it in.
    return embeds._build_requirement_checks(
        _Scenario(), confluence, _Conf(conf_level),
        min_confluence, min_confidence, opex_tier=opex_tier,
    )


def _passed(checks, key):
    return next(c.passed for c in checks if c.key == key)


def test_confidence_check_uses_the_effective_level():
    # Lv4 passes a Lv4 bar and fails the Lv5 bar an opex day imposes.
    assert _passed(_checks(4, 2, 4), "min_confidence") is True
    assert _passed(_checks(4, 2, 5), "min_confidence") is False


def test_confluence_check_uses_the_effective_count():
    assert _passed(_checks(4, 3, 4), "min_confluence") is True
    assert _passed(_checks(4, 4, 4), "min_confluence") is False


def test_confidence_detail_quotes_the_effective_level(monkeypatch):
    # The helper must not fall back to the raw config value in the text
    # either -- a "needs Lv4+" line under a Lv5 opex bar would be a lie.
    monkeypatch.setattr(config, "MIN_ALERT_CONFIDENCE_LEVEL", 4)
    detail = next(c.detail for c in _checks(4, 2, 5) if c.key == "min_confidence")
    assert "Lv5+" in detail


def test_thresholds_are_unchanged_off_an_opex_day(monkeypatch):
    monkeypatch.setattr(config, "OPEX_CAUTION_ENABLED", True)
    monkeypatch.setattr(config, "MIN_ALERT_CONFIDENCE_LEVEL", 4)
    thursday = dt.datetime(2026, 8, 20, 12, 0, tzinfo=opex.US_MARKET_TZ)
    tier = opex.current_tier(thursday)
    assert tier is None
    assert opex.effective_min_confidence_level(tier) == 4
    assert opex.effective_min_confluence(2, tier) == 2


def test_close_window_check_appears_only_while_suppressing(monkeypatch):
    monkeypatch.setattr(embeds.opex, "suppress_new_entries", lambda **kwargs: True)
    keys = [c.key for c in _checks(5, 2, 4)]
    assert "opex_close_window" in keys
    assert _passed(_checks(5, 2, 4), "opex_close_window") is False


def test_close_window_check_absent_outside_the_window(monkeypatch):
    monkeypatch.setattr(embeds.opex, "suppress_new_entries", lambda **kwargs: False)
    keys = [c.key for c in _checks(5, 2, 4)]
    assert "opex_close_window" not in keys


def test_close_window_uses_the_scan_resolved_tier(monkeypatch):
    """Task v59 A-S7: worker checks must not re-read the wall clock."""
    seen = []
    monkeypatch.setattr(embeds.opex, "suppress_new_entries", lambda *, tier: seen.append(tier) or False)

    _checks(5, 2, 4, opex_tier=opex.MONTHLY)

    assert seen == [opex.MONTHLY]


def test_the_funnel_counters_have_a_slot_for_the_new_key():
    # engine.py counts a failed check with `failed_counts[r.key] += 1` on a
    # plain dict, in both the per-ticker stats and the run-level merge. A key
    # missing from either literal turns the suppression window into a
    # KeyError mid-scan rather than a quiet hour.
    from swingbot.core.scanning import engine
    src = inspect.getsource(engine)
    assert src.count('"opex_close_window": 0') == 2


def test_the_funnel_summary_surfaces_the_suppressed_count():
    # Counting the failure without publishing it would leave the quiet hour
    # exactly as unexplained as the plan's rationale says it must not be.
    from swingbot.core.scanning import engine
    src = inspect.getsource(engine)
    assert '"failed_opex_close_window": failed_counts["opex_close_window"]' in src
