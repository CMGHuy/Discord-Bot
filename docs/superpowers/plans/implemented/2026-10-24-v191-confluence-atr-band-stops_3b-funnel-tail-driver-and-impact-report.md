# v191 — Confluence ATR-band stops, part 3b: funnel tail, stage driver and Part B impact report (V191-16..V191-18)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax. **Never read this part whole**: `grep -n "^### Task V191-17:" -A 300 <this file>`.

**Spec:** [2026-10-24-v191-confluence-atr-band-stops-design.md](../specs/2026-10-24-v191-confluence-atr-band-stops-design.md)
**Index:** [2026-10-24-v191-confluence-atr-band-stops_0-index.md](2026-10-24-v191-confluence-atr-band-stops_0-index.md) — § Global Constraints, § Contracts, § Review Focus, § Parallelisation and the task ledger are binding here; this part never changes a shared name, signature or path.
**Previous:** [part 3, V191-14..V191-15](2026-10-24-v191-confluence-atr-band-stops_3-measurement-code.md) — part 3 of the index's Parts table, split in two to stay under the 1500-line cap; the tasks, files and contracts are exactly the ledger's.

Every path below is relative to the worktree root `.claude/worktrees/2026-10-24-v191-confluence-atr-band-stops` (created by V191-1); run every command from there, never from the main checkout. Every code task ends with `python scripts/dev/complexity_gate.py` passing and the V191-1 golden still green:

```bash
python scripts/dev/testrun.py file tests/backtesting/test_v191_flag_off_golden.py
python scripts/dev/testrun.py file tests/planning/test_v191_plan_golden.py
```

Scope of this file: the funnel's Stages 2..3, the Holm family and the per-cell report (V191-16, appended to V191-15's `atr_band_funnel.py`), the staged driver `scripts/backtest/measure_atr_band_stop.py` (V191-17), and `--side short|long|both` on the v183 impact report (V191-18). No code here runs a measurement: V191-20..V191-24 (part 4) do.

Names consumed from earlier tasks: everything under `atr_band_replay.py` and `atr_band_funnel.py` (Stages −1..1) in the index § Contracts (V191-14, V191-15), plus the test helpers `KEYS`, `band_record`, `band_row`, `lifted_band_rows`, `census_row` in `tests/backtesting/test_atr_band_funnel.py` (V191-15); `gap_stats` keys `p99_down_gap_pct` / `n_down`, `gap_sizing.MIN_DOWN_GAPS`, the long stamp key `down_gap_p99_pct` (V191-5); the `_V191` reachability text (V191-2).

---

# Phase 8 — Measurement code (continued)

### Task V191-16: Funnel Stages 2..3, Holm family, reports

**Model:** opus — the walk-forward rule, the one VALIDATION shot and the two-arm Holm family decide the recorded verdict; a missing arm entering as anything but p = 1.0, or a fold counted under N 30, changes the result after the fact.

**Files:**
- Modify: `swingbot/core/backtesting/atr_band_funnel.py` (append below the Stage 1 block written by V191-15)
- Modify: `tests/backtesting/test_atr_band_funnel.py` (append)

**Interfaces:**
- Consumes: V191-15's constants, `floor_moved`, `_keys`; V191-14's record keys (`exit_mix`, `gap_through`, `gap_overshoot_r`, `fill_beyond_ceiling`, `early_stop`, `stop_distance_pct`, `stop_distance_atr`, `regime2_state`, `dollar_pnl`, `dollar_exceeds_budget`) and row keys (`moved_by`, `newly_admitted`, `adv_dollars`); existing `acceptance.bootstrap_delta`, `expectancy_r`, `win_rate`, `median_planned_rr`; `acceptance_exit_funnel._flips`, `_sides`, `_triggered_once`, `_pp`, `sign_flip_p`, `PERMUTATION_N`; `giveback_levels_funnel.holm(pvalues)` (None passes through uncounted — so a missing arm is converted to 1.0 **before** the call); `instrument.stats.ledger_qvalues(rows)` (BH, reported only).
- Produces (index § Contracts, final): `stage2(rows_by_year: dict[int, list], arm, key) -> dict` (`PASS` | `FAIL`); `stage3(rows, arm, key, *, n_resamples=BOOTSTRAP_RESAMPLES, seed=42) -> dict` (`PASS` | `FAIL`, carries `"permutation_p"`); `holm_family(stage3_by_arm: dict[str, dict | None]) -> dict`; `report(rows, arm, key, *, n_resamples=BOOTSTRAP_RESAMPLES, seed=42) -> dict`. Also `FAMILY = ("K", "R")`, `PRIMARY_ARM = "K"`.

Rules frozen here:

- **Stage 2:** per fold year, on the floor-moved stratum: N = closed component trades; a fold is positive when `N ≥ MIN_FOLD_N` and ΔExpR > 0. `PASS` when at least `MIN_POSITIVE_FOLDS` (2) of the three folds are positive. A fold under N 30 never counts as positive.
- **Stage 3:** all four harvest clauses at `stage="validation"`, week-clustered, `permutation_p` from `sign_flip_p` (n = 200, seed 42), floor-moved stratum only.
- **Family:** Holm over `{"K": p_K, "R": p_R}`, each arm's Stage 3 `permutation_p`; an arm with no Stage 3 file, or a `None` p, enters as `1.0`. An arm passes the family when its Stage 3 verdict is `PASS` **and** its Holm-adjusted p is `< HOLM_ALPHA`. BH q-values (`ledger_qvalues`) are reported, never gating. Arm K is the primary arm, stated in the output.
- **Report** (spec § Reporting), informational, nothing gates: the floor-moved summary (N, ExpR both sides, ΔExpR with 95% interval, ΔWR in pp, flips); the same summary split by `moved_by` (all rows), by direction and by horizon (floor-moved), with the top-two-horizon share of N; the `regime2` cut (descriptive, point values only; replay rows carry `None`, shown as `unknown`); dollars at fixed risk (P&L, exceedance count per direction, both sides); stop distance median in % and in ATR, and % by horizon, both sides; newly admitted count, alert days, max and mean per day, median 20-day dollar volume; exit mix, early stops, gap-through count and mean overshoot in R, `fill_beyond_ceiling`, both sides; volume change % and removed rows; median planned RR both sides; one-side-only triggers.

- [ ] **Step 1: Append the failing tests** to `tests/backtesting/test_atr_band_funnel.py`

