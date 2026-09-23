Version: ui 1.18.3 · bot 1.9.0
Bump: bot patch
Edge: harvest

# Exit-quality harvest: adaptive runner trail + stall-exit

## Problem

Measured directly off the production live book on 2026-09-10 (`docs/claude/edge-priorities.md`'s sibling memory, `prod-live-book-2026-09-10`) and never acted on since — v78 (2026-09-10) put these numbers on the Analytics dashboard as `Edge: none (integrity)` and explicitly changed no trading logic:

- **Winners bank only ~43% of the favorable move available to them** (`exit_efficiency` median 0.429, n=324 journaled winners).
- **Losers are held ~2.1× longer than winners** (disposition effect: avg loser 0.64d vs avg winner 0.31d, n=352/n=212).

Both are pool-wide facts about the *exit* side of the plan, not the *entry* side — nothing here changes which setups fire or how confident the bot is in them. That is what makes this `Edge: harvest`: the same setups, more R extracted from the ones already being taken.

## Why this needs a new acceptance gate, not the v72 funnel

`docs/claude/backtest-methodology.md` is explicit: **"`Edge: harvest` features are OUT OF SCOPE for [the v72] funnel, and that is a known gap, not an oversight... a harvest feature must say in its own pre-registration that it is not using this funnel and name the gate it is using instead."** Exits/targets/sizing move geometry by construction, so v72's clause 3 (geometry lock) rejects them by design — that clause exists to stop a *selectivity* feature from buying win rate by pulling targets nearer, which is a different failure mode than what's being tested here.

This spec defines that gate (§3) and two independently pre-registered hypotheses that use it (§4, §5). Neither hypothesis touches `swingbot/core/backtesting/acceptance.py` (v72) or its constants.

## Provenance note: this is not a reopened pre-registration

Two closed rows in `backtest-methodology.md` sit near this territory and are deliberately **not** being reused:

- `DATA_DRIVEN_STOPS_ENABLED` (edge-engine v4): closed, "unmeasurable by construction" — the old `_trade_plan_at` sizing path it measured through no longer exists (superseded by the unified v2 `plan_engine`). Its sibling helper `swingbot/core/edge/stops.py:optimal_time_stop_days` is coded but explicitly documented as advisory-only ("nothing in this codebase closes a position on it") and was never itself measured — the closed result is about `mae_informed_stop_mult`/stop-width sizing, not about time-stop-as-exit-trigger.
- Despite that distinction, §5 below gates the stall-exit behind a **brand-new flag** (`STALL_EXIT_ENABLED`), not `DATA_DRIVEN_STOPS_ENABLED`. It calls `optimal_time_stop_days()` as a plain helper function. This is the cleanest provenance available: no argument is needed about whether reusing the old flag constitutes "a genuinely new mechanism," because the old flag is never touched.
- v88 (armed confluence entries) and v90 (in-flight rejection-only entries) are entry-timing work, a different lever than anything here — no overlap.

## §3 The harvest acceptance gate (new)

New module `swingbot/core/backtesting/acceptance_harvest.py`, reusing `acceptance.py`'s primitives directly (`ArmTrade`, `cluster_bootstrap`, `bootstrap_delta`, `win_rate`, `expectancy_r`, `population_split`, the ticker-cluster bootstrap machinery, the MDE precheck) rather than re-implementing them — only the clause set and thresholds differ.

**The methodology's own framing is the design brief: for `Edge: harvest`, expectancy is the objective and win rate is a floor — the exact inversion of v72's role assignment, which the methodology doc already names as legitimate ("Inside the v72 acceptance gate the two swap roles... that is not a contradiction").**

| # | Clause | Instrument | Threshold | Rationale |
|---|---|---|---|---|
| 1 | `expectancy_gain` (objective) | ticker-cluster bootstrap ΔExpR | lower 95% bound > 0, one-sided p < 0.05 | mirrors v72 clause 1's rigor, applied to ExpR instead of WR — this is the thing harvest work exists to buy |
| 2 | `win_rate_floor` (constraint) | ticker-cluster bootstrap Δstandardised-WR | lower 95% bound ≥ −2.0pp | 2.0pp mirrors v72 clause 3's `GEOMETRY_MAX_DROP_PCT` tolerance for "how much secondary-axis slip is acceptable" — a harvest change that also improves WR is a bonus, not a requirement; only *material* WR damage blocks it. A mechanism that cannot structurally move WR (see §4) reports this clause as `SKIPPED — zero variance by construction` rather than bootstrapping a constant |
| 3 | `volume_floor` | closed-trade count, baseline vs component | cut ≤ 25% (reuses v72's `VOLUME_MAX_CUT_PCT`) | both hypotheses replay the identical entry set and only change exit behavior, so N is structurally near-identical between arms — this clause exists for defensiveness/consistency, not because it is expected to bite |
| 4 | `not_luck` | `permutation_test.py`, n=200, on ΔExpR (not ΔWR) | p < 0.05, validation stage only | same discipline as v72 clause 5, retargeted at the objective this gate actually optimizes |

No `mechanism` clause (v72 clause 6) — that clause interrogates a *removed population* (a filter/veto shape); these hypotheses don't remove trades, they change how already-accepted trades exit. Instead, **the results doc for each hypothesis must report the win→non-win outcome-flip count and rate as a disclosure table** (which trades that would have reached TP1 under the baseline arm did not under the component arm, and vice versa) — informational, not gating, because clause 1's net ΔExpR already prices in whatever those flips cost or bought.

**Funnel stages are reused as-is** (`docs/claude/backtest-methodology.md`'s Stage 0 MDE precheck → Stage 1 TRAIN plateau → Stage 2 free/repeatable walk-forward folds → Stage 3 one-shot VALIDATION), with Stage 0's MDE computed against ExpR variance instead of the WR formula in `acceptance.mde_win_rate` (a new `mde_expectancy_r` alongside it, same z-score/design-effect math, swapping the binomial variance term for the sample variance of `r_multiple`). Each hypothesis gets its **own** Stage 3 shot — the standard one-look-per-component rule, unchanged.

**This gate is written to be reused** by future `Edge: harvest` specs, not just this one — once implemented, `docs/claude/backtest-methodology.md` gets a new section pointing at it, so a future harvest spec cites it instead of re-deriving. That documentation update is a task in the implementation plan, not this spec.

## §4 Hypothesis 1 — R-adaptive chandelier trail

**Mechanism.** `swingbot/core/planning/exit_sim.py:_scale_out_exit_walk` currently trails the runner leg at a constant `plan.trail_atr_mult` (resolved from `params.TRAIL_ATR_MULT = 2.5`) for the entire runner phase, however far price has run. This hypothesis tightens the multiplier once the runner has banked a threshold amount of unrealized R, so a give-back late in a large move costs less of what was earned.

**Why this cannot move win rate.** The win/loss badge in this codebase is decided at TP1 touch (`docs/claude/backtest-methodology.md`'s badge definition: "Win = TP1 touched"), which happens in Phase 1 of the exit walk, entirely before the runner/chandelier logic in Phase 2 even starts. Nothing in this hypothesis can change whether a trade counts as a win — only how much R the winning trade nets. Clause 2 (`win_rate_floor`) is therefore `SKIPPED` by construction for this hypothesis, and clause 1 (`expectancy_gain`) is the whole test.

**Parameterization.** A single step, to keep the TRAIN grid small and the mechanism easy to attribute. The trigger keys off `extreme_close` — the same running max/min-since-TP1 the loop already tracks for the chandelier ratchet itself — not the current bar's close, so the multiplier only ever tightens, matching the existing "only ever moving toward profit, never back down" invariant instead of flapping loose again on a pullback:

```
runner_r = (extreme_close - entry_price) * sign / risk        # since entry, tracks TP1's own extreme
trail_atr_mult = TIGHTEN_ATR_MULT if runner_r >= TIGHTEN_TRIGGER_R else TRAIL_ATR_MULT
```

Because `extreme_close` never retreats, once `runner_r` crosses `TIGHTEN_TRIGGER_R` the tightened multiplier applies for the rest of the trade — consistent with the ratchet-only-forward rule already governing the stop level itself.

New `params.py` constants `TIGHTEN_TRIGGER_R` and `TIGHTEN_ATR_MULT`, resolved into a per-plan field the same way `trail_atr_mult` already is (`exit_params_for`/`_resolve_stop_mult`'s pattern). TRAIN grid: `TIGHTEN_TRIGGER_R ∈ {1.5, 2.0, 2.5}` × `TIGHTEN_ATR_MULT ∈ {1.5, 1.75, 2.0}` (9 cells; `TIGHTEN_ATR_MULT` always < `TRAIL_ATR_MULT=2.5`, tighter by construction). Flag: `ADAPTIVE_RUNNER_TRAIL_ENABLED`, default `false`.

**Code touch points.** `exit_sim.py` (the ratchet call at the line computing `trail = chandelier_stop(...)`, gated on the new flag), `params.py` (new constants + resolver), `config.py` (new `Field` entries, `search_class="searchable"` so the grid script can sweep them), `plan_types.py`/`TradePlanV2` (no new field needed — the per-plan `trail_atr_mult` field already exists; this hypothesis makes its *resolution* R-dependent rather than adding a field). The live poll path (`plan_manager.py`) and the backtest walk already share `chandelier_stop`/`runner_floor` as a single source of truth (per `exit_sim.py`'s own docstring), so wiring the flag once in the shared resolver keeps live≡backtest.

## §5 Hypothesis 2 — MAE/time stall-exit

**Mechanism.** `swingbot/core/edge/stops.py:optimal_time_stop_days` already computes, per strategy, the day by which `TIME_STOP_COVERAGE` (80%) of eventual winners had reached +0.5R — a position slower than that is, in the module's own words, "statistically dead capital." This hypothesis is the "E48 recycler" that was never built: if a plan is still open past its strategy's `optimal_time_stop_days` **and** has not yet reached the `+0.5R` marker itself, close it at market rather than continuing to hold it (subject to the existing `DEFAULT_EXPIRY_BARS`/`max_holding_days` ceiling, which still applies as the outer bound).

**Guardrails, reusing existing conventions exactly:**
- `MIN_SAMPLE = 40` journaled winners for that strategy or the mechanism does nothing (same floor `mae_informed_stop_mult` already uses) — a strategy with too little history keeps its current behavior untouched, silently.
- Applies pre-TP1 only (this is where the disposition-effect population lives — post-TP1 trades are already wins and Hypothesis 1's territory). A stall-exit firing after TP1 would be double-scoped with §4; the two hypotheses are mutually exclusive by trade phase, not just by flag.
- New flag `STALL_EXIT_ENABLED`, default `false`, independent of `DATA_DRIVEN_STOPS_ENABLED` (see provenance note above). `search_class="searchable"`.

**The real risk, stated plainly.** A stall-exit necessarily converts some trades that *would eventually* have reached TP1 into early, smaller losses (or scratches) — this is the mechanism, not a side effect, and it is exactly what clause 2 (`win_rate_floor`) exists to bound. Unlike Hypothesis 1, this one can genuinely fail the gate, and should be treated as a real coin flip going in, not a foregone conclusion.

**Code touch points.** `plan_engine.py`/`exit_sim.py` (a new stall check in the pre-TP1 walk, alongside the existing stop/target/breakeven checks — conservative ordering matters here: stop-loss still checked first on any bar, same as every other exit path), `plan_manager.py` (the live poll path needs the same check so live≡backtest holds), `config.py` (new `Field`). No changes to `edge/stops.py` — `optimal_time_stop_days` is consumed as-is.

## Data flow

Both hypotheses plug into the single exit-simulation path that already serves both live trading and backtesting (`exit_sim.py`'s documented invariant: "the live poll path, the overnight bar-check path and this module's backtest walk must never drift apart"). Neither introduces a second code path — the TRAIN/fold/VALIDATION runs exercise the *same* function the live bot will run under, which is what makes the walk-forward folds meaningful evidence about live behavior rather than a simulator-only result.

## Error handling

Both flags default `false` and are additive checks in an existing walk — with the flag off, behavior is byte-identical to today (same pattern `DATA_DRIVEN_STOPS_ENABLED` and `ADAPTIVE_RUNNER_TRAIL_ENABLED`'s sibling flags already use). Insufficient journal data (`MIN_SAMPLE` unmet) degrades to a no-op per strategy, not a bot-wide disable — a strategy with a thin journal keeps its current exit behavior while others with enough history get the new one, mirroring `mae_informed_stop_mult`'s existing per-strategy guard.

## Testing

- Unit tests for the R-adaptive trail formula (threshold boundary, both directions, flag off = byte-identical to current `chandelier_stop` output) and for the stall-exit trigger (day threshold boundary, `+0.5R` marker check, `MIN_SAMPLE` guard, pre-TP1-only scope, stop-loss-first ordering on a bar where both a stop breach and a stall condition are simultaneously true).
- `python scripts/dev/testrun.py file tests/<the touched exit_sim/stall test file>.py` per task; one full-suite run at the end of the implementation plan, per `document-conventions.md`.
- Each hypothesis's own TRAIN grid → free walk-forward folds → one VALIDATION shot, per §3's funnel, using `backtest-runner` for anything past a couple of minutes.

## Parallelisation

Not parallel-safe as a whole: both hypotheses ultimately touch `exit_sim.py`, so despite being logically independent (different trade phases, different flags), they fail the "disjoint files" test in `document-conventions.md`. The implementation plan should build `acceptance_harvest.py` first (shared, no dependents yet), then Hypothesis 1 (§4) and Hypothesis 2 (§5) sequentially, in either order — each is a group of one internally (its own TRAIN/grid/fold/validation chain is inherently serial: TRAIN gates fold, fold gates validation).

## Non-goals

- No change to entry selectivity, confluence scoring, or any gate that decides *whether* a trade fires (that is v86/v88/v90's territory).
- No reuse of `DATA_DRIVEN_STOPS_ENABLED`, `mae_informed_stop_mult`, or `mfe_informed_tp2_r` — those stay exactly as closed/gated as they are today.
- No claim that either hypothesis will pass. Hypothesis 1's downside is bounded (can only fail to help, per §4); Hypothesis 2's downside is a real possibility and the spec's honest expectation is "coin flip," not "likely win."

## Next step

`superpowers:writing-plans` turns §4 and §5 into task-level detail (TRAIN grid scripts, exact test files, the `acceptance_harvest.py` implementation, the `backtest-methodology.md` documentation task for the new harvest gate).
