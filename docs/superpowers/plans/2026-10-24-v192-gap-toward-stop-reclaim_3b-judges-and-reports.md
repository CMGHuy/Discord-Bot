# v192 — Wait for a reclaim when a market plan's next open gaps toward its stop, Part 3b: judges and reports

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`.

**Bump:** bot patch
**Edge:** expectancy — see the index.
**Spec:** [2026-10-24-v192-gap-toward-stop-reclaim-design.md](../specs/2026-10-24-v192-gap-toward-stop-reclaim-design.md)
**Index:** [2026-10-24-v192-gap-toward-stop-reclaim_0-index.md](2026-10-24-v192-gap-toward-stop-reclaim_0-index.md) — Goal, Global Constraints, § Contracts, Review Focus, Parallelisation and the task ledger live there and bind every task below. **Never read a part whole:** `grep -n "^### Task V192-18:" -A 400 <this file>`.

**Scope of this part (V192-17..V192-19):** the continuation of part 3 (`_3-measurement-code.md`, V192-14..V192-16), split off because part 3 would pass 1500 lines. The re-priced-fixed permutation null, the Stage 1 cell, the ambiguous-bar sensitivity and the report (V192-17); the judges' `--gap-reclaim` wiring and the report script (V192-18); the autopsy `--entry-type` filter for the pre-TRAIN disclosure (V192-19). The "facts every task relies on" list at the top of part 3 applies here unchanged.

**Where commands run:** every command below runs from the worktree root `.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim` (created in V192-1). Subagent shells reset their cwd between calls: prefix each command with `cd E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim &&`. Never edit the main tree's files from a task.

**Complexity:** after every code task run `python scripts/dev/complexity_gate.py`; it must pass (index § Global Constraints).

---

# Phase 9 (continued) — Null, selection and the report

### Task V192-17: Permutation null, Stage 1 cell, ambiguous sensitivity, report

**Model:** opus — the permutation null and the Stage 1 eligibility decide the one shot; the re-priced dollar view must price two different R units correctly.

**Files:**
- Modify: `swingbot/core/backtesting/arms/gap_reclaim_clauses.py` (append; created by V192-16)
- Test: `tests/backtesting/arms/test_gap_reclaim_report.py` (create)

**Interfaces:**
- Consumes: `strata_split`, `strata_rows`, `CLUSTER` (V192-16); `gap_reclaim_census.repriced_keys`, `ambiguous_keys`, `row_key`, `reachability_summary` and the census row dict shape (`entry`, `stop`, `open_price`, `fill_price`, `reclaimed`, `ambiguous`, key fields) (V192-15); existing `acceptance.bootstrap_delta(..., cluster=)`, `delta_standardised_win_rate`, `delta_expectancy_r`, `NON_INFERIORITY_R = -0.01`, `selection.CellEval`, `selection.removed_disclosure`, `selection.select_cell(cells, param_name, *, tie=)`; test fixtures `mk`, `_date`, `veto_arms` from `tests/backtesting/arms/test_gap_reclaim_clauses.py` (V192-16).
- Produces (index § Contracts, plus three in-part names V192-18 reads):
  - `SHIFT_RANGE = (20, 200)` (the v72 removal-label null's range, `permutation_test.SHIFT_RANGE`).
  - `repriced_permutation(baseline, component, repriced, *, n_perm=200, seed=42, statistic=delta_standardised_win_rate) -> dict` — keys `observed_delta_win_rate_pp, p_value, n, n_valid, seed, shift_range, removed, repriced, added, statistic, instrument`.
  - `selection_cell(value, baseline, component, *, resolvable, n_resamples, seed) -> CellEval` — eligible iff point ΔExpR ≥ `NON_INFERIORITY_R` (failure label `"expectancy_floor"`) and resolvable (`"mde"`); `delta_win_rate_pp` standardised; `expectancy_r` of the component (what `select_cell`'s plateau scores).
  - `ambiguous_sensitivity(baseline, component, ambiguous) -> dict` — keys `ambiguous_n, as_fills, as_cancels` (each `{component_n, win_rate, expectancy_r, delta_win_rate_pp, delta_expectancy_r}`).
  - `repriced_dollars(split, census_rows, *, reference_account, risk_pct) -> dict`.
  - `report(baseline, component, census_rows, *, n_resamples, seed, reference_account=100_000.0, risk_pct=1.0) -> dict` — keys `n, win_rate, expectancy_r, delta_win_rate_pp, delta_expectancy_r, outcome_flips, strata, repriced_dollars, ambiguous_sensitivity, census, splits, removed_top2_horizon_share, earnings_proximity`.
  - `EARNINGS_UNAVAILABLE` (the recorded reason string); `SPLIT_FIELDS = ("source", "direction", "horizon_key")`.

**The null (index § Global Constraints, clause 5).** v72's `permutation_test.arm_pair_permutation` refuses any pair with changed outcomes and rotates removal labels over the whole baseline. Here re-priced trades are **held at their component version in every draw**, added trades are kept in every draw, and the removal labels rotate (ticker-circular shift, one shift per draw, the v72 range) over the remaining baseline trades only. A kept trade enters the null arm as its component version when it has one, else (a really-removed trade the rotation keeps) as its baseline version, so shift 0 reproduces the component exactly. The null therefore asks only "would removing a different set of this many trades per ticker lift win rate as much".

**Stage 1 (spec § Gate).** The winner is the `g` with the highest whole-window fold-train ΔWR among cells with point ΔExpR ≥ −0.01R; ties to the smaller `g`; `selection.select_cell(..., "GAP_RECLAIM_ATR", tie="smaller")` applies the existing plateau check (`backtest_wf.PLATEAU_TOLERANCE_R = 0.03` on component ExpR; an edge cell is adoptable with its one neighbour; a spike does not proceed). The geometry, volume and mechanism clauses are not Stage 1 eligibility here (the spec names ΔExpR only); they are scored at Stage 3. The cell's disclosure carries the week-cluster ΔWR interval and `selection.removed_disclosure`.

**Re-priced dollars (spec § Reporting).** Sizing is unchanged live: `gap_sizing.size_for_plan` sizes on `E` and the stop, so both arms hold `shares = risk$ / |E − stop|` with `risk$ = reference_account × risk_pct / 100`. A baseline twin filled at the open books `r × |open − stop| × shares`; the re-priced trade filled at the reclaim price books `r × |fill − stop| × shares`. That is the one view in which the two arms' R units (`Open − stop` vs `E − stop`) compare.

- [ ] **Step 1: Write the failing tests** — create `tests/backtesting/arms/test_gap_reclaim_report.py`

```python
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


def test_the_report_carries_every_spec_section():
    baseline, component, repriced = veto_arms()
    rows = _census_for(baseline, repriced, ambiguous=set(list(sorted(repriced))[:3]))
    out = grc.report(baseline, component, rows, **FAST)
    assert set(out) == {"n", "win_rate", "expectancy_r", "delta_win_rate_pp", "delta_expectancy_r",
                        "outcome_flips", "strata", "repriced_dollars", "ambiguous_sensitivity", "census",
                        "splits", "removed_top2_horizon_share", "earnings_proximity"}
    assert out["n"] == {"baseline": 300, "component": 270}
    assert out["delta_win_rate_pp"]["lo"] <= out["delta_win_rate_pp"]["point"] <= out["delta_win_rate_pp"]["hi"]
    assert [row["stratum"] for row in out["strata"]] == list(grc.STRATA)
    assert out["repriced_dollars"]["n"] == 30 and out["ambiguous_sensitivity"]["ambiguous_n"] == 3
    assert out["census"]["total"]["reclaimed"] == 30
    assert set(out["splits"]) == set(grc.SPLIT_FIELDS) == {"source", "direction", "horizon_key"}
    assert out["splits"]["direction"]["bullish"]["n_baseline"] == 300
    assert out["removed_top2_horizon_share"] == 1.0
    assert out["earnings_proximity"] == grc.EARNINGS_UNAVAILABLE
    assert "no as-of earnings archive" in grc.EARNINGS_UNAVAILABLE


def test_the_report_of_an_empty_pair_does_not_crash():
    out = grc.report([], [], [], **FAST)
    assert out["n"] == {"baseline": 0, "component": 0} and out["delta_win_rate_pp"]["point"] is None
    assert out["census"]["verdict"] == census_mod.ZERO_DIFF and out["removed_top2_horizon_share"] == 0.0
