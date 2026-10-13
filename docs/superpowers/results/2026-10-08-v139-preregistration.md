# v139 — Confluence stop geometry: pre-registration

Written before any measurement. Spec: `docs/superpowers/specs/2026-10-08-v139-confluence-stop-geometry-design.md`.
Plan: `docs/superpowers/plans/2026-10-08-v139-confluence-stop-geometry_0-index.md` (Spec corrections 7-11 are part of this record).

Closed-row check (V139-11 Step 1): no row of "Closed pre-registrations — do not re-run these" closes a structural confluence stop sized to dollar risk, or a confluence drop by structural stop distance. v104 Part A is strategy × direction cells, v129 arm Z is a disaster stop plus close exit capped at 2%, v101 is the Fibonacci rescue; the spec's § Not a re-run argues each.

## Claim
On confluence plans whose structural stop is beyond the 2% cap:

- **Arm S:** keeping the structural stop up to a ceiling `c`, with the target re-selected against that risk and the position sized to fixed dollar risk, raises per-trade expectancy under the v92 harvest gate, on the same entries.
- **Arm D:** issuing no plan when the structural stop is beyond `c` raises pooled expectancy without breaking the v72 funnel's win-rate and volume clauses.

Two arms, two populations, two budgets. A pass in one never carries the other, and the two are never pooled.

## Definitions (frozen at the plan's creating bar)
- **Clamped plan:** `source == "confluence"`, the scenario stop is on the stop side of entry, and `planned_loss_pct(entry, scenario.stop_loss) > HARD_MAX_PLANNED_LOSS_PCT`. That is exactly the set `_clamp_stop_to_hard_cap` moves today. Every other plan is untouched in both arms.
- **Structural distance `d`:** `planned_loss_pct(entry, scenario.stop_loss)` — the stop the scenario was built with, before the clamp.
- **Ceiling grid:** `c ∈ {3.0, 4.0, 5.0}` percent, shared by both arms. Scenario admission (`analyze._scan_one`) already bounds `d` by the horizon's `max_risk_pct`, so `c` never exceeds what is admitted today.
- **Headroom:** `CLAMP_HEADROOM_PCT` (0.25), as v115 uses it. A plan is placed only when `d ≤ c − 0.25`, so a fill slightly past the trigger stays inside the stored ceiling `c` and is not cancelled as `cancelled_risk_cap`.

Boundaries carry a 1e-9 tolerance: d exactly at c − 0.25 is arm S; d exactly at c is kept by arm D.

## Arm S — structural stop, dollar sizing
- Rule, for a clamped plan:
  - `d ≤ c − 0.25`: `stop_loss = scenario.stop_loss`. TP1 and TP2 are re-selected with `select_structural_target` against the structural risk, from the same candidates and the same `MIN/MAX_RISK_REWARD_RATIO` band. The plan stores `stop_ceiling_pct = c`.
  - Same, but **no candidate clears the RR band** at the structural risk: the plan reverts to today's clamped plan (rollback). Counted and disclosed, never dropped.
  - `d > c − 0.25`: today's clamped plan.

  Arm S never adds or removes a plan (plan index, Spec correction 8); the replay asserts it. 1R is entry → structural stop; sizing is `account.compute_position_size` in `risk_pct` mode and `stop_scope.risk_sizing_ok` must pass.
