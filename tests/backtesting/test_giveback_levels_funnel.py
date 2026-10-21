"""v178 V178-3: the funnel's frozen rules on synthetic paired rows."""
import pytest

from swingbot.core.backtesting import giveback_levels_funnel as fn
from swingbot.core.backtesting.arms.windows import STAGES

TICKERS = [f"T{i}" for i in range(8)]
BUCKETS = ("2019-03-04", "2021-03-01", "2022-03-01")   # folds 2020-22 / 2021-22 / 2022
N = 200                                                 # resamples: speed, never a real run


def _row(ticker, date, deltas, *, i=0, changed=None):
    """One entry. ``deltas`` maps arm -> r_net minus control A's (1.0); arms not
    named equal A. ``changed`` names the arms whose exit differs from A
    (default: every arm with a non-zero delta)."""
    moved = {a for a, d in deltas.items() if d} if changed is None else set(changed)
    arms = {arm: {"outcome": "win", "r_net": 1.0 + deltas.get(arm, 0.0),
                  "exit_index": 20 + (arm in moved), "exit_price": 110.0 + (arm in moved)}
            for arm in fn.ARMS}
    return {"ticker": ticker, "source": "strategy", "strategy": f"S{i}", "horizon_key": "1m",
            "direction": "bullish", "signal_date": date, "planned_rr": 2.0, "arms": arms}


def _date(year, k):
    return f"{year}-{k % 12 + 1:02d}-{k // 12 % 28 + 1:02d}"


def _year_rows(year, deltas_for, n=40):
    """n rows in ``year``, spread over TICKERS; deltas_for(k, ticker_index) -> deltas."""
    return [_row(TICKERS[k % 8], _date(year, k), deltas_for(k, k % 8), i=k) for k in range(n)]


def _bucket_rows(per_arm):
    """One row per ticker per bucket; per_arm: arm -> (d_2019, d_2021, d_2022)."""
    return [_row(t, date, {a: v[b] for a, v in per_arm.items()}, i=b)
            for b, date in enumerate(BUCKETS) for t in TICKERS]


def _s0(**arms):
    """stage0 stand-ins: arm id with '.' written '_' -> (pooled delta, verdict)."""
    return {k.replace("_", "."): {"delta_r": d, "verdict": v} for k, (d, v) in arms.items()}


OPEN = "RESOLVABLE"


def test_the_arm_table_is_frozen():
    assert fn.PCT == 5.0
    assert fn.ARMS == {
        "A": {"enabled": True, "mode": "pct"}, "B": {"enabled": False, "mode": "pct"},
        "R0.75": {"enabled": True, "mode": "range", "k": 0.75},
        "R1.00": {"enabled": True, "mode": "range", "k": 1.0},
        "R1.25": {"enabled": True, "mode": "range", "k": 1.25},
        "S0.25": {"enabled": True, "mode": "profit_share", "f": 0.25},
        "S0.33": {"enabled": True, "mode": "profit_share", "f": 0.33},
        "S0.50": {"enabled": True, "mode": "profit_share", "f": 0.50}}
    assert fn.CONTROLS == ("A", "B")
    assert fn.CANDIDATES == ("R0.75", "R1.00", "R1.25", "S0.25", "S0.33", "S0.50")
    assert fn.FAMILIES == {"R": ("R0.75", "R1.00", "R1.25"), "S": ("S0.25", "S0.33", "S0.50")}
    assert fn.FAMILY_PARAM == {"R": ("k", (0.75, 1.0, 1.25)), "S": ("f", (0.25, 0.33, 0.50))}
    assert (fn.MIN_CHANGED_PER_FOLD, fn.SAME_SIGN_MIN_WINDOWS) == (30, 2)


def test_windows_come_from_the_stage_table():
    assert fn.pooled_window() == STAGES["selection"].signal_window == ("2018-06-01", "2022-12-31")
    assert fn.fold_train_windows() == [("2020", ("2018-06-01", "2020-12-31")),
                                       ("2021", ("2018-06-01", "2021-12-31")),
                                       ("2022", ("2018-06-01", "2022-12-31"))]
    assert [label for label, _ in fn.fold_test_windows()] == ["2021", "2022", "2023"]


def test_rows_in_is_inclusive_and_changed_counts_exits():
    rows = [_row("T0", "2018-06-01", {"R1.00": 0.1}), _row("T1", "2022-12-31", {}),
            _row("T2", "2023-01-02", {"R1.00": 0.1})]
    assert len(fn.rows_in(rows, fn.pooled_window())) == 2
    assert fn.changed_count(rows, "R1.00") == 2
    assert fn.changed_count(rows, "R1.00", against="B") == 2
    assert fn.changed_count(rows, "S0.25") == 0


