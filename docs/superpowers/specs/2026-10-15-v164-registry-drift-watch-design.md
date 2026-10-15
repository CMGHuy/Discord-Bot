# v164 — Registry drift watch: live ExpR vs out-of-sample, pushed weekly

**Version:** ui 1.24.0 · bot 2.5.2 (at writing)
**Bump:** bot minor; ui minor — a new Sunday retrospective part and a new ops-channel post every user of the channel sees; new columns and rows on the Analytics drift table.
**Edge:** none (integrity) — report-only. It changes no signal, threshold, badge or plan; it surfaces when the edge measured live falls short of the edge the registry was stamped with, which is what protects every pooled `ExpR` figure from silently going stale.
**Screen:** exempt (integrity)
**Panel:** quant-researcher, quant-engineer
**Status:** spec written 2026-10-15 from a brainstorm with the partner (pipeline sweep, item A1; choices: push + ExpR rule + WEAK coverage, bootstrap confidence bound, own source/strategy/horizon matching, weekly digest + instant flag).

## Why

`swingbot/core/analytics/calibration.py:badge_drift` already flags decay, but:

1. **It watches 2 of 22 registry rows.** Only `VALIDATED` rows (MACD, Volume Profile as of 2026-10-15). The 20 `WEAK` rows still emit plans (never suppressed, by user requirement) and nothing watches whether they get worse.
2. **Win rate only.** The objective is `ExpR` (CLAUDE.md "Prioritise expectancy and win rate"); win rate is a constraint.
3. **Pull only.** The flag lives in the admin Analytics `drift` block and `insights.py` text; nobody is told.
4. **Overlapping attribution.** A trade counts for every strategy family among its `target_sources`/`stop_sources`, so one trade can feed several rows and `live_n` is inflated.

## Facts the design rests on (verified 2026-10-15)

- `validation_registry.json` is a list of 22 rows keyed by `(source, strategy, horizon)`: 11 `confluence / ALL / <horizon>` rows (horizons `2w,4w,2m..9m` plus pooled `None`), 11 `strategy / <name> / None` rows. Fields: `status`, `n`, `win_rate`, `expectancy_r`, `window`, `run_date`.
- `strategy_types.HORIZONS` = `1w,2w,4w,2m..9m`. **`1w` has no confluence registry row.**
- Every live confluence trade carries `strategy = "S/R Confluence"` (`performance.primary_strategy_label` docstring); the trade's `source` field is `"strategy" | "confluence" | None` (`performance.log_trade`), horizon is `horizon_key`.
- The analytics snapshot (`snapshots.build_snapshot`) receives the main-ledger `closed` and the separate `weak_closed` ledger; `badge_drift` sees only `closed`.
- The Sunday retrospective (`tracking/retrospective.py`, Parts 8–10) is where weekly sections already live; `commands/scanning/loops.py:_ops_channel()` is the ops destination (falls back to the trades channel).
- Cohorts (`tracking/origin.py`, `ORIGINS = (NEXT_SESSION,)`) are never folded into other figures (v144).
- `metrics.r_multiple(trade)` is the single definition of realized R.

## D1 — Matching (pure, `swingbot/core/analytics/calibration.py`)

New `match_registry_rows(trades, registry_entries) -> dict[row_key, list[trade]]` plus an `unmatched` list.

- Input: regular-origin closed trades from **both** ledgers (`closed + weak_closed`); cohort trades (`not is_regular`) are excluded.
- A trade's key is `(source, strategy', horizon_key)` where `strategy' = "ALL"` when `source == "confluence"`, else the trade's `strategy`.
- A trade counts toward the exact-horizon row **and** the pooled row (`horizon None`) of its `(source, strategy')`. Strategy rows are pooled-only, so a strategy trade counts once. This is aggregation at two levels, never a trade counted for two strategies.
- A trade matching no row (a `1w` confluence trade still feeds the pooled `ALL/None` row; a trade with `source None` or an unknown strategy feeds nothing) is appended to `unmatched` when it feeds no row at all. The count is reported, never silently dropped.

## D2 — The ExpR decay rule (PRE-REGISTERED)

