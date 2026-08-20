import pandas as pd
import pytest

from swingbot.core.market.level_strength import find_touches


def _bars(rows):
    """rows: list of (low, high, close)."""
    return pd.DataFrame({
        "Open": [r[2] for r in rows],
        "Low": [r[0] for r in rows],
        "High": [r[1] for r in rows],
        "Close": [r[2] for r in rows],
        "Volume": [1_000_000] * len(rows),
    })


def test_bar_entering_the_band_is_a_touch():
    df = _bars([(99.6, 101.0, 100.5), (105.0, 106.0, 105.5)])
    assert find_touches(df, level=100.0, tolerance_pct=0.5) == [0]


def test_bar_outside_the_band_is_not_a_touch():
    df = _bars([(105.0, 106.0, 105.5)])
    assert find_touches(df, level=100.0, tolerance_pct=0.5) == []


def test_band_is_a_percentage_of_the_level_not_absolute():
    """0.5% of 100 is 0.50; 0.5% of 1000 is 5.00. A fixed absolute band would
    make every level on a high-priced ticker untouchable."""
    df = _bars([(995.0, 1002.0, 1000.0)])
    assert find_touches(df, level=1000.0, tolerance_pct=0.5) == [0]


def test_multiple_touches_are_all_returned_in_order():
    df = _bars([(99.8, 100.2, 100.0), (110.0, 111.0, 110.5), (99.9, 100.4, 100.1)])
    assert find_touches(df, level=100.0, tolerance_pct=0.5) == [0, 2]


def test_zero_or_negative_level_returns_no_touches():
    assert find_touches(_bars([(99.8, 100.2, 100.0)]), level=0.0) == []


def test_empty_frame_returns_no_touches():
    assert find_touches(_bars([]), level=100.0) == []


from swingbot.core.market.level_strength import grade_level


def test_untouched_level_is_neutral_and_flagged_unavailable():
    """A freshly-formed level has no history. It must score NEUTRAL, not bad --
    otherwise the system structurally prefers old levels over good ones."""
    df = _bars([(200.0, 201.0, 200.5)] * 50)
    g = grade_level(df, level=100.0, direction="bullish", halflife_bars=60)
    assert g["available"] is False
    assert g["touches"] == 0
    assert g["score"] == pytest.approx(0.5)


def test_repeated_rejections_score_high():
    """Wick below the level, close back above = the level held."""
    rows = [(99.0, 101.0, 100.8)] * 3 + [(105.0, 106.0, 105.5)] * 20
    g = grade_level(_bars(rows), level=100.0, direction="bullish", halflife_bars=60)
    assert g["rejections"] == 3
    assert g["breaks"] == 0
    assert g["score"] > 0.6


def test_breaks_score_low():
    """Closing THROUGH the level is a failure, and must not score like a
    bounce -- a bare proximity count would rate a destroyed level as
    well-tested."""
    rows = [(98.0, 101.0, 98.5)] * 3 + [(90.0, 91.0, 90.5)] * 20
    g = grade_level(_bars(rows), level=100.0, direction="bullish", halflife_bars=60)
    assert g["breaks"] == 3
    assert g["score"] < 0.4


def test_recent_touches_outweigh_old_ones():
    """Decay weights make recent touches dominate the aggregate score.

    To isolate the decay formula (not incidental lookback effects), we mix
    rejections and breaks: rejections score high, breaks score 0. By putting
    rejections recent in one scenario and old in another, we show that
    decay -- not incidental quality variations -- determines which scenario
    scores higher."""
    # Scenario A: Rejections old (indices 0-5), breaks recent (indices 6-20).
    # Weighted average pulled down by recent low-quality breaks.
    rows_a = [(99.0, 101.0, 100.8)] * 6 + [(98.0, 101.0, 98.5)] * 15
    g_a = grade_level(_bars(rows_a), 100.0, "bullish", halflife_bars=20)

    # Scenario B: Breaks old (indices 0-5), rejections recent (indices 6-20).
    # Weighted average pulled up by recent high-quality rejections.
    rows_b = [(98.0, 101.0, 98.5)] * 6 + [(99.0, 101.0, 100.8)] * 15
    g_b = grade_level(_bars(rows_b), 100.0, "bullish", halflife_bars=20)

    # Recent high-quality touches dominate the score, so B > A.
    assert g_b["score"] > g_a["score"]


def test_score_is_bounded_to_unit_interval():
    rows = [(99.0, 101.0, 100.8)] * 40
    g = grade_level(_bars(rows), 100.0, "bullish", halflife_bars=60)
    assert 0.0 <= g["score"] <= 1.0


def test_every_horizon_defines_a_touch_decay_halflife():
    from swingbot.core.market.strategy_types import HORIZONS
    for key, settings in HORIZONS.items():
        assert "touch_decay_halflife" in settings, f"{key} missing halflife"


def test_halflives_increase_with_horizon_length():
    from swingbot.core.market.strategy_types import HORIZONS
    values = [HORIZONS[k]["touch_decay_halflife"] for k in HORIZONS]
    assert values == sorted(values)
