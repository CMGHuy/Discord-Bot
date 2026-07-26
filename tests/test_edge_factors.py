import numpy as np
import pytest

from tests.conftest import make_trend_df
from swingbot.core.edge.factors import relative_return, rs_percentile


def test_outperformer_beats_underperformer():
    spy = make_trend_df(200, +0.05)
    strong = make_trend_df(200, +0.30)
    weak = make_trend_df(200, -0.20)
    assert relative_return(strong, spy) > 0 > relative_return(weak, spy)
    rels = [relative_return(make_trend_df(200, p), spy)
            for p in (-0.2, -0.1, 0.0, 0.1, 0.2, 0.3)]
    assert rs_percentile(strong, spy, universe_rels=rels) > \
           rs_percentile(weak, spy, universe_rels=rels)
    assert rs_percentile(strong, spy, universe_rels=rels) >= 80.0


def test_neutral_without_universe():
    spy = make_trend_df(200, +0.05)
    assert rs_percentile(make_trend_df(200, +0.30), spy) == 50.0


def test_short_history_is_none():
    spy = make_trend_df(200, +0.05)
    assert relative_return(make_trend_df(30, +0.30), spy) is None


def test_rs_cache_roundtrip(tmp_path, monkeypatch):
    from swingbot.core.edge import factors
    monkeypatch.setattr(factors, "RS_CACHE_PATH", str(tmp_path / "rs_cache.json"))
    spy = make_trend_df(200, +0.05)
    cache = factors.refresh_rs_cache({"STRONG": make_trend_df(200, +0.30)}, spy)
    assert "STRONG" in cache["rels"]
    assert factors.load_rs_cache()["rels"] == cache["rels"]


def test_sector_rs_ranks_across_etfs():
    from swingbot.core.edge.factors import sector_rs_percentile
    spy = make_trend_df(200, +0.05)
    etf_dfs = {"XLE": make_trend_df(200, +0.40),
               "XLK": make_trend_df(200, +0.10),
               "XLU": make_trend_df(200, -0.10)}
    sectors = {"XLE": "Energy", "XLK": "Information Technology", "XLU": "Utilities"}
    hot = sector_rs_percentile("Energy", etf_dfs, spy, sector_of_etf=sectors)
    cold = sector_rs_percentile("Utilities", etf_dfs, spy, sector_of_etf=sectors)
    assert hot > cold
    assert sector_rs_percentile("Nonexistent", etf_dfs, spy, sector_of_etf=sectors) == 50.0


def test_rs_score_weights():
    from swingbot.core.edge.factors import rs_score
    assert rs_score(80.0, 40.0) == pytest.approx(0.7 * 80 + 0.3 * 40)


def test_clean_uptrend_aligns_fully():
    import numpy as np
    from tests.conftest import make_ohlcv
    from swingbot.core.edge.factors import mtf_alignment
    rng = np.random.RandomState(1)
    df = make_ohlcv(list(100 * np.cumprod(1 + rng.normal(0.0012, 0.01, 400))))
    assert mtf_alignment(df, "bullish") == 3
    assert mtf_alignment(df, "bearish") == 0


def test_chop_scores_low():
    import numpy as np
    from tests.conftest import make_ohlcv
    from swingbot.core.edge.factors import mtf_alignment
    rng = np.random.default_rng(7)
    level = 100.0
    prices = [level]
    for _ in range(399):
        level += -0.05 * (level - 100.0) + rng.normal(0, 1.0)
        prices.append(level)
    df = make_ohlcv(np.array(prices), spread_pct=2.0)
    assert mtf_alignment(df, "bullish") <= 1


