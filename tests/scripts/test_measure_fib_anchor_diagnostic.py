# tests/scripts/test_measure_fib_anchor_diagnostic.py
"""v124 diagnostic: refusals, bucket arithmetic, features, identification, report. No backtests."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))


def _module():
    import measure_fib_anchor_diagnostic
    return measure_fib_anchor_diagnostic


def trade(outcome, r, direction="bullish", **flags):
    """A hand-labelled trade row; flags land in every divisor cell (d4/d6/d8)."""
    cell = {"has_leg": True, "anchored": False, "zone_confluence": False, "fib_on_leg": False,
            "zone_touch": False, "close_in_zone": False, "broke_structure": None, "leg_atr": 1.0}
    cell.update({key: value for key, value in flags.items() if key in cell})
    row = {"ticker": "AAA", "horizon_key": "4w", "direction": direction, "entry_date": "2015-06-01",
           "outcome": outcome, "r_multiple": r, "confirm_close": flags.get("confirm_close", False),
           "confirm_wick": False, "anchor_fractal": True, "tested_ratio": 0.5,
           "rolling_level_confluence": False, "identified": True, "has_fib": True}
    row.update({f"d{d}": dict(cell) for d in (4, 6, 8)})
    return row


def group(wins, losses, win_r=2.0, **flags):
    return [trade("win", win_r, **flags) for _ in range(wins)] + [trade("loss", -1.0, **flags) for _ in range(losses)]


GOOD = dict(anchored=True, zone_confluence=True, fib_on_leg=True, confirm_close=True)


@pytest.mark.parametrize("window", [("2014-12-31", "2025-12-31"), ("2015-01-01", "2026-01-02"),
                                    ("2010-01-01", "2023-12-31"), ("2026-01-02", "2026-06-30")])
def test_diagnostic_window_outside_2015_2025_is_refused(window):
    with pytest.raises(SystemExit, match="diagnostic window"):
        _module().require_diagnostic_window(window)


@pytest.mark.parametrize("window", [("2015-01-01", "2025-12-31"), ("2015-01-01", "2015-12-31")])
def test_diagnostic_window_inside_2015_2025_is_accepted(window):
    assert _module().require_diagnostic_window(window) == window


def test_reproduction_window_is_exactly_v103s():
    module = _module()
    assert module.require_repro_window(["2010-01-01", "2023-12-31"]) == ("2010-01-01", "2023-12-31")
    for window in (("2010-01-01", "2025-12-31"), ("2015-01-01", "2023-12-31")):
        with pytest.raises(SystemExit, match="reproduction runs on 2010-01-01..2023-12-31"):
            module.require_repro_window(window)


def test_bucket_arithmetic_on_hand_labelled_rows():
    module = _module()
    rows = group(20, 20, anchored=True) + group(12, 28)
    buckets = module.bucket(rows, lambda row: row["d6"]["anchored"])
    fav, rest = buckets["favourable"], buckets["rest"]
    assert (fav["n"], rest["n"]) == (40, 40)
    assert fav["win_rate"] == pytest.approx(50.0) and rest["win_rate"] == pytest.approx(30.0)
    assert fav["expectancy_r"] == pytest.approx(0.5) and rest["expectancy_r"] == pytest.approx(-0.1)
    assert module.split_passes(buckets) is True


def test_split_needs_n_30_in_each_bucket():
    module = _module()
    buckets = module.bucket(group(15, 14, anchored=True) + group(12, 28), lambda row: row["d6"]["anchored"])
    assert buckets["favourable"]["n"] == 29
    assert module.split_passes(buckets) is False


def test_split_needs_expr_no_lower_and_accepts_equal():
    module = _module()
    lower = module.bucket(group(20, 20, win_r=0.5, anchored=True) + group(12, 28),
                          lambda row: row["d6"]["anchored"])
    assert module.split_passes(lower) is False                         # WR 50 > 30 but ExpR -0.25 < -0.1
    equal = module.bucket(group(20, 20, win_r=0.75, anchored=True) + group(10, 30, win_r=2.5),
                          lambda row: row["d6"]["anchored"])
    assert equal["favourable"]["expectancy_r"] == equal["rest"]["expectancy_r"] == -0.125
    assert module.split_passes(equal) is True


def test_equal_win_rate_does_not_pass():
    module = _module()
    buckets = module.bucket(group(15, 15, anchored=True) + group(15, 15), lambda row: row["d6"]["anchored"])
    assert module.split_passes(buckets) is False
    assert module.wr_sign_positive(buckets) is False


def test_scratch_only_bucket_is_not_a_pass_and_never_raises():
    module = _module()
    rows = [trade("scratch", 0.0, anchored=True) for _ in range(40)] + group(12, 28)
    buckets = module.bucket(rows, lambda row: row["d6"]["anchored"])
    assert buckets["favourable"]["win_rate"] is None
    assert module.split_passes(buckets) is False
    assert module.wr_sign_positive(buckets) is False


def _per_divisor(flags_by_divisor):
    """A (20W/20L) and B (12W/28L); flags_by_divisor[d] names which group is favourable at d."""
    rows = group(20, 20) + group(12, 28)
    for index, row in enumerate(rows):
        in_a = index < 40
        for divisor, favoured in flags_by_divisor.items():
            row[f"d{divisor}"]["anchored"] = in_a if favoured == "A" else not in_a
    return rows


def test_leg_arm_needs_primary_and_two_divisor_signs():
    module = _module()
    passing = module.leg_arm_verdict(module.divisor_buckets(_per_divisor({4: "A", 6: "A", 8: "B"}), "anchored"))
    assert passing == {"primary_passes": True, "wr_sign_divisors": 2, "proceeds": True}
    failing = module.leg_arm_verdict(module.divisor_buckets(_per_divisor({4: "B", 6: "A", 8: "B"}), "anchored"))
    assert failing == {"primary_passes": True, "wr_sign_divisors": 1, "proceeds": False}
    no_primary = module.leg_arm_verdict(module.divisor_buckets(_per_divisor({4: "A", 6: "B", 8: "A"}), "anchored"))
    assert no_primary["proceeds"] is False


def test_single_split_verdict():
    module = _module()
    buckets = module.bucket(group(20, 20, confirm_close=True) + group(12, 28), lambda row: row["confirm_close"])
    assert module.single_split_verdict(buckets) == {"primary_passes": True, "proceeds": True}


def test_describe_and_quintiles():
    module = _module()
    rows = group(5, 5)
    for index, row in enumerate(rows):
        row["d6"]["leg_atr"] = float(index + 1)
    rows += [trade("loss", -1.0, leg_atr=None)]
    label = module.quintile_key(rows, lambda row: row["d6"]["leg_atr"])
    groups = module.describe(rows, label)
    assert set(groups) == {"Q1", "Q2", "Q3", "Q4", "Q5", "no leg"}
    assert groups["no leg"]["n"] == 1
    assert sum(stats["n"] for stats in groups.values()) == 11


def test_reproduction_compares_n_wr_expr_and_universe():
    module = _module()
    rows = group(20, 20)
    reference = {"bullish": {"n": 40, "win_rate": 50.0, "expectancy_r": 0.5}}
    assert module.reproduction(rows, "bullish", 73, reference)["matches"] is True
    assert module.reproduction(rows, "bullish", 72, reference)["matches"] is False
    assert module.reproduction(rows[:-1], "bullish", 73, reference)["matches"] is False


def test_reference_is_the_v103_arm():
    module = _module()
    assert module.REFERENCE["bullish"] == {"n": 815, "win_rate": 36.81, "expectancy_r": 0.2219}
    assert module.REFERENCE["bearish"] == {"n": 169, "win_rate": 23.67, "expectancy_r": -0.1269}
    assert module.REFERENCE_UNIVERSE_N == 73
    assert module.REPRO_WINDOW == ("2010-01-01", "2023-12-31")
    assert module.DIAG_WINDOW == ("2015-01-01", "2025-12-31")


from types import SimpleNamespace as NS  # noqa: E402

from tests.market.fib_leg_fixtures import CLEAN, MIRROR, path_frame  # noqa: E402

SIDES = [(False, "bullish"), (True, "bearish")]


def _entry(mirror):
    frame = path_frame(CLEAN[:17], mirror=mirror)
    return frame, str(frame.index[16].date())


@pytest.mark.parametrize("mirror,direction", SIDES)
def test_fib_trade_features_on_the_clean_leg(mirror, direction):
    module = _module()
    frame, date = _entry(mirror)
    zone_price = MIRROR - 11.5 if mirror else 11.5            # inside the 0.5-0.618 zone
    label = "Anchored VWAP (swing low)" if mirror else "Volume Profile HVN"
    out = module.fib_trade_features(frame, "2w", direction, date,
                                    candidates_fn=lambda df, h, price: [(zone_price, label), (zone_price, "EMA20")])
    assert out["anchor_fractal"] is True
    assert out["confirm_close"] is False                       # Close 13 is not above the prior High 14
    assert out["confirm_wick"] is True                         # wick 0.5 of range 1.0
    assert out["tested_ratio"] == 0.382                        # nearest level 12.826 to Close 13
    assert out["rolling_level_confluence"] is False            # 11.5 is > 0.25 ATR from 12.826
    for divisor in (4, 6, 8):
        cell = out[f"d{divisor}"]
        assert cell["has_leg"] is True and cell["anchored"] is True and cell["zone_confluence"] is True
        assert cell["zone_touch"] is False and cell["close_in_zone"] is False
        assert cell["broke_structure"] is True and cell["leg_atr"] > 0


def test_zone_ignores_other_families_and_missing_legs():
    module = _module()
    frame, date = _entry(False)
    out = module.fib_trade_features(frame, "2w", "bullish", date,
                                    candidates_fn=lambda df, h, price: [(11.5, "EMA20"), (14.0, "Volume Profile HVN")])
    assert out["d6"]["zone_confluence"] is False
    nan_leg = dict.fromkeys(("level_500", "level_618", "origin_price", "end_price"), float("nan"))
    assert module.zone_confluence([(11.5, "Volume Profile HVN")], nan_leg, 1.0) is False
    assert module.close_in_zone(nan_leg, 11.5) is False


def test_short_history_has_no_rolling_anchor():
    module = _module()
    prefix = path_frame(CLEAN[:10])
    assert module.rolling_anchor(prefix, 15) is None
    assert module.anchored_split(None, {"origin_price": 8.5, "end_price": 15.5}, 1.0, "bullish") is False
    assert module.anchor_is_fractal(prefix, None, "bullish") is None


def test_anchor_that_is_not_a_fractal():
    module = _module()
    prefix = path_frame(CLEAN[:9])                             # bar 7 needs bar 10 to confirm
    anchor = module.rolling_anchor(prefix, 9)
    assert anchor["low_pos"] == 7
    assert module.anchor_is_fractal(prefix, anchor, "bullish") is False


@pytest.mark.parametrize("mirror,direction", SIDES)
def test_confirmation_close_beyond_prior_bar(mirror, direction):
    module = _module()
    prefix = path_frame([10, 12], mirror=mirror)               # Close 12 > prior High 10.5
    assert module.confirm_close(prefix, direction) is True
    assert module.confirm_close(path_frame([10, 10.2], mirror=mirror), direction) is False
    assert module.confirm_close(path_frame([10], mirror=mirror), direction) is False


def test_near_needs_finite_values_and_positive_atr():
    module = _module()
    assert module.near(10.0, 10.2, 1.0) is True
    assert module.near(10.0, 10.3, 1.0) is False
    assert module.near(10.0, float("nan"), 1.0) is False
    assert module.near(10.0, 10.0, float("nan")) is False
    assert module.near(10.0, 10.0, 0.0) is False


def test_primary_divisor_is_the_fib_leg_default():
    from swingbot.core.market.fib_leg import ORIGIN_DIVISOR
    assert _module().PRIMARY_DIVISOR == ORIGIN_DIVISOR


def _explode(*args, **kwargs):
    raise AssertionError("run_fn must not be called")


@pytest.mark.parametrize("window", [("2015-01-01", "2026-03-01"), ("2010-01-01", "2023-12-31")])
def test_collect_fib_refuses_a_window_outside_2015_2025_before_running(window):
    with pytest.raises(SystemExit, match="diagnostic window"):
        _module().collect_fib({}, {}, "bullish", window, run_fn=_explode)


def test_collect_fib_stamps_features_on_reference_trades():
    module = _module()
    frame, date = _entry(False)

    def run_fn(ticker, df, strategy, horizon, **kwargs):
        assert strategy == "Fibonacci"
        trades = [NS(entry_date=date, direction="bullish", outcome="win", r_multiple=1.5)] if horizon == "2w" else []
        return NS(trades=trades)

    rows = module.collect_fib({"AAA": frame}, {}, "bullish", module.DIAG_WINDOW, run_fn=run_fn,
                              candidates_fn=lambda df, h, price: [])
    assert len(rows) == 1
    row = rows[0]
    assert (row["ticker"], row["horizon_key"], row["outcome"], row["r_multiple"]) == ("AAA", "2w", "win", 1.5)
    assert row["d6"]["anchored"] is True and row["d6"]["zone_confluence"] is False


def test_collect_repro_runs_the_reference_arm_on_v103s_window_without_features():
    module = _module()
    frame, date = _entry(False)
    seen = []

    def run_fn(ticker, df, strategy, horizon, **kwargs):
        trades = [NS(entry_date=date, direction="bullish", outcome="loss", r_multiple=-1.0),
                  NS(entry_date="2024-02-01", direction="bullish", outcome="win", r_multiple=2.0)]
        seen.append(horizon)
        return NS(trades=trades if horizon == "2w" else [])

    rows = module.collect_repro({"AAA": frame}, {}, "bullish", run_fn=run_fn)
    assert [row["entry_date"] for row in rows] == [date]       # the 2024 entry is outside 2010-2023
    assert "d6" not in rows[0] and seen


@pytest.mark.parametrize("mirror,direction", SIDES)
def test_fib_trade_features_ignore_bars_after_the_entry(mirror, direction):
    module = _module()
    full = path_frame(CLEAN + [20, 22, 5, 4], mirror=mirror)
    short = full.iloc[:17]
    date = str(short.index[16].date())
    pick = lambda df, h, price: [(11.5, "Volume Profile HVN")]  # noqa: E731
    assert (module.fib_trade_features(full, "2w", direction, date, candidates_fn=pick)
            == module.fib_trade_features(short, "2w", direction, date, candidates_fn=pick))


def test_collect_fib_drops_an_entry_in_the_2026_holdout():
    module = _module()
    frame, date = _entry(False)

    def run_fn(ticker, df, strategy, horizon, **kwargs):
        trades = [NS(entry_date="2026-01-05", direction="bullish", outcome="win", r_multiple=1.0),
                  NS(entry_date=date, direction="bullish", outcome="win", r_multiple=1.5)]
        return NS(trades=trades if horizon == "2w" else [])

    rows = module.collect_fib({"AAA": frame}, {}, "bullish", module.DIAG_WINDOW, run_fn=run_fn,
                              candidates_fn=lambda df, h, price: [])
    assert [row["entry_date"] for row in rows] == [date]
    assert not any(row["entry_date"].startswith("2026") for row in rows)


from swingbot.core.market.levels import Level
from tests.market.fib_leg_fixtures import RESTART


@pytest.mark.parametrize("index,horizon_key,expected", [
    (132, "3m", 130), (137, "3m", 135), (131, "3m", 130), (128, "2w", 125), (21, "2w", 20), (20, "2w", 20)])
def test_bucket_bar_is_the_replays_first_visit(index, horizon_key, expected):
    assert _module().bucket_bar(index, horizon_key) == expected


def test_scenario_levels_rebuilds_the_map_and_resplits_at_this_close():
    module = _module()
    frame = path_frame([10.0] * 30)                            # Close 10 everywhere
    calls = []

    def levels_fn(ticker, df, bar, horizon_key, cache):
        calls.append(bar)
        return ([Level(9.0, ["Fib 61.8%"]), Level(8.0, ["EMA20"])],
                [Level(9.2, ["Rolling resistance"]), Level(12.0, ["Swing high"])])   # 9.2 is below 10 now

    stop, target = module.scenario_levels("AAA", frame, 27, "2w", "bullish", levels_fn=levels_fn)
    assert calls == [25]
    assert (stop.price, target.price) == (9.2, 12.0)
    stop, target = module.scenario_levels("AAA", frame, 27, "2w", "bearish", levels_fn=levels_fn)
    assert (stop.price, target.price) == (12.0, 9.2)
    one_sided = module.scenario_levels("AAA", frame, 27, "2w", "bullish",
                                       levels_fn=lambda *a: ([Level(9.0, ["EMA20"])], []))
    assert one_sided is None


def test_is_identified_matches_the_replays_clamped_stop_and_derived_tp1():
    from swingbot.core.planning.builders import _clamp_stop_to_hard_cap
    module = _module()
    level = Level(95.0, ["Fib 61.8%"])
    clamped = _clamp_stop_to_hard_cap(100.0, 95.0, True)           # 98.25: risk 1.75
    rr = NS(min_risk_reward_ratio=1.5, max_risk_reward_ratio=3.0)
    near, far = 102.0, 110.0           # near pays 1.14R (< floor), far pays 5.7R (> cap)
    capped = 100.0 + (100.0 - clamped) * 3.0                       # the synthetic max_rr price

    def plan(stop, tp1, direction="bullish"):
        return NS(trigger_price=100.0, stop_loss=stop, tp1=tp1, direction=direction)

    assert module.is_identified(plan(clamped, capped), level, [near, far], rr) is True
    assert module.is_identified(plan(clamped, far), level, [near, far], rr) is False      # raw level, not the capped tp1
    assert module.is_identified(plan(clamped, capped), level, [near, 104.0], rr) is False
    assert module.is_identified(plan(clamped - 0.01, capped), level, [near, far], rr) is False
    assert module.is_identified(plan(None, capped), level, [near, far], rr) is False
    assert module.is_identified(plan(clamped, None), level, [near, far], rr) is False
    assert module.is_identified(plan(clamped, capped), level, [], rr) is False


def test_fib_labels_and_prices():
    module = _module()
    pair = (Level(9.0, ["Fib 61.8%", "EMA20"]), Level(12.0, ["Swing high", "Rolling resistance"]))
    labels = module.fib_labels(pair)
    assert labels == {"Fib 61.8%", "Swing high"}
    candidates = [(9.0, "Fib 61.8%"), (12.0, "Swing high"), (9.1, "EMA20"), (8.0, "Fib 50.0%")]
    assert module.fib_candidate_prices(candidates, labels) == [9.0, 12.0]


def _derived_tp1(entry, stop, bullish, candidates):
    from swingbot.core.planning.targets import select_structural_target
    from swingbot.scan_params import ScanParams
    params = ScanParams.from_config()
    return select_structural_target(entry, stop, bullish, candidates,
                                    params.min_risk_reward_ratio, params.max_risk_reward_ratio)


def _restart_case(stop_loss_offset=0.0, levels=None, tp1=None):
    from swingbot.core.planning.builders import _clamp_stop_to_hard_cap
    module = _module()
    frame = path_frame(RESTART)                               # Close[25] = 14.8
    stop_level = Level(13.7, ["Fib 50.0%", "EMA20"])
    levels = levels or ([stop_level], [Level(16.0, ["Rolling resistance"])])
    stop = _clamp_stop_to_hard_cap(14.8, 13.7, True)
    plan = NS(direction="bullish", trigger_price=14.8, stop_loss=stop + stop_loss_offset,
              tp1=tp1 if tp1 is not None else _derived_tp1(14.8, stop, True, [16.0]))
    return module.confluence_row("AAA", frame, "2w", 25, plan, NS(outcome="win", r_total=1.2),
                                 levels_fn=lambda *a: levels,
                                 candidates_fn=lambda df, h, price: [(13.75, "Fib 50.0%"), (13.6, "EMA20")])


def test_confluence_row_finds_the_fib_candidate_on_the_leg():
    row = _restart_case()
    assert (row["identified"], row["has_fib"]) == (True, True)
    assert (row["outcome"], row["r_multiple"], row["direction"]) == ("win", 1.2, "bullish")
    for divisor in (4, 6, 8):
        assert row[f"d{divisor}"] == {"has_leg": True, "fib_on_leg": True}   # 13.75 == level_500


def test_confluence_row_without_fib_source_has_no_cells():
    row = _restart_case(levels=([Level(13.7, ["EMA20"])], [Level(16.0, ["Rolling resistance"])]))
    assert (row["identified"], row["has_fib"]) == (True, False)
    assert "d6" not in row


def test_confluence_row_with_a_mismatched_stop_is_unidentified():
    row = _restart_case(stop_loss_offset=0.05)
    assert (row["identified"], row["has_fib"]) == (False, False)


def test_confluence_row_with_a_tp1_outside_the_rebuilt_targets_is_unidentified():
    row = _restart_case(tp1=17.3)                                # derived from the 16.0 resistance
    assert (row["identified"], row["has_fib"]) == (False, False)
    assert "d6" not in row


def test_confluence_trades_window_and_skips():
    module = _module()
    frame = path_frame(RESTART)
    seen = {}

    def replay_fn(ticker, df, horizon_key):
        seen["last"] = str(df.index[-1].date())
        return [(20, NS(direction="bullish")), (24, NS(direction="bullish")), (25, NS(direction="bullish"))]

    def exit_fn(df, index, plan, scale_out):
        assert scale_out is True
        return NS(outcome="not_triggered" if index == 24 else "win", r_total=1.0)

    start = str(frame.index[21].date())
    end = str(frame.index[25].date())
    trades = module.confluence_trades("AAA", frame, "2w", (start, end), replay_fn=replay_fn, exit_fn=exit_fn)
    assert [index for index, _, _ in trades] == [25]           # 20 before start, 24 skipped
    assert seen["last"] == end
    for window in (("2010-01-01", "2023-12-31"), ("2015-01-01", "2026-01-02")):
        with pytest.raises(SystemExit, match="diagnostic window"):
            module.confluence_trades("AAA", frame, "2w", window, replay_fn=replay_fn, exit_fn=exit_fn)


@pytest.mark.parametrize("index", [25, 27])          # 25 is the bucket bar itself; 27 is mid-bucket
@pytest.mark.parametrize("direction", ["bullish", "bearish"])
def test_confluence_row_ignores_bars_after_the_entry(direction, index):
    from swingbot.core.planning.builders import _clamp_stop_to_hard_cap
    module = _module()
    assert module.bucket_bar(index, "2w") == 25
    bullish = direction == "bullish"
    clean = path_frame(RESTART + [14.7, 14.6, 14.5, 14.4, 14.3], mirror=not bullish)
    poisoned = clean.copy()
    poisoned.iloc[index + 1:] = [[60.0, 61.0, 1.0, 1.0, 9e9] if i % 2 else [1.0, 2.0, 0.5, 1.0, 9e9]
                                 for i in range(len(clean) - index - 1)]
    close = float(clean["Close"].iloc[index])
    seen_bars = []

    def levels_fn(ticker, df, bar, horizon_key, cache):
        seen_bars.append(bar)
        base = float(df.iloc[:bar + 1]["Close"].iloc[-1])          # the as-of map reads only its own prefix
        return (([Level(base - 1.1, ["Fib 50.0%"])], [Level(base + 1.2, ["Rolling resistance"])]) if bullish
                else ([Level(base - 1.2, ["Rolling resistance"])], [Level(base + 1.1, ["Fib 50.0%"])]))

    def candidates_fn(df, horizon, price):
        return [(float(df["Close"].iloc[-1]) - 1.05, "Fib 50.0%")]

    def run(frame):
        base = float(clean["Close"].iloc[25])
        level = Level(base - 1.1 if bullish else base + 1.1, ["Fib 50.0%"])
        stop = _clamp_stop_to_hard_cap(close, level.price, bullish)
        target = base + 1.2 if bullish else base - 1.2
        plan = NS(direction=direction, trigger_price=close, stop_loss=stop,
                  tp1=_derived_tp1(close, stop, bullish, [target]))
        return module.confluence_row("AAA", frame, "2w", index, plan, NS(outcome="win", r_total=1.0),
                                     levels_fn=levels_fn, candidates_fn=candidates_fn)

    full, truncated = run(poisoned), run(clean.iloc[:index + 1])
    assert full == truncated
    assert seen_bars == [25, 25]                                   # never past the bucket bar
    assert full["identified"] is True and full["has_fib"] is True and "d6" in full


def test_scenario_levels_and_fib_prices_ignore_bars_after_the_entry_with_the_real_builders():
    from swingbot.core.backtesting.backtest_scenarios import levels_asof
    from swingbot.core.market.levels import collect_candidate_levels
    from swingbot.core.market.strategy_types import HORIZONS
    from tests.market.fib_leg_fixtures import walk_frame
    module = _module()
    index = 108                                                    # bucket bar 105
    clean = walk_frame(130)
    poisoned = clean.copy()
    poisoned.iloc[index + 1:] = clean.iloc[index + 1:].to_numpy() * 7.0
    truncated = clean.iloc[:index + 1]
    for direction in ("bullish", "bearish"):
        got = module.scenario_levels("AAA", poisoned, index, "2w", direction, levels_fn=levels_asof)
        want = module.scenario_levels("AAA", truncated, index, "2w", direction, levels_fn=levels_asof)
        assert got is not None and got == want
    prefix = clean.iloc[:module.bucket_bar(index, "2w") + 1]
    candidates = collect_candidate_levels(prefix, HORIZONS["2w"], float(prefix["Close"].iloc[-1]))
    labels = {label for _, label in candidates}
    assert labels
    assert (module._fib_prices_at(poisoned, index, "2w", labels, collect_candidate_levels)
            == module._fib_prices_at(truncated, index, "2w", labels, collect_candidate_levels))


import json


DIAG = ["2015-01-01", "2025-12-31"]
REPRO = ["2010-01-01", "2023-12-31"]


def _payloads(confluence_rows=None):
    bull = group(20, 20, **GOOD) + group(12, 28)
    bear = [dict(row, direction="bearish") for row in group(5, 10)]
    fib = [{"kind": "fib", "direction": "bullish", "window": DIAG, "universe_n": 73,
            "avwap_levels_enabled": True, "rows": bull},
           {"kind": "fib", "direction": "bearish", "window": DIAG, "universe_n": 73,
            "avwap_levels_enabled": True, "rows": bear}]
    rows = confluence_rows if confluence_rows is not None else group(20, 20, **GOOD) + group(12, 28)
    confluence = [{"kind": "confluence", "window": DIAG, "tickers": ["AAA"],
                   "universe_n": 1, "avwap_levels_enabled": True, "rows": rows}]
    repro = [{"kind": "repro", "direction": "bullish", "window": REPRO, "universe_n": 73, "rows": group(20, 20)},
             {"kind": "repro", "direction": "bearish", "window": REPRO, "universe_n": 73,
              "rows": [dict(row, direction="bearish") for row in group(5, 10)]}]
    return fib, confluence, repro


REPRO_MATCH = {"bullish": {"n": 40, "win_rate": 50.0, "expectancy_r": 0.5},
               "bearish": {"n": 15, "win_rate": 33.33, "expectancy_r": 0.0}}


def test_report_verdicts_follow_the_exit_rule():
    module = _module()
    report = module.build_report(*_payloads())
    assert report["exit_rule"] == module.EXIT_RULE
    assert report["avwap_levels_enabled"] == [True]
    assert {arm: v["proceeds"] for arm, v in report["verdicts"].items()} == {
        "arm1": True, "arm2": True, "arm3": True, "arm4": True}
    assert report["fib"]["bearish"]["arm1"]["6"]["rest"]["n"] == 15        # described, not judged
    assert report["reproduction"]["bullish"]["observed"]["n"] == 40         # from the repro payload
    assert report["reproduction"]["bullish"]["matches"] is False            # 40 trades, not 815


def test_one_unidentified_confluence_trade_makes_arm4_not_measurable():
    module = _module()
    rows = group(20, 20, **GOOD) + group(12, 28)
    rows[0] = dict(rows[0], identified=False)
    report = module.build_report(*_payloads(rows))
    assert report["confluence"]["unidentified"] == 1
    assert report["verdicts"]["arm4"] == {"proceeds": False, "not_measurable": True}
    assert "not measurable with this instrument" in module.render_markdown(report)


def test_report_refuses_a_diagnostic_payload_outside_2015_2025():
    module = _module()
    fib, confluence, repro = _payloads()
    fib[0]["window"] = ["2010-01-01", "2025-12-31"]
    with pytest.raises(SystemExit, match="diagnostic window"):
        module.build_report(fib, confluence, repro)


def test_report_refuses_a_repro_payload_not_on_v103s_window():
    module = _module()
    fib, confluence, repro = _payloads()
    repro[0]["window"] = DIAG
    with pytest.raises(SystemExit, match="reproduction runs on"):
        module.build_report(fib, confluence, repro)


def test_markdown_carries_the_exit_rule_and_every_divisor():
    module = _module()
    text = module.render_markdown(module.build_report(*_payloads()))
    assert module.EXIT_RULE in text
    for divisor in (4, 6, 8):
        assert f"d={divisor} favourable" in text
    assert "Fibonacci bearish (description only)" in text


def _write_inputs(tmp_path):
    fib, confluence, repro = _payloads()
    paths = []
    for name, payload in (("bull", fib[0]), ("bear", fib[1]), ("conf", confluence[0]),
                          ("rbull", repro[0]), ("rbear", repro[1])):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        paths.append(str(path))
    return paths


def test_report_command_needs_a_note_when_the_baseline_does_not_reproduce(tmp_path):
    module = _module()
    bull, bear, conf, rbull, rbear = _write_inputs(tmp_path)
    out, md = tmp_path / "report.json", tmp_path / "report.md"
    argv = ["report", "--repro", rbull, rbear, "--fib", bull, bear, "--confluence", conf,
            "--out", str(out), "--md", str(md)]
    with pytest.raises(SystemExit, match="does not reproduce"):
        module.main(argv)
    assert not out.exists() and not md.exists()
    note = tmp_path / "note.md"
    note.write_text("difference explained", encoding="utf-8")
    assert module.main(argv + ["--reproduction-note", str(note)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["verdicts"]["arm1"]["proceeds"] is True
    assert md.read_text(encoding="utf-8").startswith("# v124")


def test_report_command_needs_no_note_when_the_baseline_reproduces(tmp_path, monkeypatch):
    module = _module()
    monkeypatch.setattr(module, "REFERENCE", REPRO_MATCH)
    bull, bear, conf, rbull, rbear = _write_inputs(tmp_path)
    out, md = tmp_path / "report.json", tmp_path / "report.md"
    assert module.main(["report", "--repro", rbull, rbear, "--fib", bull, bear, "--confluence", conf,
                        "--out", str(out), "--md", str(md)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["reproduction"]["bullish"]["matches"] is True


def test_reproduce_command_prints_only_the_baseline(tmp_path, capsys):
    module = _module()
    _, _, _, rbull, rbear = _write_inputs(tmp_path)
    assert module.main(["reproduce", "--repro", rbull, rbear]) == 0
    printed = capsys.readouterr().out
    assert '"matches": false' in printed and "arm1" not in printed


def test_duplicate_direction_payload_is_refused_not_collapsed():
    module = _module()
    fib, confluence, repro = _payloads()
    with pytest.raises(SystemExit, match="duplicate"):
        module.build_report([fib[0], fib[0], fib[1]], confluence, repro)
    with pytest.raises(SystemExit, match="duplicate"):
        module.build_report(fib, confluence, [repro[1], repro[1]])


def test_payload_in_the_wrong_slot_is_refused():
    module = _module()
    fib, confluence, repro = _payloads()
    with pytest.raises(SystemExit, match="kind"):
        module.build_report(fib, confluence, [dict(repro[0], kind="fib"), repro[1]])
    with pytest.raises(SystemExit, match="kind"):
        module.build_report([dict(fib[0], kind="repro"), fib[1]], confluence, repro)
    with pytest.raises(SystemExit, match="kind"):
        module.build_report(fib, [dict(confluence[0], kind="fib")], repro)


def test_diagnostic_window_must_be_exactly_2015_2025():
    module = _module()
    fib, confluence, repro = _payloads()
    confluence[0]["window"] = ["2016-01-01", "2025-12-31"]      # inside, but not the window
    with pytest.raises(SystemExit, match="diagnostic window"):
        module.build_report(fib, confluence, repro)


def test_empty_favourable_bucket_does_not_pass_and_does_not_raise():
    module = _module()
    fib, confluence, repro = _payloads()
    fib[0]["rows"] = group(20, 20)                      # nothing favourable on any split
    baseline = module.render_markdown(module.build_report(*_payloads()))
    report = module.build_report(fib, confluence, repro)
    assert report["fib"]["bullish"]["arm1"]["6"]["favourable"]["win_rate"] is None
    assert report["verdicts"]["arm1"]["proceeds"] is False
    assert report["verdicts"]["arm3"]["proceeds"] is False
    assert module.render_markdown(report).count("n/a") > baseline.count("n/a")


def test_reproduction_note_must_be_non_empty(tmp_path):
    module = _module()
    bull, bear, conf, rbull, rbear = _write_inputs(tmp_path)
    note = tmp_path / "note.md"
    note.write_text("", encoding="utf-8")
    out, md = tmp_path / "report.json", tmp_path / "report.md"
    with pytest.raises(SystemExit, match="does not reproduce"):
        module.main(["report", "--repro", rbull, rbear, "--fib", bull, bear, "--confluence", conf,
                     "--out", str(out), "--md", str(md), "--reproduction-note", str(note)])
    assert not out.exists()


def test_reproduction_note_inside_a_repo_must_be_tracked(tmp_path, monkeypatch):
    module = _module()
    monkeypatch.setattr(module, "_note_is_tracked", lambda path: False)
    bull, bear, conf, rbull, rbear = _write_inputs(tmp_path)
    note = tmp_path / "note.md"
    note.write_text("explained", encoding="utf-8")
    with pytest.raises(SystemExit, match="does not reproduce"):
        module.main(["report", "--repro", rbull, rbear, "--fib", bull, bear, "--confluence", conf,
                     "--out", str(tmp_path / "r.json"), "--md", str(tmp_path / "r.md"),
                     "--reproduction-note", str(note)])


def test_note_outside_any_repo_counts_as_tracked(tmp_path):
    note = tmp_path / "note.md"
    note.write_text("x", encoding="utf-8")
    assert _module()._note_is_tracked(note) is True


def _collect(module, monkeypatch, tmp_path, argv, **patches):
    written = {}
    monkeypatch.setattr(module, "_write", lambda path, payload: written.update(payload))
    for name, value in patches.items():
        monkeypatch.setattr(module, name, value)
    assert module.main(argv + ["--out", str(tmp_path / "o.json")]) == 0
    return written


def test_collect_commands_write_payloads_build_report_accepts(tmp_path, monkeypatch):
    module = _module()
    frames = {"AAA": object()}
    common = dict(_frames_and_asof=lambda args: (frames, {}))
    repro = {}
    fib = {}
    for direction in module.DIRECTIONS:
        rows = group(20, 20, **GOOD)
        repro[direction] = _collect(module, monkeypatch, tmp_path,
                                    ["collect-repro", "--direction", direction],
                                    collect_repro=lambda *a, rows=rows, **k: rows, **common)
        fib[direction] = _collect(module, monkeypatch, tmp_path,
                                  ["collect-fib", "--direction", direction],
                                  collect_fib=lambda *a, rows=rows, **k: rows, **common)
    conf = _collect(module, monkeypatch, tmp_path, ["collect-confluence"],
                    require_ext_cache=lambda: None, _load_frames=lambda universe, tickers: frames,
                    collect_confluence=lambda *a, **k: group(20, 20, **GOOD))
    assert repro["bullish"]["kind"] == "repro" and tuple(repro["bullish"]["window"]) == module.REPRO_WINDOW
    assert repro["bullish"]["universe_n"] == 1
    for payload in (fib["bullish"], conf):
        assert tuple(payload["window"]) == module.DIAG_WINDOW and payload["universe_n"] == 1
    assert fib["bullish"]["kind"] == "fib" and conf["kind"] == "confluence"
    for payload in (fib["bullish"], fib["bearish"], conf):
        payload["window"] = list(payload["window"])         # JSON round trip
    for payload in repro.values():
        payload["window"] = list(payload["window"])
    report = module.build_report(list(fib.values()), [conf], list(repro.values()))
    assert set(report["verdicts"]) == {"arm1", "arm2", "arm3", "arm4"}


def test_overlapping_confluence_chunks_are_refused():
    module = _module()
    fib, confluence, repro = _payloads()
    other = dict(confluence[0], tickers=["AAA", "BBB"])
    with pytest.raises(SystemExit, match="overlap"):
        module.build_report(fib, [confluence[0], other], repro)
    disjoint = dict(confluence[0], tickers=["BBB"])
    assert module.build_report(fib, [confluence[0], disjoint], repro)["confluence"]["unidentified"] == 0


def test_mixed_avwap_flags_are_refused():
    module = _module()
    fib, confluence, repro = _payloads()
    fib[1]["avwap_levels_enabled"] = False
    with pytest.raises(SystemExit, match="avwap_levels_enabled"):
        module.build_report(fib, confluence, repro)
