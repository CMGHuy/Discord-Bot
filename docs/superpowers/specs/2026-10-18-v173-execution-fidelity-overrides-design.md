# v173 — Execution fidelity: what manual overrides cost against the engine

**Version:** ui 1.27.0 · bot 2.10.0 (at writing)
**Bump:** bot minor — a manual close starts recording its exit price and the plan's live state, bulk clears get their own reason, and a new API endpoint serves the override report; ui minor — the Analytics Execution tab gains an "Overrides vs engine" panel.
**Edge:** none (integrity) — a measurement. It changes no signal, gate, stop, size or badge. Any harvest it buys is behavioural (fewer costly overrides) and arrives only if the report changes how the partner acts, so it is not claimed here.
**Screen:** exempt (integrity)
**Panel:** quant-researcher, quant-engineer, financial-advisor
**Status:** spec written 2026-10-18 from a brainstorm with the partner (direction, staging, scope, approach A and both design sections approved in chat).

## Why

The brainstorm read three trading books against the bot: Murphy (*Technical
Analysis of the Financial Markets*), Douglas (*Trading in the Zone*) and
Bassal (*Swing Trading for Dummies*). Most of Murphy's and Bassal's chart
ideas are already measured in `preregistration-ledger.jsonl`: regime-matched
indicators (`v17-regime-allow` NO-LIFT), role-reversal levels
(`v31-break-retest` FAIL, `v36-level-touch-strength` NO-LIFT), earnings
blackout (`v82-earnings-blackout` NO-LIFT) and cross-horizon trend alignment
(measured, OFF). Sector RS and stop-based sizing are already built.

Douglas's lesson is the one the bot has not measured: an edge exists only
over the full sample, and a trader who skips signals, moves stops or takes
profit early is trading a different, unmeasured system. The bot already
trades its own plans mechanically. The one place a human changes an outcome
is the admin **close** verb (`trade_commands.py:_close_plan`).

Production on 2026-10-17 (read-only SELECTs):

| | Count |
|---|---|
| CLOSED plans | 563 |
| … terminal reason `manual` | 36 (20 from ACTIVE, 16 from PARTIAL) |
| … of which one bulk clear, 2026-09-30 20:54–20:55 UTC | 15 |
| … individual overrides, 2026-08-14 → 2026-09-22 | ~21 |
| Manual cancels | 0 |

Two gaps stop anyone from saying whether those overrides helped:

1. **A manual close stores no exit price and no leg.** `_close_plan` only
   appends `{status, reason, at}` to `status_history`, so the realised R of
   an override has to be reconstructed.
2. **A bulk clear is recorded the same as a decision.** The bulk endpoint
   calls the same `_close_plan` with the same `reason="manual"`.

This spec is **stage A**: it closes both gaps and reports each override
against the engine's counterfactual. **Stage B** (eToro demo fills compared
with paper plans, roadmap Stage 1) reuses the row shape and is out of scope.

## Goals

- G1. Every manual close from now on records its exit price, the price's
  source, and the plan's live exit state at the moment of the close.
- G2. Bulk clears are distinguishable from individual overrides, going
  forward and for the 15 rows from 2026-09-30.
- G3. A pure replay gives, per override, the R the engine would have
  realised had the plan been left alone.
- G4. A report script and an Analytics panel show each override and a
  summary, under a verdict rule frozen in this spec.

## Non-goals

- No pooled verdict below the floor (§ Verdict rule). With N≈21 the panel is
  descriptive only.
- No change to how a manual close settles: `legs_realized`, `r_multiple`,
  equity and every existing analytics figure are untouched. The stamp is
  extra fields on the transition entry, read only by this report.
- No ghost plans: the engine does not keep tracking a closed plan live
  (rejected approach B: new state inside `plan_manager`, and a risk that
  ghosts count toward heat or risk caps).
- No eToro code (stage B), no Discord close verb, no weekly digest.

## Design

