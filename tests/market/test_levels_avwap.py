from swingbot import config
from swingbot.core.market.levels import build_level_map
from swingbot.core.market.strategy_types import HORIZONS
from tests.helpers import make_ohlcv


def _build_level_map(df):
    """Thin wrapper over levels.build_level_map that supplies a horizon
    dict and current price, and flattens the (supports, resistances) pair
    into one list -- this test only cares which raw source labels show up
    somewhere in the map, not which side of price they land on."""
    h = HORIZONS["4w"]
    current_price = float(df["Close"].iloc[-1])
    supports, resistances = build_level_map(df, h, current_price)
    return supports + resistances


def _frame_with_clear_52w_high():
    """~260 daily bars with one unambiguous spike well inside the 52-week
    (252-bar) window: a steady climb, a sharp one-bar spike to a peak no
    other bar approaches, then a pullback into the close. That spike is
    unmistakably both the 52-week high AND a volume-spike/swing-pivot
    anchor, so avwap_anchors(df) has real anchors to find."""
    closes = [100 + i * 0.3 for i in range(200)]        # steady climb to ~160
    closes += [200 - i * 1.5 for i in range(1, 21)]      # spike to 200, sharp pullback
    closes += [170 + i * 0.1 for i in range(40)]         # drift into the close
    return make_ohlcv(closes)


def test_avwap_sources_name_their_anchor(monkeypatch):
    monkeypatch.setattr(config, "AVWAP_LEVELS_ENABLED", True)
    levels_ = _build_level_map(_frame_with_clear_52w_high())
    labels = {s for lv in levels_ for s in lv.sources}
    assert any(l.startswith("Anchored VWAP (") for l in labels)


def test_avwap_family_still_counts_once_for_confluence():
    """Per-anchor labels must NOT multiply the method count. Display detail
    and confluence weight are deliberately different things."""
    from swingbot.core.scanning.confidence import _resolve_confluence
    count, families = _resolve_confluence(
        None, ["Anchored VWAP (52w high)", "Anchored VWAP (swing low)", "EMA"])
    assert count == 2
    assert families == ["AVWAP", "EMA"]


def test_avwap_family_folds_in_explain_fallback_path():
    """explain.build_explanation's own fallback (used when no explicit
    (count, families) confluence tuple is passed in) has its own dedup,
    separate from confidence._resolve_confluence and levels.strategy_family
    -- verify it folds multiple per-anchor AVWAP labels to one family too,
    same shape as test_avwap_family_still_counts_once_for_confluence above."""
    from types import SimpleNamespace

    from swingbot.core.market.explain import build_explanation

    scenario = SimpleNamespace(
        direction="bullish",
        take_profit=100.0, target_distance_pct=5.0,
        stop_loss=95.0, stop_distance_pct=5.0,
        target2_price=None, target2_distance_pct=None,
        target_sources=["Anchored VWAP (52w high)", "Anchored VWAP (swing low)", "EMA"],
        stop_sources=["Anchored VWAP (swing low)"],
    )
    result = SimpleNamespace(ticker="TEST", horizon_label="4W", scenario=scenario)
    text = build_explanation(result)
    assert "2 methods" in text
    assert "anchored VWAP" in text


def test_avwap_disabled_produces_no_avwap_levels(monkeypatch):
    monkeypatch.setattr(config, "AVWAP_LEVELS_ENABLED", False)
    levels_ = _build_level_map(_frame_with_clear_52w_high())
    # NOTE: a bare substring check on "VWAP" would also match the always-on
    # rolling VWAP source (collect_candidate_levels emits "VWAP"
    # unconditionally, independent of this flag) and could never pass. The
    # anchored-VWAP-specific "Anchored VWAP (" prefix is what this flag
    # actually gates.
    assert not any(s.startswith("Anchored VWAP (") for lv in levels_ for s in lv.sources)
