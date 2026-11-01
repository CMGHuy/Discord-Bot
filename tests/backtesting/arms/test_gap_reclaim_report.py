"""V192-17: the re-priced-fixed permutation null, the Stage 1 cell, the ambiguous-bar
sensitivity, the re-priced dollar view and the report."""
import dataclasses

import numpy as np
import pytest

from swingbot.core.backtesting import acceptance
from swingbot.core.backtesting.arms import gap_reclaim_census as census_mod
from swingbot.core.backtesting.arms import gap_reclaim_clauses as grc
from swingbot.core.backtesting.arms import selection
from swingbot.core.planning import gap_reclaim as gr
from tests.backtesting.arms.test_gap_reclaim_clauses import _date, mk, veto_arms

FAST = dict(n_resamples=300, seed=42)


def random_veto(remove="loss", n_tickers=40, seed=7):
    """Per ticker 10..16 trades (lengths differ, so no shift is the identity for every ticker),
    outcomes drawn at 45% wins; the veto removes the first two trades of outcome ``remove`` and
    re-prices the last trade (same outcome, +0.2R)."""
    rng = np.random.default_rng(seed)
    baseline, component, repriced = [], [], set()
    for t in range(n_tickers):
        ticker = f"T{t:02d}"
        trades = [mk(ticker, "win" if w else "loss", _date(t * 20 + i))
                  for i, w in enumerate(rng.random(10 + t % 7) < 0.45)]
        gone = [trade.key for trade in trades[:-1] if trade.outcome == remove][:2]
        held = trades[-1]
        repriced.add(held.key)
        baseline.extend(trades)
        component.extend(trade for trade in trades[:-1] if trade.key not in gone)
        component.append(dataclasses.replace(held, r_multiple=held.r_multiple + 0.2))
    return baseline, component, repriced


# --- repriced_permutation ----------------------------------------------------------------------

def test_shift_zero_rebuilds_the_component_exactly():
    baseline, component, repriced = veto_arms()
    split = grc.strata_split(baseline, component, repriced)
    held = {bt.key for bt, _ in split["repriced"]}
    groups = grc._rotatable(baseline, held, {t.key for t in split["removed"]})
    fixed = [ct for _, ct in split["repriced"]] + list(split["added"])
    rebuilt = grc._null_arm(groups, fixed, {t.key: t for t in component}, 0)
    assert sorted(rebuilt, key=lambda t: t.key) == sorted(component, key=lambda t: t.key)


def test_removing_losers_is_distinguishable_from_luck():
    out = grc.repriced_permutation(*random_veto("loss"), n_perm=200, seed=42)
    assert out["observed_delta_win_rate_pp"] > 0 and out["p_value"] < 0.05
    assert (out["n"], out["seed"], out["shift_range"], out["repriced"]) == (200, 42, [20, 200], 40)


def test_removing_winners_is_not():
    out = grc.repriced_permutation(*random_veto("win"), n_perm=200, seed=42)
    assert out["p_value"] > 0.05


def test_repriced_and_added_trades_sit_in_every_null_draw():
    baseline, component, repriced = veto_arms(n_tickers=5)
    split = grc.strata_split(baseline, component, repriced)
    expected = {ct for _, ct in split["repriced"]} | set(split["added"])
    seen = []
    grc.repriced_permutation(baseline, component, repriced, n_perm=30, seed=1,
                             statistic=lambda b, c: seen.append(c) or 0.0)
    null_arms = seen[1:]                                   # seen[0] is the observed call
    assert len(null_arms) == 30
    assert all(expected <= set(arm) for arm in null_arms)
    assert all(not ({bt for bt, _ in split["repriced"]} & set(arm)) for arm in null_arms)


def test_a_repriced_outcome_flip_is_allowed_unlike_the_v72_null():
    baseline, component, repriced = veto_arms(n_tickers=5)
    flipped = [dataclasses.replace(t, outcome="loss", r_multiple=-1.0)
               if t.key in repriced else t for t in component]
    out = grc.repriced_permutation(baseline, flipped, repriced, n_perm=20, seed=3)
    assert out["n_valid"] == 20


