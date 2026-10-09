# v146 — Expectancy attribution: does confidence predict R?

**Version:** ui 1.22.0 · bot 2.2.3 (at writing)
**Bump:** bot patch (new numeric `confidence_points` stamp, `days_to_earnings` now populated, two new analytics dimensions) — every change is a recorded field or a read-side grouping; no alert, gate, level, size or exit changes for any user. The two Analytics breakdown dropdown entries (§I4) are the only UI-visible edit; they ride on this patch unless the partner rules them a `ui patch` of their own.
**Edge:** none (integrity) — measurement only; it is the admission evidence for a later expectancy screen (confidence floor / confidence-weighted sizing / bucket filters)
**Screen:** exempt (descriptive; registers nothing and spends no budget)
**Panel:** quant-researcher, quant-engineer, veteran-trader
**Status:** spec written 2026-10-09; plan not yet written.

## Why

Every alert carries a confidence level and score, and the alert gate is
`MIN_ALERT_CONFIDENCE_LEVEL` (`swingbot/config.py:275`, default 4). Nobody
has measured whether a higher score buys a higher realised R. v32 and v33
tried to *reweight* the score into a better one and both regressed; this
spec does not reweight anything. It asks the prior question — does today's
score, or any factor inside it, rank trades by expectancy at all — and
answers it once, on the live book and on TRAIN, side by side.

Three gaps block that answer today:

1. **The factor points are only text.** The trade record stores
   `confidence_breakdown` as `{factor: "… (+N)"}`
   (`swingbot/core/tracking/performance.py:614`); the integer each factor
   scored lives only in local variables of the legacy scorer
   (`swingbot/core/scanning/confidence.py:319-594`).
2. **`days_to_earnings` is always null.** `risk_features.build` takes it
   (`swingbot/core/scanning/risk_features.py:48-66`) but `attach_plan_v2`
   never passes it (`swingbot/core/scanning/analyze.py:403-421`).
3. **TRAIN rows carry no confluence or confidence.** The per-trade dump
   (`--trades-jsonl`, `scripts/backtest/run_backtest_range.py:39-46`) only
   covers the named-strategy loop (`:442-486`), and the confluence replay
   that mirrors the live confluence book (`--scenarios`, `:164-189`) emits
   aggregates only.

## What was already seen (disclosed before the verdict is fixed)

