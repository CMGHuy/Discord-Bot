# v63 — Analytics: distribution charts, holding-period rebucket, broken-column fixes

Version: ui 1.9.0 · bot 1.4.3
Bump: ui minor (1.9.0 → 1.10.0) · bot patch
Edge: none (integrity)

## What this is

Four bundled changes to the Analytics workspace's "Distributions" and "By
segment" sections, requested and scoped in one brainstorm:

1. A **root-cause fix** for a table-rendering bug that silently blanks the
   group-name column on five tables, "By ticker" among them.
2. A **rebucket** of "By holding period" from calendar-day bands to hour bands,
   converted from a text list to a bar chart.
3. **Two new win-rate bar charts** — by direction, by day of week — plus a
   **third new dimension**, win rate by the R:R ratio a trade was planned at.
4. **Removal** of the "Over time" section (4 line charts: account balance,
   drawdown, rolling returns, cumulative return by strategy) and its dead
   store code.

`Edge: none (integrity)` — this changes what the operator can *see*, not
which trades qualify or how any strategy is scored. Nothing here touches a
gate, a confidence factor, or the alert path.

## 1. The broken-column bug

`DataTable.text()` (`frontend/.../ui/data-table/data-table.ts`) is:

```ts
protected text(column: ColumnDef<T>, row: T): string {
  const value = column.value?.(row);
  return value === null || value === undefined || value === '' ? '—' : String(value);
}
```

There is no fallback to `row[column.key]` — a column with no `value` function
renders `—` for **every** row, unconditionally. Five columns across
`analytics.columns.ts` declare no `value` and are never given a `cell`
template either, so they have never rendered real text:

| Table | Column | Declaration |
|---|---|---|
| By segment (all 8 dimensions — ticker, horizon, direction, dow, month, tier, badge, source) | group name | `breakdownColumns()`'s `{ key: 'key', header: label }` |
| Strategy registry | Strategy | `STRATEGY_COLUMNS`'s `{ key: 'strategy', header: 'Strategy' }` |
| Calibration deciles | Score decile | `DECILE_COLUMNS`'s `{ key: 'decile', header: 'Score decile' }` |
| Tier calibration | Design band | `TIER_COLUMNS`'s `{ key: 'expected_band', header: 'Design band' }` |
| Drift (edge decay) | Strategy | `DRIFT_COLUMNS`'s `{ key: 'strategy', header: 'Strategy' }` |

**Fix:** add the missing `value` function to each (`(r) => r.key`, `(r) =>
r.strategy`, `(r) => r.decile`, `(r) => r.expected_band`, `(r) => r.strategy`),
matching the pattern every other plain-text column in this file and in
`trades.columns.ts` already uses. No template or store change needed — the
row objects already carry the right field, confirmed by reading
`aggregate.py`'s `StatRow` and the corresponding `BreakdownRow`/`StrategyRow`/
`DecileRow`/`TierRow`/`DriftRow` interfaces in `analytics.store.ts`.

Regression coverage: a `data-table.spec.ts` (or `analytics.columns.spec.ts`,
whichever already exists) case per column asserting the rendered cell text
equals the row's field, not `—`.

## 2. Holding-period rebucket

**Current** (`swingbot/core/analytics/metrics.py:_HOLDING_BUCKETS`), calendar
days: `0-2d, 3-7d, 8-30d, 31d+`. Rendered today as a `<dl>` list ("12 · 63.2%"
per bucket), not a chart.

**New**, hour bands with a day-scale overflow bucket:

```python
_HOLDING_BUCKETS = (
    ("0h-2h",  0.0,     2/24),
    ("2h-4h",  2/24,    4/24),
    ("4h-8h",  4/24,    8/24),
    ("8h-24h", 8/24,    1.0),
    ("1d-2d",  1.0,     2.0),
    ("2d+",    2.0,     float("inf")),
)
```

`_holding_days` already returns calendar days as a float — no unit-conversion
code changes, only the bucket table. `holding_period_split()`'s existing
contract (every bucket reported even at `n=0`, `win_rate: null` not `0` for an
empty bucket) is unchanged and still holds.