### 1. Stamping a manual close

`_close_plan(store, plan)` gains a `reason: str` parameter.

- `close_trade` (single position) passes `"manual"`.
- The bulk endpoint (`trade_commands.py`, the `store.all()` loop) passes
  `"manual_bulk"`.

Both still go through `_close_plan`, so the two paths cannot drift.

The transition entry gains an `override` object:

```json
{"status": "CLOSED", "reason": "manual", "at": "<iso>",
 "override": {"exit_price": 123.45, "price_source": "quote",
              "working_stop": 118.0, "remaining_fraction": 0.5,
              "tp2": 131.0, "bars_held": 6}}
```

- `exit_price`: the live quote the admin already attaches
  (`_attach_current_prices`). If none is available, it falls back to the last
  close in the scan's disk cache (`runner_path.cached_daily_bars`), with
  `price_source: "bar_close"`. If neither exists, `exit_price` is `null` and
  `price_source` is `"none"`.
- The remaining fields copy whatever plan state the replay needs to resume.
  The exact field list is fixed by the plan-briefer from `exit_sim_v2`'s
  inputs. The names above are illustrative and are not added if the plan
  doc already holds them unchanged at close.
- Like `stamp_runner_path`, building the stamp **never raises**: a failure
  logs and writes `override: null`, and the close goes ahead.

`record_transition` gains an optional `extra: dict | None` that is merged
into the appended entry. No other caller changes.

**Schema:** this adds fields inside `plans.doc` JSONB, the *add* operation in
`schema-evolution.md`, so no migration is needed.

**Readers of `"manual"`:** `partials.py:_REASON_BUCKET` maps `"manual_bulk"`
to the `manual` bucket. The plan greps every reader of a plan's terminal
`reason` and lists each one. `trades.py`/`lifecycle_embeds.py` key on the
legacy trade's `status`, not on this reason, and stay unchanged.

### 2. Re-tagging the 2026-09-30 bulk clear

An Alembic **data revision** sets `reason` to `"manual_bulk"` on the
terminal `status_history` entry of the plans whose last transition is
`manual` with `at` between `2026-09-30T20:54:00Z` and `2026-09-30T20:56:00Z`.
`downgrade()` reverts exactly those entries. The revision lists the plan ids
it expects (15) and refuses to run if it matches a different count.
Running it on production follows `schema-evolution.md` § Before running a
data revision on production, and the run is recorded in the commit
(mirror-production rule).

### 3. Replay core — `swingbot/core/analytics/override_fidelity.py`

Pure functions, no I/O:

- `override_state(plan) -> OverrideState | None`
  - From the stamp when one exists (`approx=False`).
  - For pre-stamp overrides, rebuilt from the plan doc plus the close bar:
    exit price = the close of the session containing `at`, live state =
    the plan's stored `working_stop` and fills. These rows are
    `approx=True`.
  - Returns `None` when neither can be built. The row is then counted as
    `unreplayable`, never dropped silently.
- `replay_override(state, bars) -> OverrideRow` runs the remaining position
  from the close under the engine's exit rules and returns `actual_r`,
  `engine_r`, `delta_r = actual_r - engine_r`, `engine_exit_reason`,
  `approx` and `source="manual"`.
  - It **reuses `exit_sim_v2`'s rules and never copies them.** If
    `simulate_exit_v2` cannot start from mid-trade state, the plan adds a
    behaviour-preserving `resume` entry point, verified by existing exit
    tests passing unchanged. The plan-briefer settles which case applies
    before the index is written.
- R uses the plan's initial risk, the same basis as `metrics.r_multiple`.
  - `actual_r` = R already realised in `legs_realized` + `remaining_fraction`
    × the R of `exit_price`.
  - `engine_r` = the same realised part + the replayed remainder.
- No lookahead: the replay sees only bars after the close session, and the
  close session itself is handled as `runner_path` does. A test asserts that
  changing a bar before the close does not change `engine_r`.