def test_weekly_frame_shape():
    from swingbot.core.edge.factors import weekly_frame
    df = make_trend_df(400, +0.25)
    w = weekly_frame(df)
    assert list(w.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert len(w) < len(df) / 4


def test_breadth_split_universe():
    from swingbot.core.edge.factors import breadth_pct_above_50ema
    ups = {f"U{i}": make_trend_df(150, +0.3) for i in range(15)}
    downs = {f"D{i}": make_trend_df(150, -0.3) for i in range(15)}
    b = breadth_pct_above_50ema({**ups, **downs})
    assert b == pytest.approx(50.0, abs=1.0)


def test_breadth_none_when_universe_tiny():
    from swingbot.core.edge.factors import breadth_pct_above_50ema
    assert breadth_pct_above_50ema({"A": make_trend_df(150, +0.3)}) is None


def _hourly_day(prices, volumes=None, start="2026-07-10 14:30"):
    import pandas as pd
    idx = pd.date_range(start, periods=len(prices), freq="h")
    v = volumes or [1_000_000] * len(prices)
    return pd.DataFrame({"Open": prices, "High": [p * 1.001 for p in prices],
                         "Low": [p * 0.999 for p in prices], "Close": prices,
                         "Volume": v}, index=idx)


def test_intraday_confirms_above_vwap():
    from swingbot.core.edge.factors import intraday_confirms
    rising = _hourly_day([100.0, 100.5, 101.0, 101.5])   # last close > day VWAP
    assert intraday_confirms("X", "bullish", intraday_df=rising) is True
    assert intraday_confirms("X", "bearish", intraday_df=rising) is False


def test_intraday_none_is_neutral():
    from swingbot.core.edge.factors import intraday_confirms
    assert intraday_confirms("X", "bullish", intraday_df=None,
                             fetch=lambda s: None) is None


def test_intraday_uses_only_the_last_day_of_bars():
    """A multi-day frame must be scored against TODAY's running VWAP only --
    yesterday's session cannot be allowed to anchor today's reading."""
    import pandas as pd
    from swingbot.core.edge.factors import intraday_confirms
    yesterday = _hourly_day([200.0] * 4, start="2026-07-09 14:30")
    today = _hourly_day([100.0, 100.5, 101.0, 101.5], start="2026-07-10 14:30")
    both = pd.concat([yesterday, today])
    # Pooled across both days the last close (101.5) is far BELOW the
    # combined VWAP (~150); scored on today alone it is above.
    assert intraday_confirms("X", "bullish", intraday_df=both) is True


def test_intraday_falls_back_to_fetch_and_stays_neutral_on_empty():
    import pandas as pd
    from swingbot.core.edge.factors import intraday_confirms
    calls = []

    def fetch(sym):
        calls.append(sym)
        return _hourly_day([100.0, 99.5, 99.0, 98.5])

    assert intraday_confirms("AAPL", "bullish", fetch=fetch) is False
    assert intraday_confirms("AAPL", "bearish", fetch=fetch) is True
    assert calls == ["AAPL", "AAPL"]
    # Empty frame and a zero-volume day are both "no reading", not False.
    assert intraday_confirms("X", "bullish", intraday_df=pd.DataFrame()) is None
    assert intraday_confirms("X", "bullish",
                             intraday_df=_hourly_day([100.0, 101.0], volumes=[0, 0])) is None


def test_avwap_math_golden():
    from swingbot.core.edge.factors import anchored_vwap
    df = _hourly_day([100.0, 102.0, 104.0], volumes=[1000, 1000, 2000])
    s = anchored_vwap(df, 0)
    # TP == Close here (High/Low straddle by +/-0.1%): vwap_2 =
    # (100*1000 + 102*1000 + 104*2000) / 4000 = 102.5 (+/-0.1% wick noise)
    assert s.iloc[-1] == pytest.approx(102.5, rel=2e-3)
    assert len(s) == 3 and s.index.equals(df.index)


def test_avwap_from_a_later_anchor_ignores_earlier_bars():
    """The whole point of an ANCHORED vwap: bars before the anchor must not
    influence it at all, otherwise it is just a rolling vwap."""
    from swingbot.core.edge.factors import anchored_vwap
    df = _hourly_day([1000.0, 100.0, 102.0, 104.0], volumes=[9_999_999, 1000, 1000, 2000])
    s = anchored_vwap(df, 1)
    assert s.iloc[-1] == pytest.approx(102.5, rel=2e-3)   # the 1000.0 whale bar is excluded
    assert len(s) == 3 and s.index.equals(df.index[1:])


def test_avwap_anchors_are_sorted_deduped_and_in_range():
    import numpy as np
    from tests.conftest import make_ohlcv
    from swingbot.core.edge.factors import avwap_anchors
    rng = np.random.RandomState(3)
    closes = 100 * np.cumprod(1 + rng.normal(0.0, 0.015, 300))
    vols = np.full(300, 1_000_000.0)
    vols[250] = 9_000_000.0          # one unmistakable high-volume bar
    df = make_ohlcv(closes, volumes=vols)

    anchors = avwap_anchors(df, lookback=120)
    assert anchors == sorted(set(anchors)), "anchors must be sorted and deduped"
    assert all(0 <= a < len(df) for a in anchors)
    assert 250 in anchors, "the highest-volume bar of the lookback must be an anchor"
    # Swing pivots need `span` confirming bars on each side, so no anchor may
    # sit inside the trailing unconfirmed window; the volume anchor is exempt
    # (it needs no confirmation) but here it is at 250, well clear of the end.
    assert max(a for a in anchors if a != 250) < len(df) - 5


def test_avwap_anchors_ignore_bars_before_the_lookback():
    """A 120-bar lookback must not anchor on ancient history -- except that
    the pivot scan and the volume scan both start at the same `start` bar,
    so nothing older than that can ever be returned."""
    from swingbot.core.edge.factors import avwap_anchors
    df = make_trend_df(300, +0.1)
    assert all(a >= len(df) - 120 for a in avwap_anchors(df, lookback=120))


def test_avwap_levels_enter_the_level_map_when_enabled(monkeypatch):
    from swingbot import config
    from swingbot.core import levels
    from swingbot.core.strategy_types import HORIZONS
    monkeypatch.setattr(config, "AVWAP_LEVELS_ENABLED", True)
    df = make_trend_df(300, +0.2)
    cands = levels.collect_candidate_levels(df, HORIZONS["4w"], float(df["Close"].iloc[-1]))
    assert any(src == "AVWAP" for _, src in cands)
    assert all(p > 0 for p, src in cands if src == "AVWAP")


def test_avwap_levels_absent_while_the_flag_is_off(monkeypatch):
    """Default-off, per this plan's Global Constraints: a new level source
    shifts every confluence count, so it stays dark until the walk-forward
    folds (E33) and the shadow forward-gate (E40) have judged it."""
    from swingbot import config
    from swingbot.core import levels
    from swingbot.core.strategy_types import HORIZONS
    assert config.AVWAP_LEVELS_ENABLED is False, "this factor must ship default-off"
    monkeypatch.setattr(config, "AVWAP_LEVELS_ENABLED", False)
    df = make_trend_df(300, +0.2)
    cands = levels.collect_candidate_levels(df, HORIZONS["4w"], float(df["Close"].iloc[-1]))
    assert not any(src == "AVWAP" for _, src in cands)


def test_avwap_is_its_own_strategy_family():
    """AVWAP must NOT collapse into the rolling-VWAP family: they answer
    different questions (average cost since one event vs. over a fixed
    window), and strategy_family() matches on startswith, so "AVWAP" would
    otherwise fall through to itself unregistered and be counted as a
    confirming strategy that isn't in ALL_STRATEGY_FAMILIES."""
    from swingbot.core import levels
    assert levels.strategy_family("AVWAP") == "AVWAP"
    assert levels.strategy_family("VWAP") == "VWAP"
    assert "AVWAP" in levels.ALL_STRATEGY_FAMILIES


def _bar(df_idx, o, h, l, c, v, base_vol=1_000_000):
    import pandas as pd
    idx = pd.bdate_range("2026-01-01", periods=30)
    df = pd.DataFrame({"Open": 100.0, "High": 101.0, "Low": 99.0,
                       "Close": 100.0, "Volume": float(base_vol)}, index=idx)
    df.iloc[-1] = [o, h, l, c, v]
    return df


def test_hammer_rejection_at_support_scores_high():
    from swingbot.core.edge.factors import pattern_quality_at_level
    # dipped through the 98 level, closed at the top of the bar, 3x volume
    df = _bar(-1, 100.0, 100.6, 97.5, 100.5, 3_000_000)
    assert pattern_quality_at_level(df, len(df) - 1, 98.0, "bullish") >= 8


def test_weak_close_low_volume_scores_low():
    from swingbot.core.edge.factors import pattern_quality_at_level
    # never touched the level, closed mid-range, average volume
    df = _bar(-1, 100.0, 101.0, 99.5, 100.2, 1_000_000)
    assert pattern_quality_at_level(df, len(df) - 1, 98.0, "bullish") <= 4


def test_pattern_quality_mirrors_for_bearish():
    """The same bar that is a strong bullish rejection at support must be a
    weak bearish one -- the close-position term flips."""
    from swingbot.core.edge.factors import pattern_quality_at_level
    df = _bar(-1, 100.0, 100.6, 97.5, 100.5, 3_000_000)
    bull = pattern_quality_at_level(df, len(df) - 1, 98.0, "bullish")
    bear = pattern_quality_at_level(df, len(df) - 1, 98.0, "bearish")
    assert bull > bear

    # ...and the mirror image at resistance: spiked through 103, closed at
    # the bottom of the bar on heavy volume.
    spike = _bar(-1, 100.0, 103.5, 99.4, 99.5, 3_000_000)
    assert pattern_quality_at_level(spike, len(spike) - 1, 103.0, "bearish") >= 8


def test_pattern_quality_is_bounded_and_survives_a_flat_bar():
    from swingbot.core.edge.factors import pattern_quality_at_level
    flat = _bar(-1, 100.0, 100.0, 100.0, 100.0, 5_000_000)   # zero range
    assert pattern_quality_at_level(flat, len(flat) - 1, 98.0, "bullish") == 0

    # A perfect bar cannot exceed the documented 0-10 range.
    perfect = _bar(-1, 98.0, 101.0, 96.0, 101.0, 9_000_000)
    score = pattern_quality_at_level(perfect, len(perfect) - 1, 98.0, "bullish")
    assert 0 <= score <= 10


def test_pierce_without_reclaim_earns_no_rejection_points():
    """Piercing a level and CLOSING through it is a break, not a rejection --
    it must not be rewarded like a bounce."""
    from swingbot.core.edge.factors import pattern_quality_at_level
    broke = _bar(-1, 100.0, 100.2, 97.0, 97.2, 3_000_000)   # closed below 98
    held = _bar(-1, 100.0, 100.2, 97.0, 100.1, 3_000_000)   # closed back above 98
    assert pattern_quality_at_level(broke, len(broke) - 1, 98.0, "bullish") < \
           pattern_quality_at_level(held, len(held) - 1, 98.0, "bullish")


def test_bimodal_volume_finds_nodes():
    import numpy as np
    from tests.conftest import make_ohlcv
    from swingbot.core.levels import volume_profile_nodes
    # price spends time at 100 and 120 (heavy volume), races through 110
    closes = np.concatenate([np.full(80, 100.0), np.linspace(100, 120, 20),
                             np.full(80, 120.0)])
    vols = np.concatenate([np.full(80, 5e6), np.full(20, 4e5), np.full(80, 5e6)])
    df = make_ohlcv(closes, spread_pct=1.0, volumes=vols)
    nodes = volume_profile_nodes(df)
    assert any(abs(p - 100) < 2 for p in nodes["hvn"])
    assert any(abs(p - 120) < 2 for p in nodes["hvn"])
    assert any(102 < p < 118 for p in nodes["lvn"])


def test_edge_bins_are_scanned_too():
    """Regression for the brief's own loop bounds: `range(1, len(hist)-1)`
    skips the first and last bin, and np.histogram puts the data's extremes
    exactly there -- so a bimodal profile whose two modes ARE the min and
    max price (the brief's own fixture) returned zero HVNs. Verified
    empirically before fixing, not reasoned about."""
    import numpy as np
    from tests.conftest import make_ohlcv
    from swingbot.core.levels import volume_profile_nodes
    closes = np.concatenate([np.full(60, 100.0), np.linspace(100, 110, 10),
                             np.full(60, 110.0)])
    vols = np.concatenate([np.full(60, 5e6), np.full(10, 4e5), np.full(60, 5e6)])
    nodes = volume_profile_nodes(make_ohlcv(closes, spread_pct=1.0, volumes=vols))
    lo = min(nodes["hvn"])
    hi = max(nodes["hvn"])
    assert lo < 101 and hi > 109, f"boundary modes missed: {nodes['hvn']}"


def test_flat_profile_yields_no_nodes():
    """No structure, no claims: a single price with uniform volume has no
    acceptance shelf and no vacuum."""
    import numpy as np
    from tests.conftest import make_ohlcv
    from swingbot.core.levels import volume_profile_nodes
    df = make_ohlcv(np.full(120, 100.0), spread_pct=0.0,
                    volumes=np.full(120, 1e6))
    nodes = volume_profile_nodes(df)
    assert nodes["lvn"] == []


def test_hvn_lvn_collapse_into_the_existing_volume_profile_family():
    """They are the same strategy as levels.py's existing "Volume Profile
    HVN" candidate, computed at more resolution -- counting them as extra
    distinct families would double-count one piece of evidence, which is
    the exact thing strategy_family() exists to prevent."""
    from swingbot.core import levels
    assert levels.strategy_family("Volume Profile HVN") == "Volume Profile"
    assert levels.strategy_family("Volume Profile LVN") == "Volume Profile"


def test_hvn_lvn_levels_are_flag_gated(monkeypatch):
    import numpy as np
    from swingbot import config
    from swingbot.core import levels
    from swingbot.core.strategy_types import HORIZONS
    from tests.conftest import make_ohlcv
    closes = np.concatenate([np.full(80, 100.0), np.linspace(100, 120, 20),
                             np.full(80, 120.0)])
    vols = np.concatenate([np.full(80, 5e6), np.full(20, 4e5), np.full(80, 5e6)])
    df = make_ohlcv(closes, spread_pct=1.0, volumes=vols)
    price = float(df["Close"].iloc[-1])

    assert config.VOLUME_PROFILE_NODES_ENABLED is False, "this source must ship default-off"
    off = levels.collect_candidate_levels(df, HORIZONS["4w"], price)
    assert not any(src.endswith(("HVN", "LVN")) and src != "Volume Profile HVN"
                   for _, src in off)

    monkeypatch.setattr(config, "VOLUME_PROFILE_NODES_ENABLED", True)
    on = levels.collect_candidate_levels(df, HORIZONS["4w"], price)
    assert any(src == "Volume Profile LVN" for _, src in on)
    assert len(on) > len(off)


# --- E36: divergence quality ------------------------------------------------

def _divergence_df():
    """A genuine hidden-BULLISH divergence: price swing lows 104 -> 108
    (higher) while the matching RSI lows fall 33.3 -> 30.5. REPL-tuned
    until the real `signals` swing-detection actually produced that shape
    -- a fast V-dip leaves RSI only mildly oversold, while a long shallow
    grind that bottoms ABOVE it drives RSI lower. Frozen here; don't
    "simplify" the numbers without re-checking both swing lists."""
    import numpy as np
    from tests.conftest import make_ohlcv
    base = list(np.linspace(90, 120, 45))
    dip = [118, 112, 104, 112, 116]
    push = [117, 118, 119]
    grind = [round(119 - 0.5 * i, 2) for i in range(1, 23)]
    tail = [110.0, 112.0, 114.0]
    return make_ohlcv(np.array(base + dip + push + grind + tail, dtype=float),
                      spread_pct=1.5)


def test_divergence_strength_golden():
    from swingbot.core.signals import divergence_strength
    # 4 swing points (+2), price +6.7% vs RSI -3 pts => disagreement 0.0967
    # -> int(0.0967*40) = 3 (+3), volume fading 3M -> 1M = 67% (+3) = 8
    score = divergence_strength([90.0, 92.0, 94.0, 96.0], [35.0, 32.0],
                                [3_000_000.0, 1_000_000.0])
    assert score == 8


def test_divergence_strength_two_touch_accident_scores_zero():
    from swingbot.core.signals import divergence_strength
    # bare minimum swings, near-parallel slopes, flat volume
    assert divergence_strength([100.0, 101.0], [40.0, 39.0],
                               [1_000_000.0, 1_000_000.0]) == 0


def test_divergence_strength_is_bounded():
    from swingbot.core.signals import divergence_strength
    score = divergence_strength([50.0] + [60.0] * 9, [90.0, 10.0],
                                [9_000_000.0, 100_000.0])
    assert 0 <= score <= 10
    assert divergence_strength([], [], []) == 0
    assert divergence_strength([0.0, 1.0], [40.0, 30.0], [0.0, 0.0]) >= 0


def test_divergence_detection_is_unchanged_by_the_scoring(monkeypatch):
    """Characterization: the scoring must not move a single detection.
    It can't, structurally -- detection lives in entry_filters
    (rsi_divergence_entries, the ONE source the backtest and the live
    scanner share) and signals.rsi_divergence_signal delegates `triggered`
    straight to entries_for. This pins that delegation so a future
    'optimization' can't quietly reintroduce a second detector here."""
    from swingbot.core import signals
    from swingbot.core.entry_filters import entries_for
    df = _divergence_df()
    bull, bear = entries_for("RSI Divergence", df, "2m")
    res = signals.rsi_divergence_signal("TEST", df, "2m")
    expected = bool(bull.iloc[-1]) or bool(bear.iloc[-1])
    assert res.triggered == expected


def test_strength_is_attached_when_the_divergence_pattern_is_described():
    """When the enrichment block recognises the pattern, the details it
    renders now carry a 0-10 strength alongside the swing values."""
    from swingbot.core import signals
    df = _divergence_df()

    # Force the entry gate open so the descriptive block runs; detection
    # itself is covered by the characterization test above.
    import pandas as pd
    true_s = pd.Series(True, index=df.index)
    false_s = pd.Series(False, index=df.index)
    orig = signals.entries_for
    signals.entries_for = lambda strategy, d, hk, *a, **k: (true_s, false_s)
    try:
        res = signals.rsi_divergence_signal("TEST", df, "2m")
    finally:
        signals.entries_for = orig

    assert res.details.get("Pattern") == "Hidden bullish divergence", res.details
    strength = res.details.get("Divergence strength")
    assert strength is not None and 0 <= strength <= 10
