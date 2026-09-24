"""v101 Phase A: Fibonacci mechanism diagnostic (TRAIN only)."""
import sys
from pathlib import Path
from types import SimpleNamespace as T

import numpy as np
import pytest

from swingbot import config
from tests.helpers import make_ohlcv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))


def _mfd():
    import measure_fib_diagnostic as mfd
    return mfd


def test_fib_level_bull_measures_down_from_the_high():
    mfd = _mfd()
    assert mfd.fib_level(110.0, 100.0, 0.5, "bullish") == pytest.approx(105.0)
    assert mfd.fib_level(110.0, 100.0, 0.382, "bullish") == pytest.approx(106.18)


def test_fib_level_bear_measures_up_from_the_low():
    mfd = _mfd()
    assert mfd.fib_level(110.0, 100.0, 0.382, "bearish") == pytest.approx(103.82)


def test_tested_ratio_is_the_nearest_entry_ratio():
    mfd = _mfd()
    # bullish levels: 0.382 -> 106.18, 0.5 -> 105.0, 0.618 -> 103.82
    assert mfd.tested_ratio(104.0, 110.0, 100.0, "bullish") == 0.618
    assert mfd.tested_ratio(106.0, 110.0, 100.0, "bullish") == 0.382


def test_structural_stop_sits_one_buffer_beyond_the_swing_extreme():
    mfd = _mfd()
    buf = mfd.STRUCTURE_BUFFER_ATR * 2.0
    assert mfd.structural_stop(110.0, 100.0, 2.0, "bullish") == pytest.approx(100.0 - buf)
    assert mfd.structural_stop(110.0, 100.0, 2.0, "bearish") == pytest.approx(110.0 + buf)


def test_deeper_ratio_stop_uses_the_next_ratio_on_the_ladder():
    mfd = _mfd()
    buf = mfd.STRUCTURE_BUFFER_ATR * 2.0
    # close 104 tests 0.618 -> deeper is 0.786 -> level 110 - 7.86 = 102.14
    assert mfd.deeper_ratio_stop(104.0, 110.0, 100.0, 2.0, "bullish") == pytest.approx(102.14 - buf)
    # bearish close 106.2 tests 0.618 (100 + 6.18) -> deeper 0.786 -> 107.86
    assert mfd.deeper_ratio_stop(106.2, 110.0, 100.0, 2.0, "bearish") == pytest.approx(107.86 + buf)


def test_apply_cap_pulls_a_too_wide_stop_in_and_flags_it():
    mfd = _mfd()
    assert mfd.apply_cap(100.0, 90.0, "bullish", 5.0) == (pytest.approx(95.0), True)
    assert mfd.apply_cap(100.0, 97.0, "bullish", 5.0) == (pytest.approx(97.0), False)
    assert mfd.apply_cap(100.0, 110.0, "bearish", 5.0) == (pytest.approx(105.0), True)


def test_cap_distance_matches_the_builder_arithmetic():
    mfd = _mfd()
    pct = mfd.capped_planned_loss_pct(mfd.HORIZONS["4w"]["max_risk_pct"])
    assert mfd.cap_distance(200.0, "4w") == pytest.approx(200.0 * pct / 100)


def test_first_touch_checks_the_stop_before_the_target_on_the_same_bar():
    mfd = _mfd()
    high, low, close = np.array([100, 112.0]), np.array([100, 94.0]), np.array([100, 100.0])
    assert mfd.simulate_first_touch(high, low, close, 0, 100.0, 95.0, 110.0, "bullish", 5) == ("loss", -1.0)


def test_first_touch_win_pays_the_planned_r():
    mfd = _mfd()
    high, low, close = np.array([100, 101, 111.0]), np.array([100, 99, 100.0]), np.array([100, 100, 110.0])
    assert mfd.simulate_first_touch(high, low, close, 0, 100.0, 95.0, 110.0, "bullish", 5) == ("win", pytest.approx(2.0))


