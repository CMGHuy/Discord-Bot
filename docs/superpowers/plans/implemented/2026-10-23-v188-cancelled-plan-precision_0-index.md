# v188 — Cancelled-plan precision: Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`. **Never read a part whole**: `grep -n "^### Task V188-3:" -A 260 docs/superpowers/plans/2026-10-23-v188-cancelled-plan-precision_1-backend.md`.

**Bump:** ui patch, bot patch
**Edge:** none (integrity) — measures whether the bot's own cancels were right and changes no cancel rule, risk cap or gate, so the live book's ExpR and win rate are predicted unchanged. The value is a number nobody has today: how often a withdrawn plan would have reached TP1, which any later cancel-rule spec must cite as its starting evidence.
**Screen:** exempt (integrity)
**Spec:** [2026-10-23-v188-cancelled-plan-precision-design.md](../specs/2026-10-23-v188-cancelled-plan-precision-design.md)
**Brief:** `.superpowers/briefs/2026-10-23-v188-cancelled-plan-precision.md`
**Worktree:** implement every task in `.claude/worktrees/2026-10-23-v188-cancelled-plan-precision` (branch of the same name, created in V188-1's first step; `docs/claude/document-lifecycle.md`). The main tree's `frontend/` may carry another session's uncommitted edits (`equity-candles.*` at plan time): never edit, stage or revert them, and never edit the main tree from a task. V188-9 runs the full suites in the worktree and merges to `main`; then `/panel staff-engineer,quant-researcher,financial-advisor` (the spec's `Panel:` line) and `/close-out` run on `main`.

## Goal

The bot withdraws pending trade plans on its own for three reasons:
`risk_cap` (price crossed the trigger but the stop sat further away than the
plan's stop ceiling allows), `invalidated` (price broke the setup before it
triggered) and `expired` (the pending window ran out). At spec time production
held 76 such cancels between 2026-07-27 and 2026-10-22 (49 `risk_cap`, 22
`invalidated`, 5 `expired`). Nobody has measured whether those calls were right.
If a large share of cancelled plans would have reached TP1, the cancel rules are
throwing away winners, and that has to be known before anyone proposes touching
a rule.

Once this ships, the admin UI has a permanent **Cancels** screen. It shows the
share of bot cancels that were right (precision, with its N and a week-clustered
interval) next to the net R they saved (R avoided minus R missed), at the same
prominence. Beside them sits a baseline: the stop-first rate of the filled plans
from the same window, strategy and horizon. Per-reason cards follow, then
right / wrong / unresolved / untriggered counts with their R, splits by origin,
direction and horizon, and a plan table that filters when a card, count or split
is clicked. Every figure under N = 10 is marked. Every headline carries the
caption "Hypothetical replay, before commissions, slippage and tax". `risk_cap`
is labelled as the outcome of a skipped, unaffordable setup and never as a
"wrong cancel". On the bot side, one patch: every future `risk_cap` cancel writes
the price that crossed the trigger onto its `status_history` entry, so later
rows use the recorded entry and not an estimate.

The idea is a replay. For each cancelled plan, the screen takes the daily bars
strictly after the cancel's NYSE trading date, up to the plan's horizon
(`HORIZONS[h]["max_holding_days"]` calendar days). It waits for price to trade
through the trigger, then walks forward bar by bar, checking the stop before TP1
(a same-bar touch of both counts as the stop and is counted as a tie). A stop
first is a right cancel at −1R. A TP1 first is a wrong cancel at the full target
R. Neither inside the window, or a window not yet over, is unresolved and marked
to the last close. No trigger touch in a finished window is
`untriggered_after_cancel`. `risk_cap` is replayed twice, from the trigger and
from the crossing price (recorded, or estimated as the cancel-day open clamped to
the trigger). The verdict logic is a pure module in `swingbot/core/analytics/`
with an injected bar loader, fed from `market_data/` through
`daily_delta.read_daily`, and served by one admin API route that memoises its
result.

It leaves alone every cancel rule, risk cap and gate, the plan manager's
decisions, order placement (paper only, eToro demo only), the backtest caches
and the Postgres schema (no Alembic revision, no new store). It is not a
fill-realism study, and manual cancels never enter a figure.

