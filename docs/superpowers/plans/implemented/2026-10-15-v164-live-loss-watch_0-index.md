# v164 Live loss watch: confluence ExpR below zero, with confidence, pushed weekly. Implementation Plan, index

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this plan whole**: pull one task with `/task-brief LW3` or `grep -n "^### Task LW3" -A 300 docs/superpowers/plans/2026-10-15-v164-live-loss-watch_*.md`.

**Spec:** [`docs/superpowers/specs/2026-10-15-v164-live-loss-watch-design.md`](../specs/2026-10-15-v164-live-loss-watch-design.md) (all sections; every applied `## Panel review` finding is a requirement)
**Bump:** bot minor; ui minor
**Edge:** none (integrity)
**Screen:** exempt (integrity)

**Goal:** Report, weekly in the Sunday retrospective and instantly (latched) in the ops channel, every registry row whose live population since 2026-10-16 has an `ExpR` below zero with ~90% one-sided week-clustered bootstrap confidence, and show the same table, beside the existing win-rate drift table, on the admin Analytics Edge tab.

**Architecture:** Pure matcher and loss rule live in `swingbot/core/analytics/calibration.py` (`match_live_rows`, `live_expr_bound`, `live_loss_watch`), reusing `backtesting/instrument/stats.week_cluster_bootstrap` through a `LiveTrade` namedtuple adapter that carries the Berlin entry date. A new `swingbot/core/tracking/live_loss_watch.py` owns the both-ledger loader and the `scheduled_jobs` latch; the retrospective gets a Sunday Part 11 (`_live_loss_watch_part`, which also clears latches), and `loops.daily_recap` posts the instant flags after the retrospective. The snapshot gains one `calibration.live_loss_watch` key, the calibration API returns it, and the Angular Edge tab renders it and the never-rendered drift table with `sb-data-table`.

**Tech Stack:** Python 3.11, numpy, pytest via `scripts/dev/testrun.py`, radon; Angular (signals) + vitest for the frontend.

## Progress

Implemented: merged as 774dce63, released bot 2.9.0 / ui 1.27.0. Panel (quant-researcher, quant-engineer) raised only ADVISORY findings; follow-ups: week-floor degeneracy at 1-2 entry weeks, looks-count caveat vs six flag looks per week, Sunday digest runs load_watch on the event loop.

## Where to work