def test_arm_trades_carry_net_r_and_the_pairing_key():
    [trade] = fn.arm_trades([_row("T0", "2019-03-04", {"R1.00": 0.25}, i=7)], "R1.00")
    assert trade.r_multiple == 1.25 and trade.outcome == "win"
    assert trade.key == ("T0", "S7", "1m", "2019-03-04", "strategy", "bullish")


def test_paired_delta_on_a_constant_shift():
    rows = _year_rows(2019, lambda k, t: {"R1.00": 0.1})
    out = fn.paired_delta(rows, "R1.00", n_resamples=N)
    assert out["delta_r"] == pytest.approx(0.1)
    assert out["ci_lo"] == pytest.approx(0.1) and out["ci_hi"] == pytest.approx(0.1)
    assert out["p"] == 0.0 and (out["n"], out["changed"]) == (40, 40)
    assert set(out) == {"arm", "against", "n", "changed", "delta_r", "ci_lo", "ci_hi", "p"}
    week = fn.week_interval(rows, "R1.00", n_resamples=N)
    assert week["lo"] == pytest.approx(0.1) and week["hi"] == pytest.approx(0.1)


def test_stage0_compares_the_measured_effect_with_the_paired_mde():
    rows = _year_rows(2019, lambda k, t: {"R1.00": 0.2 + 0.01 * (t % 3),
                                          "R0.75": 0.3 if t % 2 else -0.3})
    rows += _year_rows(2023, lambda k, t: {"R1.00": -5.0})       # outside the pooled window
    good = fn.stage0(rows, "R1.00", n_resamples=N)
    assert good["n"] == 40 and good["verdict"] == "RESOLVABLE"
    assert 0 < good["mde_paired"] < good["delta_r"]
    assert fn.stage0(rows, "R0.75", n_resamples=N)["verdict"] == "REFUSED"   # mean 0
    flat = fn.stage0(rows, "S0.25", n_resamples=N)                            # identical to A
    assert flat["delta_r"] == 0.0 and flat["verdict"] == "REFUSED"


def test_fold_train_deltas_follow_the_nested_windows():
    rows = _bucket_rows({"R1.00": (0.3, 0.0, -0.3)})
    assert fn.fold_train_deltas(rows, "R1.00") == pytest.approx([0.3, 0.15, 0.0])


GOOD = {"R0.75": (0.10, 0.10, 0.10), "R1.00": (0.12, 0.12, 0.12), "R1.25": (0.11, 0.11, 0.11)}


def test_stage1_passes_a_plateau_with_family_wide_same_sign():
    out = fn.stage1(_bucket_rows(GOOD), "R",
                    _s0(R0_75=(0.10, OPEN), R1_00=(0.12, OPEN), R1_25=(0.11, OPEN)))
    assert out["adopted"] == "R1.00" and out["verdict"] == "PASS"
    assert out["plateau"]["is_plateau"] is True
    assert out["same_sign"]["windows_by_arm"] == {"R0.75": 3, "R1.00": 3, "R1.25": 3}


@pytest.mark.parametrize("r125_verdict", [OPEN, "REFUSED"])
def test_stage1_family_wide_rule_counts_a_refused_neighbour(r125_verdict):
    rows = _bucket_rows({**GOOD, "R1.25": (-0.10, -0.10, 0.50)})   # folds -0.1, -0.1, +0.1
    out = fn.stage1(rows, "R", _s0(R0_75=(0.10, OPEN), R1_00=(0.12, OPEN),
                                   R1_25=(0.11, r125_verdict)))
    assert out["plateau"]["is_plateau"] is True
    assert out["same_sign"]["windows_by_arm"]["R1.25"] == 1
    assert out["verdict"] == "FAIL"


def test_stage1_rejects_a_spike():
    out = fn.stage1(_bucket_rows(GOOD), "R",
                    _s0(R0_75=(0.02, OPEN), R1_00=(0.12, OPEN), R1_25=(0.11, OPEN)))
    assert out["plateau"]["is_plateau"] is False and out["verdict"] == "FAIL"


def test_stage1_edge_arm_has_one_neighbour_but_faces_the_whole_family():
    rows = _bucket_rows({**GOOD, "R1.25": (-0.10, -0.10, -0.10)})
    out = fn.stage1(rows, "R", _s0(R0_75=(0.13, OPEN), R1_00=(0.12, OPEN), R1_25=(0.05, OPEN)))
    assert out["adopted"] == "R0.75"
    assert out["plateau"]["neighbors"] == {1.0: 0.12} and out["plateau"]["is_plateau"]
    assert out["verdict"] == "FAIL"                           # R1.25 never shares the sign


def test_stage1_adopts_only_an_arm_still_open_after_stage0():
    out = fn.stage1(_bucket_rows(GOOD), "R",
                    _s0(R0_75=(0.10, OPEN), R1_00=(0.12, OPEN), R1_25=(0.13, "REFUSED")))
    assert out["adopted"] == "R1.00"
    none_open = fn.stage1(_bucket_rows(GOOD), "R", _s0(
        R0_75=(0.10, "REFUSED"), R1_00=(0.12, "REFUSED"), R1_25=(0.11, "REFUSED")))
    assert (none_open["adopted"], none_open["verdict"]) == (None, "NO-CANDIDATE")