Success is measured three ways. The replay tests pin long/short mirroring, the
same-bar tie, the window edges, the cancel-day exclusion, the split guard, and
the empty and all-unresolved books. The `risk_cap` persistence test shows that
the events, statuses and stored fields a cancel produces are byte-identical
except for the one new history key. On the replicated production database, the
screen re-derives the reason counts at build time (never carried forward from the
spec) and V188-9 records them.

## Architecture

- **Pure core, three modules, all new, all in `swingbot/core/analytics/`.**
  `cancel_replay.py` is the bar walk: NYSE trading-date conversion, horizon window,
  split guard, one `replay(...)` returning a `Replay`. It re-implements
  `scripts/reports/autopsy/bars.py`'s "strictly after" walk (core may not import
  `scripts/`) and cites it. `cancel_rows.py` turns `TradePlanV2` objects into
  `CancelRow`s: reason bucket, origin, direction, entry model, recorded or
  estimated `risk_cap` entry, stop ceiling, cap-implied size, badge, exclusion.
  `cancel_precision.py` aggregates rows into figures (with
  `week_cluster_bootstrap` intervals over week-collapsed sums, so a draw costs
  about one item per week) and builds the JSON payload.
- **Import directions.** `core/analytics` → `core/planning` (`plan_types`,
  `stop_scope.plan_stop_ceiling`), `core/risk_limits` (`planned_loss_pct`),
  `core/market` (`strategy_types.HORIZONS`, `session.US_MARKET_TZ`),
  `core/backtesting/instrument/stats` (`week_cluster_bootstrap`), `core/tracking/
  origin`. Every one has a precedent in `core/analytics` (`calibration.py`,
  `expectancy_attribution.py`, `cohort.py`, `partials.py`). Nothing in the bot loop
  imports the new modules.
- **Price source: `market_data/` through `daily_delta.read_daily(ticker)`.** The
  bot's `MARKET_DATA_AUTO_REFRESH` keeps it fresh. The admin container mounts it.
  It follows the scan's Alpaca/yfinance basis routing (`daily_alpaca/` versus
  `daily/`), which `data_store.load_normalized` does not. It is split-adjusted
  (yfinance `auto_adjust`, Alpaca adjusted), and the forming bar is never
  persisted (`daily_delta` NO-LOOKAHEAD docstring). Spot metals are skipped (no
  cache). `data/backtest_cache/` is never read: nothing refreshes it on the VM.
- **Route.** `GET /api/v1/cancel-precision` in a new
  `swingbot/admin/api_v1/cancel_precision.py`, registered by appending to the
  import tuple in `swingbot/admin/api_v1/__init__.py:register()`. It runs only in
  the admin process. Its cost is one `PlanStore().records()` scan plus one
  process-cached frame per distinct ticker, and the bootstrap over week sums.
  The result is memoised in-process, keyed by `plans_repo().version()` and the
  UTC date-hour, so a busy screen recomputes at most hourly or on any plan
  write. There is no new store. A failure is a 500 on this one screen. Rollback
  is the normal image rollback, with no data step.
- **Bot patch.** `PlanManager._step_pending` passes `extra={"entry_price": fill}`
  to the `risk_cap` `record_transition` call. That is the only bot-side edit. No
  branch, threshold, event or event detail changes.
- **Screen.** Its own workspace `frontend/src/app/workspaces/cancels/` (modelled on
  `workspaces/calendar/`), route `/cancels`, nav entry under REVIEW, `spa.py`
  `WORKSPACES` gains `"cancels"`. A `CancelsStore` fetches the payload once and
  holds the filter. `CancelsSummary` renders the headline, baseline, cards, counts
  and splits. `CancelsTable` renders the plan table through `sb-data-table`. All
  figures come from the server. The client never recomputes a statistic, it only
  filters rows.

## Global Constraints