- `calibration.score_deciles` (`swingbot/core/analytics/calibration.py:37-58`)
  served at `GET /api/v1/analytics/calibration`
  (`swingbot/admin/api_v1/analytics.py:697-706`) already buckets the live book
  — but by **`quality_score`** (the plan's `quality.py` score), in **fixed
  10-point bands**, with win rate and ExpR and no interval. It is not
  reused: v146 ranks by `confidence_score` (the number beside the level the
  gate reads), uses population **quantile** deciles so every bucket has
  comparable N, and attaches the tercile CI the verdict needs. The two views
  answer different questions; the calibration endpoint is left untouched.
- `scripts/backtest/measure_factor_lift.py` (v32 Task 8) measured per-factor
  *win-rate* lift on TRAIN for the unified registry, to feed a reweight. It
  is not re-run. v146 measures ExpR, on the scorer production actually runs.
- `scripts/reports/cohort_separation_report.py:87-89` slices the journal's
  `risk_features` (exploratory). v146 reads the trades table, not the
  journal, and adds the confidence axis it lacks.
- **The scorer production runs is the legacy one.** `UNIFIED_CONFIDENCE`
  defaults to `false` (`swingbot/config.py:277-282`), and the unified
  registry is down to two zero-point factors (`swingbot/core/scanning/factors.py:443-454`).
  Both paths are stamped (§I1); the study reads whichever wrote the row.
- **The displayed `confidence_score` is level-major.** The legacy scorer
  repositions the quality score inside the final level's band
  (`confidence.py:577-585`, bands at `:157`), so score order is level order
  first, quality order within a level. The deciles below are therefore
  close to "level, then quality" — stated in the results doc, not corrected.
- **The live book is range-restricted.** Only trades at or above the alert
  level were ever paper-traded, which attenuates any score–R slope live;
  the TRAIN replay is not level-gated (§I3). A weaker live slope is the
  expected shape, not by itself a contradiction.

## Scope

In: four instrument changes (I1–I4), one report module plus thin script, one
results document, one Alembic data revision. Out: blocked candidates (v147),
any threshold, floor, weight or sizing change, VALIDATION, the calibration
endpoint, and the Reports page rendering (v150).

## Instrument

### I1 — numeric confidence points

`ConfidenceResult` (`confidence.py:232-236`) gains
`points: dict[str, int]`. The legacy scorer fills it from the locals it
already computes (`pts_distance`, `pts_stop`, `pts_regime`, `pts_adx`,
`pts_macd`, `pts_rsi`, `pts_squeeze`, `pts_candle`, and the negative
`-pts_tight_penalty` under `"Tight stop penalty"`), keyed by the same
strings as `breakdown`. The unified path fills it from each
`FactorResult.points` (`factors.py:28-32`): `run_factors` (`:62-73`) returns
a third element, the `{name: points}` map, and its two callers
(`confidence.py:627`, `measure_factor_lift.py:207`) and
`tests/scanning/test_factors.py` adopt the new shape.

Keys that are not scored factors — `Strategies confirmed (base level)`,
`Quality score`, `Track record (expectancy)`, `Level adjustment`,
`Confirming methods` — never appear in `points`.

**Neutral fallbacks stay visible.** The legacy scorer awards points for a
missing input (`regime unavailable (+7)`, `not evaluated … (+7)` / `(+5)`;
`confidence.py:388, 415, 418, 451, 463, 487`). `points` records the integer
awarded, so the sum still reconciles with the quality score. A second map,
`confidence_unevaluated: [factor, …]`, lists the factors whose line was a
fallback, so the per-factor delta (§Study) never counts "no data" as a
positive reading.

Written next to `confidence_breakdown` by `log_trade`
(`performance.py:565-635`) from its two confluence callers
(`swingbot/core/scanning/scan_run.py:980`, `short_run.py:183`), as
`confidence_points=conf.points`, `confidence_unevaluated=…`. Plans:
`TradePlanV2` (`swingbot/core/planning/plan_types.py:22`) has no
`confidence_breakdown`, only `confidence_level` (`:99`); it gains
`confidence_points: dict | None = None` and the unevaluated list, set where
`confidence_level` is set, so v151 can read them off a plan. Strategy-path
trades (`swingbot/core/scanning/strategy_pass.py:130-137`) and
plan-manager fills (`swingbot/core/planning/plan_manager.py:589-603`) carry
no score today and write `null`.

**Backfill, once, by revision** (`docs/claude/schema-evolution.md`):
`swingbot/core/db/migrations/versions/v146_001_confidence_points.py`,
`down_revision` the head at implementation time (`v116_002` at writing). For
every `trades` row whose `doc->'confidence_breakdown'` is an object, it
parses each line's trailing `(+N)` (or `-> -N quality pts` for the
penalty), skips the non-factor keys above, and writes
`confidence_points` and `confidence_unevaluated` into `doc`. A line that
matches neither form is left out and counted; the revision logs per-key
counts of parsed / skipped / unparsed. `downgrade()` drops both fields with
`drop_doc_field` (`swingbot/core/db/doc_fields.py:59`). Plans are not
backfilled (no source text). No reader ever parses the text again.

### I2 — `days_to_earnings` populated

`attach_plan_v2` passes
`days_to_earnings=earnings_calendar.sessions_to_reaction(ticker, asof, source=LiveSource())`
(`swingbot/core/market/earnings_calendar.py:96-99, 116-118`), `asof` the ET
session date of the decision bar. The unit is **NYSE sessions to the next
earnings reaction session** — the calendar's own unit, the one v82's
exposure rule used; the field keeps its name and the comment at
`risk_features.py:63-65` states the unit. `LiveSource` reads the 6-hour
cached `events.get_earnings_datetimes` (`swingbot/core/market/events.py:184`);
a failed or empty fetch, a fund, or any exception yields `None`, never a
blocked plan. No-lookahead: live, the as-of answer *is* today's calendar.
Historical rows stay `None`; nothing is backfilled.

### I3 — TRAIN per-trade rows for the confluence replay

