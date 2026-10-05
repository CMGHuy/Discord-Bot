# v122 pre-registration — pullback volume dry-up gate

**Committed before any v122 outcome is read and before any VALIDATION arm exists.** Spec: `docs/superpowers/specs/implemented/2026-10-02-v122-pullback-volume-dryup-gate-design.md` (including its frozen amendments). Plan: `docs/superpowers/plans/implemented/2026-10-02-v122-pullback-volume-dryup-gate_0-index.md` (parts `_1`, `_2`).

## Claim

Removing pullback entries whose pullback leg averaged more than `d` × the impulse leg's volume raises win rate without costing expectancy, under the standard v72 funnel.

## Instrument

`structure.pullback_vol_ratio` (v121), evaluated on **completed daily bars only**. The live sites drop today's forming bar through `strategy_pass.completed_frame`; replay slices are completed by construction. The rule rejects iff the ratio is not None and > d (`gates.ratio_exceeds`); None and NaN pass. Call sites: `strategy_pass._emit_signal` / `StrategyEngine._gated_plan` for strategy entries, and `analyze._apply_pullback_dryup` / `backtest_scenarios._dryup_kept` for confluence entries. Parity, including a forming-bar frame, is pinned by `tests/backtesting/test_pullback_dryup_parity.py`.

## Components (separate budgets, never pooled)

| Component | Knob delta | Population |
|---|---|---|
| strategy | `PULLBACK_DRYUP_SCOPE=strategy`, `PULLBACK_DRYUP_MAX_RATIO=d` | Fibonacci, EMA Crossover (pullback mode), Break & Retest, RSI, RSI Divergence, MA Ribbon, VWAP |
| confluence | `PULLBACK_DRYUP_SCOPE=confluence`, `PULLBACK_DRYUP_MAX_RATIO=d` | every confluence-sourced entry |

Arms come from `measure_arms.py` with both default engines (confluence + strategy), so each component is judged against the whole replayed book it would ship into. Order: strategy first, then confluence, one shot at a time.

## Frozen grid and selection rule

`d ∈ {0.60, 0.75, 0.90}`.

1. **Stage −1 reachability** (pilot, `d = 0.60`, the widest cut): refuse if there are zero changed outcomes. The population split is disclosed; replacements are expected and do not halt the run.
2. **Stage 0 MDE** (fold-train `selection` arms, paired bootstrap): run per cell, with `--train-effect-pp` set to that cell's fold-train standardised ΔWR. A refused cell is ineligible at Stage 1. If all three are refused, the shot is refused with the budget intact.
3. **Stage 1 selection** (fold-train only): a cell is eligible when it PASSES clauses 2–4 and 6 (SKIPPED is not a pass), with clause 6 read as below. The chosen `d` needs an eligible grid neighbour and `plateau_report()` `is_plateau`. Among those, take the largest ΔWR; on a tie, the larger `d`. Judge: `validate_component.py --stage selection --dryup-mechanism`.
4. **Stage 2 walk-forward**: `gate_win_rate`. It needs ≥ 2 of 3 folds improving, no fold worse than −1.0pp, and per-fold N ≥ 30.
5. **Stage 3 VALIDATION** 2024-01-01..2025-12-31: one shot per component. All six v72 clauses must pass, and a missing permutation p is a FAIL. Judge: `validate_component.py --stage validation --dryup-mechanism --permutation-p <p>`.

## Clause 6 reading (frozen amendment)

Mechanism is scored on the **baseline** arm. In-scope baseline trades the predicate flags at `d` form the removed population, and in-scope baseline trades it does not flag form the retained population. Trades outside the component's scope are in neither group. The clause passes iff removed WR < retained WR **and** removed ExpR ≤ 0. Replacement trades admitted by freed slots or cooldowns are part of the component arm and count fully in clauses 1–5; their count (`added`) is disclosed. Implementation: `swingbot/core/backtesting/arms/dryup_clauses.py`, wired as `validate_component.py --dryup-mechanism`.

## Clause 5 instrument (partner decision, 2026-10-02)

`python scripts/backtest/permutation_test.py --arms <the stamped VALIDATION arm file> --n 200 --seed 42`. This extends the existing script (V122-10; its fold path's output is pinned unchanged by a witness test). It circularly shifts each ticker's baseline removed labels by seeded integers in [20, 200), keeps replacement trades in every null arm, and reports p = the share of null standardised ΔWR ≥ the observed. It reads arm rows only, so it covers confluence and strategy entries alike. Its `p_value` is passed as `--permutation-p`. A pair with changed outcomes on surviving keyed trades is refused, because the removal-label null cannot model it. Producer, validation window, authoritative universe, horizon, engine, hash, and preregistration stamp checks must pass before computing a p-value.

## Disclosure (every stage)

Removed / added (replacements) / changed counts, per-direction ΔWR and ΔExpR, the top-2 horizon share of the removed trades, a statement when > 80% of the removed trades are one direction, and the `None` share of the scoped baseline population (`dry-up none share` line).

## Stop rules

A failure at any stage closes that component in `docs/claude/backtest-methodology.md`'s closed-pre-registrations table with its numbers. The code stays merged and inert (defaults off). Reopening needs a mechanism other than "pullback-leg over impulse-leg mean volume above d ∈ {0.60, 0.75, 0.90}".