```

- [ ] **Step 2: Run them to see them fail**

```bash
python scripts/dev/testrun.py file tests/backtesting/arms/test_gap_reclaim_report.py
```

Expected: FAIL — `AttributeError: module '...gap_reclaim_clauses' has no attribute 'repriced_permutation'` (and the other new names).

- [ ] **Step 3: Append to `swingbot/core/backtesting/arms/gap_reclaim_clauses.py`**

Extend the imports at the top of the module (keep V192-16's):

```python
from collections import Counter

import numpy as np

from swingbot.core.backtesting.acceptance import (NON_INFERIORITY_R, bootstrap_delta, delta_expectancy_r,
                                                  delta_standardised_win_rate)
from swingbot.core.backtesting.arms import gap_reclaim_census, selection
```

Then append:

```python
#: The v72 removal-label null's circular-shift range (permutation_test.SHIFT_RANGE): >= 20 so
#: nothing almost aligns.
SHIFT_RANGE = (20, 200)
SPLIT_FIELDS = ("source", "direction", "horizon_key")
EARNINGS_UNAVAILABLE = ("unavailable: the v1 replay row (ArmTrade) carries no earnings date and no "
                        "as-of earnings archive exists (compression_research.py:7-13); the earnings "
                        "CSVs hold final report dates, so a cut on them would be lookahead")


def _order(trade) -> tuple:
    return (trade.ticker, trade.entry_date, trade.strategy, trade.horizon_key,
            trade.source or "", trade.direction or "")


def _rotatable(baseline, held: set, removed_keys: set) -> list:
    """Per ticker, in date order, the baseline trades the null may relabel (every baseline trade
    except the held re-priced ones) and their real removal labels."""
    groups: dict = {}
    for trade in sorted((t for t in baseline if t.key not in held), key=_order):
        groups.setdefault(trade.ticker, []).append(trade)
    return [(trades, np.array([t.key in removed_keys for t in trades])) for trades in groups.values()]


def _null_arm(groups, fixed, c_by: dict, shift: int) -> list:
    """One null component: the fixed trades plus every rotatable trade whose shifted label keeps
    it, as its component version when it has one (else its baseline version)."""
    arm = list(fixed)
    for trades, labels in groups:
        rolled = np.roll(labels, shift % len(labels))
        arm.extend(c_by.get(t.key, t) for t, gone in zip(trades, rolled) if not gone)
    return arm


def repriced_permutation(baseline, component, repriced: set, *, n_perm: int = 200, seed: int = 42,
                         statistic=delta_standardised_win_rate) -> dict:
    """v72 clause 5 for the v192 arms: the removal-label null of
    permutation_test.arm_pair_permutation (ticker-circular shift of the removed labels over the
    baseline, one shift per draw), with the re-priced trades held at their component version and
    the added trades kept in every draw, so the null rotates only which trades the veto removes.
    p = share of valid null draws at or above the observed statistic."""
    split = strata_split(baseline, component, repriced)
    held = {bt.key for bt, _ in split["repriced"]}
    fixed = [ct for _, ct in split["repriced"]] + list(split["added"])
    groups = _rotatable(baseline, held, {t.key for t in split["removed"]})
    c_by = {t.key: t for t in component}
    observed = statistic(baseline, component)
    shifts = np.random.default_rng(seed).integers(*SHIFT_RANGE, size=n_perm)
    null = [statistic(baseline, _null_arm(groups, fixed, c_by, int(shift))) for shift in shifts]
    valid = [value for value in null if value is not None]
    p = None if observed is None or not valid else float(np.mean([value >= observed for value in valid]))
    return {"observed_delta_win_rate_pp": observed, "p_value": p, "n": int(n_perm), "n_valid": len(valid),
            "seed": seed, "shift_range": list(SHIFT_RANGE), "removed": len(split["removed"]),
            "repriced": len(split["repriced"]), "added": len(split["added"]),
            "statistic": getattr(statistic, "__name__", "custom"),
            "instrument": "v192: v72 removal-label null, re-priced trades held at their component "
                          "version and added trades kept in every draw"}


def _interval(baseline, component, statistic, n_resamples: int, seed: int) -> dict:
    res = bootstrap_delta(baseline, component, statistic, n_resamples=n_resamples, seed=seed, cluster=CLUSTER)
    return {"point": res.point, "lo": res.lo, "hi": res.hi, "p_greater_than_zero": res.p_greater_than_zero}


def selection_cell(value, baseline, component, *, resolvable: bool, n_resamples: int,
                   seed: int) -> selection.CellEval:
    """Stage 1's cell for one g: eligible iff the point dExpR is at or above the -0.01R floor
    and Stage 0 found it resolvable. dWR is the standardised whole-window statistic; the
    expectancy is the component's (what select_cell's plateau check scores)."""
    d_exp = delta_expectancy_r(baseline, component)
    failed = [] if d_exp is not None and d_exp >= NON_INFERIORITY_R else ["expectancy_floor"]
    if not resolvable:
        failed.append("mde")
    ci = _interval(baseline, component, delta_standardised_win_rate, n_resamples, seed)
    disclosure = {"delta_expectancy_r": d_exp, "delta_win_rate_ci": [ci["lo"], ci["hi"]],
                  **selection.removed_disclosure(baseline, component)}
    return selection.CellEval(value, not failed, delta_standardised_win_rate(baseline, component),
                              acceptance.expectancy_r(component), failed, disclosure)


def _reading(baseline, component) -> dict:
    return {"component_n": len(component), "win_rate": win_rate(component),
            "expectancy_r": expectancy_r(component),
            "delta_win_rate_pp": delta_standardised_win_rate(baseline, component),
            "delta_expectancy_r": delta_expectancy_r(baseline, component)}


def ambiguous_sensitivity(baseline, component, ambiguous: set) -> dict:
    """The component with ambiguous reclaim bars read two ways: as booked (filled at E, then
    stopped, -1R) and as gap_no_reclaim cancels (the trade dropped)."""
    kept = [t for t in component if t.key not in ambiguous]
    return {"ambiguous_n": len(component) - len(kept), "as_fills": _reading(baseline, component),
            "as_cancels": _reading(baseline, kept)}


def _dollars(trade, fill: float, row: dict, shares: float) -> float:
    return trade.r_multiple * abs(fill - row["stop"]) * shares


def repriced_dollars(split: dict, census_rows, *, reference_account: float, risk_pct: float) -> dict:
    """Re-priced trades in dollars on a fixed reference account. Both arms hold the plan's own
    size, risk$ / |E - stop|; the baseline twin filled at the open, the re-priced trade at the
    reclaim fill, so each R converts at its own risk unit."""
    rows = {gap_reclaim_census.row_key(row): row for row in census_rows if row["reclaimed"]}
    risk = reference_account * risk_pct / 100.0
    base_total = comp_total = 0.0
    n = 0
    for bt, ct in split["repriced"]:
        row = rows.get(bt.key)
        if row is None or bt.r_multiple is None or ct.r_multiple is None:
            continue
        shares = risk / abs(row["entry"] - row["stop"])
        base_total += _dollars(bt, row["open_price"], row, shares)
        comp_total += _dollars(ct, row["fill_price"], row, shares)
        n += 1
    delta = comp_total - base_total
    return {"n": n, "reference_account": reference_account, "risk_pct": risk_pct, "risk_dollars": risk,
            "baseline_dollars": round(base_total, 2), "component_dollars": round(comp_total, 2),
            "delta_dollars": round(delta, 2), "mean_delta_dollars": round(delta / n, 2) if n else None}


def _pair_row(baseline, component) -> dict:
    return {"n_baseline": len(baseline), "n_component": len(component),
            "baseline_win_rate": win_rate(baseline), "component_win_rate": win_rate(component),
            "baseline_expectancy_r": expectancy_r(baseline), "component_expectancy_r": expectancy_r(component),
            "delta_win_rate_pp": delta_standardised_win_rate(baseline, component),
            "delta_expectancy_r": delta_expectancy_r(baseline, component)}


def _split_by(baseline, component, field: str) -> dict:
    """Descriptive split; it cannot rescue a pooled fail (spec § Gate)."""
    label = lambda trade: str(getattr(trade, field))       # noqa: E731
    values = sorted({label(t) for t in [*baseline, *component]})
    return {value: _pair_row([t for t in baseline if label(t) == value],
                             [t for t in component if label(t) == value]) for value in values}


