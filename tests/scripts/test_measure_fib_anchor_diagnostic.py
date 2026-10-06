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