def test_first_touch_bearish_win():
    mfd = _mfd()
    high, low, close = np.array([100, 101, 100.0]), np.array([100, 99, 89.0]), np.array([100, 100, 90.0])
    assert mfd.simulate_first_touch(high, low, close, 0, 100.0, 105.0, 90.0, "bearish", 5) == ("win", pytest.approx(2.0))


def test_first_touch_timeout_marks_to_the_last_close_in_the_hold():
    mfd = _mfd()
    high, low, close = np.array([100, 101, 103, 150.0]), np.array([100, 99, 99, 99.0]), np.array([100, 100, 102, 150.0])
    assert mfd.simulate_first_touch(high, low, close, 0, 100.0, 95.0, 110.0, "bullish", 2) == ("timeout", pytest.approx(0.4))


def test_first_touch_is_open_when_no_forward_bar_exists():
    mfd = _mfd()
    a = np.array([100.0])
    assert mfd.simulate_first_touch(a, a, a, 0, 100.0, 95.0, 110.0, "bullish", 5) == ("open", None)


def test_reclaim_bar_is_the_first_close_beyond_the_signal_bar_extreme():
    mfd = _mfd()
    high = np.array([101, 100, 100, 100.0])
    low = np.array([99, 98, 98, 98.0])
    close = np.array([100, 99, 101.5, 102.0])
    assert mfd.reclaim_bar(high, low, close, 0, "bullish") == 2
    assert mfd.reclaim_bar(high, low, close, 0, "bearish") is None
    assert mfd.reclaim_bar(high, low, close, 0, "bullish", window=1) is None


def _impulse_frame():
    # 30-bar up impulse, then a 15-bar pullback, then a flat tail.
    closes = [100 + k for k in range(30)] + [129 - 0.8 * k for k in range(1, 16)] + [117.0] * 25
    return make_ohlcv(closes, start="2021-01-04")


def _trade(frame, i, direction, stop, target):
    entry = float(frame["Close"].iloc[i])
    return T(entry_date=str(frame.index[i].date()), direction=direction, entry=entry,
             stop_loss=stop, take_profit=target, outcome="win", r_multiple=1.0)


def test_trade_features_flags_capped_only_when_the_cap_binds():
    mfd = _mfd()
    frame, i = _impulse_frame(), 44
    entry = float(frame["Close"].iloc[i])
    hi, lo = float(frame["High"].iloc[i - 42:i + 1].max()), float(frame["Low"].iloc[i - 42:i + 1].min())
    trade = _trade(frame, i, "bullish", entry * 0.9, entry * 1.2)
    wide = mfd.trade_features(frame, i, "4w", trade, 1.0, hi, lo, 1e9, 1.5, 2.5, False)
    tight = mfd.trade_features(frame, i, "4w", trade, 1.0, hi, lo, 0.01, 1.5, 2.5, False)
    assert wide["capped"] is False and tight["capped"] is True
    assert set(wide) == {"capped", "stop_mismatch", "lifecycle_adjusted", "over_hard_cap",
                         "tested_ratio", "stop_atr", "base_simple", "deeper", "reclaim"}
    assert wide["tested_ratio"] in mfd.ENTRY_RATIOS


def test_trade_features_never_reads_past_the_signal_bar_for_geometry():
    mfd = _mfd()
    frame, i = _impulse_frame(), 44
    entry = float(frame["Close"].iloc[i])
    hi, lo = float(frame["High"].iloc[i - 42:i + 1].max()), float(frame["Low"].iloc[i - 42:i + 1].min())
    trade = _trade(frame, i, "bullish", entry * 0.9, entry * 1.2)
    base = mfd.trade_features(frame, i, "4w", trade, 1.0, hi, lo, 1e9, 1.5, 2.5, False)
    poisoned = frame.copy()
    poisoned.iloc[i + 1:, :4] = poisoned.iloc[i + 1:, :4] * 3   # future bars only
    again = mfd.trade_features(poisoned, i, "4w", trade, 1.0, hi, lo, 1e9, 1.5, 2.5, False)
    # Geometry (cap flag, tested ratio, stop distance) must not see the future.
    assert (again["capped"], again["tested_ratio"], again["stop_atr"]) == \
           (base["capped"], base["tested_ratio"], base["stop_atr"])