- Gate: the v92 harvest gate, paired, exactly as v129 ran it (constants imported from `acceptance_exit_funnel.py`: `TRAIN`, `VALIDATION`, `MDE_CEILING_R` = 0.10, `MDE_POWER` = 0.80, `ELIGIBILITY_CLAUSES` = expectancy_gain / win_rate_floor / volume), bootstrap clustered by ISO week (`cluster="week"`, instrument v2).
- Fills and costs: the repository's current exit simulation (`exit_sim.simulate_exit`, `scale_out=True`). At the creating bar neither `swingbot/core/planning/exit_sim_v2.py` (v157) nor an `--instrument` flag on `measure_confluence_stop.py`, `measure_arms.py`, `validate_component.py` or `permutation_test.py` (v158) exists, so there is nothing to pin; the instrument is the one every earlier v1 record used. "instrument v2" in the Gate line above names v129's ISO-week bootstrap design, not a fill/cost instrument.
- Disclosure only (partner decision 2026-10-10): if `swingbot/core/planning/exit_sim_v2.py` exists when Stage 1 runs (v157 merged), the Stage-1 TRAIN paired ΔExpR is also reported with `instrument=resolve("v2")` fills and costs. It never gates, never selects a cell, and is labelled "v2 disclosure, non-gating" wherever it appears. It did not exist at pre-registration.
- Universe: every ticker with a cached CSV in the main tree's `data/backtest_cache` (`BACKTEST_CACHE_DIR`, `MEASURE_ARMS_UNIVERSE=cache`; the v129 precedent, partner-approved 2026-10-08), all `LEGACY_HORIZONS`, `replay_scenarios` with live `ScanParams`, `scale_out=True`.
- Windows: TRAIN 2020-01-01..2023-12-31; VALIDATION 2024-01-01..2025-12-31, one shot.
- Stage −1: the census (plans only, no exit simulated). `refused:zero-diff` when no cell changes any plan. Identical adjacent cells are reported and put to the partner before Stage 0.
- Stage 0: paired MDE (`mde_expectancy_r_paired`, power 0.80), `target_n` projected from TRAIN closed N over 1460 → 730 days. Any cell above +0.10R, or undefined, closes the arm `UNDERPOWERED`.
- Stage 1: eligible = `expectancy_gain`, `win_rate_floor` (−2.0pp) and `volume` all PASS on TRAIN. Selected = the eligible cell with the highest lower-95% ΔExpR whose ±1-step neighbours in c are all eligible; a tie goes to the smaller c. None → `NO_ELIGIBLE_CELL`.
- Stage 2: four TRAIN calendar-year folds (2020–2023) for the selected cell. FAIL when more than half the measurable folds have ΔExpR < 0, or none is measurable.
- Stage 3: one VALIDATION replay of the selected cell only. All four harvest clauses. `not_luck` = per-ticker arm-label swap on ΔExpR, n = 200, seed 42, p < 0.05.
- A stop hit books −1.0R in both geometries, gaps included; gap-throughs are disclosed (plan index, Spec correction 6).

## Arm D — no plan beyond the ceiling
- Rule, for a clamped plan:
  - `d > c`: no plan. The scenario is rejected at build time with the reason `stop_beyond_confluence_ceiling`, counted in the funnel.
  - `d ≤ c`: today's clamped plan, unchanged.
- Gate: the standard v72 funnel through `measure_arms.py --knob CONFLUENCE_STOP_DROP_PCT=c` and `validate_component.py` (`--gate win_rate`, all six clauses at Stage 3), ticker bootstrap.
- Fills and costs: as arm S (no `--instrument` flag exists to pin).
- Population: the pooled book (`DEFAULT_ENGINES` = confluence + strategy; the knob reaches only confluence rows). Clause 3's volume cut is measured on the pooled book; the confluence-only cut is disclosed. A cut past `VOLUME_MAX_CUT_PCT` (25%) fails clause 3, recorded and not rescued.
- Universe: as arm S (`MEASURE_ARMS_UNIVERSE=cache`), stamped by `measure_arms.py` and checked by every judge.
- Windows (`windows.STAGES`): pilot 2018-06-01..2020-12-31 (first 10 tickers); fold-train selection 2018-06-01..2022-12-31; walk-forward test years 2021/2022/2023; VALIDATION 2024-01-01..2025-12-31, one shot.
- Stage −1: pilot reachability at c = 3.0 (the cell that drops most). The census numbers are disclosure.
- Stage 0: paired MDE per cell against its fold-train ΔWR (`validate_component.py --stage mde`). Stage 1: `--stage selection` over the three cells, `--mde-refused` for any cell Stage 0 refused. Stage 2: `--stage walkforward`. Stage 3: `permutation_test.py --n 200 --seed 42`, then `--stage validation --permutation-p p`.
- Dropping a plan frees the 5-bar cooldown, so the component may ADD entries; clause 6 is then SKIPPED (not a subset). Disclosed.
- The selection judge prints its plateau label as `PULLBACK_DRYUP_MAX_RATIO`; cosmetic, no verdict reads it.

## Disclosures (reported, never gating)
N per arm, ΔExpR with its 95% interval, ΔWR, outcome flips both ways, exit mix by reason, median planned RR per arm, per-horizon N, entries only one side triggered. Arm S: changed, rollback, gap-through and fill-beyond-ceiling counts, median d of the changed plans. Arm D: removed / added / changed counts, volume cut % (pooled and confluence-only).

## On a pass
The arm's result is recorded. Its knob default **stays 0** (plan index, Spec correction 7): the selected c goes into the result record, the Field help and the `.env.example` comment, and the partner decides. Arm S changes what the alert tells the partner to do (a wider stop, fewer shares on resting orders); nothing goes live without that answer.

## On a fail
One row per arm in "Closed pre-registrations — do not re-run these", and one ledger row per arm. Reopen clauses (spec § On a fail): arm S needs "a stop rule other than the confluence level itself up to a ceiling `c`, sized to fixed dollar risk"; arm D needs "a drop rule other than structural distance beyond `c`". Another grid, window or MDE ceiling is not a new mechanism.