```python
# --- Stage 2 -------------------------------------------------------------------------------

def _years(lifts_by_year, n_tickers_by_year=None):
    sizes = n_tickers_by_year or {}
    return {year: lifted_band_rows({"k1": lift}, year=year, n_tickers=sizes.get(year, 20))
            for year, lift in lifts_by_year.items()}


def test_stage2_passes_with_two_positive_folds():
    out = funnel.stage2(_years({2021: 0.3, 2022: -0.2, 2023: 0.1}), "K", "k1")
    assert out["verdict"] == "PASS" and out["positive"] == 2
    assert [f["year"] for f in out["folds"]] == [2021, 2022, 2023]
    assert out["folds"][0]["n"] == 80


def test_stage2_a_fold_under_n30_never_counts_as_positive():
    out = funnel.stage2(_years({2021: 0.3, 2022: -0.2, 2023: 0.4}, {2023: 5}), "K", "k1")
    assert out["folds"][2]["n"] == 20 and out["folds"][2]["positive"] is False
    assert out["verdict"] == "FAIL"


def test_stage2_a_missing_year_is_an_empty_fold():
    out = funnel.stage2(_years({2021: 0.3, 2022: 0.3}), "K", "k1")
    assert out["folds"][2]["n"] == 0 and out["verdict"] == "PASS"


def test_stage2_reads_only_the_floor_moved_stratum():
    by_year = _years({2021: 0.3, 2022: 0.3, 2023: 0.3})
    for rows in by_year.values():
        for r in rows:
            r["moved_by"]["k1"] = "ceiling"
    assert funnel.stage2(by_year, "K", "k1")["verdict"] == "FAIL"


# --- Stage 3 -------------------------------------------------------------------------------

def test_stage3_passes_a_clear_lift_with_its_permutation_p():
    out = funnel.stage3(lifted_band_rows({"k1": 0.3}, year=2024), "K", "k1", n_resamples=N)
    assert (out["stage"], out["arm"], out["cell"], out["verdict"]) == (3, "K", "k1", "PASS")
    assert out["permutation_p"] is not None and out["permutation_p"] < 0.05
    assert out["n_permutations"] == 200
    assert {c["name"] for c in out["gate"]["clauses"]} >= {"expectancy_gain", "permutation"}


def test_stage3_fails_a_loss():
    out = funnel.stage3(lifted_band_rows({"k1": -0.3}, year=2024), "R", "k1", n_resamples=N)
    assert out["verdict"] == "FAIL"


def test_stage3_scores_the_floor_stratum_alone():
    rows = (lifted_band_rows({"k1": -0.3}, year=2024)
            + lifted_band_rows({"k1": 3.0}, year=2025, moved="untouched"))
    assert funnel.stage3(rows, "K", "k1", n_resamples=N)["verdict"] == "FAIL"


# --- Holm family ------------------------------------------------------------------------------

def test_holm_family_a_missing_arm_enters_as_p_one():
    out = funnel.holm_family({"K": {"verdict": "PASS", "permutation_p": 0.01}, "R": None})
    assert out["primary"] == "K" and out["method"] == "holm" and out["alpha"] == 0.05
    assert out["arms"]["R"]["p"] == 1.0 and out["arms"]["R"]["reached_stage3"] is False
    assert out["arms"]["K"]["p_holm"] == pytest.approx(0.02)
    assert out["arms"]["R"]["p_holm"] == pytest.approx(1.0)
    assert out["arms"]["K"]["pass"] is True and out["arms"]["R"]["pass"] is False
    assert out["passed"] == ["K"]
    assert set(out["arms"]["K"]) >= {"q_bh", "stage3_verdict"}


def test_holm_family_step_down_with_both_arms():
    out = funnel.holm_family({"K": {"verdict": "PASS", "permutation_p": 0.04},
                              "R": {"verdict": "PASS", "permutation_p": 0.03}})
    assert out["arms"]["R"]["p_holm"] == pytest.approx(0.06)     # smallest p x 2
    assert out["arms"]["K"]["p_holm"] == pytest.approx(0.06)     # max(0.06, 1 x 0.04)
    assert out["passed"] == []


def test_holm_family_a_stage3_fail_never_passes_and_a_none_p_is_one():
    out = funnel.holm_family({"K": {"verdict": "FAIL", "permutation_p": 0.001},
                              "R": {"verdict": "PASS", "permutation_p": None}})
    assert out["arms"]["K"]["pass"] is False
    assert out["arms"]["R"]["p"] == 1.0 and out["arms"]["R"]["pass"] is False


# --- report -------------------------------------------------------------------------------------

def _report_rows():
    rows = lifted_band_rows({"k1": 0.3}, n_tickers=2)
    rows += lifted_band_rows({"k1": -0.1}, n_tickers=2, moved="untouched", year=2022)
    rows.append(band_row(None, {"k1": band_record("T50", "2021-05-17", "win", 2.0)}))
    rows.append(band_row(band_record("T60", "2021-06-15", "loss", -1.0, moved=None,
                                     direction="bearish"),
                         {"k1": band_record("T60", "2021-06-15", "loss", -1.3, pnl=-140.0,
                                            exceeds=True, direction="bearish")}))
    return rows


def test_report_carries_every_spec_figure():
    out = funnel.report(_report_rows(), "K", "k1", n_resamples=N)
    assert (out["arm"], out["cell"], out["decision_stratum"]) == ("K", "k1", "floor")
    assert out["floor_moved"]["n_rows"] == 10
    assert set(out["by_moved_by"]) == {"floor", "untouched"}
    assert set(out["by_direction"]) == {"bullish", "bearish"}
    assert set(out["by_horizon"]) == {"4w"} and out["top_two_horizon_share"] == 1.0
    assert out["regime2"] == {"unknown": out["regime2"]["unknown"]}
    assert out["dollars"]["component"]["exceed_bearish"] == 1
    assert out["dollars"]["component"]["exceed_bullish"] == 0
    assert out["newly_admitted"]["n"] == 1 and out["newly_admitted"]["max_per_day"] == 1
    assert out["newly_admitted"]["median_adv_dollars"] == 5e7
    assert out["volume"]["n_component"] - out["volume"]["n_baseline"] == 1
    assert out["stop_distance"]["median_atr"] == {"baseline": pytest.approx(0.44),
                                                  "component": pytest.approx(1.0)}
    assert set(out["exits"]["component"]) >= {"exit_mix", "early_stops", "gap_through",
                                              "mean_gap_overshoot_r", "fill_beyond_ceiling"}
    assert set(out["median_planned_rr"]) == {"baseline", "component"}
    lo, hi = out["floor_moved"]["delta_expr_lo95"], out["floor_moved"]["delta_expr_hi95"]
    assert lo is not None and hi is not None and lo <= out["floor_moved"]["delta_expr"] <= hi


def test_report_on_an_empty_stratum_has_no_numbers_and_no_crash():
    out = funnel.report(lifted_band_rows({"k1": 0.3}, moved="untouched"), "R", "k1",
                        n_resamples=N)
    assert out["floor_moved"]["n_rows"] == 0
    assert out["floor_moved"]["delta_expr"] is None
    assert out["floor_moved"]["delta_expr_lo95"] is None
    assert out["newly_admitted"]["mean_per_day"] is None
    assert out["top_two_horizon_share"] is None
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_atr_band_funnel.py`
Expected: the V191-15 tests pass; the new ones FAIL with `AttributeError: module 'swingbot.core.backtesting.atr_band_funnel' has no attribute 'stage2'` (and `stage3`, `holm_family`, `report`).

- [ ] **Step 3: Append to `swingbot/core/backtesting/atr_band_funnel.py`**

