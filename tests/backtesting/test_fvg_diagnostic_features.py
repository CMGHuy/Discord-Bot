"""v143 features: each value at a known bar, the gap match and its tolerance,
and that no feature reads a bar after the signal bar."""
import pytest

from swingbot import config
from swingbot.core.backtesting import fvg_diagnostic as fd
from swingbot.core.market.indicators import atr
from swingbot.core.planning.quality import atr_percentile, score_plan
from tests.market.fvg_frames import BULL_THIRD, FLAT, STRONG_BULL, WEAK_BULL, bar_frame
from tests.planning.test_exit_sim_single import _plan

ABOVE = (104.5, 105.5, 103.5, 104.5)     # stays above the gap top (101.5)
LATER = (104.5, 130.0, 80.0, 104.5)      # a wild bar AFTER the signal bar


def gap_frame(flat_bars=20, middle=STRONG_BULL, after=5):
    """flat bars, a middle candle, the third candle that opens a bullish gap
    101.0..101.5 (mid 101.25) at bar flat_bars + 1, then `after` quiet bars."""
    return bar_frame([FLAT] * flat_bars + [middle, BULL_THIRD] + [ABOVE] * after)


def ctx(target=101.25, stop=107.0, target_sources=(fd.STRATEGY, "EMA 50"),
        stop_sources=("Swing High",), tolerance_pct=5.0, **kw):
    """The scenario behind plan(): a bearish trade aimed at the gap's level."""
    return fd.SignalContext(target=target, target_sources=target_sources, stop=stop,
                            stop_sources=stop_sources, tolerance_pct=tolerance_pct, **kw)


def plan(**kw):
    base = dict(source="confluence", strategy=fd.STRATEGY, direction="bearish",
                trigger_price=104.5, stop_loss=107.0, tp1=101.25, quality_score=60)
    base.update(kw)
    return _plan(**base)


def test_gap_features_at_a_known_bar():
    df = gap_frame()
    i = len(df) - 1                                  # 26; the gap formed at bar 21
    atr_i = float(atr(df, 14).iloc[-1])
    out = fd.features(df, i, plan(), ctx())
    assert out["fvg_role"] == "target"
    assert out["gap_age"] == 5
    assert out["gap_open"] is True
    assert out["gap_height_atr"] == pytest.approx(0.5 / atr_i)
    assert out["displacement"] is True
    assert out["stop_atr"] == pytest.approx(2.5 / atr_i)
    assert out["quality"] is None                    # no confluence count was given
    assert out["volatility"] == pytest.approx(atr_i / 104.5)
    assert out["trend_aligned"] is None              # 27 bars: no SMA200
    assert out["earnings_distance"] is None


def test_a_weak_middle_candle_is_not_displacement():
    df = gap_frame(middle=WEAK_BULL)
    assert fd.features(df, len(df) - 1, plan(), ctx())["displacement"] is False


def test_trend_alignment_needs_200_bars_and_follows_direction():
    df = gap_frame(flat_bars=220)
    i = len(df) - 1
    assert fd.trend_aligned(df, i, "bullish") is True     # close 104.5 > SMA200 ~100.1
    assert fd.trend_aligned(df, i, "bearish") is False
    assert fd.trend_aligned(df, 198, "bullish") is None   # 199 bars


def test_no_feature_changes_when_later_bars_are_removed():
    full = bar_frame([FLAT] * 220 + [STRONG_BULL, BULL_THIRD] + [ABOVE] * 5 + [LATER] * 30)
    i = 226
    known = ctx(map_bar=224, earnings_distance=7, confluence_count=3)
    for p in (plan(), plan(direction="bullish", stop_loss=101.2, tp1=112.0)):
        out = fd.features(full, i, p, known)
        assert out == fd.features(full.iloc[:i + 1], i, p, known)
        assert out["fvg_role"] == "target" and out["quality"] is not None


GAPS = [{"mid": 101.25, "direction": "bullish", "bar_index": 21},
        {"mid": 99.0, "direction": "bullish", "bar_index": 9},
        {"mid": 104.0, "direction": "bearish", "bar_index": 30}]