def _top2_share(trades) -> float:
    counts = Counter(t.horizon_key for t in trades)
    return sum(n for _, n in counts.most_common(2)) / len(trades) if trades else 0.0


def report(baseline, component, census_rows, *, n_resamples: int, seed: int,
           reference_account: float = 100_000.0, risk_pct: float = 1.0) -> dict:
    """Every number spec § Reporting asks for at one stage, from one arm pair and its census."""
    split = strata_split(baseline, component, gap_reclaim_census.repriced_keys(census_rows))
    return {"n": {"baseline": len(baseline), "component": len(component)},
            "win_rate": {"baseline": win_rate(baseline), "component": win_rate(component)},
            "expectancy_r": {"baseline": expectancy_r(baseline), "component": expectancy_r(component)},
            "delta_win_rate_pp": _interval(baseline, component, delta_standardised_win_rate, n_resamples, seed),
            "delta_expectancy_r": _interval(baseline, component, delta_expectancy_r, n_resamples, seed),
            "outcome_flips": len(split["changed"]),
            "strata": strata_rows(split),
            "repriced_dollars": repriced_dollars(split, census_rows, reference_account=reference_account,
                                                 risk_pct=risk_pct),
            "ambiguous_sensitivity": ambiguous_sensitivity(baseline, component,
                                                           gap_reclaim_census.ambiguous_keys(census_rows)),
            "census": gap_reclaim_census.reachability_summary(census_rows),
            "splits": {field: _split_by(baseline, component, field) for field in SPLIT_FIELDS},
            "removed_top2_horizon_share": _top2_share(split["removed"]),
            "earnings_proximity": EARNINGS_UNAVAILABLE}
```

Check the dollar test by hand: risk $1,000 (100,000 × 1%); `|E − stop| = 5` → 200 shares; baseline twin `2.0 × |99 − 95| × 200 = 1,600`; re-priced `2.2 × |100.01 − 95| × 200 = 2.2 × 5.01 × 200 = 2,204.4`; delta `604.4`. Report numbers for `veto_arms()`: baseline 300, component 270 (240 kept + 30 added); every removed trade is on `4w`, so the top-two share is 1.0.

`acceptance.bootstrap_delta` on two empty arms returns `point=None` without resampling (`draws.size == 0`), which `test_the_report_of_an_empty_pair_does_not_crash` relies on.

- [ ] **Step 4: Run the report tests, V192-15/16's tests and the gate**

```bash
python scripts/dev/testrun.py file tests/backtesting/arms/test_gap_reclaim_report.py
python scripts/dev/testrun.py file tests/backtesting/arms/test_gap_reclaim_clauses.py
python scripts/dev/testrun.py file tests/backtesting/arms/test_gap_reclaim_census.py
python scripts/dev/complexity_gate.py
```

Expected: `0 failed` each; the gate passes (`repriced_permutation` cc 5, `repriced_dollars` cc 6, `report` cc 2). If `test_removing_losers_is_distinguishable_from_luck` lands at `p ≥ 0.05`, print `out` and the null's spread before touching anything: the fixture, not the rule, is what may be changed (more tickers), and the rule's null must keep the held and added trades in every draw.

- [ ] **Step 5: Commit (in the worktree)**

```bash
git add swingbot/core/backtesting/arms/gap_reclaim_clauses.py tests/backtesting/arms/test_gap_reclaim_report.py
git commit -m "feat(v192): re-priced-fixed permutation null, Stage 1 cell on the dExpR floor, ambiguous sensitivity, dollar view and report"
```

# Phase 10 — The judges, the report script and the autopsy filter

### Task V192-18: CLI: `validate_component --gap-reclaim`, `permutation_test --gap-reclaim`, `gap_reclaim_report.py`

**Model:** sonnet — wiring already-tested functions into three CLIs behind one flag each, with refusals and tests; no new rule.

**Files:**
- Modify: `scripts/backtest/validate_component.py` (import line `:18`; `_mde_design` `:76-88`; `stage_reachability` (as V192-14 left it); `_evaluate` `:194-196`; `stage_validation` `:214`; `_selection_axis` `:288-292`; `_selection_cells` `:335-348`; `main` `:380-404`; new helpers `_gap_reclaim`, `_cluster`, `_gap_sidecar`, `_repriced_for`, `_refuse_no_sidecar`, `_gap_reclaim_reachability`, `_selection_cell_for`, `_gap_reclaim_conflict`, `_dump`)
- Modify: `scripts/backtest/permutation_test.py` (`_arms_main` `:192-207`, `_parser` `:210-223`, `main` `:325-335`; new `_gap_reclaim_null`, `_arm_null`)
- Create: `scripts/reports/gap_reclaim_report.py`
- Test: `tests/backtest_scripts/test_gap_reclaim_cli.py` (create)

**Interfaces:**
- Consumes: `gap_reclaim_census.load_sidecar`, `sidecar_path`, `repriced_keys`, `reachability_summary`, `REACHABLE` (V192-15); `gap_reclaim_clauses.evaluate_gap_reclaim`, `selection_cell`, `repriced_permutation`, `report`, `CLUSTER`, `STRATA` (V192-16, V192-17); `acceptance.mde_paired(..., cluster=)` (existing); `regime2.regime_series(spy_df) -> pd.Series` (`swingbot/core/edge/regime2.py:52`); `training_data.load_daily`, `config.MARKET_REGIME_TICKER`, `fetch_backtest_data.add_data_source_arg` / `apply_data_source` (existing); the stamp key `baseline_knob_delta` (V192-14). Test fixtures: `veto_arms`, `_census_for` (V192-16, V192-17 test modules), `tests.backtesting.test_validate_component_stamps.vc` (existing).
- Produces (index § Contracts, CLI):
  - `validate_component.py --gap-reclaim` — **reachability**: the census summary is printed (and written with `--out-json`) beside the existing zero-diff check; `refused:zero-diff` when no plan armed the veto. **mde**: the paired MDE uses `cluster="week"`. **selection**: axis `GAP_RECLAIM_ATR` / label `g` / tie `smaller`, each cell through `selection_cell`. **validation**: `evaluate_gap_reclaim` with the sidecar's re-priced keys. Every stage that reads the census refuses `refused:no-gap-reclaim-sidecar` when `<arms stem>.gap_reclaim.json` is missing or carries another `knob_delta` than the arms' stamp. `--gap-reclaim` with `--gate harvest`, a mechanism flag or `--wr-statistic pooled` is a parser error.
  - `permutation_test.py --arms <file> --gap-reclaim [--n N --seed S --out-json F]` — the re-priced-fixed null; same sidecar refusal; `--out-json` now also writes the arms-mode JSON (with or without `--gap-reclaim`).
  - `scripts/reports/gap_reclaim_report.py --arms <file> [--basis <file>] --out-json <path> --out-md <path> [--resamples N] [--seed N] [--reference-account USD] [--risk-pct P] [--data-source alpaca|yfinance]`; module functions `build(args) -> dict`, `basis_section(path) -> dict`, `regime_section(baseline, component, spy) -> dict`, `render_markdown(report) -> str`, `main(argv=None) -> int`; refusal tokens `refused:no-whole-window`, `refused:no-gap-reclaim-sidecar`, `refused:basis-on-validation`, `refused:not-a-basis-pair`.

**What part 4 runs with these (for orientation; part 4 owns the exact commands):** Stage −1 `validate_component.py --stage reachability --gap-reclaim --arms <g pilot>`; Stage 0 `--stage mde --gap-reclaim --train-effect-from-arms --arms <g selection>`; Stage 1 `--stage selection --gap-reclaim --grid-arms 0.1=<..> --grid-arms 0.25=<..> --grid-arms 0.5=<..>`; Stage 2 `--stage walkforward` (unchanged, `gate_win_rate` over the 2021/2022/2023 folds); Stage 3 `permutation_test.py --arms <validation> --gap-reclaim --out-json ...` then `validate_component.py --stage validation --gap-reclaim --permutation-p <p>`; the report on the selection and validation pairs, with `--basis` on the fold-train basis pair only.

- [ ] **Step 1: Write the failing tests** — create `tests/backtest_scripts/test_gap_reclaim_cli.py`

```python
"""V192-18: --gap-reclaim in the funnel judge and the permutation CLI, and the report script."""
import dataclasses
import importlib.util
import json
import runpy
from pathlib import Path