def test_lifecycle_disabled_flags_are_false_and_arms_match_pre_lifecycle_geometry(monkeypatch):
    """With LEVEL_LIFECYCLE_STOPS_ENABLED off, apply_level_lifecycle is a
    no-op (lifecycle.py), so a trade carrying the pre-lifecycle capped stop
    must show lifecycle_adjusted=False, over_hard_cap=False (the pre-lifecycle
    cap is itself hard-cap-safe), and the #2 arm must equal the geometry
    computed with no lifecycle step at all."""
    mfd = _mfd()
    monkeypatch.setattr(config, "LEVEL_LIFECYCLE_STOPS_ENABLED", False)
    frame, i = _impulse_frame(), 44
    entry = float(frame["Close"].iloc[i])
    hi, lo = float(frame["High"].iloc[i - 42:i + 1].max()), float(frame["Low"].iloc[i - 42:i + 1].min())
    cap = mfd.cap_distance(entry, "4w")
    struct = mfd.structural_stop(hi, lo, 1.0, "bullish")
    expected_stop, _ = mfd.apply_cap(entry, struct, "bullish", cap)
    trade = _trade(frame, i, "bullish", expected_stop, entry * 1.2)

    features = mfd.trade_features(frame, i, "4w", trade, 1.0, hi, lo, cap, 1.5, 2.5, False)
    assert features["lifecycle_adjusted"] is False
    assert features["over_hard_cap"] is False

    h = mfd.HORIZONS["4w"]
    close = frame["Close"].values
    deep_stop, _ = mfd.apply_cap(entry, mfd.deeper_ratio_stop(close[i], hi, lo, 1.0, "bullish"), "bullish", cap)
    deep_target = mfd.select_structural_target(
        entry, deep_stop, True, mfd.fib_target_candidates(frame, i, h, entry), 1.5, 2.5)
    expected_deeper = mfd.simulate_first_touch(
        frame["High"].values, frame["Low"].values, close, i, entry, deep_stop, deep_target,
        "bullish", h["max_holding_days"])
    assert features["deeper"] == expected_deeper


def test_features_for_stop_mismatch_is_false_when_trade_carries_trade_plan_ats_own_stop():
    """The new stop_mismatch definition compares against _trade_plan_at's own
    (stop, target) -- the full production pipeline including
    apply_level_lifecycle -- not the pre-lifecycle structural_stop/apply_cap
    geometry."""
    mfd = _mfd()
    frame, horizon, i = _impulse_frame(), "4w", 44
    atr_s, sh_s, sl_s, _, _ = mfd._plan_series(frame, mfd.STRATEGY, horizon)
    plan_at = mfd._trade_plan_at(frame, i, "bullish", mfd.STRATEGY, horizon, atr_s, sh_s, sl_s)
    assert plan_at is not None
    entry, stop, target = plan_at
    trade = T(entry_date=str(frame.index[i].date()), direction="bullish", entry=entry,
              stop_loss=stop, take_profit=target, outcome="win", r_multiple=1.0)
    params = mfd.ScanParams.from_config()
    rr = (params.min_risk_reward_ratio, params.max_risk_reward_ratio)
    features = mfd._features_for(frame, horizon, trade, (atr_s, sh_s, sl_s), rr)
    assert features["stop_mismatch"] is False


