# v105 as-of contract and frozen measurement inputs

**Spec:** docs/superpowers/specs/2026-09-25-v105-pending-range-continuation-design.md
**Plan:** docs/superpowers/plans/2026-09-25-v105-pending-range-continuation_0-index.md
**Written at:** 9c681b686d8dd25371d137a41437b768b6a75b3b (no outcome has been run)

## Dependencies as found

- v100 ArmEngine: present, but `DEFAULT_ENGINES = ("confluence", "strategy")` has no `range` registration; `get_engine("range")` rejects it and `measure_arms.py` has no extension argument. v105 therefore retains bespoke `swingbot/core/backtesting/range_arms.py`, calling `range_source.range_plan_at` / `first_issuable` and feeding `acceptance.evaluate` / `scripts/backtest/validate_component.py`. Every `validate_component.py` invocation for these arms must include `--bespoke-instrument "range_arms: range_source.range_plan_at / first_issuable"`: this records the provenance reason and deliberately bypasses v100's `check_stamp` gate.
- v104: no code. Risk model for BOTH arms: `risk_limits.HARD_MAX_PLANNED_LOSS_PCT = 2.0` via `capped_planned_loss_pct(HORIZONS[h]["max_risk_pct"])`, drop (not clamp); sizing `account.compute_position_size` at trade-log time. If v104 lands before Task 8, re-freeze here under the new model before any run.
- Target: `targets.select_structural_target`; a synthetic capped TP1 is refused.
- Exit replay: `exit_sim.simulate_exit(scale_out=True)`; fill bar not stop/target-checked (`range_replay.EXIT_LIMITATION`).
- Scan insertion: `scan_run._sync_run_scan`, directly after `_maybe_run_strategy_pass` (after `_scan_one`'s open-position monitoring, liquidity and data-quality screens).
- PlanStore identity: `plan_id` only; range identity lives in `plan.entry_context["range"]["identity"]` and `range_candidate.may_rearm`.

## As-of contract

- Decision for session t reads daily bars completed through t-1: replay `df.iloc[:i+1]` for session i+1; live `strategy_pass.completed_frame`.
- Live quote: `range_pass.fresh_quote` (`allow_stale=False`, 15 s TTL) for proximity/crossing only.
- Replay proximity proxy: Close[i] (the price at which a user places the overnight order). Fills examined on bars i+1..i+5.

## Frozen measurement inputs

- TRAIN window: 2020-01-01..2023-12-31. Fold-test years 2021, 2022, 2023.
- Cache: `C:\\Users\\wsa_hcao\\.codex\\worktrees\\2026-09-25-v105-pending-range-continuation\\Discord-Bot\\data\\backtest_cache`, 0 files, manifest sha256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`, earliest bar unavailable (cache is empty).
- Cache availability: no measurement run is permitted against this manifest. Populate the worktree cache and re-freeze this contract before any Task 6/8/9 outcome run.
- Universe: every cached symbol passing `universe.liquidity_reason` and `universe.data_quality_issues` (no ETF exclusion).
- Horizons: all ten keys of `strategy_types.HORIZONS`.
- Constants: as in `range_candidate.py` (N_GRID, D_GRID, TOUCH_ATR, …).
- Exit model: simulate_exit scale_out=True, expiry 5 sessions, worse-of fill.
- Selection rule (`range_arms.select_cell`): eligible = component n ≥ 30 AND ΔWR > 0 AND ΔExpR ≥ −0.01; plateau = eligible with ≥ 2 eligible grid neighbours (adjacent N or adjacent d); pick max ΔExpR; ties → smaller d, then larger N; per direction independently.
- Sector clusters: count distinct `universe.sector_map("sp500")` sectors among TRAIN-issued tickers; expected ≥ 8 (fewer is reported as concentration).
- Holdout eligibility: first complete session AFTER the Task 9 pre-registration commit; never 2024-01-01..2025-12-31; never v104's 2026 holdout.

## Integrity finding (out of scope, recorded)

`presentation/instructions.py` tells a confluence stop-entry user a `cancelled_risk_cap` plan "never filled". A resting broker stop that gapped may have filled. v105 fixes the text for `range_continuation` plans only (Task 5); the confluence instance needs its own integrity spec.