Extend the imports at the top of the module (keep V191-15's lines; merge into the existing `from .acceptance import ...` and `from .acceptance_exit_funnel import ...` statements):

```python
import statistics

from swingbot.core.backtesting.instrument.stats import ledger_qvalues

from .acceptance import (BOOTSTRAP_RESAMPLES, CLOSED, bootstrap_delta, delta_expectancy_r,
                         expectancy_r, mde_paired, median_planned_rr, project_target_n,
                         render_json, win_rate)
from .acceptance_exit_funnel import (ELIGIBILITY_CLAUSES, PERMUTATION_N, _flips, _pp, _sides,
                                     _triggered_once, arm_trades, sign_flip_p)
from .giveback_levels_funnel import holm
```

Then append below the Stage 1 block:

```python
#: The Holm family (spec § Gate): arm K primary, arm R second, never pooled.
FAMILY = ("K", "R")
PRIMARY_ARM = "K"


# --- Stage 2 -------------------------------------------------------------------------

def _fold(rows, key, year) -> dict:
    baseline, component = arm_trades(floor_moved(rows, key), key)
    n = sum(1 for t in component if t.outcome in CLOSED)
    delta = delta_expectancy_r(baseline, component)
    measurable = n >= MIN_FOLD_N and delta is not None
    return {"year": year, "n": n, "delta_expr": delta, "measurable": measurable,
            "positive": measurable and delta > 0}


def stage2(rows_by_year: dict, arm, key) -> dict:
    """Walk-forward folds 2021 / 2022 / 2023 for the selected cell: PASS when
    at least MIN_POSITIVE_FOLDS folds carry N >= MIN_FOLD_N and dExpR > 0."""
    folds = [_fold(rows_by_year.get(year, []), key, year) for year in FOLD_YEARS]
    positive = sum(1 for fold in folds if fold["positive"])
    return {"stage": 2, "arm": arm, "cell": key,
            "verdict": "PASS" if positive >= MIN_POSITIVE_FOLDS else "FAIL",
            "positive": positive, "min_positive": MIN_POSITIVE_FOLDS,
            "min_fold_n": MIN_FOLD_N, "folds": folds}


# --- Stage 3 -------------------------------------------------------------------------

def stage3(rows, arm, key, *, n_resamples: int = BOOTSTRAP_RESAMPLES, seed: int = 42) -> dict:
    """The one VALIDATION shot for the selected cell: all four harvest
    clauses on the floor-moved stratum, week-clustered, permutation n = 200."""
    baseline, component = arm_trades(floor_moved(rows, key), key)
    p = sign_flip_p(baseline, component)
    result = evaluate_harvest(baseline, component, stage="validation", permutation_p=p,
                              n_resamples=n_resamples, seed=seed, cluster=CLUSTER)
    return {"stage": 3, "arm": arm, "cell": key, "verdict": result.verdict,
            "permutation_p": p, "n_permutations": PERMUTATION_N, "gate": render_json(result)}


# --- the family ----------------------------------------------------------------------

def _family_p(out) -> float:
    p = None if out is None else out.get("permutation_p")
    return 1.0 if p is None else float(p)


def _family_arm(out, p, p_holm, q) -> dict:
    verdict = None if out is None else out.get("verdict")
    return {"reached_stage3": out is not None, "stage3_verdict": verdict, "p": p,
            "p_holm": p_holm, "q_bh": q, "pass": verdict == "PASS" and p_holm < HOLM_ALPHA}


def holm_family(stage3_by_arm: dict) -> dict:
    """Holm across the two arms' Stage 3 permutation p. An arm that never
    reached Stage 3 (or carries no p) enters as p = 1.0. BH q is reported."""
    pvalues = {arm: _family_p(stage3_by_arm.get(arm)) for arm in FAMILY}
    adjusted = holm(pvalues)
    qvalues = ledger_qvalues([{"id": arm, "p": p} for arm, p in pvalues.items()])
    arms = {arm: _family_arm(stage3_by_arm.get(arm), pvalues[arm], adjusted[arm], qvalues[arm])
            for arm in FAMILY}
    return {"stage": "family", "method": "holm", "alpha": HOLM_ALPHA, "primary": PRIMARY_ARM,
            "arms": arms, "passed": [arm for arm in FAMILY if arms[arm]["pass"]]}


# --- report (spec § Reporting; informational, nothing gates) -----------------------------

def _median(values) -> float | None:
    vals = [v for v in values if v is not None]
    return float(statistics.median(vals)) if vals else None


def _summary(rows, key, n_resamples, seed, *, interval=True) -> dict:
    baseline, component = arm_trades(rows, key)
    wr_base, wr_cell = win_rate(baseline), win_rate(component)
    out = {"n_rows": len(rows), "n_baseline": len(baseline), "n_component": len(component),
           "expr_baseline": expectancy_r(baseline), "expr_component": expectancy_r(component),
           "delta_expr": delta_expectancy_r(baseline, component),
           "delta_expr_lo95": None, "delta_expr_hi95": None,
           "wr_baseline": wr_base, "wr_component": wr_cell, "delta_wr_pp": _pp(wr_cell, wr_base),
           "flips": _flips(rows, key)}
    if interval and baseline and component:
        boot = bootstrap_delta(baseline, component, delta_expectancy_r,
                               n_resamples=n_resamples, seed=seed, cluster=CLUSTER)
        out["delta_expr_lo95"], out["delta_expr_hi95"] = boot.lo, boot.hi
    return out


def _groups(rows, name_of) -> dict:
    out: dict = {}
    for row in rows:
        out.setdefault(str(name_of(row)), []).append(row)
    return dict(sorted(out.items()))


def _by(rows, key, n_resamples, seed, name_of, *, interval=True) -> dict:
    return {name: _summary(group, key, n_resamples, seed, interval=interval)
            for name, group in _groups(rows, name_of).items()}


def _regime_of(key):
    def name(row):
        record = row["cells"][key] or row["baseline"] or {}
        return record.get("regime2_state") or "unknown"
    return name


def _top_two_share(rows, key) -> float | None:
    counts = Counter(r["horizon_key"] for r in rows if r["cells"][key] is not None)
    total = sum(counts.values())
    return sum(n for _, n in counts.most_common(2)) / total if total else None


def _dollar_side(records) -> dict:
    out = {"pnl": round(sum(r["dollar_pnl"] for r in records), 2)}
    for direction in ("bullish", "bearish"):
        out[f"exceed_{direction}"] = sum(1 for r in records if r["direction"] == direction
                                         and r["dollar_exceeds_budget"])
    return out


def _dollars(rows, key) -> dict:
    base, comp = _sides(rows, key)
    budget = REFERENCE_ACCOUNT["balance"] * REFERENCE_ACCOUNT["risk_pct"] / 100.0
    return {"budget": budget, "baseline": _dollar_side(base), "component": _dollar_side(comp)}


def _two_sided_median(base, comp, field, horizon=None) -> dict:
    def pick(records):
        return _median(r[field] for r in records if horizon is None or r["horizon_key"] == horizon)
    return {"baseline": pick(base), "component": pick(comp)}


def _stop_distance(rows, key) -> dict:
    base, comp = _sides(rows, key)
    horizons = sorted({r["horizon_key"] for r in base + comp})
    return {"median_pct": _two_sided_median(base, comp, "stop_distance_pct"),
            "median_atr": _two_sided_median(base, comp, "stop_distance_atr"),
            "median_pct_by_horizon": {h: _two_sided_median(base, comp, "stop_distance_pct", h)
                                      for h in horizons}}


def _newly(rows, key) -> dict:
    new = [r for r in rows if r["newly_admitted"][key]]
    per_day = Counter(r["entry_date"] for r in new)
    return {"n": len(new), "alert_days": len(per_day),
            "max_per_day": max(per_day.values(), default=0),
            "mean_per_day": len(new) / len(per_day) if per_day else None,
            "median_adv_dollars": _median(r["adv_dollars"] for r in new)}


def _exit_side(records) -> dict:
    overshoots = [r["gap_overshoot_r"] for r in records
                  if r["gap_through"] and r["gap_overshoot_r"] is not None]
    return {"exit_mix": dict(Counter(r["exit_mix"] for r in records)),
            "early_stops": sum(1 for r in records if r["early_stop"]),
            "gap_through": sum(1 for r in records if r["gap_through"]),
            "mean_gap_overshoot_r": sum(overshoots) / len(overshoots) if overshoots else None,
            "fill_beyond_ceiling": sum(1 for r in records if r["fill_beyond_ceiling"])}


def _exits(rows, key) -> dict:
    base, comp = _sides(rows, key)
    return {"baseline": _exit_side(base), "component": _exit_side(comp)}


def _volume(rows, key, baseline, component) -> dict:
    n_base = sum(1 for t in baseline if t.outcome in CLOSED)
    n_comp = sum(1 for t in component if t.outcome in CLOSED)
    return {"n_baseline": n_base, "n_component": n_comp,
            "change_pct": (n_comp - n_base) / n_base * 100.0 if n_base else None,
            "removed_rows": sum(1 for r in rows
                                if r["baseline"] is not None and r["cells"][key] is None)}


def report(rows, arm, key, *, n_resamples: int = BOOTSTRAP_RESAMPLES, seed: int = 42) -> dict:
    """Everything spec § Reporting asks for one arm and cell. The decision
    stratum is floor-moved; the moved_by split covers every row."""
    stratum = floor_moved(rows, key)
    baseline, component = arm_trades(stratum, key)
    only_base, only_cell = _triggered_once(stratum, key)
    return {
        "arm": arm, "cell": key, "decision_stratum": MOVED_FLOOR,
        "floor_moved": _summary(stratum, key, n_resamples, seed),
        "by_moved_by": _by(rows, key, n_resamples, seed, lambda r: r["moved_by"].get(key)),
        "by_direction": _by(stratum, key, n_resamples, seed, lambda r: r["direction"]),
        "by_horizon": _by(stratum, key, n_resamples, seed, lambda r: r["horizon_key"]),
        "top_two_horizon_share": _top_two_share(stratum, key),
        "regime2": _by(stratum, key, n_resamples, seed, _regime_of(key), interval=False),
        "dollars": _dollars(stratum, key),
        "stop_distance": _stop_distance(stratum, key),
        "newly_admitted": _newly(stratum, key),
        "exits": _exits(stratum, key),
        "volume": _volume(stratum, key, baseline, component),
        "median_planned_rr": {"baseline": median_planned_rr(baseline),
                              "component": median_planned_rr(component)},
        "only_baseline_triggered": only_base, "only_cell_triggered": only_cell,
    }
```

Notes for the implementer: `holm` lives in `giveback_levels_funnel.py`; importing it pulls that module's imports once, which is fine inside `swingbot/core/backtesting/`. `render_json(result)["clauses"]` items carry `"name"` (`acceptance.py:649`); the clause names are `expectancy_gain`, `win_rate_floor`, `volume`, `permutation`. `_summary`'s interval needs both sides non-empty; a one-row stratum may still return a degenerate interval from `bootstrap_delta`, which is reported as is.

- [ ] **Step 4: Run the tests and the gates**

```bash
python scripts/dev/testrun.py file tests/backtesting/test_atr_band_funnel.py
python scripts/dev/complexity_gate.py
```
Expected: `0 failed`; complexity gate passes (every new function is a flat build; `report` has no branch).

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/atr_band_funnel.py tests/backtesting/test_atr_band_funnel.py
git commit -m "feat(backtest): v191 funnel stages 2..3 -- walk-forward folds, the VALIDATION shot, two-arm Holm family and the spec report

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V191-17: Driver `measure_atr_band_stop.py`; reachability text

**Model:** sonnet — a sibling of the v139 driver (`scripts/backtest/measure_confluence_stop.py`, read it first) with per-arm file names, the 2023 fold and a family command; the stage functions it calls are already pinned by V191-15/16.

**Files:**
- Create: `scripts/backtest/measure_atr_band_stop.py`
- Modify: `swingbot/core/backtesting/arms/reachability.py` (the `_V191` text written by V191-2 names the driver)
- Test: `tests/backtest_scripts/test_measure_atr_band_stop.py` (create; joins the suite that already holds `tests/backtest_scripts/`)

**Interfaces:**
- Consumes: `atr_band_replay.replay_entries`, `census`, `ARMS`, `K_STEPS`, `cell_key` (V191-14); `atr_band_funnel.FOLD_TRAIN`, `FOLD_2023`, `VALIDATION`, `FOLD_YEARS`, `DATA_SOURCE`, `INSTRUMENT`, `FAMILY`, `stage_minus1`, `stage0`, `stage1`, `stage2`, `stage3`, `holm_family`, `report` (V191-15, V191-16); test helpers `census_row`, `lifted_band_rows` (V191-15); existing `backtest_scenarios._resolve_replay_workers`, `instrument.cli.add_instrument_arg` / `spec_from_args` / `require_v1`, `training_data.select` / `load_daily`, `strategy_types.LEGACY_HORIZONS`, `measure_arms.cached_universe`.
- Produces (index § Contracts): the CLI `--arm K|R  --stage -1|0|1|2|3  --family  --out-dir  --preregistration  --tickers  --workers  --resamples  --data-source alpaca` (plus `--instrument`, default `v1`, anything else refused); `RESULTS = docs/superpowers/results/v191`; `PREFIX = "2026-10-24-v191-arm{arm}"`; family file `2026-10-24-v191-family.json`. Module functions the tests and part 4 use: `stage_path(out_dir, arm, stage)`, `rows_path(out_dir, arm, name)`, `family_path(out_dir)`, `run_stage(arm, stage, out_dir, *, build, n_resamples)`, `run_family(out_dir)`, `build(kind, arm, window, cells, *, tickers=None, workers=None)`, `main(argv)`.

Rules (mirroring v139 exactly, per arm):

- `REQUIRES = {0: (-1, "REACHABLE"), 1: (0, "POWERED"), 2: (1, "SELECTED"), 3: (2, "PASS")}`; each stage reads the same arm's previous verdict file and refuses without the verdict it needs. Stage 0 runs on Stage −1's `reachable_cells`, Stage 1's candidates are Stage 0's `powered_cells`.
- Rows files: `census-train` (Stage −1), `train` (fold-train, every `k`, built once and reused by Stages 0–2), `fold2023` (`FOLD_2023`, the selected `k` only), `validation` (`VALIDATION`, the selected `k` only). Stage 2's 2021 and 2022 folds come from the `train` rows; 2023 from `fold2023`.
- Stage 3 is refused when its output exists, when `--tickers` is given, and unless `--preregistration` names an existing file called `2026-10-24-v191-confluence-atr-band-stops-design.md`. `--tickers` (smoke runs) needs an `--out-dir` other than `RESULTS`.
- `--family` takes no `--arm`; it refuses while either arm is still open (no Stage 3 file and no non-advancing verdict on file) and writes `holm_family({"K": stage3 or None, "R": stage3 or None})`.
- Every real build selects `DATA_SOURCE` ("alpaca") in-process and in every pool worker (`initializer`), because `BACKTEST_CACHE_DIR` set in the worktree would otherwise default the source to yfinance; `--data-source` accepts `alpaca` only. Each stage file records `instrument` and `data_source`.
- Date windows come from `atr_band_funnel` only; the script holds no window literal.

- [ ] **Step 1: Write the failing tests** in `tests/backtest_scripts/test_measure_atr_band_stop.py`

```python
"""V191-17: the v191 driver -- the census before any outcome, the per-arm
stage order, the one-shot and pre-registration refusals, the selected-cell-only
2023 fold and VALIDATION replays, and the two-arm Holm family. `build` is
faked; no replay runs."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "backtest"))
import measure_atr_band_stop as mabs  # noqa: E402

from swingbot.core.backtesting import atr_band_funnel as funnel
from swingbot.core.backtesting.arms import reachability as reach
from tests.backtesting.test_atr_band_funnel import census_row, lifted_band_rows

N = 200
GRID = [0.75, 1.0, 1.5]
PLATEAU = {"k0.75": 0.30, "k1": 0.31, "k1.5": 0.29}
CENSUS = [census_row(ticker="T01"), census_row(("untouched", "floor", "floor"), ticker="T02")]
YEARS = {funnel.FOLD_TRAIN: (2021, 2022), funnel.FOLD_2023: (2023,), funnel.VALIDATION: (2024,)}


def _fake_build(calls, census=None):
    def build(kind, arm, window, cells):
        calls.append((kind, arm, tuple(window), [float(k) for k in cells]))
        if kind == "census":
            return CENSUS if census is None else census
        keys = [f"k{float(k):g}" for k in cells]
        return [row for year in YEARS[tuple(window)]
                for row in lifted_band_rows({key: PLATEAU[key] for key in keys}, year=year)]
    return build


def _run(arm, stage, out_dir, calls, **kw):
    return mabs.run_stage(arm, stage, out_dir, build=_fake_build(calls, **kw), n_resamples=N)


def _prereg(tmp_path):
    path = tmp_path / mabs.PREREGISTRATION.name
    path.write_text("x", encoding="utf-8")
    return path


def test_paths_and_the_frozen_names():
    assert mabs.stage_path("d", "K", -1).name == "2026-10-24-v191-armK-stageM1.json"
    assert mabs.stage_path("d", "R", 3).name == "2026-10-24-v191-armR-stage3.json"
    assert mabs.rows_path("d", "K", "train").name == "2026-10-24-v191-armK-train-rows.json"
    assert mabs.family_path("d").name == "2026-10-24-v191-family.json"
    assert mabs.RESULTS.parts[-3:] == ("superpowers", "results", "v191")
    assert mabs.PREREGISTRATION.name == "2026-10-24-v191-confluence-atr-band-stops-design.md"


def test_stage0_refuses_without_the_census(tmp_path):
    with pytest.raises(SystemExit, match="run stage -1 first"):
        _run("K", 0, tmp_path, [])


def test_a_zero_diff_census_closes_the_arm(tmp_path):
    calls = []
    out = _run("K", -1, tmp_path, calls, census=[census_row(("untouched",) * 3)])
    assert out["verdict"] == "refused:zero-diff"
    with pytest.raises(SystemExit, match="arm K closed at stage -1 with refused:zero-diff"):
        _run("K", 0, tmp_path, calls)


def test_census_reads_plans_only_then_stage0_builds_train_rows_once(tmp_path):
    calls = []
    assert _run("K", -1, tmp_path, calls)["verdict"] == "REACHABLE"
    assert calls == [("census", "K", funnel.FOLD_TRAIN, GRID)]
    assert _run("K", 0, tmp_path, calls)["verdict"] == "POWERED"
    assert calls[1] == ("rows", "K", funnel.FOLD_TRAIN, GRID)
    _run("K", 0, tmp_path, calls)
    assert len(calls) == 2          # the rows file is reused, not rebuilt


def test_stage0_runs_only_the_reachable_cells(tmp_path):
    calls = []
    _run("R", -1, tmp_path, calls, census=[census_row(("untouched", "floor", "floor"))])
    out = _run("R", 0, tmp_path, calls)
    assert [cell["cell"] for cell in out["cells"]] == ["k1", "k1.5"]


def test_full_chain_replays_2023_and_validation_for_the_selected_cell_only(tmp_path):
    calls = []
    for stage in (-1, 0, 1):
        assert _run("K", stage, tmp_path, calls)["verdict"] in mabs.ADVANCING
    assert mabs._load(mabs.stage_path(tmp_path, "K", 1))["selected"] == {"cell": "k1", "k": 1.0}
    stage2 = _run("K", 2, tmp_path, calls)
    assert stage2["verdict"] == "PASS" and calls[-1] == ("rows", "K", funnel.FOLD_2023, [1.0])
    assert [fold["n"] for fold in stage2["folds"]] == [80, 80, 80]
    out = _run("K", 3, tmp_path, calls)
    assert (out["verdict"], out["cell"]) == ("PASS", "k1")
    assert calls[-1] == ("rows", "K", funnel.VALIDATION, [1.0])
    assert out["report"]["cell"] == "k1"
    assert (out["instrument"], out["data_source"]) == ("v1", "alpaca")


def test_arms_keep_separate_files(tmp_path):
    calls = []
    _run("K", -1, tmp_path, calls)
    with pytest.raises(SystemExit, match="arm R stage 0 needs 2026-10-24-v191-armR-stageM1.json"):
        _run("R", 0, tmp_path, calls)


def test_stage3_refuses_when_output_exists(tmp_path):
    calls = []
    for stage in (-1, 0, 1, 2, 3):
        _run("K", stage, tmp_path, calls)
    with pytest.raises(SystemExit, match="arm K's one VALIDATION shot is spent"):
        _run("K", 3, tmp_path, calls)


def test_family_refuses_while_an_arm_is_open(tmp_path):
    calls = []
    for stage in (-1, 0, 1, 2, 3):
        _run("K", stage, tmp_path, calls)
    _run("R", -1, tmp_path, calls)                        # REACHABLE: arm R is still open
    with pytest.raises(SystemExit, match="arm\\(s\\) R still open"):
        mabs.run_family(tmp_path)


def test_family_holm_with_an_arm_closed_before_stage3(tmp_path):
    calls = []
    for stage in (-1, 0, 1, 2, 3):
        _run("K", stage, tmp_path, calls)
    _run("R", -1, tmp_path, calls, census=[census_row(("untouched",) * 3)])
    out = mabs.run_family(tmp_path)
    p_k = mabs._load(mabs.stage_path(tmp_path, "K", 3))["permutation_p"]
    assert out["arms"]["R"]["p"] == 1.0 and out["arms"]["R"]["reached_stage3"] is False
    assert out["arms"]["K"]["p_holm"] == pytest.approx(min(1.0, 2 * p_k))
    assert mabs.family_path(tmp_path).exists()


def test_cli_refusals(tmp_path, capsys):
    assert mabs.main(["--arm", "K", "--stage", "3", "--out-dir", str(tmp_path)]) == 1
    assert "refused:no-preregistration" in capsys.readouterr().err
    wrong = tmp_path / "other-spec.md"
    wrong.write_text("x", encoding="utf-8")
    assert mabs.main(["--arm", "K", "--stage", "3", "--out-dir", str(tmp_path),
                      "--preregistration", str(wrong)]) == 1
    assert "refused:no-preregistration" in capsys.readouterr().err
    assert mabs.main(["--arm", "K", "--stage", "3", "--tickers", "3", "--out-dir", str(tmp_path),
                      "--preregistration", str(_prereg(tmp_path))]) == 1
    assert "refused:partial-validation" in capsys.readouterr().err
    assert mabs.main(["--arm", "K", "--stage", "0", "--tickers", "3"]) == 1
    assert "refused:smoke-run" in capsys.readouterr().err
    assert mabs.main(["--stage", "0", "--out-dir", str(tmp_path)]) == 1
    assert "refused:no-arm" in capsys.readouterr().err
    assert mabs.main(["--family", "--arm", "K", "--out-dir", str(tmp_path)]) == 1
    assert "refused:family-takes-no-arm" in capsys.readouterr().err


def test_cli_accepts_alpaca_and_instrument_v1_only(tmp_path):
    with pytest.raises(SystemExit):
        mabs.main(["--arm", "K", "--stage", "-1", "--out-dir", str(tmp_path),
                   "--data-source", "yfinance"])
    with pytest.raises(SystemExit, match="not wired yet"):
        mabs.main(["--arm", "K", "--stage", "-1", "--out-dir", str(tmp_path),
                   "--instrument", "v2"])


def test_cli_runs_the_census_stage(tmp_path, monkeypatch):
    monkeypatch.setattr(mabs, "build", lambda kind, arm, window, cells, **kw: CENSUS)
    assert mabs.main(["--arm", "K", "--stage", "-1", "--out-dir", str(tmp_path)]) == 0
    assert mabs.stage_path(tmp_path, "K", -1).exists()


def test_build_selects_alpaca_before_any_bar_is_read(monkeypatch):
    selected, loaded = [], []
    monkeypatch.setattr(mabs, "universe", lambda: ["AAA", "BBB"])
    monkeypatch.setattr(mabs.training_data, "select", lambda name=None: selected.append(name))
    monkeypatch.setattr(mabs.training_data, "load_daily",
                        lambda ticker: loaded.append((tuple(selected), ticker)))
    assert mabs.build("rows", "K", funnel.FOLD_TRAIN, [1.0], workers=1) == []
    assert selected == ["alpaca"]
    assert loaded == [(("alpaca",), "AAA"), (("alpaca",), "BBB")]


def test_reachability_rows_name_the_driver():
    for attr in ("CONFLUENCE_ATR_STOP_FLOOR", "CONFLUENCE_ATR_TARGET_MODE"):
        assert "scripts/backtest/measure_atr_band_stop.py" in reach.REGISTRY[attr].reason
        assert "measure_arms.py" in reach.REGISTRY[attr].reason
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_measure_atr_band_stop.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'measure_atr_band_stop'`.

- [ ] **Step 3: Write `scripts/backtest/measure_atr_band_stop.py`**

```python
#!/usr/bin/env python3
"""v191 ATR-band stops: Stage -1..3 driver per arm, plus the two-arm Holm family.

  --arm K|R --stage -1  census of plans on fold-train, no outcome -> REACHABLE | refused:zero-diff
  --arm K|R --stage 0   paired dExpR MDE on fold-train             -> POWERED | UNDERPOWERED
  --arm K|R --stage 1   fold-train plateau selection over k         -> SELECTED | NO_ELIGIBLE_CELL
  --arm K|R --stage 2   walk-forward folds 2021 / 2022 / 2023       -> PASS | FAIL
  --arm K|R --stage 3   ONE-SHOT VALIDATION, selected k only        -> PASS | FAIL
  --family              Holm across both arms' Stage 3 p            -> the family file

Each stage reads the same arm's previous verdict JSON and refuses without the
verdict it needs, so a closed arm cannot be advanced by hand. Fold-train rows
are replayed once (stage 0) and reused; the 2023 fold and VALIDATION replay
the selected k only. Stage 3 is refused when its output exists and without
--preregistration <the v191 spec>. Instrument v1 and data source alpaca only;
the universe is measure_arms.cached_universe(): in a worktree set
MEASURE_ARMS_UNIVERSE=cache, HISTORY_STORE_DIR and BACKTEST_CACHE_DIR.

PROGRESS: a flushed line per ticker, plus
logs/measure_atr_band_stop.<arm>.<census|rows>.progress (percent, rewritten
per ticker, deleted on completion).

Run: python scripts/backtest/measure_atr_band_stop.py --arm K --stage -1
"""
from __future__ import annotations

import argparse
import functools
import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "scripts" / "data"), str(ROOT / "scripts" / "backtest")]

from swingbot.core.backtesting import atr_band_funnel as funnel  # noqa: E402
from swingbot.core.backtesting import atr_band_replay as abr  # noqa: E402
from swingbot.core.backtesting.acceptance import BOOTSTRAP_RESAMPLES  # noqa: E402
from swingbot.core.backtesting.backtest_scenarios import _resolve_replay_workers  # noqa: E402
from swingbot.core.backtesting.instrument import cli as instrument_cli  # noqa: E402
from swingbot.core.market.strategy_types import LEGACY_HORIZONS  # noqa: E402
from swingbot.core.marketdata import training_data  # noqa: E402

RESULTS = ROOT / "docs" / "superpowers" / "results" / "v191"
LOG_DIR = ROOT / "logs"
PREFIX = "2026-10-24-v191-arm{arm}"
FAMILY_FILE = "2026-10-24-v191-family.json"
PREREGISTRATION = (ROOT / "docs" / "superpowers" / "specs"
                   / "2026-10-24-v191-confluence-atr-band-stops-design.md")
#: stage -> (the stage it consumes, the verdict that stage must carry).
REQUIRES = {0: (-1, "REACHABLE"), 1: (0, "POWERED"), 2: (1, "SELECTED"), 3: (2, "PASS")}
ADVANCING = ("REACHABLE", "POWERED", "SELECTED", "PASS")
KINDS = {"rows": abr.replay_entries, "census": abr.census}


def stage_path(out_dir, arm, stage) -> Path:
    label = "M1" if stage == -1 else str(stage)
    return Path(out_dir) / f"{PREFIX.format(arm=arm)}-stage{label}.json"


def rows_path(out_dir, arm, name) -> Path:
    return Path(out_dir) / f"{PREFIX.format(arm=arm)}-{name}-rows.json"


def family_path(out_dir) -> Path:
    return Path(out_dir) / FAMILY_FILE


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write(path, blob, indent=1) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(blob, indent=indent), encoding="utf-8")


def _refuse(message):
    raise SystemExit(f"refused: {message}")


# --- replay ------------------------------------------------------------------

def _init_worker() -> None:
    """Every process reads the alpaca store: BACKTEST_CACHE_DIR in a worktree
    would otherwise default the training source to yfinance."""
    training_data.select(funnel.DATA_SOURCE)


def _worker(task):
    """One ticker, one arm, every legacy horizon -- the process-pool entry point."""
    kind, arm, ticker, window, cells = task
    frame = training_data.load_daily(ticker)
    if frame is None or len(frame) == 0:
        return ticker, []
    return ticker, KINDS[kind](ticker, frame, LEGACY_HORIZONS, arm=arm,
                               start=window[0], end=window[1], cells=cells)


def _write_progress(path, done, total) -> None:
    try:
        path.write_text(f"{done}/{total} tickers ({done / total * 100:.0f}%)\n",
                        encoding="utf-8")
    except OSError:
        pass


def universe() -> list[str]:
    from measure_arms import cached_universe
    return cached_universe()


def _run_tasks(tasks, record, workers) -> None:
    n_workers = _resolve_replay_workers(workers)
    if n_workers <= 1 or len(tasks) <= 1:
        _init_worker()
        for task in tasks:
            record(*_worker(task))
        return
    with ProcessPoolExecutor(max_workers=n_workers, initializer=_init_worker) as pool:
        for future in as_completed([pool.submit(_worker, task) for task in tasks]):
            record(*future.result())


def build(kind, arm, window, cells, *, tickers=None, workers=None) -> list:
    """Replay every universe ticker for one arm; rows come back in ticker
    order, so the output is identical whatever order the pool finishes in."""
    names = universe()
    names = names[:tickers] if tickers else names
    tasks = [(kind, arm, ticker, tuple(window), tuple(float(k) for k in cells))
             for ticker in names]
    LOG_DIR.mkdir(exist_ok=True)
    progress = LOG_DIR / f"measure_atr_band_stop.{arm}.{kind}.progress"
    by_ticker: dict = {}

    def record(ticker, rows):
        by_ticker[ticker] = rows or []
        print(f"  [arm {arm} {kind} {window[0]}..{window[1]}] {len(by_ticker)}/{len(tasks)} "
              f"{ticker}: {len(by_ticker[ticker])} entries", flush=True)
        _write_progress(progress, len(by_ticker), len(tasks))

    _run_tasks(tasks, record, workers)
    progress.unlink(missing_ok=True)
    return [row for ticker in sorted(by_ticker) for row in by_ticker[ticker]]


# --- stages ------------------------------------------------------------------

def _previous(out_dir, arm, stage) -> dict:
    """The same arm's verdict JSON this stage consumes, or a refusal."""
    needed_stage, needed_verdict = REQUIRES[stage]
    path = stage_path(out_dir, arm, needed_stage)
    if not path.exists():
        _refuse(f"arm {arm} stage {stage} needs {path.name} -- run stage {needed_stage} first")
    previous = _load(path)
    if previous["verdict"] != needed_verdict:
        _refuse(f"arm {arm} closed at stage {needed_stage} with {previous['verdict']} "
                f"-- stage {stage} does not run")
    return previous


def _saved(out_dir, arm, name, kind, window, cells, build_fn) -> list:
    """Rows from the rows file, building (and saving) them when absent."""
    path = rows_path(out_dir, arm, name)
    if not path.exists():
        _write(path, build_fn(kind, arm, window, cells), indent=None)
    return _load(path)


def _train_rows(out_dir, arm, build_fn) -> list:
    return _saved(out_dir, arm, "train", "rows", funnel.FOLD_TRAIN, abr.K_STEPS, build_fn)


def _stage_m1(out_dir, arm, build_fn, n_resamples) -> dict:
    rows = _saved(out_dir, arm, "census-train", "census", funnel.FOLD_TRAIN, abr.K_STEPS,
                  build_fn)
    return funnel.stage_minus1(rows, arm)


def _stage0(out_dir, arm, build_fn, n_resamples) -> dict:
    cells = _previous(out_dir, arm, 0)["reachable_cells"]
    return funnel.stage0(_train_rows(out_dir, arm, build_fn), arm, cells=cells)


def _stage1(out_dir, arm, build_fn, n_resamples) -> dict:
    cells = _previous(out_dir, arm, 1)["powered_cells"]
    rows = _train_rows(out_dir, arm, build_fn)
    out = funnel.stage1(rows, arm, cells=cells, n_resamples=n_resamples)
    out["reports"] = [funnel.report(rows, arm, abr.cell_key(k), n_resamples=n_resamples)
                      for k in abr.K_STEPS]
    return out


def _fold_rows(out_dir, arm, k, build_fn) -> dict:
    """Folds inside fold-train come from the train rows; the 2023 fold is
    replayed for the selected k only."""
    train = _train_rows(out_dir, arm, build_fn)
    last_train_year = int(funnel.FOLD_TRAIN[1][:4])
    by_year = {year: [r for r in train if r["entry_date"][:4] == str(year)]
               for year in funnel.FOLD_YEARS if year <= last_train_year}
    by_year[int(funnel.FOLD_2023[0][:4])] = _saved(out_dir, arm, "fold2023", "rows",
                                                   funnel.FOLD_2023, [k], build_fn)
    return by_year


def _stage2(out_dir, arm, build_fn, n_resamples) -> dict:
    selected = _previous(out_dir, arm, 2)["selected"]
    return funnel.stage2(_fold_rows(out_dir, arm, selected["k"], build_fn), arm,
                         selected["cell"])


def _stage3(out_dir, arm, build_fn, n_resamples) -> dict:
    _previous(out_dir, arm, 3)
    selected = _load(stage_path(out_dir, arm, 1))["selected"]
    rows = _saved(out_dir, arm, "validation", "rows", funnel.VALIDATION, [selected["k"]],
                  build_fn)
    out = funnel.stage3(rows, arm, selected["cell"], n_resamples=n_resamples)
    out["report"] = funnel.report(rows, arm, selected["cell"], n_resamples=n_resamples)
    return out


_STAGES = {-1: _stage_m1, 0: _stage0, 1: _stage1, 2: _stage2, 3: _stage3}


def run_stage(arm, stage, out_dir, *, build, n_resamples: int = BOOTSTRAP_RESAMPLES) -> dict:
    """Run one stage for one arm and write its verdict JSON. Stages -1..2 are
    fold-train and deterministic, so they may be re-run; stage 3 may not."""
    out_dir = Path(out_dir)
    target = stage_path(out_dir, arm, stage)
    if stage == 3 and target.exists():
        _refuse(f"{target.name} exists -- arm {arm}'s one VALIDATION shot is spent")
    out = _STAGES[stage](out_dir, arm, build, n_resamples)
    out.update({"instrument": funnel.INSTRUMENT, "data_source": funnel.DATA_SOURCE})
    _write(target, out)
    return out


# --- the family ----------------------------------------------------------------

def _closed(out_dir, arm) -> bool:
    """Closed once Stage 3 ran, or once any stage carries a non-advancing verdict."""
    if stage_path(out_dir, arm, 3).exists():
        return True
    paths = [stage_path(out_dir, arm, stage) for stage in (-1, 0, 1, 2)]
    return any(path.exists() and _load(path)["verdict"] not in ADVANCING for path in paths)


def _stage3_or_none(out_dir, arm):
    path = stage_path(out_dir, arm, 3)
    return _load(path) if path.exists() else None


def run_family(out_dir) -> dict:
    """Holm across both arms, once both are closed; an arm closed before
    Stage 3 enters as p = 1.0 (atr_band_funnel.holm_family)."""
    out_dir = Path(out_dir)
    open_arms = [arm for arm in funnel.FAMILY if not _closed(out_dir, arm)]
    if open_arms:
        _refuse(f"arm(s) {', '.join(open_arms)} still open -- the family runs once both "
                "arms are closed")
    out = funnel.holm_family({arm: _stage3_or_none(out_dir, arm) for arm in funnel.FAMILY})
    _write(family_path(out_dir), out)
    return out


# --- CLI ---------------------------------------------------------------------

def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument("--stage", type=int, choices=sorted(_STAGES))
    which.add_argument("--family", action="store_true")
    parser.add_argument("--arm", choices=sorted(abr.ARMS), default=None)
    parser.add_argument("--out-dir", type=Path, default=RESULTS)
    parser.add_argument("--preregistration", type=Path, default=None)
    parser.add_argument("--tickers", type=int, default=None)
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--resamples", type=int, default=BOOTSTRAP_RESAMPLES)
    parser.add_argument("--data-source", choices=(funnel.DATA_SOURCE,), default=funnel.DATA_SOURCE)
    instrument_cli.add_instrument_arg(parser)
    return parser


def _preregistered(path) -> bool:
    return path is not None and path.exists() and path.name == PREREGISTRATION.name


def _cli_refusal(args) -> str | None:
    if args.family:
        return None if args.arm is None else \
            "refused:family-takes-no-arm -- --family reads both arms' Stage 3 files"
    if args.arm is None:
        return "refused:no-arm -- a stage runs for one arm: --arm K or --arm R"
    if args.tickers and args.stage == 3:
        return ("refused:partial-validation -- stage 3 is the one shot and runs "
                "the full universe; drop --tickers")
    if args.tickers and args.out_dir.resolve() == RESULTS.resolve():
        return ("refused:smoke-run -- --tickers needs a scratch --out-dir, never "
                "the committed results directory")
    if args.stage == 3 and not _preregistered(args.preregistration):
        return (f"refused:no-preregistration -- stage 3 needs --preregistration "
                f"<committed {PREREGISTRATION.name}>. This is the one shot.")
    return None


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    instrument_cli.require_v1(instrument_cli.spec_from_args(args), "measure_atr_band_stop.py",
                              "a later plan")
    refusal = _cli_refusal(args)
    if refusal:
        print(refusal, file=sys.stderr)
        return 1
    if args.family:
        out = run_family(args.out_dir)
        print(f"v191 family: passed {out['passed'] or 'none'} -> {family_path(args.out_dir)}",
              flush=True)
        return 0
    build_fn = functools.partial(build, tickers=args.tickers, workers=args.workers)
    out = run_stage(args.arm, args.stage, args.out_dir, build=build_fn,
                    n_resamples=args.resamples)
    print(f"arm {args.arm} stage {args.stage}: {out['verdict']} -> "
          f"{stage_path(args.out_dir, args.arm, args.stage)}", flush=True)
    return 0 if out["verdict"] in ADVANCING else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Name the driver in the reachability text** — `swingbot/core/backtesting/arms/reachability.py`

In `_V191` (written by V191-2), replace the last sentence `"Gated by the v92 harvest gate through a v139-style staged driver, not "` / `"measure_arms.py."` with:

```python
         "never. Gated by the v92 harvest gate through "
         "scripts/backtest/measure_atr_band_stop.py, not measure_arms.py.")