- Read-only against production data. No Alembic revision, no new table, no new store. Paper only; eToro stays demo-only.
- **No cancel rule changes.** The only `swingbot/core/planning/` edit in this plan is the `extra=` argument in V188-1. `plan_manager` branches, thresholds, events and event details stay byte-identical.
- The reason allowlist is closed: `REASONS = ("risk_cap", "invalidated", "expired")`. `"manual"` is out of scope (counted, never scored, never in the table). Every other code (for example `never_triggered`, `no_session_data`, linked-trade close reasons) goes to `"other"`, which keeps its own N and stays out of the headline.
- The outcome names are frozen: `right`, `wrong`, `unresolved`, `untriggered_after_cancel`. Never `never_triggered`.
- Precision = right / (right + wrong). All four counts are always shown. R avoided = number of right rows × 1.0R. R missed = the sum of the wrong rows' full target R `|tp1 − entry| / |entry − stop|`, with no partial exit. Net R = R avoided − R missed.
- Small-N marker: `SMALL_N = 10`. Any figure with `n < 10` (n = right + wrong) is marked: cards, splits, the headline, the baseline and the `risk_cap` crossing-price row. N is printed on every figure.
- Interval: the 95% percentile interval (2.5, 97.5) of `week_cluster_bootstrap` at its default 10 000 resamples and seed 42, clustered by the ISO week of the cancel day (the fill day for baseline rows).
- The copy is frozen: `CAPTION = "Hypothetical replay, before commissions, slippage and tax"`, `RISK_CAP_LABEL = "Outcome of the skipped setup, unaffordable at the cap"`, `TP1_NOTE = "A TP1 hit counts the full target R with no partial exit; the bot does not bank winners in full."`, and the `risk_cap` estimate label `"estimated"` versus `"recorded"`.
- The replay starts strictly after the cancel's NYSE trading date. A same-bar stop+TP1 counts as the stop and is a tie. Long and short are mirrored. `SPLIT_GUARD = 0.25` (mirrors `bars.py`).
- Every function stays under cyclomatic complexity 15 (`scripts/dev/complexity_gate.py`). No legacy function gets worse.
- Tests join existing suites only: `tests/analytics/` (suite `edge-analytics`), `tests/admin/` (suite `admin`), `tests/planning/` (its existing suite). No new `tests/` directory. Frontend specs are vitest beside their sources.
- The UI is designed for phone (< 640), tablet (640–1023) and desktop (≥ 1024) together (`docs/claude/ui-design.md`): phone one column, tablet two, desktop the full row. Touch targets are at least 44px on clickable cards, counts and split rows. A table of five rows or fewer on the client shows no pager.
- Per-task verification is the narrow run (`python scripts/dev/testrun.py file <test>`, or `cd frontend && npx ng test --include <spec>`). The full suites run once, in V188-9.
- Before a task's first test run against the database, run `/replicate-prod-db` (CLAUDE.md).
- Do not bump `VERSION.json` in a task: `/close-out` resolves `ui patch, bot patch` and regenerates `version_history.json`.

## Spec clarifications (plan-writer decisions, 2026-10-23)

These fill the gaps the spec left to the builder. They are fixed here before any row is scored.