def test_lifecycle_arm_simulates_with_the_widened_stop_and_target(monkeypatch):
    """apply_level_lifecycle's enabled, widening branch: _lifecycle_arm must
    return exactly the (stop, tp1) it hands back, not the pre-widening pair
    it was called with."""
    mfd = _mfd()

    def fake_apply_level_lifecycle(df, index, *, entry, stop, tp1, atr_val, direction,
                                   strategy, horizon_key, level_map=None, candidate_levels=None):
        return stop - 1.0, tp1 + 2.0, {"lifecycle_stop": {"price": stop - 1.0}}

    monkeypatch.setattr(mfd, "apply_level_lifecycle", fake_apply_level_lifecycle)
    frame = _impulse_frame()
    result = mfd._lifecycle_arm(frame, 44, 117.0, 110.0, 130.0, 1.0, "bullish", "4w", [])
    assert result == (109.0, 132.0)


def test_lifecycle_arm_passes_through_when_lifecycle_leaves_the_pair_unchanged(monkeypatch):
    """When apply_level_lifecycle finds no tested anchor to widen onto (or
    the flag is off), it hands back the same (stop, tp1) it was given --
    _lifecycle_arm must not alter that pass-through pair."""
    mfd = _mfd()

    def fake_apply_level_lifecycle(df, index, *, entry, stop, tp1, atr_val, direction,
                                   strategy, horizon_key, level_map=None, candidate_levels=None):
        return stop, tp1, {}

    monkeypatch.setattr(mfd, "apply_level_lifecycle", fake_apply_level_lifecycle)
    frame = _impulse_frame()
    result = mfd._lifecycle_arm(frame, 44, 117.0, 110.0, 130.0, 1.0, "bullish", "4w", [])
    assert result == (110.0, 130.0)


def test_simple_stats_counts_decided_and_drops_non_trades():
    mfd = _mfd()
    pairs = [("win", 2.0), ("loss", -1.0), ("timeout", 0.5), ("no_target", None), ("open", None)]
    s = mfd.simple_stats(pairs)
    assert s["n"] == 2 and s["win_rate"] == pytest.approx(50.0)
    assert s["expectancy_r"] == pytest.approx((2.0 - 1.0 + 0.5) / 3)
    assert s["closed"] == 3 and s["dropped"] == 2


def _record(direction, horizon, outcome, r, capped, entry_date="2021-06-01", *,
           lifecycle_adjusted=False, over_hard_cap=False):
    trade = T(direction=direction, entry_date=entry_date, outcome=outcome, r_multiple=r)
    features = {"capped": capped, "stop_mismatch": False, "lifecycle_adjusted": lifecycle_adjusted,
                "over_hard_cap": over_hard_cap, "tested_ratio": 0.5, "stop_atr": 2.0,
                "base_simple": (outcome, r), "deeper": (outcome, r), "reclaim": ("no_reclaim", None)}
    return {"ticker": "AAA", "horizon_key": horizon, "trade": trade, "features": features}


def test_summarise_partitions_capped_and_structural():
    mfd = _mfd()
    rows = ([_record("bullish", "3m", "win", 2.0, False) for _ in range(3)]
            + [_record("bullish", "3m", "loss", -1.0, True) for _ in range(2)])
    out = mfd.summarise(rows)
    bull = out["bullish"]
    assert bull["n_rows"] == 5 and bull["cap_rate"] == pytest.approx(0.4)
    assert bull["structural_only"]["pooled"]["win_rate"] == pytest.approx(100.0)
    assert bull["capped_only"]["pooled"]["win_rate"] == pytest.approx(0.0)
    assert out["bearish"]["n_rows"] == 0
    assert set(bull["horizons"]) == set(mfd.HORIZONS)


def test_summarise_reports_exact_lifecycle_and_over_hard_cap_rates():
    mfd = _mfd()
    rows = [
        _record("bullish", "3m", "win", 2.0, False, lifecycle_adjusted=True, over_hard_cap=True),
        _record("bullish", "3m", "win", 2.0, False, over_hard_cap=True),
        _record("bullish", "3m", "loss", -1.0, False),
        _record("bullish", "3m", "loss", -1.0, False),
    ]
    out = mfd.summarise(rows)
    bull = out["bullish"]
    assert bull["lifecycle_rate"] == pytest.approx(0.25)   # 1 of 4
    assert bull["over_hard_cap_rate"] == pytest.approx(0.5)  # 2 of 4