```

so the full constant reads `... Confluence plans only; strategy plans never. Gated by the v92 harvest gate through scripts/backtest/measure_atr_band_stop.py, not measure_arms.py.` V191-2's `test_reachability_row_is_confluence_only` (`"measure_arms.py" in reason`) still holds.

- [ ] **Step 5: Run the tests and the gates**

```bash
python scripts/dev/testrun.py file tests/backtest_scripts/test_measure_atr_band_stop.py
python scripts/dev/testrun.py file tests/test_config_v191_atr_band.py
python scripts/dev/testrun.py file tests/backtesting/arms/test_reachability.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_measure_confluence_stop.py
python scripts/dev/complexity_gate.py
```
Expected: `0 failed`; `_cli_refusal` stays under complexity 15 (seven returns).

- [ ] **Step 6: Commit**

```bash
git add scripts/backtest/measure_atr_band_stop.py swingbot/core/backtesting/arms/reachability.py tests/backtest_scripts/test_measure_atr_band_stop.py
git commit -m "feat(backtest): v191 stage driver -- per-arm stage chain, one-shot refusals, alpaca-only build, two-arm Holm family

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

# Phase 9 — Part B impact report

### Task V191-18: Part B impact report `--side long, short or both`

**Model:** sonnet — a read-only descriptive report extended along one table-driven axis; the one subtlety is keeping the default (`short`) output byte-identical, pinned below.

