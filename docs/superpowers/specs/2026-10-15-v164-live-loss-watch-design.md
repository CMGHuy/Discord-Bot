# v164 — Live loss watch: confluence ExpR below zero, with confidence, pushed weekly

**Version:** ui 1.24.0 · bot 2.5.2 (at writing)
**Bump:** bot minor; ui minor — a new Sunday retrospective part and a new ops-channel post every user of the channel sees; new rows and columns on the Analytics drift view.
**Edge:** none (integrity) — report-only. It changes no signal, threshold, badge or plan; it tells the partner when a live confluence population is losing money with confidence, which is what keeps every pooled `ExpR` claim honest.
**Screen:** exempt (integrity)
**Panel:** quant-researcher, quant-engineer
**Status:** spec written 2026-10-15 from a brainstorm with the partner (pipeline sweep, item A1); panel review applied the same day, after which the partner chose **zero, not the registry,** as the baseline (see `## Panel review`); amended from the plan brief (`.superpowers/briefs/2026-10-15-v164-live-loss-watch.md`) and the partner's UI-host choice.

## Why

`swingbot/core/analytics/calibration.py:badge_drift` flags win-rate decay against the registry, but it watches only the 2 `VALIDATED` rows, uses win rate rather than `ExpR`, is pull-only (admin Analytics `drift` block, `insights.py`), and counts one trade for every strategy family among its sources.

The panel showed that comparing live R against the registry's `expectancy_r` is not apples to apples **today**: rows carry no exit model, scale-out or friction provenance (`scripts/backtest/run_backtest_range.py:439-444`), `--emit-registry` defaults to the v1 exit model with frictions deducted (`:490`, `config.py:843-855`) while live R is v2 blended R without frictions (`metrics.py:200-212`), 15 of 22 rows predate v31's R:R change, three rows are TRAIN-window figures, and registry `n`/WR exclude scratches and timeouts. A "below the registry" flag could not tell decay from arithmetic.

So the rule compares live ExpR against **zero**, a baseline that needs no provenance: "this population is losing money, with confidence". Registry figures appear in the digest as **labelled context only**. Re-stamping the registry with provenance (so a live-vs-OOS rule becomes valid) is a separate, later spec.

## Facts the design rests on (verified 2026-10-15)

- `validation_registry.json`: 22 rows keyed `(source, strategy, horizon)` — 11 `confluence / ALL / <horizon>` rows (`2w,4w,2m..9m`, pooled `None`), all `WEAK` with negative `expectancy_r`; 11 `strategy / <name> / None` rows.
- `STRATEGY_ALERTS_MODE` defaults to `off` (`config.py:1041-1043`; `known-traps.md`), so the weak ledger and the 11 `strategy` rows sit near live N 0. **The rule can only ever trip on confluence rows in the current configuration.** Strategy rows still appear in the digest, with their N, so that changes visibly if the mode is switched on.
- `strategy_types.HORIZONS` = `1w,2w,4w,2m..9m`; `1w` has no confluence registry row.
- Trade fields: `source` (`"strategy" | "confluence" | None`) exists only since `log_trade` gained it (`performance.py:612,646`), `origin` since v144 (`:648`; absent on older trades, `origin.is_regular` handles that), `horizon_key`, `closed_at` as UTC ISO (`:801,982`). Confluence plans built through `builders.py:687` carry the real primary strategy in `strategy`; older paths carry `"S/R Confluence"`. The matcher keys confluence trades on `source`, never on `strategy`, so both are fine.
- `snapshots.refresh_snapshot` selects status in `("win","loss","closed")` (`snapshots.py:120`) and splits into `closed`/`weak_closed` via `ledger.split_by_ledger`; `build_snapshot` takes them as separate arguments.
- `backtesting/instrument/stats.py:week_cluster_bootstrap(baseline, component, statistic, *, n_resamples, seed=WEEK_BOOTSTRAP_SEED)` resamples ISO weeks of `entry_date` (read with `getattr`), drops undefined draws.
- `swingbot/core/db/repositories/scheduled.py:scheduled_repo()` offers `fired_on(job)` / `mark(job, date_iso)`; both columns are `sa.Text NOT NULL`, so the literal `"cleared"` needs no migration.
- `tracking/retrospective.py:build_daily_retrospective(all_trades, today=None)` has Sunday-only Parts 8–9 (Part 10 runs daily) inside `_section(...)`, buckets days with `_berlin_date`, and accepts a `today` override (`!recap <date>`, `:395`). Its caller `recap._post_retrospective` loads **main-ledger trades only**. Long tables go through `_emit_table` (≤1500 chars per message).

## D1 — Population and matching (pure, `swingbot/core/analytics/calibration.py`)

New `match_live_rows(trades, registry_entries) -> MatchResult` (buckets per row key, plus counts).