def _fold_rows(spec):
    """spec: year -> (delta on a changed row, number of changed rows of 40)."""
    rows = []
    for year, (delta, changed) in spec.items():
        rows += _year_rows(year, lambda k, t, d=delta, c=changed: {"R1.00": d if k < c else 0.0})
    return rows


def test_stage2_passes_three_improving_folds():
    out = fn.stage2(_fold_rows({2021: (0.1, 40), 2022: (0.1, 40), 2023: (0.1, 40)}), "R1.00")
    assert (out["gate"], out["improving_folds"], out["verdict"]) == ("PASS", 3, "PASS")
    assert out["mean_delta_r"] == pytest.approx(0.1)
    assert [f["test_year"] for f in out["folds"]] == ["2021", "2022", "2023"]


def test_stage2_a_fold_needs_30_changed_exits_to_count_as_improving():
    # deltas +0.1, +0.0725, -0.01: backtest_wf.gate alone passes (2 of 3 > 0)
    out = fn.stage2(_fold_rows({2021: (0.1, 40), 2022: (0.1, 29), 2023: (-0.01, 40)}), "R1.00")
    assert out["gate"] == "PASS"
    assert [f["improving"] for f in out["folds"]] == [True, False, False]
    assert out["verdict"] == "FAIL"


def test_stage2_a_fold_below_the_degradation_floor_fails():
    out = fn.stage2(_fold_rows({2021: (0.1, 40), 2022: (0.1, 40), 2023: (-0.1, 40)}), "R1.00")
    assert (out["gate"], out["verdict"]) == ("FAIL", "FAIL")


def test_pick_stage3_takes_the_best_mean_and_breaks_ties_to_family_r():
    s2 = lambda m, v="PASS": {"mean_delta_r": m, "verdict": v}    # noqa: E731
    assert fn.pick_stage3({"S0.33": s2(0.05), "R1.00": s2(0.05)}) == "R1.00"
    assert fn.pick_stage3({"R1.00": s2(0.03), "S0.33": s2(0.05)}) == "S0.33"
    assert fn.pick_stage3({"R1.00": s2(0.09, "FAIL"), "S0.33": s2(0.02)}) == "S0.33"
    assert fn.pick_stage3({}) is None


def test_holm_step_down():
    out = fn.holm({"a": 0.01, "b": 0.04, "c": 0.03, "d": None, "e": 0.9})
    assert out["a"] == pytest.approx(0.04)          # 4 x 0.01
    assert out["c"] == pytest.approx(0.09)          # 3 x 0.03
    assert out["b"] == pytest.approx(0.09)          # max(2 x 0.04, 0.09)
    assert out["e"] == pytest.approx(0.9) and out["d"] is None
    assert fn.holm({"a": 0.6, "b": 0.7})["a"] == 1.0   # capped


def test_cells_looked_at_is_the_frozen_150():
    assert fn.cells_looked_at() == 150
    assert fn.cells_looked_at(sensitivity=12) == 162


def test_run_funnel_stops_at_stage0_when_every_arm_is_refused():
    rows = _year_rows(2019, lambda k, t: {}) + _year_rows(2021, lambda k, t: {})
    out = fn.run_funnel(rows, n_resamples=N)
    assert out["stopped_at"] == "stage0" and out["stage3_arm"] is None
    assert out["stage1"] == {} and out["stage2"] == {}
    assert set(out["stage0"]) == set(out["holm"]) == set(out["week_interval"]) == set(fn.CANDIDATES)


def test_run_funnel_carries_one_arm_to_stage3():
    def deltas(k, t):
        noise = 0.01 * (t % 3)
        return {"R0.75": 0.20 + noise, "R1.00": 0.21 + noise, "R1.25": 0.20 + noise}
    rows = [r for year in (2019, 2021, 2022, 2023) for r in _year_rows(year, deltas)]
    out = fn.run_funnel(rows, n_resamples=N)
    assert {a: out["stage0"][a]["verdict"] for a in fn.CANDIDATES} == {
        "R0.75": OPEN, "R1.00": OPEN, "R1.25": OPEN,
        "S0.25": "REFUSED", "S0.33": "REFUSED", "S0.50": "REFUSED"}
    assert out["stage1"]["R"]["verdict"] == "PASS"
    assert out["stage1"]["S"]["verdict"] == "NO-CANDIDATE"
    assert set(out["stage2"]) == {"R1.00"} and out["stage2"]["R1.00"]["verdict"] == "PASS"
    assert (out["stopped_at"], out["stage3_arm"]) == (None, "R1.00")
    assert out["week_interval"]["R1.00"]["lo"] > 0
