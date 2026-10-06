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
