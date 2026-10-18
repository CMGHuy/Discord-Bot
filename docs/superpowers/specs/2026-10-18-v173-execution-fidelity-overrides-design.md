# v173 — Execution fidelity: what manual overrides cost against the engine

**Version:** ui 1.27.0 · bot 2.10.0 (at writing)
**Bump:** bot minor — a manual close starts recording its exit price and quote time, bulk clears get their own reason, and a new API endpoint serves the override report; ui minor — the Analytics Execution tab gains an "Overrides vs engine" panel.
**Edge:** none (integrity) — a measurement. It changes no signal, gate, stop, size or badge. Any harvest it buys is behavioural (fewer costly overrides) and arrives only if the report changes how the partner acts, so it is not claimed here.
**Screen:** exempt (integrity)
**Panel:** quant-researcher, quant-engineer, financial-advisor
**Status:** spec written 2026-10-18 from a brainstorm with the partner (direction, staging, scope, approach and both design sections approved in chat); revised the same day after the panel (see `## Panel review`).

## Why

The brainstorm read three trading books against the bot: Murphy (*Technical
Analysis of the Financial Markets*), Douglas (*Trading in the Zone*) and
Bassal (*Swing Trading for Dummies*). Most of Murphy's and Bassal's chart
ideas are already measured in `preregistration-ledger.jsonl`:

- Regime-matched indicators: `v17-regime-allow`, NO-LIFT.
- Role-reversal levels: `v31-break-retest` FAIL, `v36-level-touch-strength`
  NO-LIFT.
- Earnings blackout: `v82-earnings-blackout`, NO-LIFT.
- Cross-horizon trend alignment: measured, OFF.

Sector RS and stop-based sizing are already built.

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
   appends `{status, reason, at}` to `status_history`.
2. **A bulk clear is recorded the same as a decision.** The bulk endpoint
   calls the same `_close_plan` with the same `reason="manual"`.

This spec is **stage A**: it closes both gaps and reports each override
against the engine's counterfactual. **Stage B** (eToro demo fills compared
with paper plans, roadmap Stage 1) reuses the row shape and is out of scope.

## Goals

- G1. Every manual close from now on records its exit price, the price's
  source, when the quote was taken, and how fresh the bar cache was.
- G2. Bulk clears are distinguishable from individual overrides, going
  forward and for the 15 rows from 2026-09-30.
- G3. A deterministic replay gives, per override, the R and dollars the
  engine would have realised had the plan been left alone, on the same cost
  basis as the actual close.
- G4. A report script and an Analytics panel show each override and a
  summary, under a verdict rule frozen in this spec.

## Non-goals

- No pooled verdict below the floors (§ Verdict rule). With N≈21 the panel
  is descriptive only.
- No change to how a manual close settles: `legs_realized`, `r_multiple`,
  equity and every existing analytics figure are untouched. The stamp is
  extra fields on the transition entry, read only by this report.
- No ghost plans: the engine does not keep tracking a closed plan live
  (rejected approach B: new state inside `plan_manager`, and a risk that
  ghosts count toward heat or risk caps).
- No mid-trade `resume` entry point in `exit_sim_v2` (panel: its state is
  path-dependent; §3 replays from the fill instead).
- No eToro code (stage B), no Discord close verb, no weekly digest.
- No advice. The verdict describes overrides that were made; it is not a
  policy on overriding more or less often.

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
              "quote_ts": "<iso>", "bars_asof": "2026-10-17"}}