**Files:**
- Modify: `scripts/reports/short_gap_sizing_impact.py`
- Modify: `tests/scripts/test_short_gap_sizing_impact.py` (append; every existing test stays as it is and must stay green)

**Interfaces:**
- Consumes: `gap_stats(df, lookback)` keys `p99_down_gap_pct`, `n_down` and `gap_sizing.MIN_DOWN_GAPS` (V191-5); the long stamp key `down_gap_p99_pct` on stored trades (V191-5); existing `compute_position_size(entry, stop, cfg, gap_floor_pct=)`, `r_multiple`, the module's own helpers.
- Produces: CLI `--side {short,long,both}` (default `short`); `Side` (NamedTuple: `name, direction, stamp_key, stats_key, count_key, min_gaps`), `SHORT`, `LONG`, `SIDES`; `closed_side(trades, side)`; `resize_closed(trades, frames, *, side, balance, risk_pct) -> dict` (result key `n_closed_shorts` or `n_closed_longs`); `render_long_markdown(result, *, run_date, db_name, balance, risk_pct) -> str`; summary keys `n_exceed_before`, `n_exceed_after` (both sides; rendered for longs only). `side=SHORT` defaults on `trade_p99`, `_bars_p99`, `resize_trade`, `_result_table`, `_stdout_lines`; `closed_shorts` and `resize_closed_shorts` keep their signatures.
- Byte identity: with `--side short` or no `--side`, stdout and the markdown file equal today's output exactly. `closed_shorts`, `resize_closed_shorts`, `render_markdown`, `LIMITS`, `ROLLBACK_NOTE` keep their text; the generalised helpers produce today's strings for `SHORT` (the plural is `f"{side.name}s"` = `shorts`, the exceedance rows and line are appended for `LONG` only).