1. **Window.** `until = cancel_day + timedelta(days=HORIZONS[horizon_key]["max_holding_days"])`. Bars with `cancel_day < day <= until` are walked. The window has `elapsed` when the frame's last bar date is `>= until`. An unknown horizon key excludes the row (`"unknown_horizon"`). This is the single place the rule lives: `cancel_replay.window_end`.
2. **Trading date.** `trading_date(at)` parses the ISO string. An aware value is converted to `America/New_York` (`session.US_MARKET_TZ`), and a naive value is read as UTC first. Then `.date()` is taken.
3. **Touch.** Without a touch of the entry level (`high >= entry` long, `low <= entry` short) the plan is `untriggered_after_cancel` if the window has elapsed, and `unresolved` (r `None`) if not. From the touch bar onward, including the touch bar, each bar checks the stop before TP1.
4. **Mark-to-market.** An `unresolved` row that touched is marked at the close of the last walked bar: `r = (close − entry) / risk` for a long, mirrored for a short. Its R is summed into `unresolved_r` and never enters precision or net R.
5. **`risk_cap` crossing price.** The CANCELLED history entry's `entry_price` gives `entry_source = "recorded"` (written from V188-1 onward). Without it, the entry is `max(cancel-day open, trigger)` for a long or `min(cancel-day open, trigger)` for a short, with `entry_source = "estimated"`. There is no cancel-day bar → excluded `"no_cancel_entry"`. Both `risk_cap` rows apply the touch rule to their own entry level.
6. **Cap-implied size.** `cap_size_pct = 100 × plan_stop_ceiling(plan) / planned_loss_pct(entry, stop)` on `risk_cap` rows (the share of a normal position that keeps the planned loss at the ceiling); `None` on other rows. `stop_ceiling_pct` records the ceiling in force.
7. **Baseline.** Filled plans are those that pass `partials.is_filled`. They are replayed from `trigger_price`, strictly after the first ACTIVE transition's trading date, without a touch requirement (they were already in). They are kept when their fill day lies within `[first cancel_day, last cancel_day]` of the scored cancels and their `(strategy, horizon_key)` pair occurs among them. The baseline's `precision` field is the stop-first rate.
8. **Headline.** `headline.all` pools the trigger-entry rows of all three REASONS. `headline.without_risk_cap` drops `risk_cap`. The `risk_cap` crossing-price rows appear only in `cards.risk_cap_fill`, which the screen always shows beside `cards.risk_cap`.
9. **Rule changes in the window.** `RULE_CHANGES = (("2026-09-28", "v104 structural stops and stop-ceiling scope"), ("2026-10-14", "v139 stored stop ceiling"))`. V188-4 re-checks `git log --merges --grep v183` at build time and adds a v183 row with its merge date only if it has merged. The payload lists only the rows whose date falls inside the scored window.
10. **Data as of.** `data_as_of` is the latest last-bar date among the frames used. `None` when no frame loaded.
11. **Exclusions** (row kept in the table, never scored): `no_bars`, `split_guard`, `bad_levels` (risk ≤ 0, or TP1 not beyond the entry in the trade's direction), `unknown_horizon`, `no_cancel_entry`.

## Contracts

### `swingbot/core/analytics/cancel_replay.py` (V188-2)

```python
OUTCOMES = ("right", "wrong", "unresolved", "untriggered_after_cancel")
SPLIT_GUARD = 0.25

@dataclass(frozen=True)
class Replay:
    outcome: str            # one of OUTCOMES
    r: float | None         # right -1.0; wrong full target R; unresolved MTM or None; untriggered None
    tie: bool               # decided by a same-bar stop+TP1 touch
    touch_day: date | None
    exit_day: date | None
    until: date
    elapsed: bool

def trading_date(at: str) -> date: ...
def window_end(start: date, horizon_key: str) -> date | None: ...
def split_guard_ok(frame: pd.DataFrame, day: date, level: float) -> bool: ...
def last_bar_day(frame: pd.DataFrame) -> date | None: ...
def replay(frame: pd.DataFrame, *, bullish: bool, entry: float, stop: float, tp1: float,
           after: date, until: date, require_touch: bool = True) -> Replay: ...
```
Frames are `read_daily` output: a tz-naive `DatetimeIndex`, plus `Open/High/Low/Close` columns.

### `swingbot/core/analytics/cancel_rows.py` (V188-3)

```python
REASONS = ("risk_cap", "invalidated", "expired")
OTHER = "other"
MANUAL = "manual"
FILLED = "filled"
ENTRY_MODELS = ("trigger", "cancel_fill")
EXCLUSIONS = ("no_bars", "split_guard", "bad_levels", "unknown_horizon", "no_cancel_entry")
Loader = Callable[[str], pd.DataFrame | None]

@dataclass(frozen=True)
class CancelRow:
    plan_id: str
    ticker: str
    strategy: str
    horizon_key: str
    direction: str              # "long" | "short"
    origin: str                 # "regular" | "next_session"
    reason: str                 # REASONS member, OTHER, or FILLED (baseline rows)
    raw_reason: str | None
    cancel_day: date            # fill day for FILLED rows
    entry_model: str            # ENTRY_MODELS member
    entry_source: str | None    # "estimated" | "recorded" on cancel_fill rows, else None
    entry: float | None
    stop: float | None
    tp1: float | None
    badge: str | None
    stop_ceiling_pct: float | None
    cap_size_pct: float | None
    replay: Replay | None
    excluded: str | None        # EXCLUSIONS member or None

    @property
    def entry_date(self) -> str: ...   # cancel_day.isoformat(); the bootstrap's week key

def reason_bucket(raw: str | None) -> str: ...          # REASONS -> itself, "manual" -> MANUAL, else OTHER
def cancel_entry(plan, frame, cancel_day: date) -> tuple[float | None, str | None]: ...
def cancel_rows(plans: list, loader: Loader) -> list[CancelRow]: ...   # CANCELLED, non-manual plans; +1 cancel_fill row per risk_cap
def filled_rows(plans: list, loader: Loader) -> list[CancelRow]: ...   # is_filled plans, reason FILLED
def manual_count(plans: list) -> int: ...
```

### `swingbot/core/analytics/cancel_precision.py` (V188-4)

```python
SMALL_N = 10
CI_PCT = (2.5, 97.5)
CAPTION, RISK_CAP_LABEL, TP1_NOTE   # Global Constraints copy
RULE_CHANGES: tuple[tuple[str, str], ...]

def figure(rows: list[CancelRow], *, with_interval: bool = True) -> dict: ...
def baseline_population(filled: list[CancelRow], scored: list[CancelRow]) -> list[CancelRow]: ...
def precision_payload(plans: list, loader: Loader, *, generated_at: str) -> dict: ...
```

**Figure** (JSON):
`{"n": int, "total": int, "excluded": int, "precision": float|null, "precision_ci": [lo, hi]|null, "r_avoided": float, "r_missed": float, "net_r": float, "net_r_ci": [lo, hi]|null, "counts": {"right": int, "wrong": int, "unresolved": int, "untriggered_after_cancel": int}, "unresolved_r": float, "ties": int, "small_n": bool}`.
`n` = right + wrong. `total` = every row in the group, excluded ones included. `precision` is a 0..1 fraction. R values are rounded to 2 dp and fractions to 4 dp.

**Row** (JSON):
`{"plan_id", "ticker", "strategy", "horizon_key", "direction", "origin", "reason", "raw_reason", "cancel_date", "entry_model", "entry_source", "entry", "stop", "tp1", "badge", "stop_ceiling_pct", "cap_size_pct", "outcome", "r", "tie", "exit_date", "excluded"}`.
`outcome`, `r` and `exit_date` are `null` for an excluded row.

**Payload** (`precision_payload` return value, and the route's 200 body):
```
{"generated_at": str, "data_as_of": str|null, "caption": str, "risk_cap_label": str,
 "tp1_note": str, "small_n_threshold": 10,
 "window": {"first": str|null, "last": str|null},
 "rule_changes": [{"date": str, "label": str}],
 "out_of_scope": {"manual": int},
 "headline": {"all": Figure, "without_risk_cap": Figure},
 "baseline": Figure,
 "cards": {"risk_cap": Figure, "risk_cap_fill": Figure, "invalidated": Figure,
           "expired": Figure, "other": Figure},
 "splits": {"origin": {"regular": Figure, "next_session": Figure},
            "direction": {"long": Figure, "short": Figure},
            "horizon": {<horizon_key>: Figure, ...}},
 "rows": [Row, ...]}
```
`splits` are computed over the headline-`all` population. A split key appears only when it has at least one row. `rows` holds every cancel row (both `risk_cap` entry models, `other`, excluded), newest cancel first. Baseline rows are never in `rows`.

### Route (V188-5)

`GET /api/v1/cancel-precision`, `@require_auth`, no query params (an unknown param → 400 via `ApiError`). The 200 body is the payload. Module-level helpers in `swingbot/admin/api_v1/cancel_precision.py`: `_load_plans() -> list[dict]` (`PlanStore().records()`), `_bar_loader(ticker: str) -> pd.DataFrame | None` (`None` for spot metals, else `daily_delta.read_daily(ticker)`), `_memo_key() -> tuple`, `_MEMO: dict`, `reset_memo() -> None` (for tests).

### Frontend (V188-6..V188-8)

- `frontend/src/app/api/models.ts`: `CancelOutcome`, `CancelFigure`, `CancelPlanRow`, `CancelPrecision` (the payload, field names exactly as above).
- `frontend/src/app/stores/cancels.store.ts`: `CancelsStore` (`providedIn: 'root'`), `load(): Observable<CancelPrecision>` (GET `/api/v1/cancel-precision`), signals `data`, `loading`, `error`, `filter: Signal<CancelFilter>`, methods `pickCard(card: CancelCardKey | null)`, `pickOutcome(o: CancelOutcome | null)`, `pickSplit(s: CancelSplit | null)`, `clearFilter()`, computed `rows: Signal<CancelPlanRow[]>`. Types `CancelCardKey = 'risk_cap' | 'risk_cap_fill' | 'invalidated' | 'expired' | 'other'`, `CancelSplit = { dim: 'origin' | 'direction' | 'horizon'; value: string }`, `CancelFilter = { card: CancelCardKey | null; outcome: CancelOutcome | null; split: CancelSplit | null }`.
- `frontend/src/app/workspaces/cancels/cancels.helpers.ts`: `figureText(f: CancelFigure): string` (`"62% of 37"`, `"— of 0"`), `ciText(ci: [number, number] | null): string`, `rText(r: number | null): string`, `verdictLabel(row: CancelPlanRow): string`, `filterRows(rows: CancelPlanRow[], f: CancelFilter): CancelPlanRow[]`.
- `frontend/src/app/workspaces/cancels/cancels-summary.ts`: `CancelsSummary` (`sb-cancels-summary`), input `data: CancelPrecision`, input `filter: CancelFilter`, outputs `card`, `outcome`, `split`.
- `frontend/src/app/workspaces/cancels/cancels-table.ts`: `CancelsTable` (`sb-cancels-table`), input `rows: CancelPlanRow[]`.
- `frontend/src/app/workspaces/cancels/cancels.ts`: `Cancels` page; `cancels.routes.ts`: `cancelsRoutes`.

## Review Focus

1. **An evening-ET cancel carries a UTC `at` that already reads as the next date.** A cancel at `2026-08-04T01:30:00+00:00` is 2026-08-03 in New York. The replay must start after the 2026-08-03 bar, or it skips a real bar. Pinned in V188-2 (`test_utc_after_midnight_maps_to_the_previous_ny_session`).
2. **A ticker split inside the window.** Adjusted bars against plan levels written in raw prices would score a phantom stop or TP1. The split guard excludes the row as `split_guard`, and the row stays visible. Pinned in V188-2 and V188-3.
3. **A `risk_cap` cancel with no cancel-day bar** (data gap, freshly listed ticker). The crossing-price row is excluded `no_cancel_entry` and not silently replayed from the trigger. Pinned in V188-3.
4. **An empty book, or every row unresolved.** The route returns 200 with `n = 0`, `precision: null`, null intervals, `small_n: true`. The screen shows "— of 0" and the small-N marker, never an error. Pinned in V188-4, V188-5 and V188-7.
5. **A plan written before v139 with no `stop_ceiling_pct`, or a non-strategy plan.** `plan_stop_ceiling` falls back (2% for non-strategy, scope ceiling for strategy), and `cap_size_pct` is still computed and never raises. Pinned in V188-3.

## Parallelisation

| Task | Can run with | Sequential edge (reason) |
|---|---|---|
| V188-1 | V188-2 (after V188-1's worktree step) | first task: creates the worktree; owns `plan_manager.py` |
| V188-2 | V188-1 | after V188-1's worktree step; disjoint file `cancel_replay.py` |
| V188-3 | none | after V188-1 (reads the `entry_price` history key it writes) and V188-2 (consumes `Replay`, `replay`, `trading_date`, `window_end`, `split_guard_ok`) |
| V188-4 | none | after V188-3: consumes `CancelRow`, `cancel_rows`, `filled_rows`, `manual_count` |
| V188-5 | none | after V188-4: the route serves `precision_payload` |
| V188-6 | none | after V188-5: the store consumes the endpoint V188-5 introduces |
| V188-7 | none | after V188-6: consumes `CancelPrecision`, `CancelFilter` and the helpers |
| V188-8 | none | after V188-7: the page composes `CancelsSummary`; shares `CancelsStore` |
| V188-9 | none | after every other task: the single full-suite run, complexity gate, count check and merge |

Effectively sequential after the V188-1 ∥ V188-2 pair: each later task consumes the previous task's symbols or endpoint.

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-10-23-v188-cancelled-plan-precision_1-backend.md` | V188-1..V188-4 | worktree, `risk_cap` entry persistence, pure replay, rows, aggregation and payload |
| 2 | `2026-10-23-v188-cancelled-plan-precision_2-screen.md` | V188-6..V188-9 | API types, store and helpers, summary component, table, page and registration, full-suite verification and merge |
| 3 | `2026-10-23-v188-cancelled-plan-precision_3-route.md` | V188-5 | admin route `GET /api/v1/cancel-precision` (split from part 1 at write time: five tasks at full code exceeded the 1500-line cap) |

## Task ledger

| Id | Title | Part | Model | Files (C create / M modify) | Creates for later tasks |
|---|---|---|---|---|---|
| V188-1 | Worktree; `risk_cap` cancels record their crossing price | 1 | sonnet | M `swingbot/core/planning/plan_manager.py`; C `tests/planning/test_risk_cap_entry_recorded.py` | worktree branch `2026-10-23-v188-cancelled-plan-precision`; CANCELLED `risk_cap` history entry key `"entry_price"` (float) |
| V188-2 | Pure post-cancel replay | 1 | opus | C `swingbot/core/analytics/cancel_replay.py`, `tests/analytics/test_cancel_replay.py` | `OUTCOMES`, `SPLIT_GUARD`, `Replay`, `trading_date`, `window_end`, `split_guard_ok`, `last_bar_day`, `replay` (§ Contracts) |
| V188-3 | Cancelled and filled plans to replay rows | 1 | opus | C `swingbot/core/analytics/cancel_rows.py`, `tests/analytics/test_cancel_rows.py` | `REASONS`, `OTHER`, `MANUAL`, `FILLED`, `ENTRY_MODELS`, `EXCLUSIONS`, `Loader`, `CancelRow`, `reason_bucket`, `cancel_entry`, `cancel_rows`, `filled_rows`, `manual_count` |
| V188-4 | Figures, intervals, baseline and payload | 1 | opus | C `swingbot/core/analytics/cancel_precision.py`, `tests/analytics/test_cancel_precision.py` | `SMALL_N`, `CI_PCT`, `CAPTION`, `RISK_CAP_LABEL`, `TP1_NOTE`, `RULE_CHANGES`, `figure`, `baseline_population`, `precision_payload` → Payload JSON |
| V188-5 | Admin route `GET /api/v1/cancel-precision` | 3 | sonnet | C `swingbot/admin/api_v1/cancel_precision.py`, `tests/admin/test_api_v1_cancel_precision.py`; M `swingbot/admin/api_v1/__init__.py` | endpoint `/api/v1/cancel-precision`; `_load_plans`, `_bar_loader`, `_memo_key`, `_MEMO`, `reset_memo` |
| V188-6 | API types, `CancelsStore` and pure helpers | 2 | sonnet | M `frontend/src/app/api/models.ts`; C `frontend/src/app/stores/cancels.store.ts`, `cancels.store.spec.ts`, `frontend/src/app/workspaces/cancels/cancels.helpers.ts`, `cancels.helpers.spec.ts`, `frontend/src/app/testing/cancel-fixtures.ts` | `CancelOutcome`, `CancelFigure`, `CancelPlanRow`, `CancelPrecision`, `CancelsStore`, `CancelCardKey`, `CancelSplit`, `CancelFilter`, `figureText`, `ciText`, `rText`, `verdictLabel`, `filterRows`, fixture `CANCEL_PAYLOAD`, `EMPTY_CANCEL_PAYLOAD` |
| V188-7 | Summary: headline, baseline, reason cards, counts, splits | 2 | sonnet | C `frontend/src/app/workspaces/cancels/cancels-summary.ts`, `cancels-summary.spec.ts` | `CancelsSummary` (`sb-cancels-summary`, inputs `data`, `filter`, outputs `card`, `outcome`, `split`) |
| V188-8 | Plan table, page, route, nav and SPA registration | 2 | sonnet | C `frontend/src/app/workspaces/cancels/cancels-table.ts`, `cancels-table.spec.ts`, `cancels.ts`, `cancels.spec.ts`, `cancels.routes.ts`; M `frontend/src/app/app.routes.ts`, `frontend/src/app/shell/shell.ts`, `swingbot/admin/spa.py` (+ its existing workspace test if one pins `WORKSPACES`) | `CancelsTable`, `Cancels`, `cancelsRoutes`; route `/cancels`; `WORKSPACES` gains `"cancels"` |
| V188-9 | Full suites, complexity gate, production-replica count check, merge | 2 | sonnet | none (merge commit; `/close-out` bumps ui patch + bot patch and regenerates `version_history.json`) | merged branch on `main`; build-time reason counts recorded in the merge commit body |
