Version: ui 1.18.3 · bot 1.9.1
Bump: bot minor · ui minor
Edge: expectancy (phase 1) · volume (phase 3, conditional on phase 1) · none (integrity) for phase 2

# Strategy path goes live: strategy-sourced alerts, ledger split, entry-context snapshot, bearish arms

## Problem

Verified in code on 2026-09-17 during the brainstorm this spec closes:

- **The live scan loop never trades a strategy signal.** Every plan it builds is
  `source="confluence"` (`swingbot/core/planning/builders.py:build_confluence_plan`).
  The strategy path — `entry_filters.entries_for` → `builders.build_strategy_plan` —
  is reached live only from the `!ticker` command (`swingbot/commands/info.py:89`),
  which tracks nothing. `swingbot/core/backtesting/registry.py:get_badge`'s own
  docstring records this: the per-strategy badge rows live under a source
  "the live scan loop never calls", and confluence plans *borrow* them through the
  primary-confirming-method fallback.
- **So the positive populations never reach the book.** The live book (2026-09-10
  probe, N=782) is 80% confluence-sourced and net negative (ExpR −0.136R), mirroring
  the confluence VALIDATION pool (N=4641, 53.5%, −0.171R). The two VALIDATED
  strategies — MACD (VALIDATION N=112, WR 50.0%, ExpR +0.219R) and Volume Profile
  (N=32, 53.1%, +0.547R) — are measured under the same v2 exit simulator the live
  tracker runs, and are traded nowhere.
- **Seven strategies are masked bullish-only on stale evidence.**
  `strategy_types.STRATEGY_GATES` restricts Fibonacci, RSI, MA Ribbon, VWAP,
  Support/Resistance, MACD and Volume Profile to `("bullish",)`. The masks come from
  `results/2026-07-train-tuning.md` Step 3, measured under the fixed per-strategy
  reward:risk table and the WR≥80 bar that plan v31 deleted. Every grid since ran
  with the mask on, so the bearish arms are unmeasured under current arithmetic.
  Two of them (Support/Resistance, Elliott Wave) beat their own bullish arm even
  under the old arithmetic.
- **There is no training set for any future trade-selection model.**
  `backtest.BacktestTrade` stores entry, exit, direction, prices, outcome and R.
  None of the context the live plan builder already computes at alert time
  (`scanning/analyze.py:_build_quality_inputs` — regime, RS percentile, breadth,
  ATR percentile, volume ratio, HTF bias, gap stats) is recorded for a backtested
  or replayed trade.

