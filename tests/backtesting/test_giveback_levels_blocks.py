"""v178 V178-4: the seven descriptive blocks and the side readings on hand-built rows."""
import pytest

from swingbot.core.backtesting import giveback_levels_blocks as bl


def _res(r, *, runner=True, exit_index=20, exit_price=110.0, best=112.0, best_index=18,
         stop=True, gap=0.0, new_best=False, shock=False, moves=3, allowance=0.02,
         floor=None, outcome="win", exit_date="2021-03-05"):
    run = dict(tp1_index=10, best=best, best_index=best_index, allowance_pct=allowance,
               floor_bound=floor, stop_moves=moves, shock=shock,
               gap_r=gap if stop else None, new_best_within_10=new_best if stop else None)
    return {"outcome": outcome, "r_net": r, "exit_index": exit_index, "exit_price": exit_price,
            "exit_date": exit_date, **(run if runner else dict.fromkeys(run))}


def _row(arms, *, hk="4w", direction="bullish", regime="trend", risk=5.0):
    return {"ticker": "AAA", "horizon_key": hk, "direction": direction, "regime": regime,
            "risk": risk, "runner_fraction": 0.5, "arms": arms}


LOSS = dict(runner=False, outcome="loss")
ROWS = [
    _row({"A": _res(1.0, exit_price=108.0), "B": _res(0.8, runner=False),
          "R1.00": _res(1.2, new_best=True, best_index=19, shock=True),
          "S0.33": _res(1.2, floor=True)}),
    _row({arm: _res(-1.0, **LOSS) for arm in ("A", "B", "R1.00", "S0.33")},
         hk="3m", regime="chop"),
    _row({"A": _res(0.5, exit_index=30, exit_date="2021-03-12"), "B": _res(0.6, runner=False),
          "R1.00": _res(0.3, exit_index=25, exit_price=105.0, gap=-0.1, best_index=10,
                        exit_date="2021-03-12"),
          "S0.33": _res(0.3, exit_index=26, exit_price=105.0, floor=False)},
         hk="6m", direction="bearish", regime=None),
]


def test_constants_are_frozen():
    assert (bl.SHAKEOUT_BARS, bl.QUICK_STOP_BARS, bl.TR_SHOCK_ATR, bl.ADX_TREND_MIN) == (10, 3, 2.0, 20.0)


def test_book_sets_arm_and_control_side_by_side_at_fixed_risk():
    out = bl.book(ROWS, "R1.00", risk_dollars=100.0)
    assert out["arm"]["n"] == out["A"]["n"] == 3
    assert out["arm"]["dollars"] == pytest.approx(50.0) and out["A"]["dollars"] == pytest.approx(50.0)
    assert out["arm"]["max_drawdown_dollars"] == pytest.approx(100.0)   # +120, then -100


def test_allowance_share_percentiles_and_none_without_runners():
    out = bl.allowance_share(ROWS, "R1.00")
    assert out["n"] == 2 and out["p10"] == out["p50"] == out["p90"] == pytest.approx(0.02)
    assert bl.allowance_share(ROWS, "B") is None


def test_shakeouts_count_new_best_and_quick_stops():
    out = bl.shakeouts(ROWS, "R1.00")
    assert (out["stop_exits"], out["new_best_10"], out["quick_stops"]) == (2, 1, 1)
    assert out["new_best_share"] == pytest.approx(0.5)


def test_given_back_signs_by_direction_and_counts_gaps():
    out = bl.given_back(ROWS, "R1.00", risk_dollars=100.0)
    # bullish: (112 - 110) / 5 * 0.5 = 0.2R; bearish: max(0, (112 - 105) * -1) = 0
    assert out["max_r"] == pytest.approx(0.2) and out["max_dollars"] == pytest.approx(20.0)
    assert out["gapped"] == 1 and out["gap_r_total"] == pytest.approx(-0.1)


def test_stop_moves_and_worst_week():
    assert bl.stop_moves(ROWS, "R1.00")["max"] == 3
    assert bl.stop_moves(ROWS, "B") is None
    assert bl.worst_week(ROWS, "R1.00", risk_dollars=100.0) == {
        "week": "2021-W09", "dollars": pytest.approx(20.0), "runners": 1}


def test_shock_split_and_regime_split_pair_against_control_a():
    out = bl.shock_split(ROWS, "R1.00")
    assert out["shock"] == {"n": 1, "delta_r": pytest.approx(0.2)}
    assert out["calm"] == {"n": 1, "delta_r": pytest.approx(-0.2)}
    reg = bl.regime_split(ROWS, "R1.00")
    assert reg["trend"]["delta_r"] == pytest.approx(0.2) and reg["chop"]["n"] == 1
    assert reg["unknown"] == 1


def test_horizon_concentration_versus_b_and_flips():
    assert list(bl.per_horizon(ROWS, "R1.00")) == ["4w", "3m", "6m"]     # ALL_HORIZONS order
    conc = bl.concentration(ROWS, "R1.00")
    assert conc["top2_horizon_share"] is None                           # total ΔR is ~0
    assert conc["long"]["n"] == 2 and conc["short"]["delta_r"] == pytest.approx(-0.2)
    assert bl.versus_b(ROWS, "R1.00")["delta_r"] == pytest.approx((0.4 + 0.0 - 0.3) / 3)
    assert bl.flips(ROWS, "R1.00") == 0


def test_near_duplicate_only_for_s_arms_with_r100_present():
    assert bl.near_duplicate(ROWS, "S0.33") == {"floor_bound_share": pytest.approx(0.5),
                                                "differs_from_r100": 1}
    assert bl.near_duplicate(ROWS, "R1.00") is None
    no_r = [{**r, "arms": {k: r["arms"][k] for k in ("A", "S0.33")}} for r in ROWS]
    assert bl.near_duplicate(no_r, "S0.33") is None                    # validation rows


def test_describe_arm_carries_seven_blocks_and_side_readings():
    out = bl.describe_arm(ROWS, "S0.33", risk_dollars=100.0)
    assert list(out)[:7] == ["1_book", "2_allowance", "3_shakeouts", "4_given_back",
                             "5_stop_moves", "6_worst_week", "7_shock"]
    assert {"per_horizon", "concentration", "versus_b", "near_duplicate", "regime", "flips"} <= set(out)


def test_top2_share_and_empty_blocks():
    rows = [_row({"A": _res(0.0), "R1.00": _res(1.0)}, hk="2w"),
            _row({"A": _res(0.0), "R1.00": _res(0.5)}, hk="4w"),
            _row({"A": _res(0.0), "R1.00": _res(-0.5)}, hk="3m")]
    assert bl.concentration(rows, "R1.00")["top2_horizon_share"] == pytest.approx(1.5)
    none = [_row({"A": _res(0.0, **LOSS), "B": _res(0.0, **LOSS)})]
    assert bl.worst_week(none, "B", risk_dollars=1.0) == {"week": None, "dollars": 0.0, "runners": 0}
    assert bl.given_back(none, "B", risk_dollars=1.0)["max_r"] is None