FVG = (fd.STRATEGY,)


def test_match_uses_the_level_fvg_is_a_source_of_target_before_stop():
    both = ctx(target=101.0, target_sources=FVG, stop=99.5, stop_sources=FVG)
    assert fd.match_gap(GAPS, both) == (GAPS[0], "target")
    stop_only = ctx(target=101.0, target_sources=("EMA 50",), stop=99.5, stop_sources=FVG)
    assert fd.match_gap(GAPS, stop_only) == (GAPS[1], "stop")       # 101.25 is nearer the target, but
    #                                                                 FVG is not a source of the target


def test_match_tolerance_is_a_percent_of_the_level_and_inclusive():
    at_edge = ctx(target=100.0, target_sources=FVG, tolerance_pct=1.25)    # 101.25 is 1.25% away
    assert fd.match_gap(GAPS[:1], at_edge) == (GAPS[0], "target")
    just_past = ctx(target=100.0, target_sources=FVG, tolerance_pct=1.24)
    assert fd.match_gap(GAPS[:1], just_past) == (None, "unidentified")


def test_match_unidentified_paths():
    no_source = ctx(target_sources=("EMA 50",), stop_sources=("Swing High",))
    assert fd.match_gap(GAPS, no_source) == (None, "unidentified")
    bearish_only = ctx(target=104.0, target_sources=FVG)
    assert fd.match_gap(GAPS[2:], bearish_only) == (None, "unidentified")   # bearish gap ignored
    assert fd.match_gap([], ctx()) == (None, "unidentified")
    assert fd.match_gap(GAPS, ctx(target=None, target_sources=FVG)) == (None, "unidentified")
    falls_through = ctx(target=150.0, target_sources=FVG, stop=99.0, stop_sources=FVG)
    assert fd.match_gap(GAPS, falls_through) == (GAPS[1], "stop")   # nothing near the target


def test_unidentified_trade_has_no_gap_features_but_keeps_the_plan_features():
    df = gap_frame()
    out = fd.features(df, len(df) - 1, plan(), ctx(target_sources=("EMA 50",)))
    assert out["fvg_role"] == "unidentified"
    assert [out[k] for k in fd.GAP_FEATURES] == [None] * 4
    assert out["stop_atr"] is not None and out["volatility"] is not None


DIP = (104.5, 105.0, 101.2, 104.0)       # trades back into the gap (top 101.5): filled


def test_the_gap_is_looked_up_on_the_map_bar_and_open_is_read_at_the_signal_bar():
    # gap forms at bar 21; the map was built at bar 23; bar 25 fills the gap; signal at bar 27
    df = bar_frame([FLAT] * 20 + [STRONG_BULL, BULL_THIRD, ABOVE, ABOVE, ABOVE, DIP, ABOVE, ABOVE])
    i = len(df) - 1
    stale = fd.features(df, i, plan(), ctx(map_bar=23))
    assert (stale["fvg_role"], stale["gap_open"], stale["gap_age"]) == ("target", False, 6)
    atr_i = float(atr(df, 14).iloc[-1])
    assert stale["gap_height_atr"] == pytest.approx(0.5 / atr_i)     # ATR14 at the SIGNAL bar
    assert stale["displacement"] is True
    fresh = fd.features(df, i, plan(), ctx(map_bar=None))            # a map built at the signal bar
    assert fresh["fvg_role"] == "unidentified" and fresh["gap_open"] is None
    assert fd.features(df, 24, plan(), ctx(map_bar=23))["gap_open"] is True    # before the fill


def test_the_map_bar_is_never_read_past_the_signal_bar():
    df = bar_frame([FLAT] * 20 + [STRONG_BULL, BULL_THIRD, ABOVE, ABOVE])
    late_map = ctx(map_bar=23)
    assert fd.map_gaps(df, 20, late_map) == fd.map_gaps(df.iloc[:21], 20, late_map) == []
    assert fd.features(df, 20, plan(), late_map)["fvg_role"] == "unidentified"