import pytest

from swingbot import config
from swingbot.core.backtesting.arms import gap_reclaim_census as census_mod
from swingbot.core.backtesting.arms.provenance import build_stamp
from swingbot.core.backtesting.arms.windows import ALL_HORIZONS, STAGES
from tests.backtesting.arms.test_gap_reclaim_clauses import veto_arms
from tests.backtesting.arms.test_gap_reclaim_report import _census_for
from tests.backtesting.test_validate_component_stamps import vc

ROOT = Path(__file__).resolve().parent.parent.parent
PERMUTATION = ROOT / "scripts" / "backtest" / "permutation_test.py"
_spec = importlib.util.spec_from_file_location("gap_reclaim_report_script",
                                               ROOT / "scripts" / "reports" / "gap_reclaim_report.py")
report_script = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(report_script)

VETO = {"MARKET_ENTRY_NEXT_OPEN": True, "GAP_RECLAIM_ATR": 0.25}
NEXT_OPEN = {"MARKET_ENTRY_NEXT_OPEN": True}
BASELINE, COMPONENT, REPRICED = veto_arms()
UNIVERSE = sorted({t.ticker for t in BASELINE})


@pytest.fixture(autouse=True)
def _world(monkeypatch):
    from swingbot.core.marketdata import training_data
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "yfinance")   # v162: no store in tests
    training_data.reset()
    monkeypatch.setattr(vc, "_full_universe", lambda: UNIVERSE)
    monkeypatch.setattr(report_script, "_spy_frame", lambda: None)
    yield
    training_data.reset()


def write_arms(tmp_path, stage, *, name="arms", knobs=VETO, baseline_knobs=NEXT_OPEN, census=True,
               census_knobs=None, census_rows=None, component=None):
    stamp = build_stamp(stage=stage, signal_window=STAGES[stage].signal_window, universe=UNIVERSE,
                        horizons=ALL_HORIZONS, engines=("confluence", "strategy"), knob_delta=knobs,
                        engine_hash_baseline="h", engine_hash_component="h", changed_outcomes=1,
                        preregistration="docs/superpowers/specs/2026-10-24-v192-gap-toward-stop-reclaim-design.md",
                        baseline_knob_delta=baseline_knobs)
    path = tmp_path / f"{name}.json"
    rows = {"baseline": [dataclasses.asdict(t) for t in BASELINE],
            "component": [dataclasses.asdict(t) for t in (component or COMPONENT)]}
    path.write_text(json.dumps({"provenance": stamp, **rows}), encoding="utf-8")
    if census:
        census_rows = _census_for(BASELINE, REPRICED) if census_rows is None else census_rows
        side = {"knob_delta": census_knobs or knobs, "rows": census_rows,
                "summary": census_mod.reachability_summary(census_rows)}
        census_mod.sidecar_path(path).write_text(json.dumps(side), encoding="utf-8")
    return path


def _vc(*argv):
    return vc.main([*argv, "--title", "v192", "--window", "w", "--resamples", "200", "--gap-reclaim"])


# --- validate_component ------------------------------------------------------------------------

def test_reachability_prints_the_census_and_passes_an_armed_veto(tmp_path, capsys):
    out_json = tmp_path / "stage-1.json"
    assert _vc("--stage", "reachability", "--arms", str(write_arms(tmp_path, "pilot")),
               "--out-json", str(out_json)) == 0
    out = capsys.readouterr().out
    assert "REACHABLE" in out and '"armed": 30' in out
    assert json.loads(out_json.read_text())["verdict"] == census_mod.REACHABLE


def test_reachability_refuses_a_census_where_nothing_armed(tmp_path, capsys):
    flat = [dict(row, decision="open", reclaimed=False) for row in _census_for(BASELINE, REPRICED)]
    assert _vc("--stage", "reachability", "--arms", str(write_arms(tmp_path, "pilot", census_rows=flat))) == 1
    assert "refused:zero-diff" in capsys.readouterr().err


@pytest.mark.parametrize("stage,funnel", [("pilot", "reachability"), ("validation", "validation")])
def test_a_missing_census_is_refused(tmp_path, capsys, stage, funnel):
    path = write_arms(tmp_path, stage, census=False)
    assert _vc("--stage", funnel, "--arms", str(path), "--permutation-p", "0.01") == 1
    assert "refused:no-gap-reclaim-sidecar" in capsys.readouterr().err


def test_a_census_of_another_run_is_refused(tmp_path, capsys):
    path = write_arms(tmp_path, "validation", census_knobs={"MARKET_ENTRY_NEXT_OPEN": True, "GAP_RECLAIM_ATR": 0.5})
    assert _vc("--stage", "validation", "--arms", str(path), "--permutation-p", "0.01") == 1
    assert "refused:no-gap-reclaim-sidecar" in capsys.readouterr().err