```

- `exit_price` and `quote_ts`: the live quote the admin already attaches
  (`_attach_current_prices`) and the time it was taken.
  - With no quote, it falls back to the last close in the live scan's
    cache (`runner_path.cached_daily_bars`, i.e. `market_data/daily`), with
    `price_source: "bar_close"` and `quote_ts: null`.
  - With neither, `exit_price` is `null` and `price_source` is `"none"`.
- `bars_asof`: the date of the last bar in that cache at close time.
  Together with `quote_ts`, it makes the row reproducible later.
- No live exit state is stamped. The replay re-derives it from the fill
  (§3), so the stamp holds only what the replay cannot reconstruct.
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
terminal `status_history` entry of exactly **15 plan ids pinned in the
revision**.

- The ids come from the production SELECT (last transition `manual`, `at`
  in 2026-09-30 20:54–20:56 UTC) and are written in by the plan task.
- The revision refuses to run if any pinned id is missing or its terminal
  reason is not `manual`.
- `downgrade()` reverts exactly those entries.
- Running it on production follows `schema-evolution.md` § Before running
  a data revision on production, and the run is recorded in the commit
  (mirror-production rule).

### 3. Replay core — `swingbot/core/analytics/override_fidelity.py`

Pure functions, no I/O.

**Never resume; replay from the fill.** `exit_sim_v2` cannot start mid-trade.
`walk_v2`/`simulate_exit_v2` take `(entry_index, entry_price, plan)`, and
`_runner_v2` rebuilds its stop and stall state from the TP1 bar
(`exit_sim_v2.py:145`, `:174-200`). The engine is deterministic, so
replaying the whole trade from the plan's real fill bar and price, with the
same plan, *is* the "left alone" counterfactual.

- `engine_path(plan, bars)` runs `walk_v2` from the fill index. The fill is
  the ACTIVE entry in `status_history`, mapped to its NYSE session.
- **Parity check.** The replay must not exit before the override's
  session, because the live plan was still open then.
  - If it does, the row is `parity_mismatch`: excluded from sums and
    counted.
  - For a PARTIAL plan, the replay's TP1 bar must equal the live TP1
    session, or the row is `parity_mismatch` too.

**One cost basis for both arms.**

- The TP1 leg of a PARTIAL plan is identical in both arms by
  construction. It is taken from `legs_realized` for **both**.
- The diverging remainder (`1 - tp1_fraction` for PARTIAL, `1` for ACTIVE,
  as at `plan_manager.py:1115`) is booked once through `costs.book` with
  the same `frictions.py` model on both arms:
  - Actual arm: a one-leg exit at `exit_price`, with a stop-style exit
    fill.
  - Engine arm: the replay's own remainder leg(s).
- `delta_r = actual_r - engine_r`. R uses the plan's initial risk, the
  basis of `metrics.r_multiple`. Dollars = R × the plan's stored dollar
  risk. The plan-briefer names the field v170's alerts already read.
- Both arms are **net of modelled frictions and pre-tax**.

**The override session is the same for both arms (no lookahead).** `at` is
converted to America/New_York and assigned to an NYSE session:

| `at` falls | Override session | Actual exit price when not stamped (`approx`) |
|---|---|---|
| Before the open of a trading day | That day | That session's open |
| During regular hours | That day | That session's close |
| After the close of a trading day | That day | That session's close |
| On a non-trading day | The last trading session | That session's close |

- If the override session's high or low touches the engine's stop or
  target, the engine might have exited before the human did. The row is
  then `ambiguous`: excluded from sums and counted.
- Otherwise the engine continues from the **next** session. It never sees
  the override session's range as a later path.

**Rows and statuses.** `replay_override(plan, bars, asof) -> OverrideRow`
carries `actual_r`, `engine_r`, `delta_r`, the dollar equivalents,
`engine_exit_reason`, `state_at_close` (ACTIVE/PARTIAL), `horizon`,
`direction`, `approx` (no stamp, so the exit price comes from the table
above), `source="manual"` and one `status`:

| `status` | Meaning | In sums |
|---|---|---|
| `resolved` | The engine exited, or hit its hold cap (`timeout`, `_hold_cap_bars`), within the data | yes |
| `open` | The data ends before any engine exit **and** before the hold cap | no, counted |
| `stale` | The cache's last bar is before the latest NYSE session ≤ `asof` | no, counted |
| `ambiguous` | Override-session range touches the engine's stop/target | no, counted |
| `parity_mismatch` | The replay disagrees with the live path before the override | no, counted |
| `split_affected` | A split/dividend adjustment (`adjustments.py`) falls between fill and last bar | no, counted |
| `unreplayable` | No fill, no bars, or no exit price derivable | no, counted |

- The bars come only from `runner_path.cached_daily_bars`
  (`market_data/daily`, the live scan's cache, `known-traps.md`), read in
  one place, and **never fetched**.
- **Helped / hurt / neutral:** `delta_r > +0.05` helped, `< -0.05` hurt,
  otherwise neutral. The ±0.05R dead band is frozen.
- `summarise(rows)` returns the descriptive totals (N by status, ΣΔR and
  Σ$, helped/hurt/neutral) and splits by `state_at_close`, `horizon` and
  `direction`.

### 4. Verdict rule (frozen now, evaluated once, never tuned)

**Population:** individual (`manual`, not `manual_bulk`), stamped (not
`approx`), `resolved` rows.

**The verdict becomes evaluable when all of the following hold:**
- At least `VERDICT_FLOOR = 30` population rows.
- At least `WEEK_FLOOR = 10` distinct ISO weeks among them.
- No eligible stamped individual override is still `open`.
- Excluded statuses (`stale`, `ambiguous`, `parity_mismatch`,
  `split_affected`, `unreplayable`) are ≤ 20% of eligible stamped
  individual overrides.

**Until then:** **`WAITING`**, with no mean and no interval.

**One evaluation:**
- The first run where the conditions hold computes mean ΔR with
  `week_cluster_bootstrap` (`swingbot/core/backtesting/instrument/stats.py`,
  its own `WEEK_BOOTSTRAP_SEED` and resample count), pooled across
  ACTIVE/PARTIAL.
- Outcomes:
  - CI entirely below 0 → **`COST`**.
  - CI entirely above 0 → **`SAVED`**.
  - Otherwise → **`INCONCLUSIVE`**.
- The result is written once to `preregistration-ledger.jsonl` as
  `v173-override-fidelity` and **frozen**. Later runs show that recorded
  verdict and keep the descriptive rows live. They never recompute it,
  because watching a live CI until it crosses zero inflates false
  positives.
- A re-read on a later sample is a new spec. The floors, the dead band and
  the 20% cap are module constants; changing any of them is a new spec,
  not an edit (`backtest-methodology.md`, closed pre-registrations).

**Scope:** the verdict covers the overrides the partner chose to make, given
what they saw at the time. It says nothing about overriding more or less
often, and nothing about trades that were not overridden.

### 5. Report script, API, panel

- `scripts/reports/execution_fidelity_report.py`
  - Reads plans and `market_data/daily` and never fetches.
  - Prints the row table, the summary and splits, and the verdict state.
    It writes the ledger row on the evaluating run (§4).
  - Runs on the VM against the real book. A dev-DB run is fixture data,
    prints a banner saying so, and never writes the ledger
    (`working-conventions.md` § Investigating production).
- `GET /api/v1/analytics/override-fidelity`
  - Computed on request (~21 rows, so no store and no cron). It reads the
    frozen verdict from the ledger and never evaluates it.
  - Returns `{rows, summary, verdict}`. Behind `require_auth`, like its
    siblings in `analytics.py`.

**Panel "Overrides vs engine"** on `analytics/tabs/execution.ts`, built from
the tab's existing `Panel`/`PanelHeader`/`PanelError` pieces.

Every R figure carries its signed dollars beside it, the convention of the
v170 alerts.

**Verdict tiles**, in this order:
- Net effect in dollars and R (ΣΔ), leading, because expectancy comes
  before counts.
- Overrides counted.
- Helped / hurt / neutral, with the hint "counts ignore size".
- The verdict badge.

Tiles wrap two per row on phones, and the badge text never truncates.

**Badge copy is scoped, never a policy:**

| State | Copy |
|---|---|
| WAITING | "N of 30 needed. No conclusion yet." |
| COST | "Your overrides cost $X (Y R) vs the engine" |
| SAVED | "Your overrides saved $X (Y R) vs the engine" |
| INCONCLUSIVE | "No clear difference vs the engine" |

**Fixed caption under the tiles:**

> Compares the overrides you made with what the engine would have done.
> Past closes only, not advice on future ones. A close for a reason the
> engine cannot see (a gap, earnings, needing the cash) can still be right.
> Figures are after modelled costs and before tax. Closing early can also
> change the tax holding period. There is no target number of overrides.

**Exclusion notes:** one line per non-zero count, for example "15 closes
from one bulk clear on 2026-09-30 are not decisions, so they are left out"
and "3 estimated rows are shown but not counted".

**Row table:**
- Columns: close date, ticker, horizon, state at close, actual, engine, Δ
  (each in $ and R), engine exit, status.
- An `approx` row is labelled "estimated exit: daily close, not your fill"
  beside its Δ.
- Below 640px each row becomes a card that leads with ticker, close date
  and Δ in $ and R. The engine exit, status and the estimate label are
  secondary lines. There is no horizontal page scroll, and touch targets
  are at least 44px.

**Empty state:** "No manual overrides in scope."

**Checks:** at mobile, tablet and desktop widths with Playwright
(`ui-design.md`).

### Stage B hook

Each `OverrideRow` carries `source`. Stage B adds `source="etoro_demo"` rows
from demo fills, and the summary groups by source. No stage B code ships here.

## Testing

**Replay unit tests on synthetic bars**, one per status and exit path:
- Runner stop.
- TP2.
- Trail.
- Hold-cap `timeout` (resolved, not `open`).
- `open`.
- `stale`.
- `ambiguous`.
- `parity_mismatch`, both the ACTIVE early-exit case and the PARTIAL TP1
  disagreement.
- `split_affected`.
- `unreplayable`.
- `approx` exit price, one test per row of the session table, including a
  UTC→ET date boundary and a weekend `at`.

**No lookahead:**
- Changing any bar before the fill does not change `engine_r`.
- Changing the override session's high/low flips a row between `resolved`
  and `ambiguous`, and never changes a `resolved` `engine_r`.

**Cost parity:** an override whose `exit_price` equals the engine's exit
price on the same session gives `delta_r == 0`.

**Verdict rule:**
- 29 rows → WAITING.
- 30 rows over 9 weeks → WAITING.
- One eligible row `open` → WAITING.
- Exclusions at 21% → WAITING.
- Seeded ΔR sets → each of COST, SAVED, INCONCLUSIVE.
- A second evaluation reads the frozen ledger row and does not recompute.

**`_close_plan`:**
- A single close stamps `manual` with the four `override` fields.
- A bulk close stamps `manual_bulk`.
- A stamp failure still closes the plan, with `override: null`.

**Other:**
- `partials.py` maps `manual_bulk` to `manual`.
- Data revision: upgrade/downgrade round-trip on a fixture, and a refusal
  on a missing or already-changed pinned id.
- API shape test: the bulk exclusion, dollars beside R, and the verdict
  read from the ledger.
- Frontend spec: the panel, each badge state's copy, the caption, the
  empty state and the card layout.

Every test uses fixture data and never the database, including the local
production replica. Any pooled figure a plan or results doc quotes is
re-derived from the live production book with its N, window and source
(`pooled-numbers`). A replica is a snapshot, not the live book.

## Risks

- **The verdict may take a long time.** With no override in 25 days and the
  approx rows excluded, the panel is likely to stay `WAITING` for months.
  That is the honest answer. Stage B supplies volume, under its own
  population and its own spec.
- **The replay disagrees with the live path** (`parity_mismatch`). Live and
  backtest exits are meant to match. A high mismatch share is itself a
  finding, it shows in the counts, and it holds the verdict at WAITING
  through the 20% cap.
- **The plan's dollar-risk field may be missing on old plans.** Such a row
  shows R only, with a "—" for dollars, and stays in the R sums.

## Panel review

2026-10-18. The three roles ran serially on commit `6b0fd792`. Every finding
was applied; none was rejected.

- quant-engineer [BLOCKING]: `exit_sim_v2` cannot resume mid-trade, and its
  state is path-dependent -- applied: §3 replays from the fill with a parity
  check, `resume` moved to Non-goals, and the stamp reduced to
  exit_price/price_source/quote_ts/bars_asof.
- quant-engineer [BLOCKING] + quant-researcher: the arms used different R
  and cost bases -- applied: the TP1 leg comes from `legs_realized` for both
  arms, the remainder is booked once through `costs.book`/`frictions.py` on
  both, and the remainder fraction follows `plan_manager.py:1115`.
- quant-engineer [BLOCKING] + quant-researcher: the close-session rule was
  unspecified (lookahead or a hidden engine advantage) -- applied: an
  `ambiguous` status, the engine resumes the next session, and a test on a
  change to the override bar.
- quant-engineer [BLOCKING]: the cache was not named and had no freshness
  or split check -- applied: `market_data/daily` via `cached_daily_bars`
  only, plus `stale` and `split_affected` statuses.
- financial-advisor [BLOCKING]: R only, with no dollars -- applied: signed
  dollars beside every R figure.
- financial-advisor [BLOCKING] + quant-researcher: the badge read as a
  policy -- applied: scoped badge copy, a fixed caption and a Scope
  paragraph in §4.
- financial-advisor [BLOCKING]: WAITING was undefined and the counts led --
  applied: "N of 30 needed" copy, net dollars lead the tiles, and a
  "counts ignore size" hint.
- quant-researcher: the live verdict invited stopping when it crossed --
  applied: one evaluation, written to the ledger and frozen.
- quant-researcher: the floor counted rows, not weeks -- applied:
  `WEEK_FLOOR = 10`.
- quant-researcher + quant-engineer: a home-made bootstrap -- applied:
  `week_cluster_bootstrap` with its own seed.
- quant-researcher: approx rows padded N -- applied: the verdict counts
  stamped rows only, and approx rows are descriptive.
- quant-researcher: excluding `open` rows is a selection effect --
  applied: the verdict waits while any eligible row is open.
- quant-researcher: no cap on unreplayable rows -- applied: ≤ 20% across
  all exclusion statuses.
- quant-researcher: helped/hurt undefined -- applied: a frozen ±0.05R dead
  band.
- quant-researcher: pooled vs per state -- applied: the verdict is pooled,
  with splits by state/horizon/direction reported.
- quant-engineer: the approx session assignment and timezone -- applied:
  the ET session table.
- quant-engineer: the meaning of `open` vs `timeout` -- applied: the
  status table.
- quant-engineer: the data revision selected by a time window -- applied:
  15 pinned ids plus a refusal.
- financial-advisor: pre-cost/pre-tax and holding period -- applied: the
  caption.
- financial-advisor: plain-language approx label and the bulk exclusion
  reason -- applied: exclusion notes and a row label.
- financial-advisor: mobile card order, tile wrap and touch targets --
  applied in §5.
- financial-advisor: the waiting copy must not nudge -- applied: "no
  target number of overrides" in the caption.