- A replay that reaches the end of the cached bars before any exit is
  `open`: it is shown, and excluded from ΔR sums.
- `summarise(rows) -> OverrideSummary` returns N, ΣΔR, mean ΔR, helped and
  hurt counts, bulk and unreplayable counts, and the verdict below.

### 4. Verdict rule (frozen now, never tuned)

- `VERDICT_FLOOR = 30` individual, replayed, non-`open` overrides.
- Below the floor: **`WAITING`**. The panel and report show rows and counts
  only, with no mean and no interval.
- At or above the floor: mean ΔR with a 95% bootstrap CI (10 000 resamples,
  fixed seed), clustered by ISO week of the close.
  - CI entirely below 0 → **`OVERRIDES COST`**.
  - CI entirely above 0 → **`OVERRIDES SAVE`**.
  - Otherwise → **`INCONCLUSIVE`**.
- `approx` rows count toward N, and the panel shows how many there are.
  The floor and the rule are module constants. Changing either is a new
  spec, not an edit (`backtest-methodology.md`, closed pre-registrations).

### 5. Report script, API, panel

- `scripts/reports/execution_fidelity_report.py`
  - Reads plans and the scan's cached daily bars and never fetches.
  - Prints a row table plus the summary.
  - Runs on the VM against the real book. A dev-DB run is fixture data and
    prints a banner saying so (`working-conventions.md` § Investigating
    production).
- `GET /api/v1/analytics/override-fidelity`
  - Computed on request (~21 rows, so no store and no cron).
  - Returns `{rows, summary}`. Behind `require_auth`, like its siblings in
    `analytics.py`.
- **Panel "Overrides vs engine"** on `analytics/tabs/execution.ts`, built
  from the tab's existing `Panel`/`PanelHeader`/`PanelError` pieces.
  - Verdict tiles: real overrides N, ΣΔR, helped/hurt, verdict badge, and
    the approx and bulk counts as tile hints.
  - Row table: close date, ticker, horizon, state at close
    (ACTIVE/PARTIAL), actual R, engine R, ΔR, engine exit, approx marker.
    Below 640px the rows become stacked cards with no horizontal page
    scroll.
  - Empty state: "No manual overrides in scope."
  - Checked at mobile, tablet and desktop widths with Playwright
    (`ui-design.md`).

### Stage B hook

Each `OverrideRow` carries `source`. Stage B adds `source="etoro_demo"` rows
from demo fills, and the summary groups by source. No stage B code ships here.

## Testing

- Replay unit tests on synthetic bars, one per path:
  - Runner stop hit.
  - TP2 hit.
  - Trail exit.
  - Time stop.
  - Still open at the end of the data.
  - Approx reconstruction.
  - Unreplayable.
- The no-lookahead test (§3).
- Verdict rule tests:
  - N=29 gives `WAITING`.
  - Seeded synthetic ΔR sets give each of COST, SAVE and INCONCLUSIVE.
- `_close_plan` tests:
  - A single close stamps `manual`.
  - A bulk close stamps `manual_bulk`.
  - A stamp failure still closes the plan, with `override: null`.
- `partials.py` maps `manual_bulk` to `manual`.
- Data revision: upgrade/downgrade round-trip on a fixture, and a refusal
  on a count mismatch.
- API shape test, including the bulk exclusion.
- Frontend spec for the panel, the WAITING state and the empty state.
- Every test uses fixture data. No pooled figure comes from the dev DB.

## Risks

- **`exit_sim_v2` cannot resume mid-trade.** Mitigation: a
  behaviour-preserving `resume` entry point, with the existing exit tests as
  the guard (complexity < 15, `code-complexity.md`).
- **The approx exit price of the 21 old rows is a daily close, not the
  fill.** They are labelled `approx`, and the panel shows the count.
- **Overrides may stay rare** (none for 25 days). The report then stays
  `WAITING`, which is the honest answer, and stage B supplies volume.