Rules: a long's p99 is the trade's stored `down_gap_p99_pct` stamp when present, else the p99 of down-gaps (`p99_down_gap_pct`, a positive percent) over the `LOOKBACK` completed daily bars before the open, `None` under `MIN_DOWN_GAPS` down-gaps; sizing is v183's `max(|entry − stop|, entry × p99 / 100)` through `compute_position_size(..., gap_floor_pct=p99)`. A dollar exceedance is `pnl < −(unit + EXCEED_TOL_DOLLARS)` with `EXCEED_TOL_DOLLARS = 0.5` (0.01-share rounding noise), counted before and after. `--side both` prints the short lines, then the long lines, and writes the short document followed by the long one.

- [ ] **Step 1: Append the failing tests** to `tests/scripts/test_short_gap_sizing_impact.py`

```python
# --- v191: --side long / both ----------------------------------------------------------------

def _down_bars(down_pct, n=300, start="2024-01-01"):
    """Close 100 every day; even days open down_pct below the prior close, odd days 0.5% above,
    so every down-gap equals down_pct (p99 == down_pct) and n_down is about n / 2."""
    rows = []
    for i in range(n):
        o = 100.0 * (1 - down_pct / 100.0) if i % 2 == 0 else 100.5
        rows.append((o, max(o, 100.0) * 1.001, min(o, 100.0) * 0.999, 100.0))
    return make_ohlcv(rows, start=start)


def _long(tid="l1", ticker="AAA", exit_price=97.0, status="loss", **kw):
    t = {"id": tid, "ticker": ticker, "direction": "bullish", "status": status,
         "entry": 100.0, "stop_loss": 99.0, "exit_price": exit_price,
         "opened_at": "2025-03-01T15:00:00+00:00", "closed_at": "2025-03-05T15:00:00+00:00"}
    t.update(kw)
    return t


def _run_long(trades, frames):
    return imp.resize_closed(trades, frames, side=imp.LONG, balance=BAL, risk_pct=RISK)


def test_sides_table():
    assert imp.SIDES == {"short": imp.SHORT, "long": imp.LONG}
    assert (imp.LONG.direction, imp.LONG.stamp_key, imp.LONG.stats_key, imp.LONG.count_key) == \
        ("bullish", "down_gap_p99_pct", "p99_down_gap_pct", "n_down")
    assert imp.LONG.min_gaps == imp.MIN_DOWN_GAPS == 60
    assert (imp.SHORT.direction, imp.SHORT.stamp_key) == ("bearish", "up_gap_p99_pct")


def test_long_down_gap_wider_than_stop_cuts_shares_and_counts_the_exceedance():
    out = _run_long([_long()], {"AAA": _down_bars(3.0)})
    (row,) = out["rows"]
    assert out["n_closed_longs"] == 1
    assert (row["p99"], row["p99_source"]) == (pytest.approx(3.0), "bars")
    assert row["shares_before"] == pytest.approx(100.0)
    assert row["shares_after"] == pytest.approx(33.33)
    assert row["r"] == pytest.approx(-3.0)                       # gapped through 99 to 97
    assert (row["pnl_before"], row["pnl_after"]) == (pytest.approx(-300.0), pytest.approx(-99.99))
    s = out["summary"]
    assert (s["n_exceed_before"], s["n_exceed_after"]) == (1, 0)


def test_long_stamp_wins_and_too_few_down_gaps_mean_no_cut():
    stamp = {"rule": "gap_p99", "down_gap_p99_pct": 2.0, "n_down_gaps": 120}
    (row,) = _run_long([_long(gap_sizing=stamp)], {})["rows"]
    assert (row["p99"], row["p99_source"], row["shares_after"]) == (2.0, "stamp", pytest.approx(50.0))
    (row,) = _run_long([_long()], {"AAA": _down_bars(3.0, n=40)})["rows"]
    assert (row["p99"], row["p99_source"]) == (None, "none")
    assert row["shares_after"] == row["shares_before"]


def test_each_side_reads_only_its_own_direction():
    trades = [_long(), _short()]
    assert [r["id"] for r in _run_long(trades, {"AAA": _down_bars(3.0)})["rows"]] == ["l1"]
    assert [r["id"] for r in _run(trades, {"AAA": _bars(3.0)})["rows"]] == ["t1"]


def test_short_summary_counts_exceedances_but_its_markdown_is_unchanged():
    out = _run([_short()], {"AAA": _bars(3.0)})
    assert (out["summary"]["n_exceed_before"], out["summary"]["n_exceed_after"]) == (1, 0)
    text = imp.render_markdown(out, run_date="2026-11-02", db_name="swingbot_prod_replica",
                               balance=BAL, risk_pct=RISK)
    assert "Losses past the fixed risk" not in text
    assert "| Closed shorts in the book | 1 |" in text
    assert "| Mean size cut, gap-sized shorts |" in text


def test_long_markdown_carries_every_measure_and_the_coupled_rollback():
    out = _run_long([_long()], {"AAA": _down_bars(3.0)})
    text = imp.render_long_markdown(out, run_date="2026-11-02", db_name="swingbot_prod_replica",
                                    balance=BAL, risk_pct=RISK)
    for needle in ("# v191 gap sizing impact: the live book's closed longs re-sized",
                   "| Closed longs in the book | 1 |", "| Losses past the fixed risk, before | 1 |",
                   "| Losses past the fixed risk, after | 0 |", "## Long-book drawdown",
                   "## Limits", "## Rollback", "LONG_GAP_SIZING=false",
                   "CONFLUENCE_ATR_STOP_FLOOR", "stay in the book as recorded",
                   "-$300.00", "-$99.99", "not a gate", "--side long"):
        assert needle in text, needle


def _main(monkeypatch, tmp_path, capsys, name, *extra):
    from swingbot import config
    from swingbot.core.db import engine
    monkeypatch.setattr(config, "DATABASE_URL", "postgresql+psycopg://u:p@h:5/swingbot")
    monkeypatch.setattr(engine, "reset_engine", lambda: None)
    monkeypatch.setattr(imp, "_trades", lambda: [_short(), _long()])
    monkeypatch.setattr(imp, "_frames", lambda tickers: {"AAA": _bars(3.0)})
    out = tmp_path / name
    assert imp.main(["--out", str(out), *extra]) == 0
    return capsys.readouterr().out, out.read_text(encoding="utf-8")


def test_default_side_is_short_and_byte_identical(monkeypatch, tmp_path, capsys):
    default_out, default_md = _main(monkeypatch, tmp_path, capsys, "a.md")
    short_out, short_md = _main(monkeypatch, tmp_path, capsys, "b.md", "--side", "short")
    assert (default_out, default_md) == (short_out, short_md)
    result = imp.resize_closed_shorts([_short(), _long()], {"AAA": _bars(3.0)},
                                      balance=BAL, risk_pct=RISK)
    assert default_out == "\n".join(imp._stdout_lines(result)) + "\n"
    run_date = default_md.split("**Run:** ")[1][:10]
    assert default_md == imp.render_markdown(result, run_date=run_date,
                                             db_name="swingbot", balance=BAL, risk_pct=RISK)


def test_both_sides_print_and_write_short_then_long(monkeypatch, tmp_path, capsys):
    out, md = _main(monkeypatch, tmp_path, capsys, "c.md", "--side", "both")
    lines = out.splitlines()
    assert lines[0].startswith("closed_shorts: ")
    assert any(line.startswith("closed_longs: ") for line in lines)
    assert lines[-1].startswith("exceed_before/after: ")
    assert md.index("closed shorts re-sized") < md.index("closed longs re-sized")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_short_gap_sizing_impact.py`