- **Population (pre-registered):** trades with `status in ("win","loss","closed")` from **both** ledgers, `origin.is_regular`, and **`opened_at` on or after `EXPR_WATCH_START = 2026-10-16`** (the day after this spec's commit; Berlin date of `opened_at`, computed with `core.market.session.BERLIN_TZ` — `calibration.py` must not import `retrospective.py`, which imports it). Manual closes (`closed`) are **included** — they are real outcomes of the live book — and counted separately in the digest.
- **Key:** `(source, strategy', horizon_key)`, `strategy' = "ALL"` when `source == "confluence"`.
- A trade counts toward its exact-horizon row and the pooled (`horizon None`) row of its `(source, strategy')`. Two aggregation levels, never two strategies.
- **Counted, never dropped:** `no_source` (no `source` key), `unknown_strategy` (a `source` with no matching row), `no_r` (`metrics.r_multiple` is `None`), `manual_close`. A `1w` confluence trade feeds only the pooled row and is not "unmatched".

## D2 — The loss rule (PRE-REGISTERED)

Fixed here, before any trade it will judge exists (D1's start date is after this commit). Never loosened or tightened after observing what it flags; a change is a new spec written before looking.

- **Constants:** `EXPR_WATCH_LIVE_N_FLOOR = 20`, `EXPR_WATCH_CONFIDENCE = 0.90` (one-sided), `EXPR_WATCH_RESAMPLES = 10_000`, seed `stats.WEEK_BOOTSTRAP_SEED`.
- **Statistic:** mean of `metrics.r_multiple` as written (scale-out R is rounded to 2 dp there and single-exit R is not; used unchanged, pinned by a golden fixture with legs).
- **Bound:** `week_cluster_bootstrap(live_trades, (), mean_r_of_first_arm, n_resamples=EXPR_WATCH_RESAMPLES)` via a thin adapter object exposing `entry_date` (the Berlin-date ISO string of `opened_at`; the helper reads it with `getattr`, so plain dicts cannot be passed); an empty draw returns `None` from the statistic, and an empty draws array yields no bound (row cannot trip); `bound_upper` = 90th percentile of the draws. Week clustering covers same-week and same-setup-across-horizons correlation. A fresh generator per row (the helper builds its own), so a row's bound never depends on row order.
- **Trips when:** `live_n >= 20` **and** `bound_upper < 0`.
- **Meaning, stated in every post:** "live ExpR for this row is below zero with ~90% one-sided confidence" — not "the edge decayed versus its backtest".
- **Operating characteristic:** a simulation test pins the per-look false-flag rate for a null population with true mean R 0 at N = 20, 50, 100, using R draws shaped like scale-out outcomes (−1 R mass, BE scratches, a right tail). The measured rates are written into the test as the documented behaviour; the 11 nested confluence rows are correlated, so the digest states "11 correlated looks per week; flags are prompts to investigate, not verdicts" instead of applying a multiplicity correction.

Output row: `source, strategy, horizon, live_n, live_wr, live_expr, bound_upper, alert, registry_status, registry_window_kind, registry_run_date, registry_expr`. The registry columns are labelled **"backtest context — not comparable"**. `registry_window_kind` is `TRAIN` or `VALIDATION`, derived from the row's `window` against `backtest-methodology.md` § windows.

**`badge_drift` is untouched** — rule, matching, callers. A golden test pins its output.

## D3 — Delivery

- **Weekly digest:** new Part 11 of `build_daily_retrospective`, Sundays only, inserted before the `if failed_sections:` block, inside `_section("live loss watch", failed_sections)`. Because the retrospective receives main-ledger trades only, Part 11 loads its own population (both ledgers) through a helper. `build_daily_retrospective` is already radon F: the change there is one `with` plus one call. Rows with an alert first, then confluence rows, then strategy rows; footer lines: the D1 counts and the "11 correlated looks" caveat. 22 rows overflow Discord's 2000-character limit, so **Part 11 always splits itself** through `_emit_table` (tested).
- **Instant flag (latched):** runs from `loops.daily_recap`, right after `recap._post_retrospective()` — never from `!recap` (which always passes a channel override) or a backdated recap. The latch is marked only when `send_guarded` returns a message, since it swallows send failures; `recap` must not import `loops` at module top. For each row with `alert` true and no open latch: one ops-channel post (`loops._ops_channel()`), then `scheduled_repo().mark("live_loss_watch:<row key>", today)`. A latched row never posts again until the latch is cleared. **Clearing happens only in the Sunday digest**, when the row's `bound_upper >= 0`; it marks the job with the literal `"cleared"`. One post per episode, no daily flapping, reruns idempotent. All day boundaries use `_berlin_date`; a trade with a missing or unparseable entry timestamp is counted in `no_entry_date` and excluded.
- Never writes `validation_registry.json`, never changes a badge, never suppresses or alters a plan.

## D4 — Admin surface

- `snapshots.build_snapshot` adds `calibration.live_loss_watch` (D1+D2 rows and counts) beside the unchanged `drift`, computed from `closed + weak_closed`. The plan brief lists every caller of `build_snapshot` and confirms `weak_closed` is passed on each.
- `/api/v1/analytics/calibration` returns `live_loss_watch` (`.get("live_loss_watch", [])`, so a snapshot cached before deploy still serves). `build_snapshot` gains one dict key only (it is radon C).
- **UI (partner's choice):** a new section on the Analytics **Edge** tab renders the live-loss-watch table and, under it, the existing win-rate drift table — `DRIFT_COLUMNS` / `store.drift()` are defined but rendered by no component today. Both use the existing data-table component.
- Existing exact-key tests change with it: `tests/analytics/test_snapshots.py:26`, `tests/admin/test_api_v1_analytics.py:208`.

## Complexity

Every new function < 15 (`radon cc`). Matcher, counts, bound, row builder, latch and digest formatter are separate functions; the formatter is table-driven.

## Testing

All local, free (`testrun.py file`):

- Matcher: confluence → horizon + pooled rows; strategy → pooled only; `1w` → pooled only; trade entered before `EXPR_WATCH_START` excluded; cohort trade excluded; weak-ledger trade included; each count bucket (`no_source`, `unknown_strategy`, `no_r`, `manual_close`, `no_entry_date`).
- Bound: identical across runs and across input order; same-week trades move together (a two-week fixture).
- Rule boundaries: `live_n` 19 vs 20; `bound_upper` just below vs at 0.
- Operating characteristic: the null simulation at N = 20/50/100, rates pinned.
- Latch: posts once; silent on rerun the same day; silent while latched; re-arms only after a Sunday clear; silent for a backdated `!recap`.
- Retrospective: Part 11 on Sunday only; splits under 2000 characters; a raising matcher lands in `failed_sections`.
- `badge_drift` golden unchanged; `r_multiple` golden with legs.
- Frontend: analytics store/column spec for the new table.

## Parallelisation

- **Group 1 (sequential):** D1 → D2 — the rule consumes the matcher's buckets.
- **Group 2 (parallel after Group 1):** D3 (retrospective, loops, latch) and D4 (snapshot, API, frontend) — both consume D2's rows, disjoint files.
- **Final:** one full-suite run.

## Out of scope

- A live-vs-registry rule. It needs the registry re-stamped with exit-model, scale-out, friction and window provenance under v2 arithmetic — a separate spec.
- Retuning `badge_drift` or its attribution; any automatic re-badging.
- A2 (live/replay parity job) — its own spec.

## Panel review

quant-researcher (12 ADVISORY) and quant-engineer (4 BLOCKING, 6 ADVISORY), 2026-10-15, on the first draft (`7052b1df`, live ExpR vs registry `expectancy_r`).

- quant-engineer 1 [BLOCKING] / quant-researcher 1, 2, 10: registry ExpR not comparable to live R (no exit-model/friction provenance, v1 default, pre-v31 rows, TRAIN windows, `n_eval` vs all-trades counting) -- applied: partner chose zero as the baseline; registry columns are labelled context; re-stamp deferred to a separate spec.
- quant-engineer 2 [BLOCKING]: undefined timezone for the day cut -- applied: `_berlin_date` everywhere, missing timestamps counted and excluded.
- quant-engineer 3 [BLOCKING] / quant-researcher 8: stateless instant flag double-posts and flaps; backdated `!recap` posts stale alerts -- applied: `scheduled_repo` latch, Sunday-only clearing, real-today only.
- quant-engineer 4 [BLOCKING]: status filter and `weak_closed` threading unstated -- applied: `win/loss/closed` with manual closes included and counted; brief verifies every `build_snapshot` caller.
- quant-researcher 3: no time floor on the live sample -- applied: `EXPR_WATCH_START = 2026-10-16`, prospective only.
- quant-researcher 4: OOS point estimate treated as a constant, winner's curse -- applied by construction: no registry baseline.
- quant-researcher 5: per-trade bootstrap ignores week clustering -- applied: `stats.week_cluster_bootstrap`.
- quant-researcher 6, quant-engineer 10: multiplicity and repeated looks -- applied: operating-characteristic simulation pinned; digest states the correlated-looks caveat and the meaning of a flag; latch limits repeat posts. No BH correction: the rows are nested and correlated, and a flag is a prompt, not a verdict.
- quant-researcher 7: percentile bootstrap under-covers at small skewed N; floor of 20 unjustified -- applied: the simulation measures the real false-flag rate at N=20 and pins it rather than claiming 90%.
- quant-researcher 9: "22-row coverage" is hollow with `STRATEGY_ALERTS_MODE=off` -- applied: stated in Facts and Why; strategy rows shown with their N.
- quant-researcher 11: blinding only partial -- applied: the start date after this commit makes the rule judge only trades that did not exist when it was written.
- quant-researcher 12, quant-engineer 7: silent `None`-R and pre-`source` exclusions -- applied: every exclusion counted by reason in the digest.
- quant-engineer 5: `r_multiple` rounding asymmetry -- applied: used unchanged, golden fixture with legs.
- quant-engineer 6: determinism beyond the seed -- applied: the existing helper and its named seed; per-row fresh generator; golden test is the guard against a numpy bit-generator change.
- quant-engineer 8: "every confluence trade is S/R Confluence" was wrong for the `builders.py:687` path -- applied: Facts corrected; the matcher keys on `source`.
- quant-engineer 9: chunking is certain, not conditional -- applied: Part 11 always splits, tested.
