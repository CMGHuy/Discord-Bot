from swingbot.core.plan_engine import badge_stats_line, stamp_badge
from swingbot.core.registry import get_badge

from tests.test_plan_engine_model import _plan


def test_stamp_validated():
    # Numbers from the exit-v2 validation single run (Task 32, 2026-07-18).
    p = _plan(strategy="Fibonacci")
    stamp_badge(p)
    assert p.badge == "VALIDATED"
    assert p.badge_stats["win_rate"] == 82.3


def test_stamp_weak():
    # The WEAK exemplar has moved twice: RSI was rescued to VALIDATED in
    # Tasks 95-97, then EMA Crossover followed in V25 when the emitter stopped
    # scoring against V6's voided `win_rate >= 80`. **No registered strategy
    # is WEAK any more** (see test_every_registered_strategy_is_now_validated),
    # so the only remaining WEAK path is the unregistered fallback -- which is
    # the one that actually needs to keep working, since it is what an unknown
    # or newly-added strategy gets.
    p = _plan(strategy="Not A Registered Strategy")
    stamp_badge(p)
    assert p.badge == "WEAK"
    assert p.badge_stats["n"] == 0


def test_every_registered_strategy_is_now_validated():
    """V25's consequence, pinned deliberately rather than discovered later.

    Removing the voided `win_rate >= 80` clause left all 11 strategies passing
    V6 Step 3's rule on the 2024-2025 window, so the badge **no longer
    discriminates between strategies**: `WEAK_CAUTION_TEXT` can never render
    for a recognised one, and `quality.component_badge` returns a constant +20
    on every live plan. That is the honest output of the corrected rule, not a
    bug -- but it means the live WEAK-vs-VALIDATED split that measured
    -0.213R against +0.781R has no successor until a discriminator that the
    V6 rule does not flatten is chosen (Wilson LB, an N floor, expectancy
    bands). If this test starts failing, that choice was made -- update it
    deliberately."""
    from swingbot.core.backtest import ALL_STRATEGIES
    assert all(get_badge("confluence", s, "4w").status == "VALIDATED"
               for s in ALL_STRATEGIES)


def test_stats_line():
    line = badge_stats_line(get_badge("strategy", "Fibonacci"))
    assert "N=203" in line and "82.3%" in line