def test_mde_uses_the_week_cluster_only_under_the_flag(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(vc, "mde_paired", lambda *a, **k: seen.append(k["cluster"]) or 1.0)
    path = write_arms(tmp_path, "selection")
    _vc("--stage", "mde", "--arms", str(path), "--train-effect-pp", "5")
    vc.main(["--stage", "mde", "--arms", str(path), "--title", "t", "--window", "w", "--train-effect-pp", "5"])
    assert seen == ["week", "ticker"]


def test_selection_reads_the_g_axis_and_ties_to_the_smaller_g(tmp_path, capsys):
    grid = []
    for g in ("0.1", "0.25", "0.5"):
        knobs = {"MARKET_ENTRY_NEXT_OPEN": True, "GAP_RECLAIM_ATR": float(g)}
        grid += ["--grid-arms", f"{g}={write_arms(tmp_path, 'selection', name=f'g{g}', knobs=knobs)}"]
    out_json = tmp_path / "stage1.json"
    assert _vc("--stage", "selection", *grid, "--out-json", str(out_json)) == 0
    out = capsys.readouterr().out
    assert "g=0.1 eligible=True" in out and "verdict=selected selected=0.1" in out
    assert json.loads(out_json.read_text())["selected"] == 0.1


def test_validation_scores_the_strata_and_writes_the_result(tmp_path, capsys):
    out_json = tmp_path / "stage3.json"
    assert _vc("--stage", "validation", "--arms", str(write_arms(tmp_path, "validation")),
               "--permutation-p", "0.01", "--out-json", str(out_json)) == 0
    result = json.loads(out_json.read_text())
    assert result["verdict"] == "PASS" and result["cluster"] == "week"
    assert result["split"]["repriced"] == 30 and result["split"]["removed"] == 60
    mechanism = next(c for c in result["clauses"] if c["name"] == "mechanism")
    assert mechanism["verdict"] == "PASS" and "unchanged" in mechanism["detail"]


@pytest.mark.parametrize("extra", [["--gate", "harvest"], ["--headroom-mechanism"], ["--wr-statistic", "pooled"]])
def test_conflicting_flags_are_a_parser_error(tmp_path, extra):
    with pytest.raises(SystemExit):
        _vc("--stage", "validation", "--arms", str(write_arms(tmp_path, "validation")), *extra)


# --- permutation_test --------------------------------------------------------------------------

def _permutation(argv):
    namespace = runpy.run_path(str(PERMUTATION))
    main = namespace["main"]
    main.__globals__["_full_universe"] = lambda: UNIVERSE
    return main(argv)


def test_permutation_runs_the_repriced_null_and_writes_its_json(tmp_path, capsys):
    out_json = tmp_path / "perm.json"
    path = write_arms(tmp_path, "validation")
    assert _permutation(["--arms", str(path), "--gap-reclaim", "--n", "50", "--out-json", str(out_json)]) == 0
    out = json.loads(out_json.read_text())
    assert out["repriced"] == 30 and out["n"] == 50 and out["verdict"] in ("REAL", "INDISTINGUISHABLE FROM LUCK")
    assert "re-priced trades held" in out["instrument"]


def test_permutation_without_the_flag_is_the_unchanged_v72_null(tmp_path, capsys):
    """veto_arms re-prices with the same outcome, so population_split sees no changed pair and
    the v72 removal-label null runs as today: no 'repriced' key, changed == 0."""
    path = write_arms(tmp_path, "validation")
    assert _permutation(["--arms", str(path), "--n", "20"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert "repriced" not in out and out["changed"] == 0


def test_permutation_refuses_a_missing_census(tmp_path, capsys):
    path = write_arms(tmp_path, "validation", census=False)
    assert _permutation(["--arms", str(path), "--gap-reclaim", "--n", "20"]) == 1
    assert "refused:no-gap-reclaim-sidecar" in capsys.readouterr().err


# --- gap_reclaim_report.py ---------------------------------------------------------------------

def _report(tmp_path, *extra):
    out_json, out_md = tmp_path / "report.json", tmp_path / "report.md"
    code = report_script.main(["--arms", str(write_arms(tmp_path, "validation")), "--out-json", str(out_json),
                               "--out-md", str(out_md), "--resamples", "200", *extra])
    return code, out_json, out_md


def test_the_report_script_writes_json_and_markdown(tmp_path):
    code, out_json, out_md = _report(tmp_path)
    assert code == 0
    data = json.loads(out_json.read_text())
    assert data["n"] == {"baseline": 300, "component": 270} and data["regime"] == {
        "unavailable": "no SPY frame in the selected training data"}
    md = out_md.read_text()
    for text in ("# v192 gap-reclaim report", "| removed |", "| repriced |", "Earnings proximity: unavailable"):
        assert text in md


def test_the_report_cuts_by_regime_when_spy_is_available(tmp_path, monkeypatch):
    import pandas as pd
    monkeypatch.setattr(report_script, "regime_series",
                        lambda spy: pd.Series(["bull_quiet"] * len(spy.index), index=spy.index))
    spy = pd.DataFrame({"Close": 1.0}, index=pd.to_datetime([t.entry_date for t in BASELINE]))
    section = report_script.regime_section(BASELINE, COMPONENT, spy)
    assert set(section) == {"bull_quiet", "unknown"}           # the added trades fall on Tuesdays
    assert section["bull_quiet"]["n_baseline"] == 300


def test_the_basis_section_reads_a_fold_train_basis_pair(tmp_path):
    basis = write_arms(tmp_path, "selection", name="basis", knobs=NEXT_OPEN, baseline_knobs=None, census=False)
    code, out_json, _ = _report(tmp_path, "--basis", str(basis))
    assert code == 0
    section = json.loads(out_json.read_text())["basis"]
    assert section["stage"] == "selection" and section["close_fill"]["n"] == 300 and section["next_open"]["n"] == 270


@pytest.mark.parametrize("stage,knobs,baseline_knobs,token", [
    ("validation", NEXT_OPEN, None, "refused:basis-on-validation"),
    ("selection", VETO, NEXT_OPEN, "refused:not-a-basis-pair"),
])
def test_a_wrong_basis_pair_is_refused(tmp_path, capsys, stage, knobs, baseline_knobs, token):
    basis = write_arms(tmp_path, stage, name="basis", knobs=knobs, baseline_knobs=baseline_knobs, census=False)
    code, out_json, _ = _report(tmp_path, "--basis", str(basis))
    assert code == 1 and token in capsys.readouterr().err and not out_json.exists()


def test_the_report_refuses_arms_without_a_census_or_whole_window_rows(tmp_path, capsys):
    path = write_arms(tmp_path, "validation", census=False)
    assert report_script.main(["--arms", str(path), "--out-json", str(tmp_path / "r.json"),
                               "--out-md", str(tmp_path / "r.md")]) == 1
    assert "refused:no-gap-reclaim-sidecar" in capsys.readouterr().err
    folds = tmp_path / "folds.json"
    folds.write_text(json.dumps({"provenance": {}, "folds": []}), encoding="utf-8")
    assert report_script.main(["--arms", str(folds), "--out-json", str(tmp_path / "r.json"),
                               "--out-md", str(tmp_path / "r.md")]) == 1
    assert "refused:no-whole-window" in capsys.readouterr().err
```

- [ ] **Step 2: Run them to see them fail**

```bash
python scripts/dev/testrun.py file tests/backtest_scripts/test_gap_reclaim_cli.py
```

Expected: FAIL at collection — `FileNotFoundError` for `scripts/reports/gap_reclaim_report.py`; once it exists, `unrecognized arguments: --gap-reclaim`.

- [ ] **Step 3: `validate_component.py`**

Import line `:18` becomes:

```python
from swingbot.core.backtesting.arms import dryup_clauses, gap_reclaim_census, gap_reclaim_clauses, headroom_clauses, reachability  # noqa: E402
```

Add after `_wr_statistic` (`:72-74`):

```python
def _gap_reclaim(args):
    """v192: --gap-reclaim scores the gap-reclaim veto on its frozen strata."""
    return getattr(args, "gap_reclaim", False)

def _cluster(args):
    """v192: the gap-reclaim gate's intervals are week-clustered (spec § Gate); v1 elsewhere."""
    return gap_reclaim_clauses.CLUSTER if _gap_reclaim(args) else "ticker"

def _dump(path, payload):
    if path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(payload, indent=1), encoding="utf-8")

def _gap_sidecar(arms_path):
    """The census beside ``arms_path`` when the same run wrote it (same knob delta), else None."""
    side = gap_reclaim_census.load_sidecar(arms_path)
    stamp = json.loads(Path(arms_path).read_text()).get("provenance") or {}
    if side is None or side.get("knob_delta") != (stamp.get("knob_delta") or {}):
        return None
    return side

def _repriced_for(arms_path):
    return gap_reclaim_census.repriced_keys(_gap_sidecar(arms_path)["rows"])

def _refuse_no_sidecar():
    print("refused:no-gap-reclaim-sidecar -- --gap-reclaim needs the census measure_arms wrote beside "
          "these arms (<arms stem>.gap_reclaim.json, same knob delta). Budget intact.", file=sys.stderr)
    return 1

def _gap_reclaim_reachability(args):
    """Stage -1 for v192: the census summary decides reachability (spec § Gate)."""
    side = _gap_sidecar(args.arms)
    if side is None:
        return _refuse_no_sidecar()
    summary = side["summary"]
    print(json.dumps(summary, indent=1)); _dump(args.out_json, summary)
    if summary["verdict"] != gap_reclaim_census.REACHABLE:
        print("refused:zero-diff -- no market plan armed the veto (census). Budget intact.", file=sys.stderr); return 1
    print("REACHABLE -- the veto arms on market plans; Stage 0 may proceed."); return 0

def _gap_reclaim_conflict(args):
    """The parser error for a flag the v192 gate does not combine with, else None."""
    if not args.gap_reclaim:
        return None
    if args.gate == "harvest":
        return "--gap-reclaim scores the v72 win-rate funnel; the v92 harvest gate is a different gate"
    if args.dryup_mechanism or args.headroom_mechanism or args.mechanism_json:
        return "--gap-reclaim scores clause 6 on its own strata; drop the other mechanism reading"
    if _wr_statistic(args) != "standardised":
        return "--gap-reclaim is pre-registered on the standardised dWR"
    return None
```

In `stage_reachability` (V192-14's version), insert immediately before the final `print("REACHABLE -- the component changes trades; ...")` line:

```python
    if _gap_reclaim(args):
        return _gap_reclaim_reachability(args)
```

In `_mde_design`, the paired call becomes:

```python
        paired = mde_paired(baseline, component, statistic, observed_n=observed,
                            target_n=target, n_resamples=args.resamples, seed=args.seed,
                            cluster=_cluster(args))
```

Replace `_evaluate` (`:194-196`):

```python
def _evaluate(args, baseline, component, stage):
    common = dict(stage=stage, permutation_p=args.permutation_p, n_resamples=args.resamples, seed=args.seed)
    if _gap_reclaim(args):
        return gap_reclaim_clauses.evaluate_gap_reclaim(baseline, component, _repriced_for(args.arms), **common)
    return evaluate_harvest(baseline, component, **common) if args.gate == "harvest" else evaluate(baseline, component, wr_statistic=_wr_statistic(args), **common)
```

Replace `stage_validation` (`:214`):

```python
def stage_validation(args):
    if _gap_reclaim(args) and _gap_sidecar(args.arms) is None:
        return _refuse_no_sidecar()
    return _run_gate(args, "validation")
```

`_selection_axis` gains a first branch:

```python
def _selection_axis(args):
    """(config attr, printed label, tie rule) of the grid the active mechanism selects on."""
    if _gap_reclaim(args):
        return 'GAP_RECLAIM_ATR', 'g', 'smaller'
    if getattr(args, 'headroom_mechanism', False):
        return 'HEADROOM_MIN_R', 'h', 'smaller'
    return 'PULLBACK_DRYUP_MAX_RATIO', 'd', 'larger'
```

Add before `_selection_cells` and use it there:

```python
def _selection_cell_for(args, value, path, baseline, component):
    """One Stage 1 cell: v192's dExpR-floor cell under --gap-reclaim, else today's evaluate_cell."""
    resolvable = value not in args.mde_refused
    if _gap_reclaim(args):
        return gap_reclaim_clauses.selection_cell(value, baseline, component, resolvable=resolvable,
                                                  n_resamples=args.resamples, seed=args.seed)
    mechanism = _cell_mechanism(args, path, baseline, component, value)
    return evaluate_cell(value, baseline, component, resolvable=resolvable,
                         n_resamples=args.resamples, seed=args.seed, mechanism=mechanism)


def _selection_cells(args, grid):
    full_universe = _full_universe()
    cells = []
    for value, path in grid:
        arms = _selection_input(path, full_universe)
        if arms is None:
            return None
        cells.append(_selection_cell_for(args, value, path, *arms))
    return cells
```

In `main`, add after the `--mechanism-json` argument line:

```python
    parser.add_argument("--gap-reclaim", action="store_true", help="v192: score the gap-reclaim veto on its frozen strata (needs <arms stem>.gap_reclaim.json)")
```

and after the `--wr-statistic`/harvest `parser.error` check:

```python
    conflict = _gap_reclaim_conflict(args)
    if conflict:
        parser.error(conflict)
```

- [ ] **Step 4: `permutation_test.py`**

Add after `arm_pair_permutation` (`:97`):

```python
def _gap_reclaim_null(args, blob, baseline, component) -> dict:
    """v192: the re-priced-fixed removal-label null over the census's re-priced keys."""
    from swingbot.core.backtesting.arms import gap_reclaim_census, gap_reclaim_clauses

    side = gap_reclaim_census.load_sidecar(args.arms)
    if side is None or side.get("knob_delta") != (blob.get("provenance") or {}).get("knob_delta"):
        raise ValueError("refused:no-gap-reclaim-sidecar -- --gap-reclaim needs the census measure_arms "
                         "wrote beside these arms (<arms stem>.gap_reclaim.json, same knob delta). Budget intact.")
    return gap_reclaim_clauses.repriced_permutation(baseline, component,
                                                    gap_reclaim_census.repriced_keys(side["rows"]),
                                                    n_perm=args.n, seed=args.seed)


def _arm_null(args, blob, baseline, component) -> dict:
    if getattr(args, "gap_reclaim", False):
        return _gap_reclaim_null(args, blob, baseline, component)
    return arm_pair_permutation(baseline, component, n_perm=args.n, seed=args.seed)
```

Replace `_arms_main` (`:192-207`):

```python
def _arms_main(args) -> int:
    loaded = _load_arm_pair(args.arms)
    if loaded is None:
        return 1
    blob, baseline, component = loaded
    if _stamp_gate_refused(blob, baseline, component):
        return 1
    try:
        out = _arm_null(args, blob, baseline, component)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    out["verdict"] = ("REAL" if out["p_value"] is not None and out["p_value"] < 0.05
                      else "INDISTINGUISHABLE FROM LUCK")
    text = json.dumps(out, indent=1)
    print(text)
    if args.out_json:
        Path(args.out_json).write_text(text, encoding="utf-8")
    return 0
```

In `_parser`, after `--shift-replay`:

```python
    p.add_argument("--gap-reclaim", action="store_true",
                   help="v192: re-priced-fixed removal-label null (needs <arms stem>.gap_reclaim.json)")
```

In `main`, after the `--shift-replay` block:

```python
    if args.gap_reclaim and not args.arms:
        _parser().error("--gap-reclaim needs --arms")
```

Add a docstring usage line: `python scripts/backtest/permutation_test.py --arms stamped.json --gap-reclaim [--n 200 --seed 42 --out-json F]`.

- [ ] **Step 5: Create `scripts/reports/gap_reclaim_report.py`**

```python
#!/usr/bin/env python3
"""v192: the gap-reclaim report -- every spec § Reporting number for one stamped arm pair.

    python scripts/reports/gap_reclaim_report.py --arms <arms.json> [--basis <basis-arms.json>]
        --out-json <path> --out-md <path> [--resamples N] [--seed N]
        [--reference-account USD] [--risk-pct P] [--data-source alpaca]

--arms is a whole-window measure_arms file (selection or validation) with its census
<stem>.gap_reclaim.json beside it. --basis is the fold-train next-open basis pair (component
MARKET_ENTRY_NEXT_OPEN=true against an empty baseline); it is refused on a validation stamp,
because next-open vs close fill is read on fold-train only (spec § On a pass). The regime cut is
descriptive (regime2 state of SPY on the signal date); there is no earnings cut (no as-of
earnings archive). Descriptive: nothing here decides a stage.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "scripts" / "data")]

from swingbot.core.backtesting.acceptance import (BOOTSTRAP_RESAMPLES, ArmTrade,  # noqa: E402
                                                  delta_expectancy_r, delta_standardised_win_rate,
                                                  expectancy_r, win_rate)
from swingbot.core.backtesting.arms import gap_reclaim_census, gap_reclaim_clauses  # noqa: E402
from swingbot.core.edge.regime2 import regime_series  # noqa: E402

BASIS_DELTA = {"MARKET_ENTRY_NEXT_OPEN": True}


class Refused(Exception):
    """A refusal token and its reason; the CLI prints it and exits 1."""


def _parser() -> argparse.ArgumentParser:
    from fetch_backtest_data import add_data_source_arg
    p = argparse.ArgumentParser(description="v192 gap-reclaim report")
    p.add_argument("--arms", required=True, type=Path)
    p.add_argument("--basis", type=Path, default=None)
    p.add_argument("--out-json", required=True, type=Path)
    p.add_argument("--out-md", required=True, type=Path)
    p.add_argument("--resamples", type=int, default=BOOTSTRAP_RESAMPLES)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--reference-account", type=float, default=100_000.0)
    p.add_argument("--risk-pct", type=float, default=1.0)
    add_data_source_arg(p)
    return p


def _load_pair(path) -> tuple:
    blob = json.loads(Path(path).read_text(encoding="utf-8"))
    if "baseline" not in blob or "component" not in blob:
        raise Refused(f"refused:no-whole-window -- {path} has no whole-window rows (a fold-only file?).")
    return blob, [ArmTrade(**r) for r in blob["baseline"]], [ArmTrade(**r) for r in blob["component"]]


def _arm(trades) -> dict:
    return {"n": len(trades), "win_rate": win_rate(trades), "expectancy_r": expectancy_r(trades)}


def _pair(baseline, component) -> dict:
    return {"n_baseline": len(baseline), "n_component": len(component),
            "baseline_win_rate": win_rate(baseline), "component_win_rate": win_rate(component),
            "delta_win_rate_pp": delta_standardised_win_rate(baseline, component),
            "delta_expectancy_r": delta_expectancy_r(baseline, component)}


def basis_section(path) -> dict:
    """Next-open baseline vs today's v1 close fill, fold-train only (disclosure)."""
    blob, baseline, component = _load_pair(path)
    stamp = blob.get("provenance") or {}
    if stamp.get("stage") == "validation":
        raise Refused("refused:basis-on-validation -- next-open vs close fill is read on fold-train only.")
    if stamp.get("knob_delta") != BASIS_DELTA or stamp.get("baseline_knob_delta"):
        raise Refused("refused:not-a-basis-pair -- the basis pair is component MARKET_ENTRY_NEXT_OPEN=true "
                      "against an empty baseline.")
    return {"stage": stamp.get("stage"), "close_fill": _arm(baseline), "next_open": _arm(component),
            "delta_win_rate_pp": delta_standardised_win_rate(baseline, component),
            "delta_expectancy_r": delta_expectancy_r(baseline, component),
            "note": "disclosure only; decides nothing (spec § Replay basis)"}


def _spy_frame():
    from swingbot import config
    from swingbot.core.marketdata import training_data
    return training_data.load_daily(config.MARKET_REGIME_TICKER)


def regime_section(baseline, component, spy) -> dict:
    """Descriptive regime2 cut: SPY's state on each trade's signal date ('unknown' when absent)."""
    if spy is None:
        return {"unavailable": "no SPY frame in the selected training data"}
    states = {str(ts.date()): str(state) for ts, state in regime_series(spy).items()}
    label = {t.key: states.get(t.entry_date, "unknown") for t in [*baseline, *component]}
    values = sorted(set(label.values()))
    return {value: _pair([t for t in baseline if label[t.key] == value],
                         [t for t in component if label[t.key] == value]) for value in values}


def build(args) -> dict:
    blob, baseline, component = _load_pair(args.arms)
    side = gap_reclaim_census.load_sidecar(args.arms)
    if side is None:
        raise Refused("refused:no-gap-reclaim-sidecar -- the report needs <arms stem>.gap_reclaim.json.")
    out = {"arms": str(args.arms), "provenance": blob.get("provenance"),
           "census_health": {key: side.get(key) for key in ("repriced_in_component",
                                                            "repriced_absent_from_component")},
           **gap_reclaim_clauses.report(baseline, component, side["rows"], n_resamples=args.resamples,
                                        seed=args.seed, reference_account=args.reference_account,
                                        risk_pct=args.risk_pct),
           "regime": regime_section(baseline, component, _spy_frame())}
    if args.basis:
        out["basis"] = basis_section(args.basis)
    return out


def _fmt(value, spec: str = "+.4f") -> str:
    return "n/a" if value is None else format(value, spec)


def _interval_line(name: str, block: dict, spec: str) -> str:
    return (f"- {name}: {_fmt(block['point'], spec)} [{_fmt(block['lo'], spec)}, {_fmt(block['hi'], spec)}] "
            f"(week-cluster bootstrap)")


def _strata_lines(rows) -> list[str]:
    lines = ["| Stratum | N | Decided | WR | ExpR | Baseline WR | Baseline ExpR |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['stratum']} | {r['n']} | {r['decided']} | {_fmt(r['win_rate'], '.2f')} | "
                     f"{_fmt(r['expectancy_r'])} | {_fmt(r['baseline_win_rate'], '.2f')} | "
                     f"{_fmt(r['baseline_expectancy_r'])} |")
    return lines


def _split_lines(title: str, block: dict) -> list[str]:
    lines = [f"### {title}", "", "| Value | Base N | Comp N | dWR pp | dExpR |", "|---|---|---|---|---|"]
    for value, row in block.items():
        lines.append(f"| {value} | {row['n_baseline']} | {row['n_component']} | "
                     f"{_fmt(row['delta_win_rate_pp'], '+.2f')} | {_fmt(row['delta_expectancy_r'])} |")
    return lines + [""]


def _census_lines(census: dict) -> list[str]:
    lines = ["| Horizon | Direction | Market plans | Armed | Reclaimed | Ambiguous | Open through stop | Risk cap |",
             "|---|---|---|---|---|---|---|---|"]
    for c in census["cells"]:
        lines.append(f"| {c['horizon_key']} | {c['direction']} | {c['market_plans']} | {c['armed']} | "
                     f"{c['reclaimed']} | {c['ambiguous']} | {c['open_through_stop']} | {c['risk_cap']} |")
    return lines


def render_markdown(report: dict) -> str:
    dollars, amb = report["repriced_dollars"], report["ambiguous_sensitivity"]
    lines = ["# v192 gap-reclaim report", "", f"Arms: `{report['arms']}`", "",
             f"- N: baseline {report['n']['baseline']}, component {report['n']['component']}",
             _interval_line("dWR (pp, standardised)", report["delta_win_rate_pp"], "+.2f"),
             _interval_line("dExpR (R)", report["delta_expectancy_r"], "+.4f"),
             f"- outcome flips: {report['outcome_flips']}", "", "## Strata", "",
             *_strata_lines(report["strata"]), "", "## Re-priced trades in dollars", "",
             f"- n {dollars['n']}, risk ${dollars['risk_dollars']:.0f} per trade: baseline "
             f"${dollars['baseline_dollars']:.2f}, component ${dollars['component_dollars']:.2f}, "
             f"delta ${dollars['delta_dollars']:.2f}", "", "## Ambiguous-bar sensitivity", "",
             f"- ambiguous fills: {amb['ambiguous_n']}; dWR as fills {_fmt(amb['as_fills']['delta_win_rate_pp'], '+.2f')}pp, "
             f"as cancels {_fmt(amb['as_cancels']['delta_win_rate_pp'], '+.2f')}pp", "", "## Census", "",
             *_census_lines(report["census"]), "", "## Splits (descriptive)", ""]
    for field, block in report["splits"].items():
        lines += _split_lines(field, block)
    lines += ["## Regime (descriptive)", "", f"```\n{json.dumps(report['regime'], indent=1)}\n```", "",
              f"Earnings proximity: {report['earnings_proximity']}", ""]
    if "basis" in report:
        lines += ["## Next-open basis (fold-train, disclosure)", "", f"```\n{json.dumps(report['basis'], indent=1)}\n```", ""]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    from fetch_backtest_data import apply_data_source
    apply_data_source(args)
    try:
        report = build(args)
    except Refused as exc:
        print(f"{exc} Budget intact.", file=sys.stderr)
        return 1
    for path in (args.out_json, args.out_md):
        path.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(report, indent=1, default=str) + "\n", encoding="utf-8")
    args.out_md.write_text(render_markdown(report), encoding="utf-8")
    print(f"wrote {args.out_json}\nwrote {args.out_md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

`test_the_report_cuts_by_regime_when_spy_is_available` monkeypatches the module-level `regime_series` name, which `regime_section` reads at call time; the added trades in `veto_arms` sit one day after a Monday (a Tuesday the fake SPY index lacks), so they land in `unknown`.

- [ ] **Step 6: Run the CLI tests, the judges' existing tests and the gate**

```bash
python scripts/dev/testrun.py file tests/backtest_scripts/test_gap_reclaim_cli.py
python scripts/dev/testrun.py file tests/backtesting/test_validate_component_cli.py
python scripts/dev/testrun.py file tests/backtesting/test_validate_component_stamps.py
python scripts/dev/testrun.py file tests/backtesting/test_validate_component_headroom.py
python scripts/dev/testrun.py file tests/backtesting/test_validate_component_dryup.py
python scripts/dev/testrun.py file tests/backtesting/test_permutation_test_arms.py
python scripts/dev/testrun.py file tests/backtesting/test_permutation_shift_replay.py
python scripts/dev/complexity_gate.py
```

Expected: `0 failed` each; the gate passes (`validate_component.main` gains one branch, `_gap_reclaim_conflict` cc 6, `_arms_main` cc 6, `render_markdown` cc 3).

- [ ] **Step 7: Commit (in the worktree)**

```bash
git add scripts/backtest/validate_component.py scripts/backtest/permutation_test.py scripts/reports/gap_reclaim_report.py tests/backtest_scripts/test_gap_reclaim_cli.py
git commit -m "feat(v192): --gap-reclaim in validate_component and permutation_test; gap_reclaim_report.py"
```

### Task V192-19: Autopsy `--entry-type` filter

**Model:** sonnet — one optional filter on an existing read-only report script and its tests.

**Files:**
- Modify: `scripts/reports/book_autopsy.py` (`_parser` `:30-42`, `main` `:45-66`; new `ENTRY_TYPES`, `filter_entry_type`, `_output_stem`)
- Test: `tests/scripts/test_book_autopsy_entry_type.py` (create)

**Interfaces:**
- Consumes (all exist today): `autopsy.rows.load_rows`, `BookRow.entry_type` (`scripts/reports/autopsy/rows.py:57`, filled from the export's `entry_type` column for trade and plan rows), `autopsy.report.build_report`, `render_markdown` (header notes render as `- Note: ...`, `report.py:147`); test helpers `_trade`, `EXPIRED_PLAN`, `FAST`, `rows`, `cuts`, `script` from `tests/scout/test_book_autopsy.py`.
- Produces (index § Contracts): `book_autopsy.py --entry-type market|stop_entry|limit`; `ENTRY_TYPES = ("market", "stop_entry", "limit")`; `filter_entry_type(rows, entry_type) -> list` (None keeps every row). With the flag the outputs are `<out-dir>/<date>-book-autopsy-<entry_type>.json` and `.md`, `header["entry_type_filter"]` is set and a header note records the filter; without it every output is what it is today.

**Why:** V192-21 (part 4) re-cuts the 2026-10-21 autopsy cells to market plans only, as the disclosure the spec requires before TRAIN (the motivating `open_gap_bucket=favourable` cell pools stop-entry, limit and market rows). The rejection tallies carry no entry type, so they stay unfiltered and the note says so.

- [ ] **Step 1: Write the failing tests** — create `tests/scripts/test_book_autopsy_entry_type.py`

```python
"""V192-19: book_autopsy --entry-type keeps one entry family's rows (the v192 pre-TRAIN
market-only disclosure); without the flag the report and its file names are unchanged."""
import csv
import json
from pathlib import Path

import pandas as pd
import pytest

from tests.scout.test_book_autopsy import EXPIRED_PLAN, FAST, _trade, cuts, rows, script

TYPES = ("market", "stop_entry", "limit")


@pytest.fixture(autouse=True)
def _today_sectors(monkeypatch):
    monkeypatch.setattr(cuts, "load_sector_map", lambda: {"AAA": "Technology", "BBB": "Energy"})


def _files(tmp_path: Path, n: int = 90):
    records = [dict(_trade(i, ("AAA", "BBB")[i % 2]), entry_type=TYPES[i % 3]) for i in range(n)]
    records.append(EXPIRED_PLAN)                                       # a stop_entry plan row
    rows_csv = tmp_path / "rows.csv"
    with rows_csv.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows.EXPORT_COLUMNS))
        writer.writeheader()
        for record in records:
            writer.writerow({c: record.get(c, "") for c in rows.EXPORT_COLUMNS})
    rej_csv = tmp_path / "rejections.csv"
    rej_csv.write_text("date,reason,count\n2026-03-02,risk_cap,4\n", encoding="utf-8")
    bars_dir = tmp_path / "bars"
    bars_dir.mkdir()
    days = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2025-12-01", "2026-04-30")]
    lines = ["Date,Open,High,Low,Close,Volume"] + [f"{d},100,100.5,99.5,100,1000000" for d in days]
    (bars_dir / "AAA.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return rows_csv, rej_csv, bars_dir


def _run(tmp_path, *extra):
    rows_csv, rej_csv, bars_dir = _files(tmp_path)
    out = tmp_path / "results"
    code = script.main([str(rows_csv), str(rej_csv), "--bars-dir", str(bars_dir), "--out-dir", str(out),
                        "--date", "2026-10-24", *FAST, *extra])
    return code, out


def test_filter_entry_type_keeps_one_family_and_none_keeps_all(tmp_path):
    loaded = rows.load_rows(_files(tmp_path)[0])
    assert script.ENTRY_TYPES == TYPES
    assert script.filter_entry_type(loaded, None) == loaded
    market = script.filter_entry_type(loaded, "market")
    assert len(market) == 30 and {r.entry_type for r in market} == {"market"}
    assert len(script.filter_entry_type(loaded, "stop_entry")) == 31      # 30 trades + the plan row


def test_the_market_only_report_is_written_under_its_own_name(tmp_path):
    code, out = _run(tmp_path, "--entry-type", "market")
    assert code == 0
    data = json.loads((out / "2026-10-24-book-autopsy-market.json").read_text(encoding="utf-8"))
    assert data["header"]["n"] == 30 and data["header"]["entry_type_filter"] == "market"
    assert any("entry-type filter: market" in note for note in data["header"]["notes"])
    md = (out / "2026-10-24-book-autopsy-market.md").read_text(encoding="utf-8")
    assert "- Note: entry-type filter: market" in md
    assert not (out / "2026-10-24-book-autopsy.json").exists()


def test_without_the_flag_nothing_changes(tmp_path):
    code, out = _run(tmp_path)
    assert code == 0
    data = json.loads((out / "2026-10-24-book-autopsy.json").read_text(encoding="utf-8"))
    assert data["header"]["n"] == 90 and "entry_type_filter" not in data["header"]
    assert not any("entry-type filter" in note for note in data["header"]["notes"])


def test_an_unknown_entry_type_is_a_usage_error(tmp_path):
    with pytest.raises(SystemExit):
        _run(tmp_path, "--entry-type", "moc")
```

`_trade` rows are all closed trades with a realised R (the scout test counts 48 of 48), so the header `n` is the trade count: 90 unfiltered, 30 per entry type.

- [ ] **Step 2: Run them to see them fail**

```bash
python scripts/dev/testrun.py file tests/scripts/test_book_autopsy_entry_type.py
```

Expected: FAIL — `AttributeError: module 'book_autopsy_script' has no attribute 'ENTRY_TYPES'` and `unrecognized arguments: --entry-type`.

- [ ] **Step 3: Implement in `scripts/reports/book_autopsy.py`**

Add to the usage block of the module docstring:

```
        [--entry-type market|stop_entry|limit]   (v192: one entry family; outputs named <date>-book-autopsy-<type>)
```

Add after `RESULTS_DIR` (`:27`):

```python
#: v192: the entry families a plan row carries (TradePlanV2.entry_type).
ENTRY_TYPES = ("market", "stop_entry", "limit")


def filter_entry_type(rows, entry_type: str | None) -> list:
    """v192: keep only the rows of one entry family (trade and plan rows alike); None keeps all."""
    rows = list(rows)
    return rows if entry_type is None else [row for row in rows if row.entry_type == entry_type]


def _output_stem(day: str, entry_type: str | None) -> str:
    return f"{day}-book-autopsy" if entry_type is None else f"{day}-book-autopsy-{entry_type}"
```

In `_parser`, before `return p`:

```python
    p.add_argument("--entry-type", choices=ENTRY_TYPES, default=None,
                   help="v192: keep one entry family's rows; outputs are named <date>-book-autopsy-<type>")
```

Replace `main` (`:45-66`):

```python
def _record_filter(report: dict, entry_type: str | None) -> None:
    if entry_type is None:
        return
    report["header"]["entry_type_filter"] = entry_type
    report["header"]["notes"].append(f"entry-type filter: {entry_type} rows only (v192 disclosure); "
                                     "rejection tallies carry no entry type and are unfiltered")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    args = _parser().parse_args(argv)
    frictions = friction_settings()
    inputs = {}
    loaded = filter_entry_type(load_rows(args.rows, frictions=frictions, input_fingerprints=inputs),
                               args.entry_type)
    rejections = load_rejections(args.rejections, input_fingerprints=inputs)
    invocation = {"command": [sys.executable, str(Path(__file__).resolve()), *argv],
                  "options": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()}}
    report = build_report(loaded, rejections,
                          bars_dir=args.bars_dir, n_resamples=args.resamples,
                          seed=args.seed, balance=args.balance, frictions=frictions,
                          input_fingerprints=inputs, invocation=invocation)
    _record_filter(report, args.entry_type)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    stem = _output_stem(args.date, args.entry_type)
    json_path = args.out_dir / f"{stem}.json"
    md_path = args.out_dir / f"{stem}.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    h = report["header"]
    print(f"wrote {json_path}\nwrote {md_path}")
    print(f"N {h['n']}, bar-covered {h['bar_covered_n']}, cells tested {h['cells_tested']}")
    return 0
```

The invocation block already records `entry_type` among `options`, so the JSON says how it was cut.

- [ ] **Step 4: Run the new tests, the existing autopsy tests and the gate**

```bash
python scripts/dev/testrun.py file tests/scripts/test_book_autopsy_entry_type.py
python scripts/dev/testrun.py file tests/scout/test_book_autopsy.py
python scripts/dev/complexity_gate.py
```

Expected: `0 failed` each (the scout tests pin the unfiltered output, which must not move); the gate passes.

- [ ] **Step 5: Run part 3's changed-test selection once**

```bash
python scripts/dev/testrun.py changed
```

Expected: `0 failed`, `0 xfailed`. This is the diff-selected run for V192-14..V192-19, not the plan's full suite (that is V192-26).

- [ ] **Step 6: Commit (in the worktree)**

```bash
git add scripts/reports/book_autopsy.py tests/scripts/test_book_autopsy_entry_type.py
git commit -m "feat(v192): book_autopsy --entry-type -- one entry family's rows for the pre-TRAIN market-only disclosure"
```