Expected: the existing tests pass; the new ones FAIL with `AttributeError: module 'short_gap_sizing_impact' has no attribute 'resize_closed'` (and `SIDES`, `LONG`, `render_long_markdown`), and `main` rejecting `--side`.

- [ ] **Step 3: Implement in `scripts/reports/short_gap_sizing_impact.py`**

Docstring: change the first line to `"""v183/v191 impact: the live book's closed shorts (and, with --side, longs) re-sized under the gap rule.` and add one paragraph before `Run locally`: `--side long (v191 Part B) re-sizes closed longs with the p99 DOWN-gap (stored down_gap_p99_pct stamp, else the bars before the open, fewer than MIN_DOWN_GAPS: no change); --side both writes the short document, then the long one. The default, short, is byte-identical to the v183 report.` (The argparse description is the first line; it is never printed in a normal run.)

Imports: add `from typing import NamedTuple` and change the gap-sizing import to `from swingbot.core.planning.gap_sizing import LOOKBACK, MIN_DOWN_GAPS, MIN_UP_GAPS  # noqa: E402`.

Below `SPEC = ...` add:

```python
LONG_SPEC = "../specs/2026-10-24-v191-confluence-atr-band-stops-design.md"
#: A loss past the fixed risk by more than this is an exceedance; less is the
#: rounding noise of 0.01-share sizing.
EXCEED_TOL_DOLLARS = 0.5


class Side(NamedTuple):
    name: str          # "short" | "long"
    direction: str     # the book's direction for this side
    stamp_key: str     # the stored gap_sizing p99 key
    stats_key: str     # the gap_stats p99 key
    count_key: str     # the gap_stats count key
    min_gaps: int      # fewer gaps: no usable p99


SHORT = Side("short", "bearish", "up_gap_p99_pct", "p99_up_gap_pct", "n_up", MIN_UP_GAPS)
LONG = Side("long", "bullish", "down_gap_p99_pct", "p99_down_gap_pct", "n_down", MIN_DOWN_GAPS)
SIDES = {"short": SHORT, "long": LONG}
```

Below `ROLLBACK_NOTE = (...)` add:

```python
LONG_LIMITS = (
    "- p99 over about 125 down-gaps is roughly the one or two largest down-gaps of the year: noisy, "
    "the same limit v183 accepted for shorts.\n"
    "- Position caps are off and OPEX scaling is pinned to 1.0 so only the gap rule moves size; "
    "with the live caps the cut is the same or smaller.\n"
    "- No long carried a down-gap stamp before v191 shipped; its p99 is recomputed from the cached daily bars "
    "before the open, so a bar-cache gap shows up as `none` (size unchanged).\n"
    "- R, win rate and ExpR are identical on both sides by construction (R is measured on the stop); "
    "only dollars move.\n"
    "- A gap beyond the ticker's own p99 can still exceed the budget; the exceedance rows count those losses.\n"
)

LONG_ROLLBACK_NOTE = (
    "- **No deploy needed:** set `LONG_GAP_SIZING=false` in `.env` or the admin config page; the bot hot-reloads. "
    "A live `CONFLUENCE_ATR_STOP_FLOOR > 0` is honoured only with `LONG_GAP_SIZING` and `SHORT_GAP_SIZING` "
    "both on, so turning this off also zeroes a live floor (logged at ERROR).\n"
    "- Plans stamped while the switch was on keep their stamped rule; long plans created after the flip "
    "size on the stop exactly as before v191.\n"
    "- Paper trades already sized by the gap rule stay in the book as recorded; nothing re-sizes them.\n"
)
```

