# v114 — Scenario stop band: 1.5-2.0% stops at real levels, 2% maximum loss unchanged

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
everywhere.

**Correction (same day).** The floor is not the only binding gate. With the
reward and risk:reward filters off, 482 scenarios have a stop of 2% or more
(382 of them 2-3%), so a stop that far away is findable. They are rejected
because the nearest target is too close: a 2% stop needs a target at least 3%
away for risk:reward 1.5, plus the per-horizon reward floor. The floor and the
risk:reward ratio interact, so lowering the floor works by also lowering the
target distance the ratio demands. Any plan built from this spec
must measure the floor and the ratio together, not the floor alone.

## Decision taken with the partner (2026-09-30, final)

After several same-day revisions (a 1.0% floor, a 2.5% cap, RR 1.0 then 2.0,
a 2.5% reward floor were each proposed and withdrawn), the partner settled on
**one threshold change**:

- **`MIN_STOP_DISTANCE_PCT` 2.0 -> 1.5.**
- **`MIN_RISK_REWARD_RATIO` stays 1.5.**
- **`MIN_REWARD_PCT` stays 2.0.**
- **Maximum planned loss stays 2.0%** (`HARD_MAX_PLANNED_LOSS_PCT`).
- Stops stay at **real support/resistance levels**. The scan never places a
  stop at an arbitrary distance to hit a percentage.

## Design

Band: **stop 1.5% to 2.0% from entry**; reward and risk:reward rules unchanged.

1. `MIN_STOP_DISTANCE_PCT` default 2.0 -> **1.5** (`swingbot/config.py`), and
   the production `.env`, which sets `MIN_STOP_DISTANCE_PCT=2.0` explicitly,
   so a default change alone does not reach production.
2. Scenario admission ceiling (`analyze._scan_one`, currently
   `max(MAX_STOP_LOSS_PCT, h["max_risk_pct"])`, 7-11%) becomes the planned-loss
   cap read from `HARD_MAX_PLANNED_LOSS_PCT`, so scenarios that can never be
   issued are no longer built. The cap's value does not change.
3. Backtest replay uses the same admission code (`backtest_scenarios.py`
   default `min_stop_distance_pct: 2.0`, `armed_replay.py`, `scan_params.py`,
   `gating.py`, `arms/reachability.py`); all move together so parity holds.
   `armed_replay` already relaxes the floor to 0 at arm time; that stays.
4. Requirement-check text (`requirements.py`) states the band.
5. Strategy plans whose builder chooses its own stop (`builders.py`,
   `short_builders.py`) are unchanged.

**Non-goals.** No change to the 2% cap, sizing, reward floor, risk:reward,
structural-stop scope (`STRUCTURAL_STOP_SCOPE` stays empty), strategy entry
logic, or where stops sit.

## What the measurement says (2026-09-30, production cache, 820 frames)

With the live per-horizon reward floor, RR 1.5 and the 2.0% cap:

| Minimum stop distance | Scenarios today |
|---|---|
| 2.0% (current) | 0 |
| **1.5% (chosen)** | **1** (one bearish 7m) |
| 1.0% | 24 |

The admission ceiling (2.0% vs the horizon's 7-11%) gives the same counts
today; it matters for correctness, not volume. **On today's data this change
barely restores alerts.** Whether it restores them on ordinary days is what
the backtest's volume measurement answers; the spec does not assume it.

## Integrity requirement (not subject to validation)

No plan may be issued with a planned loss above 2.0%. A test asserts this
across every horizon and both directions, and the `risk_cap` rejection stays
as the backstop. Existing open positions and plans keep the stop they were
issued with.

## Risk

- A 1.5% stop sits closer to ordinary daily noise than 2.0%, so win rate may
  fall. The `tight_stop` flag (stop below the horizon's ATR cushion) stratifies
  the validation.
- Volume gain may be too small to matter (1 scenario today). A result that
  passes the quality clauses but adds almost no alerts is reported as such.

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