Ranked by `docs/claude/edge-priorities.md` — pooled `ExpR` first — the largest
lever available is not another filter on the confluence pool (seven such filters
are already closed in `backtest-methodology.md`'s table). It is putting the
already-validated strategy populations into the book. That is phase 1. Phases 2
and 3 are its prerequisites and its direction-completion, and the prerequisites
for the two follow-on specs in the roadmap at the end.

## Decisions taken in the brainstorm (2026-09-17)

1. Better trade identification will use **meta-labeling** (a secondary model on
   entry-time features) — spec 2, not this one. Two hand-weighted blended scores
   (v32, v33) already regressed; a third linear score is not a new mechanism.
2. Model artefact policy: **train offline with scikit-learn as a scripts-only
   dependency, commit a JSON artefact, score in pure numpy at runtime.** No new
   runtime dependency in the prod image.
3. A model verdict **stamps and journals first, gates later** under a
   pre-registered flip rule. Paper trades keep opening until the statistic says
   the mechanism is trusted.
4. Order: this spec → spec 2 (confluence meta-label) → spec 3 (per-strategy
   rescue via the same harness).
5. WEAK strategies **do trade live**, but their P&L is kept in a **separate WEAK
   ledger**, never summed into the existing figures.
6. The ledger split is shown in **Discord and the admin dashboard/analytics**.

## §1 Phase 1 — Strategy-sourced alert path

**Where.** A second pass inside `scanning/scan_run.py:_sync_run_scan`, per
ticker × horizon, after the confluence pass. It calls
`entry_filters.entries_for(strategy, df_completed, horizon_key)` for every strategy
in the registry and, where the last row fires, `builders.build_strategy_plan(df,
len(df_completed)-1, ...)`. The masks in `STRATEGY_GATES` and the regime gate
apply exactly as in the backtest, because it is the same function.

**Completed bars only.** `df_completed` excludes the current session's partial bar.
A signal fires live on exactly the bar the backtest would fire on. The pass runs at
most once per ticker × horizon × session, keyed on the completed bar's date; a
scan later in the same session finds the key already consumed and does nothing.

**Entry parity.** `backtest.ENTRY_SHIFT == 0`: the simulator enters at the signal
bar's close. Live, the plan is created at the first scan after the session close
with `trigger_price = entry_price = that close`, `entry_type = "market"`, and the
existing lifecycle manager takes over from the next session — which is what
`plan_engine.simulate_exit` does. The only thing that can differ is the price the
tracker first sees versus the recorded close; the shadow soak measures it.

**Laggard rule for shorts.** The v34 `RS_GATE` (bottom quartile of combined RS for
bearish setups, `scan_run.py:444`) applies to strategy-sourced bearish plans too,
using the same `item.rs_combined` value. Phase 3 measures bearish arms under the
same rule (§4), so live and measured populations match.

**Config.** One new field, `STRATEGY_ALERTS_MODE` ∈ `{off, shadow, live}`,
default `off`. With `off` the pass does not run and the scan is byte-identical to
today. `shadow`: every strategy plan is built, badge-stamped, stored in
`PlanStore`, and walked through the lifecycle by the existing manager, but opens
no paper trade and posts no alert. `live`: plans post as alerts and open paper
trades under `paper_trade_decision`, both badges. Per-strategy override list
`STRATEGY_ALERTS_LIVE_STRATEGIES` (empty = all) so the flip rule below can be
applied one strategy at a time.

**Collisions.** `PerformanceTracker.open_trade_for_ticker` already enforces one
trade per ticker; a strategy plan on a ticker with an open trade is stored, not
opened — same as a second confluence plan today. When a confluence plan and a
strategy plan fire for the same ticker and direction in one pass, the strategy
plan opens and the confluence plan is stored, because the strategy population has
the higher measured expectancy. Opposite-direction collisions follow the existing
thesis-flip logic (`scan_run.py:585`) unchanged. `one_at_a_time` in the backtest is
per (ticker, strategy, horizon); live is per ticker and therefore stricter, so live
N ≤ backtest N — recorded as a known population difference, not a bug.

**Trust rule — pre-registered here, before any shadow data exists.** A strategy
moves from `shadow` to `live` when all three hold on its shadow plans:
`N_closed ≥ 30`; shadow `ExpR ≥ badge ExpR + NON_INFERIORITY_R`
(`acceptance.NON_INFERIORITY_R = −0.01`, i.e. no more than 0.01R worse than the
badge, on the same DECIDED definition); median |first-seen price − recorded
close| / stop distance ≤ 0.10. Evaluated by a pure function
`edge/strategy_soak.py:soak_verdict(shadow_trades, badge) -> dict` with the three
clauses reported separately. Run by hand via `!soak <strategy>` and shown on the
admin Strategies page; the flip itself is a config edit, never automatic.

**Alert surface.** Strategy alerts reuse the existing plan embed with the
`source="strategy"` line and the badge block already rendered for confluence
plans. WEAK plans carry the WEAK warning already used. No new embed.

## §2 Ledger split

**Stamp.** `TradePlanV2` and the trade record gain `ledger: "main" | "weak"`,
frozen at creation. Rule: `source == "strategy" and badge.status == "WEAK"` →
`weak`; everything else → `main`. Confluence plans that borrow a WEAK badge from
their primary method stay `main`: they are the current book, and moving them would
empty the main figure overnight. A later promotion (spec 3) changes new trades
only; history is never rewritten. Persisted through the JSONB `doc` via
`db/codec.py` like `cohort_stats` — no migration.

**Reporting.** Every P&L, N, win-rate and expectancy figure the bot reports today
becomes the `main` figure, with `main` computed as `ledger != "weak"` so every
pre-existing trade (no field) stays where it is. A separate `weak` block reports
the WEAK ledger's P&L, N, WR, ExpR. The two are never summed. Surfaces:

- Discord: `!stats`, `!performance` gain a "WEAK ledger" block; the digest gains
  one line.
- Admin: `ledger` joins `analytics/aggregate.DIMENSIONS`; the dashboard P&L card
  shows main and weak side by side; existing analytics charts gain a `ledger`
  filter (default `main`, so nothing a user sees today changes value). The
  Angular side is one filter control plus one card — `Bump: ui minor` because the
  headline number gains a sibling the user reads daily.

## §3 Phase 2 — Entry-context snapshot

**Module.** `swingbot/core/edge/context.py`, one public function:

```python
def entry_context(df, *, direction, horizon_key, stop, target, asof: dict) -> dict
```

`df` is the frame cut at the entry bar (inclusive). `asof` carries the
cross-sectional values the caller already holds for that bar. Returns a flat dict
of floats/ints/short strings — JSON-serialisable as-is. A feature that cannot be
computed yet is `None`, never a default that looks like a measurement.

**Features.**

- Geometry: `stop_atr`, `stop_pct`, `planned_rr`, `swing_high_atr`,
  `swing_low_atr`, `horizon_key`, `direction`.
- Ticker state: `atr_pctile_250`, `vol_ratio_20`, `rsi_14`, `adx_14`,
  `bb_width_pctile_250`, `htf_aligned` (EMA-50/200 vs direction, the existing
  `get_htf_bias` rule), `gap_p90_pct` and `gap_fragile` (existing `gates.gap_stats`
  / `stop_beyond_gap_noise`), `dow`.
- As-of cross-sectional (passed in): `regime2_state`, `rs_pctile`,
  `sector_pctile`, `rs_combined`.

Excluded on purpose: confluence count and confidence level (scan-only, would be
null on every strategy row), anything from options chains or the earnings
calendar (not in the cache; would fail the truncation test).

**NO-LOOKAHEAD.** Every input is the entry bar or earlier. Tests include the
truncation check from `architecture.md`: `entry_context(full.iloc[:i+1]) ==
entry_context(trunc)` for every i in a fixture.

**Three stamp sites, one function.**

- `backtesting/backtest.py`: `BacktestTrade.context: dict | None = None`, filled
  at both construction sites (v1 loop ~L353, v2 branch ~L429) from `df.iloc[:i+1]`.
  Cross-sectional inputs computed once per universe run, not per trade.
  `run_backtest_range.py --json` carries it through, so a TRAIN run of any
  strategy emits a labelled training table.
- `backtesting/backtest_scenarios.py:replay_scenarios`: the yielded plan at bar
  `i` is stamped via the shared helper.
- Live: `planning/params.py:stamp_entry_context(plan, df, asof)` beside
  `stamp_cohort`, called from `scanning/analyze.py:attach_plan_v2` and from the
  phase-1 strategy pass, reusing the regime/RS/sector values the scan already
  holds for the item. Flows to the journal through `performance.py`'s record dict
  and to Postgres through the JSONB `doc`.

**Cost cap.** Measure one strategy over TRAIN before and after; accepted slowdown
≤ 20%. If exceeded, precompute the rolling series once per frame and index them,
as `_plan_series` already does for ATR and volume ratio.

## §4 Phase 3 — Bearish-arm re-derivation

**Measured.** For each of the seven masked strategies, TRAIN 2020-01-01..2023-12-31,
bearish side unmasked, current arithmetic (`--exit-model v2 --scale-out
--tp2 levels --frictions on`), liquidity-filtered cached universe, the laggard rule
applied through the snapshot's `rs_combined` (bottom quartile). Script:
`scripts/backtest/measure_bearish_arms.py`, one strategy per invocation, flushed
per-symbol progress, dispatched to `backtest-runner`.

**Decision rule, fixed before the run.**

- *Stage 1* — pooled bearish arm, (a) under the strategy's existing horizon mask
  and (b) across all horizons. Clears if: `WR ≥ 50`, `ExpR > 0`, `N ≥ 30`,
  scratches+timeouts ≤ 50% of closed, and ≥ 2 of the 3 `ANCHORED_FOLDS` years
  hold `N ≥ 15` with `ExpR > 0`. (a) preferred when both clear.
- *Stage 2* — a bearish-specific horizon subset, allowed only when Stage 1 fails
  on `WR` alone with `ExpR > 0`. Must pass the v84 plateau check (≥ 4 neighbouring
  subsets also clear WR≥50, N≥30). One subset selection per strategy. Requires an
  optional `"horizons_by_direction": {"bearish": (...)}` key in `STRATEGY_GATES`,
  honoured by `entries_for`.
- Clauses live in a pure function `backtesting/arm_rule.py:arm_verdict(...)`.

**On clear.** Mask gains `"bearish"`. Five WEAK strategies: arm goes live into the
`weak` ledger; registry row re-emitted as TRAIN-window, both directions,
`run_date` set (the schema already supports this — legacy badge refresh
2026-09-10). MACD and Volume Profile: recorded, **not enabled** — enabling would
dilute a VALIDATED badge with an unvalidated population; their arms wait for their
own VALIDATION shot in spec 3.

**On fail.** A row in `backtest-methodology.md`'s closed table with the numbers;
mask unchanged. **No VALIDATION shot is spent in this spec.**

## Data flow

Scan tick → confluence pass (unchanged) → strategy pass on completed bars →
`build_strategy_plan` → `stamp_cohort` + `stamp_entry_context` + badge + ledger →
`PlanStore` → (mode `live`) alert + `paper_trade_decision` → tracker → journal
record with `source`, `ledger`, `entry_context` → analytics `stats_by("ledger")`
→ Discord/admin. Backtest and replay write the same `context` dict on their trade
records → `--json` → future training tables (spec 2).

## Error handling

- Strategy pass failure for one ticker logs and continues; it never aborts the
  confluence pass.
- `entry_context` never raises on short frames; missing features are `None`.
- Mode `off` is asserted byte-identical by a scan snapshot test.
- Ledger absent on a record ⇒ `main`, by the `!= "weak"` rule.
- The soak verdict reports each clause; a missing badge (n=0) fails clause 2
  explicitly rather than passing vacuously.

## Testing

Per task `python scripts/dev/testrun.py file tests/test_<file>.py`; frontend
`npm test -- --include <spec>`. Once, as the plan's final task: one `full` run and
one `cd frontend && npm test`.

- Phase 1: completed-bar rule (fixture with partial bar); parity test — live
  builder at bar i equals the backtest's plan at bar i; once-per-session key;
  collision precedence; trust rule clauses; `off` byte-identical snapshot.
- Ledger: stamp rule incl. borrowed-WEAK confluence → `main`; all existing
  figures unchanged on a fixture book with no `weak` trades; `stats_by("ledger")`.
- Phase 2: truncation test; null-not-default; JSON round trip; live and backtest
  stamps call the same function (mock-count).
- Phase 3: each `arm_verdict` clause; measurement script dry-run on a
  three-ticker fixture; `horizons_by_direction` honoured by `entries_for` with
  the existing 12 call sites untouched.
- Frontend: ledger filter spec; WEAK card spec.

## Parallelisation

- **Sequential first:** config field (`STRATEGY_ALERTS_MODE`, override list) and
  the `ledger` field on plan/trade records — everything else consumes them.
- **Phase 1, Group A (parallel):** scan strategy pass (`scan_run.py`); ledger
  stamp + main/weak split in `tracking/performance.py`; `strategy_soak.py`.
- **Phase 1, Group B (parallel, after A):** Discord `!stats`/`!performance`/`!soak`;
  admin API (`analytics` dimension, Strategies page soak endpoint); Angular
  filter + card. Three disjoint trees.
- **Phase 2:** `edge/context.py` + tests first; then three stamp sites in
  parallel (`backtest.py`, `backtest_scenarios.py`, `params.py`+`analyze.py`).
  **Not beside Phase 1 Group A** — both edit `analyze.py`/`scan_run.py`.
- **Phase 3:** sequential throughout; depends on Phase 2 (`rs_combined` as-of).
- Final verification task last.

## Non-goals

No model, no verdict stamp, no change to which confluence plans open (spec 2). No
per-strategy rescue hypothesis and no VALIDATION shot (spec 3). No bullish-side RS
leader gate (closed negative on TRAIN, v34). No change to `acceptance.py` or its
constants. No re-run of any row in the closed pre-registrations table.

## Roadmap — specs 2 and 3, as agreed 2026-09-17

**Spec 2 — Meta-label on the confluence pool.** `Edge: expectancy`. Training
table from phase 2's `context` on TRAIN replay trades; label = DECIDED win.
Offline training (scikit-learn, scripts-only) with `ANCHORED_FOLDS` walk-forward
inside TRAIN; committed JSON artefact beside `validation_registry.json`; pure-numpy
scorer at runtime; verdict stamped on every plan and journaled in `shadow`; flip
to gating the *paper trade only* (alert still posts, labelled) under a rule
pre-registered in that spec; one VALIDATION shot. Live journal (Jul–Sep 2026) is a
monitoring set only, never training data.

**Spec 3 — Per-strategy rescue through the same harness.** `Edge: expectancy`.
One pre-registration per WEAK strategy: meta-label filter scoped to that strategy,
TRAIN → folds → one VALIDATION shot only if TRAIN clears. Also re-measures the
stale pre-v31 registry rows honestly under current arithmetic, and spends the
deferred MACD / Volume Profile bearish-arm shots. A strategy that earns VALIDATED
starts writing to the `main` ledger from that day.

## Next step

`superpowers:writing-plans` → `docs/superpowers/plans/2026-09-17-v93-strategy-path-live.md`
(split into `_N` parts if any file would pass 1500 lines).
