import pytest

from swingbot.core import quality


@pytest.mark.parametrize("direction,regime,expected", [
    ("bullish", "bullish", 15), ("bullish", None, 8), ("bullish", "bearish", 0),
    ("bearish", "bearish", 15), ("bearish", None, 8), ("bearish", "bullish", 0),
])
def test_component_regime(direction, regime, expected):
    # regime.get_market_regime().trend is binary ("bullish"|"bearish", no
    # "neutral" state exists) -- None (feed unavailable/off) is the only
    # neutral case.
    assert quality.component_regime(direction, regime) == expected


@pytest.mark.parametrize("direction,bias,expected", [
    ("bullish", "bullish", 15), ("bullish", "neutral", 8), ("bullish", "bearish", 0),
    ("bearish", "bearish", 15), ("bearish", "neutral", 8), ("bearish", "bullish", 0),
    ("bearish", None, 8),
])
def test_component_htf(direction, bias, expected):
    assert quality.component_htf(direction, bias) == expected


@pytest.mark.parametrize("count,expected",
                         [(0, 0), (1, 7), (2, 12), (3, 16), (4, 20), (9, 20)])
def test_component_confluence(count, expected):
    assert quality.component_confluence(count) == expected


@pytest.mark.parametrize("ratio,expected", [
    (0.79, 0), (0.8, 4), (1.19, 4), (1.2, 8), (1.99, 8), (2.0, 10),
    (None, 0), (float("nan"), 0),
])
def test_component_volume(ratio, expected):
    assert quality.component_volume(ratio) == expected


@pytest.mark.parametrize("pct,expected",
                         [(0.95, 0), (0.9, 0), (0.89, 5), (0.7, 5), (0.69, 10),
                          (0.0, 10), (None, 5)])   # unknown -> middle score
def test_component_atr_percentile(pct, expected):
    assert quality.component_atr_percentile(pct) == expected


@pytest.mark.parametrize("dist,expected",
                         [(0.0, 10), (0.5, 10), (0.51, 6), (1.5, 6),
                          (1.51, 3), (3.0, 3), (3.01, 0)])
def test_component_distance(dist, expected):
    assert quality.component_distance(dist) == expected


def test_atr_percentile_spike_ranks_high():
    from tests.helpers import make_ohlcv
    # calm tape, then 20 violently-ranged bars at the end -> current
    # normalized ATR sits in the top of its trailing distribution.
    calm = [(100.0, 100.5, 99.5, 100.0)] * 300
    wild = [(100.0, 112.0, 88.0, 100.0)] * 20
    df = make_ohlcv(calm + wild)
    pct = quality.atr_percentile(df)
    assert pct is not None and pct >= 0.9


def test_atr_percentile_short_frame_is_none():
    from tests.helpers import make_ohlcv
    assert quality.atr_percentile(make_ohlcv([100.0] * 20)) is None


def test_perfect_inputs_score_100_tier_a():
    r = quality.score_plan(direction="bullish", regime="bullish", htf_bias="bullish",
                           confluence_count=4, volume_ratio=2.5, atr_pct=0.3,
                           trigger_distance_pct=0.2, badge_status="VALIDATED")
    assert r.score == 100 and r.tier == "A"


def test_all_zero_inputs_score_0_tier_c():
    r = quality.score_plan(direction="bullish", regime="bearish", htf_bias="bearish",
                           confluence_count=0, volume_ratio=0.5, atr_pct=0.95,
                           trigger_distance_pct=5.0, badge_status="WEAK")
    assert r.score == 0 and r.tier == "C"


def test_breakdown_has_seven_named_rows_summing_to_score():
    r = quality.score_plan(direction="bullish", regime=None, htf_bias="bullish",
                           confluence_count=2, volume_ratio=1.5, atr_pct=0.5,
                           trigger_distance_pct=1.0, badge_status="VALIDATED")
    assert [name for name, _ in r.breakdown] == \
        ["regime", "htf", "confluence", "volume", "atr_percentile",
         "trigger_distance", "badge"]
    assert sum(pts for _, pts in r.breakdown) == r.score


def test_tier_boundaries():
    assert quality._tier(75) == "A" and quality._tier(74) == "B"
    assert quality._tier(50) == "B" and quality._tier(49) == "C"


def test_audit_script_never_imported_by_swingbot():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "swingbot"
    offenders = [p for p in root.rglob("*.py")
                 if "audit_quality_score" in p.read_text(encoding="utf-8")]
    assert offenders == [], offenders