Written here before any live ExpR per row has been looked at for this purpose. It must never be loosened or tightened after observing what it flags; a change is a new, documented decision made before looking (same discipline as `badge_drift`'s docstring).

- **Constants:** `EXPR_DRIFT_LIVE_N_FLOOR = 20`, `EXPR_DRIFT_CONFIDENCE = 0.90` (one-sided), `EXPR_DRIFT_RESAMPLES = 10_000`, `EXPR_DRIFT_SEED = 164`.
- **Bound:** the 90th percentile of the bootstrap distribution of the mean of the row's live R multiples (resample with replacement, `numpy.random.default_rng(EXPR_DRIFT_SEED)`, percentile method). Trades whose `r_multiple` is `None` are excluded from both `live_n` and the bound.
- **Trips when:** `live_n >= 20` **and** `bound_upper < row.expectancy_r`.
- Applies identically to `VALIDATED` and `WEAK` rows.
- Deterministic: same trades, same order-independent result (sort R values before resampling).

Output row: `source, strategy, horizon, status, oos_n, oos_wr, oos_expr, oos_run_date, live_n, live_wr, live_expr, expr_bound_upper, expr_alert`.

**`badge_drift` is untouched** — its rule, its family matching, its callers. The digest shows its `drift_alert` next to the new `expr_alert`, each labelled with its own rule. A golden test pins `badge_drift`'s output.

## D3 — Delivery

- **Weekly digest:** new Part 11 in `build_daily_retrospective`, Sundays only, inside the existing `_section(...)` guard so a failure skips the part and is listed like the others. A compact table of all 22 rows (row, status, OOS N/WR/ExpR, live N/WR/ExpR, bound, WR flag, ExpR flag), rows with any flag first; last line `unmatched: <n> trades`. It must fit Discord's 2000-character message limit: if the retrospective's message list already chunks long parts, reuse that; if not (unverified at writing — the plan brief checks), Part 11 splits itself into several entries of `messages`.
- **Instant flag:** on the weekday recap run, compute D2 twice — on trades with `closed_at` before today's session date, and on all trades. A row whose `expr_alert` is false in the first and true in the second gets one ops-channel post (`_ops_channel()`): row, live N/ExpR, bound, OOS ExpR, rule text. Stateless — no table, no schema change. A day the bot is down can miss an instant flag; the Sunday digest still shows it.
- Never writes `validation_registry.json`, never changes a badge, never suppresses or alters a plan.

## D4 — Admin surface

- `snapshots.build_snapshot` adds `calibration.expr_drift` (D1+D2 rows) beside the unchanged `drift`.
- `/api/v1/analytics/calibration` returns `expr_drift`; the Analytics workspace drift table gains the ExpR columns and the WEAK rows from `expr_drift`. The Discord digest and the UI read the same function, so they cannot disagree.

## Complexity

Every new function < 15 (`radon cc`). The bootstrap, the matcher and the row builder are separate functions; the digest formatter is table-driven.

## Testing

All local, free (`testrun.py file`):

- Matcher: confluence trade → horizon row + pooled row; strategy trade → pooled row only; `1w` confluence → pooled only; `source None` → `unmatched`; cohort trade excluded; weak-ledger trade included.
- Bootstrap: fixed seed gives an identical bound across runs and across input order.
- Rule boundaries: `live_n` 19 vs 20; bound just above vs just below OOS ExpR; `None` R excluded from N.
- Instant flag: fires once when a row newly trips; silent when it was already tripped yesterday; silent when it clears.
- `badge_drift` golden: output unchanged for a fixture book.
- Retrospective: Part 11 present on Sunday, absent Mon–Sat; a raising matcher lands in `failed_sections`, not an exception.
- Frontend: analytics store/column spec for the new fields.

## Parallelisation

- **Group 1 (sequential):** D1 → D2. The rule consumes the matcher's buckets.
- **Group 2 (parallel after Group 1):** D3 digest/instant flag and D4 snapshot/API/UI both consume D2's rows and touch disjoint files (`tracking/retrospective.py`, `commands/scanning/` vs `analytics/snapshots.py`, `admin/api_v1/analytics.py`, `frontend/`).
- **Final:** one full-suite run.

## Out of scope

- Retuning the WR rule or its attribution.
- Any automatic re-badging or registry regeneration (only `--emit-registry` does that).
- A2 (live/replay parity job) — its own spec.
