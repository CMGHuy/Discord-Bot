# v114 — Scenario stop band: 1.0-2.5% stops at real levels, 2.5% maximum loss

**Version:** ui 1.21.0 · bot 1.11.1 (at writing)
**Bump:** bot minor if it ships (the alert stream and the risk limit visibly change)
**Edge:** volume

## Why this

Production on 2026-09-30 posts nothing. Every scan since ~19:00 UTC on
2026-09-29 rejects all ~760 ticker/horizon combinations at "no qualifying
entry point". Postgres, the schema, data fetching and level detection are all
healthy (investigated 2026-09-30; not the database change).

The cause is two stop rules that no longer agree:

- **Scenario admission** (`levels.build_scenarios`, called from
  `analyze._scan_one`) requires the stop to be at least
  `MIN_STOP_DISTANCE_PCT` (2.0) away and at most
  `max(MAX_STOP_LOSS_PCT, horizon max_risk_pct)` — 7% to 11%.
- **Issue time** (`attach_plan_v2`, since `f01e87e2` on 2026-09-28) rejects
  any plan whose planned loss exceeds the 2% hard cap
  (`HARD_MAX_PLANNED_LOSS_PCT`, `stop_scope.stop_ceiling`).

Before 2026-09-28 the wide admission band was harmless-looking because a stop
beyond 2% was posted and then cancelled on fill (15 `cancelled_risk_cap` in two
weeks). Now it is rejected at issue, so the effective band is "at least 2.0%
and at most 2.0%". Measured on the production cache on 2026-09-30 (820
ticker/horizon frames, both directions):

| Minimum stop distance | Scenarios admitted |
|---|---|
| 2.0% (current) | 0 |
| 1.5% | 1 |
| 1.0% | 24 |
| none | 182 |

With every filter relaxed there are 1,638 scenarios, so levels exist
everywhere.

**Correction (same day).** The floor is not the only binding gate. With the
reward and risk:reward filters off, 482 scenarios have a stop of 2% or more
(382 of them 2-3%), so a stop that far away is findable. They are rejected
because the nearest target is too close: a 2% stop needs a target at least 3%
away for risk:reward 1.5, plus the per-horizon reward floor. The floor and the
risk:reward ratio interact, so lowering the floor to 1.0% works by also
lowering the target distance the ratio demands. Any plan built from this spec
must measure the floor and the ratio together, not the floor alone.

## Decision taken with the partner (2026-09-30)

- The **maximum planned loss per trade is 2.5%** (was 2.0%). A smaller loss is
  fine. A stop of 2.0-2.5% is acceptable provided the profit target is at
  least 2.5%.
- The stop **must not be too near the entry**: floor **1.0%**.
- Stops stay at **real support/resistance levels**. The scan never places a
  stop at an arbitrary distance to hit a percentage.
- Reward rule: target **at least 2.5% away and at least as far as the stop**
  (risk:reward >= 1.0).

## Design

Band: **stop 1.0% to 2.5% from entry**; **reward >= 2.5% and >= stop**.

1. `MIN_STOP_DISTANCE_PCT` default 2.0 -> **1.0**.
2. `HARD_MAX_PLANNED_LOSS_PCT` (`swingbot/core/risk_limits.py`) 2.0 -> **2.5**.
   It is the single source of the cap: `attach_plan_v2` reject,
   `stop_scope.stop_ceiling` / `capped_planned_loss_pct`, `PlanManager`, and
   sizing all read it. Any place that hard-codes 2 or 2.0 as the cap is found
   by the plan's first task and made to read the constant.
3. Scenario admission ceiling stops being the horizon's 7-11% and becomes the
   same constant, so scenarios that can never be issued are no longer built.
4. `MIN_REWARD_PCT` 2.0 -> **2.5** and `MIN_RISK_REWARD_RATIO` 1.5 -> **1.0**.
   The per-horizon reward floor (`sr_target_min_pct * 0.15`, 3.3% for the
   longest horizons) still applies on top, so long horizons need more than 2.5%.
5. Backtest replay uses the same admission code (`backtest_scenarios.py`
   default `min_stop_distance_pct: 2.0`, `armed_replay.py`, `scan_params.py`,
   `gating.py`, `arms/reachability.py`); all move together so parity holds.
   `armed_replay` already relaxes the floor to 0 at arm time; that stays.
6. Requirement-check text (`requirements.py`) states the band and reward rule.
7. Strategy plans whose builder chooses its own stop (`builders.py`,
   `short_builders.py`) already cap at the stop ceiling and follow the new
   constant automatically.

**Non-goals.** No change to sizing rules, structural-stop scope
(`STRUCTURAL_STOP_SCOPE` stays empty), strategy entry logic, or where stops
sit. Nothing is moved to a fixed percentage.

## What the measurement says (2026-09-30, production cache, 820 frames)

Real-level stops of 2.0-2.5% do not exist today: floor 2.0% gives 0 scenarios
at a 2.0% or a 2.5% cap, even with risk:reward 1.0 and a 2.5% reward floor.
Floor 1.0% gives 23 (RR 1.5) or 25 (RR 1.0), and the cap value does not change
that. So on today's data **raising the cap is not what brings alerts back; the
1.0% floor is.** The 2.5% cap is a risk-limit decision the partner made on its
merits; its cost is measured in validation, not assumed free.

## Integrity requirement (not subject to validation)

No plan may be issued with a planned loss above the cap, and the cap has one
source. A test asserts this across every horizon and both directions, and the
`risk_cap` rejection stays as the backstop. Existing open positions and plans
keep the stop they were issued with. Docs that state the 2% rule (`CLAUDE.md`
and `docs/claude/`, the Codex mirror `AGENTS.md`, strategy-type pages) are
updated in the release commit so no document still says 2%.

## Risk

- A 1.0% stop is inside ordinary daily range for volatile tickers, so stops may
  be hit by noise and win rate may fall. The `tight_stop` flag (stop below the
  horizon's ATR cushion) stratifies the validation.
- **Risk:reward 1.5 -> 1.0 will likely trip the geometry-lock clause** of the
  v72 acceptance gate (median planned RR and mean win R must not fall more than
  2%). That clause is not relaxed to fit this spec. If it fails, the outcome is
  NO-LIFT for the RR change, and the plan falls back to measuring the band
  with RR left at 1.5 (23 scenarios today).
- A 2.5% cap raises the worst-case loss per trade by 25% against the same
  account size; sizing reads the cap, so position size per trade falls in
  proportion for stops at the cap.

## Validation

Pre-registered before any run, per `docs/claude/backtest-methodology.md` and
the `backtest-gate` skill. Thresholds are the repo's existing acceptance
gates, chosen by the plan's first task from `acceptance.py` /
`acceptance_harvest.py` (not invented or tuned here). This is a volume change,
so the volume clause is read as a floor on gain, and the win-rate and
expectancy clauses are the non-inferiority constraints. TRAIN and walk-forward
first, then one shot on VALIDATION. A NO-LIFT result closes this spec and
production stays at the current behaviour, with the 2.0% cap unchanged.

Until validation passes, production keeps rejecting everything the current
band rejects; the flag/default flip ships only on a pass.

## Parallelisation

Sequential throughout: the config default and the shared admission code must
land before the replay parity test and the validation run can mean anything.