def test_phase_a_candidates_needs_both_the_wr_floor_and_n():
    mfd = _mfd()
    thin = [_record("bullish", "3m", "win", 2.0, False) for _ in range(29)]
    assert mfd.summarise(thin)["candidates"] == []
    enough = thin + [_record("bullish", "3m", "win", 2.0, False)]
    cands = mfd.summarise(enough)["candidates"]
    assert {(c["direction"], c["mechanism"]) for c in cands} >= {("bullish", "#1 structural_only")}


def _fake_summary(frame, i):
    entry = float(frame["Close"].iloc[i])
    d = str(frame.index[i].date())
    return T(trades=[
        T(direction="bullish", entry_date=d, entry=entry, stop_loss=entry * 0.95,
          take_profit=entry * 1.1, outcome="win", r_multiple=2.0, context={}),
        T(direction="bearish", entry_date=d, entry=entry, stop_loss=entry * 1.05,
          take_profit=entry * 0.9, outcome="loss", r_multiple=-1.0, context={"rs_combined": 10.0}),
        T(direction="bearish", entry_date=d, entry=entry, stop_loss=entry * 1.05,
          take_profit=entry * 0.9, outcome="win", r_multiple=2.0, context={"rs_combined": 80.0}),
    ])


def test_collect_takes_bulls_from_the_live_pass_and_laggard_bears_from_the_unmasked_pass():
    mfd = _mfd()
    frame = make_ohlcv([100 + 0.1 * k for k in range(300)], start="2020-01-01")
    seen_gates = []

    def run_fn(ticker, df, strategy, horizon, **kw):
        seen_gates.append(dict(mfd.STRATEGY_GATES.get(strategy) or {}))
        return _fake_summary(df, 250)

    records, meta = mfd.collect({"AAA": frame}, {}, horizons=("3m",), run_fn=run_fn)
    assert [r["trade"].direction for r in records] == ["bullish", "bearish"]
    assert meta == {"bearish_before_rs": 2, "bearish_after_rs": 1}
    assert seen_gates[0].get("directions") == ("bullish",)            # live gate
    assert seen_gates[1].get("directions") == ("bullish", "bearish")  # unmasked
    assert mfd.STRATEGY_GATES["Fibonacci"]["directions"] == ("bullish",)  # restored
    assert set(records[0]["features"]) >= {"capped", "deeper", "reclaim"}


def test_reproduction_report_is_exact_only_on_the_v93_figures():
    mfd = _mfd()
    pooled = {"n": 89, "win_rate": 21.3, "expectancy_r": -0.255}
    summary = {"bearish": {"baseline": {"pooled": pooled}}, "bullish": {"baseline": {"pooled": {}}}}
    ok = mfd.reproduction_report(summary, {"bearish_before_rs": 226, "bearish_after_rs": 107})
    off = mfd.reproduction_report(summary, {"bearish_before_rs": 225, "bearish_after_rs": 107})
    assert ok["v93_exact"] is True and off["v93_exact"] is False


def test_render_markdown_names_every_mechanism_and_the_reproduction_line():
    mfd = _mfd()
    rows = [_record("bullish", "3m", "win", 2.0, False) for _ in range(3)]
    result = mfd.summarise(rows)
    result["reproduction"] = mfd.reproduction_report(result, {"bearish_before_rs": 0, "bearish_after_rs": 0})
    md = mfd.render_markdown(result)
    for needle in ("#1 structural_only", "#2 deeper_stop", "#4 reclaim", "v93 reproduction", "Candidates",
                  "lifecycle rate", "over-hard-cap rate"):
        assert needle in md