Replace `closed_shorts`, `_bars_p99`, `trade_p99`, `resize_trade` and `resize_closed_shorts` with:

```python
def closed_side(trades: list[dict], side: Side) -> list[dict]:
    return [t for t in trades if t.get("direction") == side.direction and t.get("status") in CLOSED]


def closed_shorts(trades: list[dict]) -> list[dict]:
    return closed_side(trades, SHORT)


def _bars_p99(trade: dict, bars, side: Side = SHORT) -> float | None:
    if bars is None or bars.empty or not trade.get("opened_at"):
        return None
    idx = pd.DatetimeIndex(bars.index)
    idx = idx.tz_localize(None) if idx.tz is not None else idx
    stats = gap_stats(bars[idx < _opened_session(trade)], lookback=LOOKBACK)
    return stats[side.stats_key] if stats[side.count_key] >= side.min_gaps else None


def trade_p99(trade: dict, bars, side: Side = SHORT) -> tuple[float | None, str]:
    stamp = trade.get("gap_sizing") or {}
    if stamp.get(side.stamp_key) is not None:
        return float(stamp[side.stamp_key]), "stamp"
    p99 = _bars_p99(trade, bars, side)
    return (p99, "bars") if p99 is not None else (None, "none")
```

In `resize_trade`, add the parameter `side: Side = SHORT` last and change only its p99 line to `p99, source = trade_p99(trade, bars, side)`; the rest of its body stays.

In `_summary`, add two keys after `"pnl_after"`:

```python
            "n_exceed_before": sum(x["pnl_before"] < -(unit + EXCEED_TOL_DOLLARS) for x in rows),
            "n_exceed_after": sum(x["pnl_after"] < -(unit + EXCEED_TOL_DOLLARS) for x in rows),
```

Replace `resize_closed_shorts` with:

```python
def resize_closed(trades: list[dict], frames: dict, *, side: Side, balance: float,
                  risk_pct: float) -> dict:
    cfg = _fixed_cfg(balance, risk_pct)
    closed = closed_side(trades, side)
    with _fixed_risk():
        rows = [row for t in closed
                if (row := resize_trade(t, frames.get(t.get("ticker")), cfg, side))]
    return {f"n_closed_{side.name}s": len(closed), "rows": rows,
            "summary": _summary(rows, balance, risk_pct)}


def resize_closed_shorts(trades: list[dict], frames: dict, *, balance: float, risk_pct: float) -> dict:
    return resize_closed(trades, frames, side=SHORT, balance=balance, risk_pct=risk_pct)
```

Generalise `_result_table` (same strings for `SHORT`):

```python
def _exceed_rows(s: dict, side: Side) -> list:
    if side is SHORT:
        return []
    return [("Losses past the fixed risk, before", s["n_exceed_before"]),
            ("Losses past the fixed risk, after", s["n_exceed_after"])]


def _result_table(result: dict, s: dict, side: Side = SHORT) -> str:
    n_bars = s["n_analysed"] - s["n_from_stamp"] - s["n_no_p99"]
    mean_r = "n/a" if s["mean_r"] is None else f"{s['mean_r']:+.3f}R"
    plural = f"{side.name}s"
    rows = [
        (f"Closed {plural} in the book", result[f"n_closed_{plural}"]),
        ("Analysed (R computable)", s["n_analysed"]),
        ("p99 from a stored stamp / from bars / none", f"{s['n_from_stamp']} / {n_bars} / {s['n_no_p99']}"),
        ("Gap-sized (share cut)", f"{s['n_gap_sized']} ({_pct(s['share_gap_sized_pct'])})"),
        (f"Mean size cut, gap-sized {plural}", _pct(s["mean_cut_pct_gap_sized"])),
        (f"Mean size cut, all analysed {plural}", _pct(s["mean_cut_pct_all"])),
        ("Mean R (identical both sides)", mean_r),
        ("Dollar P&L at fixed risk, before", _money(s["pnl_before"])),
        ("Dollar P&L at fixed risk, after", _money(s["pnl_after"])),
    ] + _exceed_rows(s, side)
    return "| Measure | Value |\n|---|---|\n" + "".join(f"| {k} | {v} |\n" for k, v in rows)
```

`render_markdown` is untouched (it calls `_result_table(result, s)`, i.e. `SHORT`). Add below it:

```python
def render_long_markdown(result: dict, *, run_date: str, db_name: str, balance: float,
                         risk_pct: float) -> str:
    s = result["summary"]
    return (
        "# v191 gap sizing impact: the live book's closed longs re-sized\n\n"
        f"**Spec:** [v191 design]({LONG_SPEC}) § \"Part B — gap-aware dollar sizing for longs and shorts\"\n"
        f"**Run:** {run_date} on `{db_name}` (read-only replica of production), "
        "`scripts/reports/short_gap_sizing_impact.py --side long`\n"
        "**Status:** descriptive, not a gate. `LONG_GAP_SIZING=false` is the revert path.\n\n"
        "## What is measured\n\n"
        "Each closed long (status win/loss/closed, direction bullish) is sized twice at a fixed risk of "
        f"{_money(s['unit'])} per trade (balance {_money(balance)}, {risk_pct}%): on the stop, and with the gap "
        "floor `max(|entry - stop|, entry x p99_down_gap / 100)`. p99 source: the trade's stored stamp, else the "
        "down-gaps over the 250 completed daily bars before the open (fewer than 60 down-gaps: no p99, no change). "
        "Dollar P&L = shares x stop distance x the book's R. An exceedance is a dollar loss past the fixed risk.\n\n"
        f"## Result\n\n{_result_table(result, s, LONG)}\n"
        "## Worst five dollar losses\n\nBefore (stop sizing):\n\n"
        f"{_worst_table(s['worst_before'])}\nAfter (gap sizing):\n\n{_worst_table(s['worst_after'])}\n"
        f"## Long-book drawdown\n\n{_drawdown_table(s, balance)}\n"
        f"## Limits\n\n{LONG_LIMITS}\n## Rollback\n\n{LONG_ROLLBACK_NOTE}"
    )


def _render(result: dict, side: Side, **kw) -> str:
    return render_markdown(result, **kw) if side is SHORT else render_long_markdown(result, **kw)
```

Generalise `_stdout_lines` (same lines for `SHORT`):

```python
def _stdout_lines(result: dict, side: Side = SHORT) -> list[str]:
    s = result["summary"]
    n_bars = s["n_analysed"] - s["n_from_stamp"] - s["n_no_p99"]
    plural = f"{side.name}s"
    lines = [f"closed_{plural}: {result[f'n_closed_{plural}']}", f"analysed: {s['n_analysed']}",
             f"p99_stamp/bars/none: {s['n_from_stamp']}/{n_bars}/{s['n_no_p99']}",
             f"gap_sized: {s['n_gap_sized']} ({_pct(s['share_gap_sized_pct'])})",
             f"mean_cut_gap_sized: {_pct(s['mean_cut_pct_gap_sized'])}",
             f"mean_cut_all: {_pct(s['mean_cut_pct_all'])}", f"mean_r: {_num(s['mean_r'])}",
             f"pnl_before: {_money(s['pnl_before'])}", f"pnl_after: {_money(s['pnl_after'])}"]
    if side is not SHORT:
        lines.append(f"exceed_before/after: {s['n_exceed_before']}/{s['n_exceed_after']}")
    return lines
```

In `main`: add the argument `ap.add_argument("--side", choices=("short", "long", "both"), default="short", help="which closed trades to re-size (v191 adds long and both; default short, the v183 report)")` after `--risk-pct`, and replace everything from `trades = _trades()` to the `args.out.write_text(...)` line with:

```python
    sides = [SHORT, LONG] if args.side == "both" else [SIDES[args.side]]
    trades = _trades()
    tickers = sorted({t["ticker"] for side in sides for t in closed_side(trades, side)})
    frames = _csv_frames(tickers, args.bars_dir) if args.bars_dir else _frames(tickers)
    results = [(side, resize_closed(trades, frames, side=side, balance=args.balance,
                                    risk_pct=args.risk_pct)) for side in sides]
    print("\n".join(line for side, result in results for line in _stdout_lines(result, side)))
    if args.out:
        run_date = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
        text = "\n".join(_render(result, side, run_date=run_date, db_name=db_name,
                                 balance=args.balance, risk_pct=args.risk_pct)
                         for side, result in results)
        args.out.write_text(text, encoding="utf-8")
    return 0
```

For `--side short` the ticker set, the one result, the printed lines and the single-document text are exactly today's.

- [ ] **Step 4: Run the tests and the gates**

```bash
python scripts/dev/testrun.py file tests/scripts/test_short_gap_sizing_impact.py
python scripts/dev/complexity_gate.py
```
Expected: `0 failed`, every pre-v191 test in the file unchanged and green; `main` stays under complexity 15.

- [ ] **Step 5: Commit**

```bash
git add scripts/reports/short_gap_sizing_impact.py tests/scripts/test_short_gap_sizing_impact.py
git commit -m "feat(reports): v191 Part B impact report -- --side long|both with down-gap p99 and dollar exceedance; short output byte-identical

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