def test_the_null_is_reproducible_for_one_seed():
    arms = random_veto("loss")
    assert grc.repriced_permutation(*arms, n_perm=50, seed=9) == grc.repriced_permutation(*arms, n_perm=50, seed=9)


# --- selection_cell ----------------------------------------------------------------------------

def _shifted(trades, by):
    return [dataclasses.replace(t, r_multiple=t.r_multiple + by) for t in trades]


@pytest.mark.parametrize("by,eligible", [(0.0, True), (-0.005, True), (-0.02, False)])   # -0.01 itself is a float tie: not pinned
def test_the_expectancy_floor_is_the_point_delta(by, eligible):
    baseline, _, _ = veto_arms()
    cell = grc.selection_cell(0.25, baseline, _shifted(baseline, by), resolvable=True, **FAST)
    assert cell.eligible is eligible
    assert cell.failed == ([] if eligible else ["expectancy_floor"])
    assert cell.disclosure["delta_expectancy_r"] == pytest.approx(by)


def test_an_mde_refused_cell_is_ineligible_and_says_why():
    baseline, component, _ = veto_arms()
    cell = grc.selection_cell(0.10, baseline, component, resolvable=False, **FAST)
    assert cell.eligible is False and cell.failed == ["mde"]


def test_the_cell_carries_standardised_dwr_component_expr_and_a_week_interval():
    baseline, component, _ = veto_arms()
    cell = grc.selection_cell(0.10, baseline, component, resolvable=True, **FAST)
    assert cell.value == 0.10
    assert cell.delta_win_rate_pp == pytest.approx(acceptance.delta_standardised_win_rate(baseline, component))
    assert cell.expectancy_r == pytest.approx(acceptance.expectancy_r(component))
    lo, hi = cell.disclosure["delta_win_rate_ci"]
    assert lo <= cell.delta_win_rate_pp <= hi
    assert cell.disclosure["removed"] == 60 and cell.disclosure["added"] == 30


def test_equal_cells_select_the_smaller_g():
    baseline, component, _ = veto_arms()
    cells = [grc.selection_cell(g, baseline, component, resolvable=True, **FAST) for g in (0.50, 0.10, 0.25)]
    result = selection.select_cell(cells, "GAP_RECLAIM_ATR", tie="smaller")
    assert (result.verdict, result.selected) == (selection.SELECTED, 0.10)


def test_a_lone_good_cell_between_flat_ones_is_a_spike():
    baseline, component, _ = veto_arms()
    flat = _shifted(baseline, -0.005)
    cells = [grc.selection_cell(0.10, baseline, flat, resolvable=True, **FAST),
             grc.selection_cell(0.25, baseline, component, resolvable=True, **FAST),
             grc.selection_cell(0.50, baseline, flat, resolvable=True, **FAST)]
    assert all(cell.eligible for cell in cells)
    assert selection.select_cell(cells, "GAP_RECLAIM_ATR", tie="smaller").verdict == selection.SPIKE


# --- ambiguous_sensitivity ---------------------------------------------------------------------

def test_ambiguous_fills_counted_as_cancels():
    baseline, component, repriced = veto_arms(n_tickers=10)
    ambiguous = set(list(sorted(repriced))[:4])
    out = grc.ambiguous_sensitivity(baseline, component, ambiguous)
    assert out["ambiguous_n"] == 4
    assert out["as_fills"]["component_n"] == len(component)
    assert out["as_cancels"]["component_n"] == len(component) - 4
    assert out["as_fills"]["delta_win_rate_pp"] == pytest.approx(
        acceptance.delta_standardised_win_rate(baseline, component))


def test_no_ambiguous_bar_leaves_both_readings_equal():
    baseline, component, _ = veto_arms(n_tickers=5)
    out = grc.ambiguous_sensitivity(baseline, component, set())
    assert out["ambiguous_n"] == 0 and out["as_fills"] == out["as_cancels"]


# --- repriced_dollars and report ---------------------------------------------------------------