`--trades-jsonl` becomes valid with `--scenarios`. `_replay_ticker`
(`swingbot/core/backtesting/backtest_scenarios.py:192-217`) returns, beside
each `ExitResult` (`swingbot/core/planning/exit_sim.py:61-68`), a row with
`ticker`, `horizon_key`, `signal_date`, `direction`, `entry`, `stop_loss`,
`outcome`, `r_total`, the plan's `entry_context`, and three new fields
computed on the replay's `window` (`df.iloc[:i+1]`):

- `confluence_count` — the `n_confl` already computed at `:145`;
- `confidence_score`, `confidence_points`, `confidence_unevaluated` —
  `score_confidence` called exactly as live (`analyze.py:953-958`) with
  `regime_trend` from `get_market_regime` (`swingbot/core/scanning/regime.py:88`)
  on SPY sliced to the signal bar, `track_record=None` (the live book is
  not as-of; the legacy path then makes no expectancy adjustment).

`run_scenario_mode` today builds no as-of map, so `entry_context.rs_pctile`
and `regime2_state` would be empty; it gains the same `_build_asof_map`
call (`run_backtest_range.py:49`) the strategy loop uses. The replay is
not level-gated, matching how it runs today. The named-strategy rows
(`BacktestTrade`, `swingbot/core/backtesting/backtest.py:94-108`) are
untouched: live strategy trades carry no score, so a score there would
compare to nothing.

### I4 — two analytics dimensions

`DIMENSIONS` / `_EXTRACTORS` (`swingbot/core/analytics/aggregate.py:107-123`)
gain `confluence` = `str(len(t["target_sources"]))` (every trade record
writes the list, `performance.py:619`; an empty list reads `"0"`) and
`rs_quintile` from `entry_context.rs_pctile` (`Q1` … `Q5` at 20-point
cuts, `unknown` when absent). The endpoint
(`swingbot/admin/api_v1/analytics.py:398-423`) validates against
`DIMENSIONS` and serves them unchanged; the dropdown is a hard-coded list
(`frontend/src/app/stores/analytics.store.ts:275-286`, pinned by
`analytics.store.spec.ts:738-741`), so two entries — "Confluence" and
"RS quintile" — are added there.

## Study

`swingbot/core/analytics/expectancy_attribution.py` is the module; it is
pure apart from one loader and one writer.
`scripts/reports/expectancy_attribution.py` is a thin wrapper (argument
parsing, call, print).

**Populations, never pooled.**

| | Live | TRAIN |
|---|---|---|
| Source | closed trades from Postgres (`TradeLog`), both ledgers | `--scenarios --train --trades-jsonl` rows |
| Confidence analyses | rows with non-null `confidence_score` | every row |
| R | `metrics.r_multiple` (`swingbot/core/analytics/metrics.py:173`) | `r_total` |

VALIDATION is never read.

**Per population, one N / WR / ExpR row per bucket of:**
confidence decile (population quantiles of `confidence_score`, ties broken
by rank), confluence count, `regime2_state`, RS quintile, and earnings
bucket (`0-5`, `6-10`, `11-20`, `>20` sessions, `none`, `unknown`). Live
earnings comes from `risk_features.days_to_earnings` and is `unknown` for
every trade before I2 ships. TRAIN earnings is computed by the study with
`sessions_to_reaction(…, source=CsvSource())` as of each signal date (the
v82 calendar; actual report dates, which the results doc notes as a mild
optimism the v82 row also accepted).

**Per-factor ExpR delta.** For each factor key: ExpR of rows where it
scored > 0, minus ExpR where it scored 0, excluding rows where it is in
`confidence_unevaluated`. Live history before I1 comes from the backfill.

**Monotonicity.** Spearman ρ(`confidence_score`, R) and top-minus-bottom
tercile ExpR, with a 95% bootstrap CI — 10,000 resamples clustered by
entry ISO week (the Stage −2 convention: same-week trades are not
independent), fixed seed recorded in the output.

**Buckets with N < 30** are shown greyed and enter no verdict.
`MIN_CELL_N` (20, `aggregate.py:22`) is untouched; 30 is the
methodology's TRAIN floor.

## The verdict (pre-registered here)

Computed once, at the run the plan schedules, and recorded in the results
document. On the top-minus-bottom tercile ExpR CI:

- **PREDICTIVE** — lower bound > 0 in **both** populations.
- **WEAK** — lower bound > 0 in exactly one.
- **NOT PREDICTIVE** — otherwise. A CI wholly below zero is reported as
  "inverted" inside this verdict, not as a fourth one.