def test_gap_is_open_needs_the_same_bar_and_direction():
    gap = {"bar_index": 21, "direction": "bullish"}
    assert fd.gap_is_open([{"bar_index": 21, "direction": "bullish"}], gap)
    assert not fd.gap_is_open([{"bar_index": 21, "direction": "bearish"}], gap)
    assert not fd.gap_is_open([{"bar_index": 22, "direction": "bullish"}], gap)


def test_the_stop_role():
    df = gap_frame()
    scenario = ctx(target=112.0, target_sources=("EMA 50",), stop=101.2, stop_sources=FVG)
    out = fd.features(df, len(df) - 1,
                      plan(direction="bullish", stop_loss=101.2, tp1=112.0), scenario)
    assert out["fvg_role"] == "stop" and out["gap_age"] == 5


def test_replay_quality_scores_the_causal_inputs_with_the_live_scorer(monkeypatch):
    monkeypatch.setattr(config, "HTF_CONFLUENCE_ENABLED", True)
    df = gap_frame(flat_bars=220)
    i = len(df) - 1
    inputs = fd.quality_inputs(df, i, plan(), 3)
    assert inputs == {"regime": None, "htf_bias": "bullish", "confluence_count": 3,
                      "volume_ratio": 1.0, "atr_pct": atr_percentile(df),
                      "trigger_distance_pct": 0.0, "rs_percentile": None, "breadth": None}
    expected = score_plan(direction="bearish", badge_status="WEAK", **inputs).score
    assert fd.replay_quality(df, i, plan(), 3) == expected
    assert fd.features(df, i, plan(), ctx(confluence_count=3))["quality"] == expected


def test_replay_quality_moves_with_its_inputs_and_is_never_made_up(monkeypatch):
    monkeypatch.setattr(config, "HTF_CONFLUENCE_ENABLED", True)
    df = gap_frame(flat_bars=220)
    i = len(df) - 1
    base = fd.replay_quality(df, i, plan(), 3)
    assert fd.replay_quality(df, i, plan(), None) is None
    assert fd.replay_quality(df, i, plan(), 4) > base > fd.replay_quality(df, i, plan(), 1)
    aligned = plan(direction="bullish", stop_loss=101.2, tp1=112.0)   # with the 50-bar EMA bias
    assert fd.replay_quality(df, i, aligned, 3) > base
    assert fd.replay_quality(df, i, plan(trigger_price=110.0), 3) < base   # 5% from the close


def test_volume_ratio_needs_twenty_bars():
    df = gap_frame()
    assert fd.volume_ratio(df.iloc[:19]) is None
    assert fd.volume_ratio(df) == 1.0
    loud = df.copy()
    loud.iloc[-1, loud.columns.get_loc("Volume")] = 3_000_000.0
    assert fd.volume_ratio(loud) == pytest.approx(3.0 / 1.1)   # 20-bar mean is 1.1M


def test_quality_inputs_and_confluence_count_ignore_later_bars(monkeypatch):
    monkeypatch.setattr(config, "HTF_CONFLUENCE_ENABLED", True)
    full = bar_frame([FLAT] * 220 + [STRONG_BULL, BULL_THIRD] + [ABOVE] * 5 + [LATER] * 30)
    i = 226
    full.loc[full.index[i + 1:], "Volume"] = 9_000_000.0
    cut = full.iloc[:i + 1]
    assert fd.quality_inputs(full, i, plan(), 3) == fd.quality_inputs(cut, i, plan(), 3)
    count = fd.target_confluence_count(full, i, "2w", 101.25, 2.0)
    assert count == fd.target_confluence_count(cut, i, "2w", 101.25, 2.0)
    assert count >= 1                                    # the gap itself is a level there
    assert fd.target_confluence_count(full, i, "2w", None, 2.0) == 0


def test_earnings_distance_uses_the_covered_span():
    assert fd.earnings_distance(10, [5, 20, 40]) == 10
    assert fd.earnings_distance(20, [5, 20, 40]) == 0
    assert fd.earnings_distance(4, [5, 20, 40]) is None      # before the first record
    assert fd.earnings_distance(41, [5, 20, 40]) is None     # after the last
    assert fd.earnings_distance(10, []) is None
    assert fd.earnings_distance(None, [5]) is None