def _census_for(baseline, repriced, *, open_price=99.0, fill=100.01, ambiguous=()):
    rows = []
    for trade in baseline:
        if trade.key in repriced:
            rows.append({"ticker": trade.ticker, "strategy": trade.strategy, "horizon_key": trade.horizon_key,
                         "signal_date": trade.entry_date, "source": trade.source, "direction": trade.direction,
                         "entry": 100.0, "stop": 95.0, "open_price": open_price, "atr": 2.0,
                         "reclaim_level": 99.8, "gap_atr": 0.5, "decision": gr.RECLAIM_WAIT,
                         "reclaimed": True, "ambiguous": trade.key in ambiguous, "fill_price": fill})
    return rows


def test_repriced_dollars_price_each_arm_in_its_own_risk_unit():
    baseline, component, repriced = veto_arms(n_tickers=1)        # one re-priced trade: +2.0R -> +2.2R
    split = grc.strata_split(baseline, component, repriced)
    out = grc.repriced_dollars(split, _census_for(baseline, repriced), reference_account=100_000.0, risk_pct=1.0)
    # risk $1,000 on E 100 / stop 95 -> 200 shares; baseline 2.0R x (99 - 95) x 200; component 2.2R x 5.01 x 200
    assert out["n"] == 1 and out["risk_dollars"] == 1000.0
    assert out["baseline_dollars"] == pytest.approx(1600.0)
    assert out["component_dollars"] == pytest.approx(2204.4)
    assert out["delta_dollars"] == pytest.approx(604.4) and out["mean_delta_dollars"] == pytest.approx(604.4)


def test_repriced_dollars_with_no_repriced_trade():
    baseline, component, _ = veto_arms(n_tickers=2)
    out = grc.repriced_dollars(grc.strata_split(baseline, component, set()), [],
                               reference_account=100_000.0, risk_pct=1.0)
    assert out["n"] == 0 and out["delta_dollars"] == 0.0 and out["mean_delta_dollars"] is None


def _full_report():
    baseline, component, repriced = veto_arms()
    rows = _census_for(baseline, repriced, ambiguous=set(list(sorted(repriced))[:3]))
    return grc.report(baseline, component, rows, **FAST)


def test_the_report_carries_every_spec_section():
    out = _full_report()
    assert set(out) == {"n", "win_rate", "expectancy_r", "delta_win_rate_pp", "delta_expectancy_r",
                        "outcome_flips", "strata", "repriced_dollars", "ambiguous_sensitivity", "census",
                        "splits", "removed_top2_horizon_share", "earnings_proximity"}
    assert out["n"] == {"baseline": 300, "component": 270}


def test_the_report_sections_hold_the_pair_numbers():
    out = _full_report()
    assert out["delta_win_rate_pp"]["lo"] <= out["delta_win_rate_pp"]["point"] <= out["delta_win_rate_pp"]["hi"]
    assert [row["stratum"] for row in out["strata"]] == list(grc.STRATA)
    assert out["repriced_dollars"]["n"] == 30 and out["ambiguous_sensitivity"]["ambiguous_n"] == 3
    assert out["census"]["total"]["reclaimed"] == 30


def test_the_report_splits_concentration_and_earnings_disclosure():
    out = _full_report()
    assert set(out["splits"]) == set(grc.SPLIT_FIELDS) == {"source", "direction", "horizon_key"}
    assert out["splits"]["direction"]["bullish"]["n_baseline"] == 300
    assert out["removed_top2_horizon_share"] == 1.0
    assert out["earnings_proximity"] == grc.EARNINGS_UNAVAILABLE
    assert "no as-of earnings archive" in grc.EARNINGS_UNAVAILABLE


def test_the_report_of_an_empty_pair_does_not_crash():
    out = grc.report([], [], [], **FAST)
    assert out["n"] == {"baseline": 0, "component": 0} and out["delta_win_rate_pp"]["point"] is None
    assert out["census"]["verdict"] == census_mod.ZERO_DIFF and out["removed_top2_horizon_share"] == 0.0