- **Branch and worktree:** `2026-10-15-v164-live-loss-watch`, at `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v164-live-loss-watch` (written `$WT` below). The main tree is `$R` = `E:/Documents/Private/Projects/Discord-Bot`. LW1 Step 0 creates the worktree with the `worktree-lifecycle` skill (reuse it if `git worktree list` already shows it); name `$WT` in every subagent dispatch.
- **Never `cd`** (it breaks the guardrail hooks). Use absolute paths and `git -C $WT`. `python $WT/scripts/dev/testrun.py file tests/...` resolves test paths against `$WT`. Frontend: `npm --prefix $WT/frontend run test -- <spec path>`.
- **This plan file is committed on `main`.** Only the implementation is branched. Each task commits on the branch. After every task, `git -C $R status --short` must show the main tree unchanged by this plan (another session's v162 files may be present there; never touch or stage them).

## Global Constraints

- **Report-only.** Never writes `validation_registry.json`, never changes a badge, never suppresses or alters a plan or a signal.
- **`badge_drift` is untouched** — rule, matching, callers (`calibration.py:83`, `DRIFT_LIVE_N_FLOOR = 20`, `DRIFT_THRESHOLD_POINTS = 10.0`). LW2 pins its output with a golden test.
- **Pre-registered constants, verbatim from the spec, never tuned:** `EXPR_WATCH_START = dt.date(2026, 10, 16)` (Berlin date of `opened_at`, on or after), `EXPR_WATCH_LIVE_N_FLOOR = 20`, `EXPR_WATCH_CONFIDENCE = 0.90` (one-sided), `EXPR_WATCH_RESAMPLES = 10_000`, seed `stats.WEEK_BOOTSTRAP_SEED` (42). **Trips when `live_n >= 20` and `bound_upper < 0`.** `bound_upper` = the 90th percentile of the week-cluster bootstrap draws of the mean R; an empty draws array means no bound and the row cannot trip.
- **Population:** status in `("win", "loss", "closed")`, from **both** ledgers, `origin.is_regular(trade)`, Berlin date of `opened_at` >= `EXPR_WATCH_START`. Manual closes (`closed`) are included and counted.
- **Key:** `(source, strategy', horizon_key)` with `strategy' = "ALL"` when `source == "confluence"`. A trade counts toward its exact-horizon row and the pooled (`horizon None`) row of its `(source, strategy')`. Matched on `source`, never on `strategy`.
- **Counted, never dropped:** `no_source`, `unknown_strategy`, `no_r`, `manual_close`, `no_entry_date` (exact keys, `calibration.WATCH_COUNT_KEYS`). A `1w` confluence trade feeds only the pooled row and is not unmatched.
- **Statistic:** `metrics.r_multiple` as written (legged R rounded to 2 dp, single-exit R not), unchanged.
- **Meaning text, in every post and on the UI:** `live ExpR for this row is below zero with ~90% one-sided confidence — not "the edge decayed versus its backtest"`. Registry columns labelled `backtest context — not comparable`. Digest footer caveat: `11 correlated looks per week; flags are prompts to investigate, not verdicts`. No multiplicity correction.
- **Time:** every day boundary is a Berlin date (`core.market.session.BERLIN_TZ`); `calibration.py` must **not** import `retrospective.py` (cycle: `retrospective.py:29` imports `calibration`).
- **Latch:** job name `live_loss_watch:<source>/<strategy>/<horizon or "pooled">` in `scheduled_jobs` (`swingbot/core/db/repositories/scheduled.py`); latched = `fired_on(job) not in (None, "cleared")`. Marked only when `send_guarded` returns a message. Cleared (literal `"cleared"`) only by the Sunday digest built for the real Berlin today, when the row's `bound_upper >= 0`. No migration (`fired_on` is `sa.Text`).
- **Instant flag runs only from `loops.daily_recap`**, after `recap._post_retrospective()`; never from `!recap` or a backdated recap. `recap.py` gains no import of `loops`.
- **Legacy complexity:** `build_daily_retrospective` (radon F) gains exactly one `with _section(...)` + one call; `build_snapshot` (radon C) gains exactly one dict key. Every new or changed function ends < 15 (`python -m radon cc -s -n C <files>` prints nothing new).
- **No schema change:** `live_loss_watch` is a key inside the JSON snapshot blob; the API serves a pre-deploy cached snapshot via a default.
- **Per-task verification is the narrow run** (`python $WT/scripts/dev/testrun.py file <test>`); one full-suite run as the final task (LW7).
- **Version bump** (bot minor, ui minor) is applied by `/close-out` from the `**Bump:**` header; no task edits `VERSION.json`.

## Deviations from the spec text (controller decisions, binding)

1. **Snapshot value shape.** `calibration.live_loss_watch` is the dict `{"rows": [...], "counts": {...}}` (spec: "D1+D2 rows and counts", one dict key). The API default for a pre-deploy snapshot is therefore `{"rows": [], "counts": {}}`, not `[]`.
2. **Shared loader and latch module.** The both-ledger loader (`load_watch`) and the latch helpers live in a new `swingbot/core/tracking/live_loss_watch.py`, used by both the retrospective Part 11 (clear) and `loops` (flag), so neither imports the other.
3. **Embed kind.** The instant flag reuses `Kind.RETROSPECTIVE` with detail `live loss watch` (no new `Kind`, so no embed-registry change); body carries the meaning text.
4. **Backdated Sunday recap.** Part 11 is shown for any Sunday `today` (it always reports current data); latch clearing runs only when `today` equals the real Berlin date.
5. **Row order:** alert rows first; then confluence rows in `strategy_types.HORIZONS` order with the pooled row last; then strategy rows by name. The same order is served to the UI.
6. **Test homes:** matcher, rule, goldens and simulation in a new `tests/analytics/test_live_loss_watch.py`; loader/latch in `tests/tracking/test_live_loss_watch.py`; Part 11 in `tests/tracking/test_retrospective_live_loss.py`; flag in `tests/commands/test_live_loss_flag.py`. All directories already belong to a suite; no `tests/suites.toml` edit.

## Parallelisation

- **Group 1 (sequential):** LW1 → LW2. LW2 consumes LW1's `MatchResult`/`LiveTrade` and appends to the same files (`calibration.py`, `tests/analytics/test_live_loss_watch.py`).
- **Group 2 (two parallel chains, after LW2):**
  - Chain D3: LW3 → LW4. LW4 consumes LW3's `load_watch`, `is_latched`, `mark_latched`, `clear_latches`.
  - Chain D4: LW5 → LW6. LW6 consumes the `live_loss_watch` key LW5 adds to the calibration API.
  - The chains touch disjoint files (D3: `core/tracking/`, `commands/scanning/`, their tests; D4: `core/analytics/snapshots.py`, `admin/api_v1/analytics.py`, `frontend/`, their tests) and share only LW2's contract, so they may run side by side.
- **Final:** LW7 (full suite) runs last, after all others are committed.

## Task ledger

| Task | Title | Part | Model | Files (C = create, M = modify) | Creates, consumed later |
|---|---|---|---|---|---|
| LW1 | Population matcher: `match_live_rows`, Berlin entry date, count buckets | 1 | sonnet — one module, behaviour fixed by spec D1 | M `swingbot/core/analytics/calibration.py`, C `tests/analytics/test_live_loss_watch.py` | `EXPR_WATCH_START = dt.date(2026, 10, 16)`; `WATCH_COUNT_KEYS = ("no_source", "unknown_strategy", "no_r", "manual_close", "no_entry_date")`; `LiveTrade = namedtuple("LiveTrade", "entry_date r status")` (`entry_date` = Berlin-date ISO `"YYYY-MM-DD"`); `@dataclass(frozen=True) MatchResult(buckets: dict[tuple[str, str, str \| None], list[LiveTrade]], counts: dict[str, int])` (one bucket per registry row key, empty list when unmatched); `row_key(entry: dict) -> tuple[str, str, str \| None]`; `berlin_entry_date(trade: dict) -> str \| None`; `match_live_rows(trades: list[dict], registry_entries: list[dict]) -> MatchResult` |
| LW2 | Loss rule: week-cluster bound, rows, ordering; null operating-characteristic simulation; `badge_drift` and `r_multiple` goldens | 1 | opus — statistical code that feeds the alert, crosses `analytics` and `backtesting` | M `swingbot/core/analytics/calibration.py`, M `tests/analytics/test_live_loss_watch.py` | `EXPR_WATCH_LIVE_N_FLOOR = 20`; `EXPR_WATCH_CONFIDENCE = 0.90`; `EXPR_WATCH_RESAMPLES = 10_000`; `LIVE_LOSS_MEANING: str`; `LIVE_LOSS_LOOKS_CAVEAT: str`; `REGISTRY_CONTEXT_LABEL = "backtest context — not comparable"`; `registry_window_kind(window: str \| None) -> str \| None` (`"TRAIN"`/`"VALIDATION"`/`None`); `live_expr_bound(live: list[LiveTrade], *, n_resamples: int = EXPR_WATCH_RESAMPLES) -> float \| None`; `live_loss_row(entry: dict, live: list[LiveTrade], *, n_resamples: int = EXPR_WATCH_RESAMPLES) -> dict` with exactly the keys `source, strategy, horizon, live_n, live_wr, live_expr, bound_upper, alert, registry_status, registry_window_kind, registry_run_date, registry_expr`; `live_loss_watch(trades: list[dict], registry_entries: list[dict], *, n_resamples: int = EXPR_WATCH_RESAMPLES) -> dict` returning `{"rows": list[dict], "counts": dict[str, int]}` (rows ordered per Deviation 5) |
| LW3 | Loader + latch module; retrospective Part 11 (Sunday digest, always split, clears latches) | 2 | opus — crosses `tracking`, `analytics`, `db`, `backtesting`; touches a radon-F legacy builder | C `swingbot/core/tracking/live_loss_watch.py`, M `swingbot/core/tracking/retrospective.py`, C `tests/tracking/test_live_loss_watch.py`, C `tests/tracking/test_retrospective_live_loss.py` | `live_loss_watch.LATCH_PREFIX = "live_loss_watch:"`; `LATCH_CLEARED = "cleared"`; `latch_job(row: dict) -> str`; `is_latched(row: dict) -> bool`; `mark_latched(row: dict, today: dt.date) -> None`; `clear_latches(rows: list[dict]) -> list[str]`; `load_watch(*, n_resamples: int = calibration.EXPR_WATCH_RESAMPLES) -> dict`; `retrospective._live_loss_watch_part(today: dt.date) -> list[str]`; `retrospective._format_live_loss_watch(watch: dict) -> list[str]` |
| LW4 | Instant latched ops-channel flag from `daily_recap` | 2 | sonnet — one command module plus an embed builder, latch contract given | M `swingbot/commands/scanning/loops.py`, M `swingbot/commands/scanning/notices.py`, C `tests/commands/test_live_loss_flag.py` | `notices.live_loss_flag_embed(row: dict)`; `loops._post_live_loss_flags(today: dt.date) -> int` (posts sent) |
| LW5 | Snapshot key + calibration API field | 3 | sonnet — one dict key and one response field, contract tests updated | M `swingbot/core/analytics/snapshots.py`, M `swingbot/admin/api_v1/analytics.py`, M `tests/analytics/test_snapshots.py`, M `tests/admin/test_api_v1_analytics.py` | snapshot `calibration["live_loss_watch"]` = `calibration.live_loss_watch([*closed, *weak_closed], registry_entries)`; `GET /api/v1/analytics/calibration` adds `"live_loss_watch": {"rows": [...], "counts": {...}}` (default `{"rows": [], "counts": {}}`) |
| LW6 | Frontend: model, store computeds, columns, Edge tab renders live-loss-watch and drift tables | 3 | sonnet — store/columns/tab inside one workspace, shapes fixed by LW5 | M `frontend/src/app/api/models.ts`, M `frontend/src/app/stores/analytics.store.ts`, M `frontend/src/app/workspaces/analytics/analytics.columns.ts`, M `frontend/src/app/workspaces/analytics/tabs/edge.ts`, M `frontend/src/app/stores/analytics.store.spec.ts`, M `frontend/src/app/workspaces/analytics/analytics.columns.spec.ts`, M `frontend/src/app/workspaces/analytics/tabs/edge.spec.ts` | `LiveLossRow`, `LiveLossWatch` (models.ts); `AnalyticsCalibration.live_loss_watch?: LiveLossWatch`; `store.liveLossWatch: Signal<LiveLossRow[]>`; `store.liveLossCounts: Signal<Record<string, number>>`; `LIVE_LOSS_COLUMNS: ColumnDef<LiveLossRow>[]` |
| LW7 | Full suite, once | 3 | haiku — runs one command, no code | — | — |

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `docs/superpowers/plans/2026-10-15-v164-live-loss-watch_1-matcher-rule.md` | LW1..LW2 | D1 matcher and counts, D2 pre-registered loss rule, operating-characteristic simulation, goldens |
| 2 | `docs/superpowers/plans/2026-10-15-v164-live-loss-watch_2-delivery.md` | LW3..LW4 | D3: loader and latch module, Sunday Part 11, instant latched flag |
| 3 | `docs/superpowers/plans/2026-10-15-v164-live-loss-watch_3-admin-suite.md` | LW5..LW7 | D4: snapshot key, API field, Edge tab tables; final full suite |