**Frontend:** the "By holding period" panel changes from a `<dl>` to an
`sb-histogram` bar (win rate 0–100, `max=100`, `referenceLine` = the range's
overall win rate — the same visual contract `decileHistogram` already uses).
Each bar's label carries its sample size, e.g. `"0h-2h (n=12)"`, since the bar
height alone cannot distinguish "empty bucket" from "0% win rate at n=3" —
the exact distinction `holding_period_split`'s own docstring says must not be
conflated.

Existing tests asserting the old bucket names (`tests/analytics/
test_metrics_derived.py`, `tests/admin/test_api_analytics.py`) are updated to
the new set, not merely relaxed — the specific bucket boundaries are the
thing under test.

## 3. Three win-rate distribution charts

All three follow the same shape: an `sb-histogram`, `count` = win rate
(0–100), `max="100"`, `referenceLine` = the applicable overall win rate,
label suffixed `(n=N)`, every category rendered even at `n=0` (no category is
ever silently dropped from the axis).

### 3a. By direction (NEW panel, "By segment" section — all-time)

Source: `snapshot()?.by?.direction`, which already exists
(`aggregate.py`'s `direction` dimension, unchanged). Raw keys are `"bullish"`/
`"bearish"` (confirmed against `direction-arrow.ts`'s existing mapping) —
labelled **Long**/**Short** to match how direction reads everywhere else in
this SPA. Fixed order `[bullish, bearish]` (Long above Short), zero-filled if
one side never traded in the account's history.

### 3b. By day of week (NEW panel, "By segment" section — all-time)

Source: `snapshot()?.by?.dow` (`aggregate.py`'s existing `dow` dimension,
`_DOW_NAMES` Monday–Sunday). The generic breakdown table sorts every
dimension busiest-first (`stats_by`'s own contract) — correct for ticker or
strategy, wrong for a calendar axis. This chart re-sorts client-side into
Monday→Sunday order and zero-fills any day with no closes (a bot that never
closes trades on a Saturday should show an empty Saturday bar, not a missing
one — the same "empty is a measured answer" rule `holding_period_split`
already follows).

Both 3a and 3b are **all-time**, like the "By segment" table they sit beside
— they read `snapshot()`, not the range-scoped `performance()`. Putting them
in the range-scoped "Distributions" section instead would silently mix a
scoped chart with an all-time number, the exact trap `analytics_performance()`'s
own docstring calls out for `win_rate`/`expectancy_r` vs. `derived`.

They sit **alongside**, not instead of, the existing "Group by" dimension
picker — the picker's table still carries n/wins/losses/expectancy/profit
factor/P&L per direction or day, which a single win-rate bar does not. The
picker keeps `direction` and `dow` as options.

### 3c. By planned R:R (NEW dimension + panel, "Distributions" section — range-scoped)

Not the realized R-multiple outcome — bucketing by the *closed* R-multiple is
close to circular (an R > 0 trade is definitionally a win, so that bucket
would read ~100% and say nothing). This buckets by `risk_reward_ratio`, the
ratio the trade was **planned** at, at entry:

```python
_RISK_REWARD_BUCKETS = (
    ("<1.5", 0.0, 1.5),
    ("1.5-2", 1.5, 2.0),
    ("2-3",   2.0, 3.0),
    ("3-4",   3.0, 4.0),
    ("4+",    4.0, float("inf")),
)
```

`1.5` is the account's own `MIN_RISK_REWARD_RATIO` gate default — trades
below it should be rare-to-absent post-gate, and the `<1.5` bucket existing
at all is itself a finding if it is ever non-empty (a trade logged before the
gate existed, or whose effective R:R moved after a scale-out).

New `swingbot/core/analytics/metrics.py` function, `risk_reward_split()`,
same contract as `holding_period_split()`/`exit_reason_split()`: every bucket
reported even at `n=0`, `win_rate: null` (never `0`) for an empty bucket.
Wired into `/api/v1/analytics/performance` (`swingbot/admin/api_v1/
analytics.py`) as a new `"risk_reward_split"` key, scoped to `scoped` (the
same range-filtered trade list every other field in that response already
uses) — so this chart, unlike 3a/3b, respects the date-range control and
belongs in "Distributions" beside "By holding period".

## 4. Remove "Over time"

Deletes the section heading and its 4 panels (Account balance, Drawdown,
Rolling returns, Cumulative return by strategy) from `analytics.ts`'s
template. Nothing else in the codebase reads the backing store code
(confirmed by grep — only this template and each computed's own spec test
reference them), so it is deleted, not left dead:

- `analytics.store.ts`: `equitySeries`, `drawdownSeries`, `benchmarkSeries`,
  `cumulativeByStrategy`, `rollingReturnsChart`, `balanceWithBenchmark`,
  `cumulativeByStrategyChart`, and the now-unused `toSeries()`/`SeriesPoint`
  helpers plus the `LineChartSeries` import.
- `analytics.ts`: the `LineChart`/`LineChartSeries` imports, the
  `drawdownSeriesForChart` computed, `fmtLineValue`, `seriesRange` (all
  confirmed to have no caller outside the deleted section).
- Their spec coverage in `analytics.store.spec.ts` and
  `analytics.snapshot.spec.ts`.

`snapshot()?.equity_curve` / `?.drawdown` themselves are backend fields
serving other consumers (`!stats`, the heatmap) and are **not** touched —
only the frontend computeds built on top of them for this one section.

## Decisions

1. **Fix the bug at the column-declaration level, not the table component.**
   `DataTable.text()`'s "no fallback" behaviour is a deliberate contract (the
   type comment: "`null` renders as an em dash, because a value that has not
   been computed is not zero and not an empty string") — every other column
   in this codebase supplies `value` explicitly. Adding a `row[key]` fallback
   to the component would paper over the next missing `value` instead of
   surfacing it the way this one was found.
2. **Direction/day-of-week stay all-time; only the R:R bucket is
   range-scoped.** Matches the data each is actually built from — no new
   backend work for 3a/3b (`aggregate.py` already produces both), a genuine
   new aggregation for 3c.
3. **The R:R bucket is a new, narrow backend function, not a `DIMENSIONS`
   entry.** `stats_by`'s generic dimensions drop a group entirely when no
   trade falls in it; every other bucketed-split function in `metrics.py`
   (`holding_period_split`, `exit_reason_split`) guarantees the full fixed
   set. `risk_reward_split` follows the second family, deliberately, since a
   `<1.5` or `4+` bucket sitting empty is itself the finding.
4. **Holding-period buckets are relabelled, not additionally kept.** The old
   `0-2d/3-7d/8-30d/31d+` bands are replaced outright; tests asserting the
   old names are updated, not duplicated alongside a legacy set.

## Out of scope

- Removing `direction`/`dow` from the generic "Group by" picker now that
  dedicated charts exist. Section 3b above explains why they still carry
  distinct information (n/wins/losses/expectancy/PF/P&L); revisit only if
  the picker is found to go unused for those two.
- The `tier` entry in the frontend's `BREAKDOWN_DIMENSIONS` list, which no
  longer has a matching backend dimension (`aggregate.py`'s own v32 Task 11
  comment: "tier... retired"). Selecting it silently returns an empty table.
  Real bug, unrelated to this spec's four asks — filed as a follow-up, not
  fixed here.
- Any change to which trades qualify, how confidence is scored, or any gate
  — this spec is reporting-only, per `Edge: none (integrity)` above.

## Parallelisation

- **Group 1 (parallel):** the five broken-column fixes (§1) — one file
  (`analytics.columns.ts`), five independent one-line edits, no shared state
  with anything else here. Safe to do first and alone.
- **Group 2 (parallel):** backend bucket work — `_HOLDING_BUCKETS` rebucket
  (§2) and the new `risk_reward_split()` (§3c) are both isolated additions to
  `metrics.py` plus their own tests; disjoint functions, no shared lines.
- **Sequential:** the `/api/v1/analytics/performance` wiring for
  `risk_reward_split` (§3c) depends on Group 2's `risk_reward_split()`
  existing. The frontend store computeds (§2's histogram mapping, §3a/3b/3c
  new computeds) depend on their respective backend fields existing. The
  template changes (§2's dl→histogram swap, §3's three new panels, §4's
  removal) depend on the store computeds existing, and all touch
  `analytics.ts`'s template in the same file — sequential among themselves.
- **Full-suite verification is the plan's last task**, once, over everything
  above — `scripts/dev/testrun.py full` and `cd frontend && npm test` — per
  this repo's standing convention.