A tercile whose N < 30 makes its population's clause fail. No threshold is
chosen from these tables. Later runs (the v150 page, a growing book) are
descriptive and never revise this verdict; a new verdict needs a new spec.

**What each verdict licenses.** PREDICTIVE licenses one Stage −2 screen for
a confidence floor *or* confidence-weighted sizing — nothing ships from it
directly. Any bucket that looks bad (a regime, an RS quintile, an earnings
bucket, a factor with negative delta) becomes a **screen candidate**, never
a filter. WEAK or NOT PREDICTIVE closes "raise the confidence floor" as a
measured no; the bucket candidates stand on their own.

## Output

- `docs/superpowers/results/<date>-v146-expectancy-attribution.md` — both
  populations side by side, verdict on top, looks-count and the caveats above.
- `data/reports/expectancy-attribution.json` — the module's latest result,
  written on every run (`data/` is mounted into both the bot and admin
  containers; the writer creates `data/reports/`). The module exposes
  `load_latest() -> dict | None`, returning a JSON-serialisable dict, so
  v150 imports it rather than re-running the study. Shape:
  `{generated_at, verdict, seed, populations: {live: {...}, train: {...}}}`,
  each population carrying `buckets`, `factors`, `monotonicity`, with a
  `thin: true` flag on every N < 30 bucket. The name used everywhere it is
  shown is **"Expectancy attribution"** — the Analytics workspace's existing
  "Attribution" tab (`frontend/src/app/workspaces/analytics/tabs/attribution.ts`,
  v94) is a different view.

`v146` joins `EXEMPT` in `tests/backtesting/test_preregistration_ledger_file.py:35`
if the plan adds a closed-table row to `backtest-methodology.md` (the v143
precedent: a read-only diagnostic, no budget, no ledger row).

## Testing

- **I1:** for every factor key either scorer can emit with points, a
  scenario matrix asserts `points[key]` equals the integer the scorer
  added, and that the migration's parser, run on that `breakdown`,
  returns the same `points` and `unevaluated` — so the parse provably
  covers every key `confidence.py` emits, fallbacks and the negative
  penalty included. The revision runs up and down on a fixture DB
  (`tests/db/test_migrations.py` single-head rule holds); an unparseable
  line is counted, not fatal.
- **I2:** with a stub `EarningsSource`, the stamped value equals
  `sessions_to_reaction` as of the decision bar; a raising source stamps
  `None` and the plan still posts.
- **I3:** truncating the frame after the signal bar changes none of the new
  fields (no-lookahead); `--trades-jsonl` with `--scenarios` writes one row
  per closed `ExitResult`.
- **I4:** extractor values on hand-built trades (missing `entry_context`,
  empty `target_sources`, quintile edges); the endpoint accepts both dims;
  the frontend spec lists them.
- **Study:** deciles, tercile CI and verdict on synthetic populations
  built to be predictive, flat and inverted; thin buckets excluded;
  `load_latest()` round-trips the written file.

The TRAIN replay runs once through `backtest-runner`, with flushed
per-ticker progress and a percent file deleted on completion.

## Parallelisation

- **Group 1 (parallel):** I2 (`analyze.py`, `risk_features.py` comment), I4
  (`aggregate.py`, `analytics.store.ts` + spec) — disjoint files, no shared
  symbol.
- **Sequential:** I1 before I3 (I3 writes `conf.points`, which I1
  introduces) and before the revision (it reuses I1's parser). I3 before
  the TRAIN replay; the replay and the live read before the study run;
  the study module can be written alongside Group 1 against fixtures, but
  its run waits for I1–I4. Results document last; full suite once, as the
  final task.

## What follows

- **v147 — gate counterfactual.** The blocked-candidate half this spec
  leaves out: what the trades the gates refused would have made.
- **v150 — Reports workspace.** Renders this report from `load_latest()`
  under the name "Expectancy attribution".
- **v151 — Why panel.** Consumes `confidence_points` (and the unevaluated
  list) to show per-factor points numerically instead of parsing text.
- On **PREDICTIVE**, a Stage −2 screen spec for a confidence floor or
  confidence-weighted sizing; on any verdict, one screen spec per bad
  bucket the partner chooses to pursue.
