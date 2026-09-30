# v114 — Scenario stop band: admit stops between a floor and the 2% hard cap

**Version:** ui 1.21.0 · bot 1.11.1 (at writing)
**Bump:** bot minor if it ships (the alert stream visibly changes)
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
everywhere; the floor is the binding gate.

## Decision taken with the partner (2026-09-30)

- The **maximum loss per trade is 2%**. A planned loss below 2% is fine.
- The stop **must not be too near the entry**.
- Floor chosen: **1.0%**. Band = **1.0% to 2.0%**.

## Design

1. `MIN_STOP_DISTANCE_PCT` default becomes **1.0**.
2. The scenario admission ceiling stops being the horizon's 7-11% and becomes
   the same 2% hard cap that issue time enforces, read from one place
   (`HARD_MAX_PLANNED_LOSS_PCT`) rather than a second copy of the number.
   Scenarios that can never be issued are no longer built.
3. The backtest replay uses the same admission code
   (`backtest_scenarios.py` default `min_stop_distance_pct: 2.0`,
   `armed_replay.py`, `scan_params.py`, `gating.py`,
   `arms/reachability.py`). All move together so replay parity holds.
   `armed_replay` already relaxes the floor to 0 at arm time; that stays.
4. The requirement check text (`requirements.py`, "needs N%+") states the band.
5. Strategy plans whose builder chooses its own stop (`builders.py`,
   `short_builders.py`) are unchanged: they already cap at the stop ceiling.

**Non-goals.** No change to the 2% cap itself, to position sizing, to
structural-stop scope (`STRUCTURAL_STOP_SCOPE` stays empty), to targets or
reward floors, or to any strategy's entry logic.

## Integrity requirement (not subject to validation)

No plan may be issued with a planned loss above 2%. A test asserts this across
every horizon and both directions after the change, and the existing
`risk_cap` rejection stays as the backstop.

## Risk

A 1.0% stop is inside ordinary daily range for volatile tickers, so stops may
be hit by noise. Win rate can fall while volume rises. The existing
`tight_stop` flag (stop below the horizon's ATR cushion) is already logged and
is the natural stratifier: the validation reports results split by it.

## Validation

Pre-registered before any run, per `docs/claude/backtest-methodology.md` and
the `backtest-gate` skill. Thresholds are the repo's existing acceptance
gates, chosen by the plan's first task from `acceptance.py` /
`acceptance_harvest.py` (not invented or tuned here). This is a volume change,
so the volume clause is read as a floor on gain, and the win-rate and
expectancy clauses are the non-inferiority constraints. TRAIN and walk-forward
first, then one shot on VALIDATION. A NO-LIFT result closes this spec and
production stays at the current behaviour, with the 2% cap unchanged.

Until validation passes, production keeps rejecting everything the current
band rejects; the flag/default flip ships only on a pass.

## Parallelisation

Sequential throughout: the config default and the shared admission code must
land before the replay parity test and the validation run can mean anything.
