# v63 — Analytics distribution charts (plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

Version: ui 1.9.0 · bot 1.4.3
Bump: ui minor (1.9.0 → 1.10.0) · bot patch
Edge: none (integrity)

Spec: `docs/superpowers/specs/implemented/2026-08-25-v63-analytics-distribution-charts-design.md`
— read it first; it carries the diagnosis, the field-name research (e.g. why
direction is `bullish`/`bearish` on the wire, not `long`/`short`) and the
reasoning for every decision below. This plan does not repeat it.

**Goal:** Fix five tables whose group/label column silently renders `—`
forever, rebucket "By holding period" from calendar days to hours, add three
new win-rate distribution charts (direction, day of week, planned R:R), and
remove the "Over time" section and its now-dead store code.

**Architecture:** Backend changes are additive (`swingbot/core/analytics/
metrics.py` gets a rebucketed table and one new pure function; `swingbot/
admin/api_v1/analytics.py` wires the new field into an existing response).
Frontend changes are a `ColumnDef` fix, four new/changed `AnalyticsStore`
computeds (all `HistogramBin[]`, the same shape `decileHistogram`/
`monthHistogram` already use), and template-only wiring in `analytics.ts`.
No new UI component — every chart is an existing `sb-histogram`.

**Tech Stack:** Python 3.11 / pytest (backend), Angular 19 signals / Vitest
(frontend), `sb-histogram` (`frontend/src/app/ui/histogram.ts`).

## Global Constraints

1. **TDD, no exceptions** — failing test first, for the stated reason, then
   the minimal fix. This is a bug-fix-plus-feature plan, not a refactor; no
   behaviour changes beyond what each task states.
2. **No `VERSION.json` bump inside these tasks.** The release commit is
   separate.
3. **Per-task verification is the narrow run** — `python scripts/dev/
   testrun.py file <path>` for Python, `cd frontend && npx vitest run
   <path>` for a single spec file. `testrun.py full` and `npm test` each run
   **once**, as the final task.
4. **Every new/changed chart follows the existing `HistogramBin` contract**
   (`{ label: string; count: number }`, `sb-histogram`'s own type) — no new
   chart component.
5. **An empty category is a zero-height bar, never a dropped one.** Every
   bucket/day/direction renders even at `n=0` — the same rule
   `holding_period_split`'s own docstring already states, applied
   consistently to the three new dimensions.

## Parallelisation

- **Group 1 (parallel, independent of everything else):** Task 1 (the five
  broken columns) — one file, `analytics.columns.ts`, untouched by any other
  task here. Do this whenever; it blocks nothing and nothing blocks it.
- **Group 2 (parallel with each other, both in `metrics.py` but disjoint
  functions):** Task 2 (`_HOLDING_BUCKETS` rebucket) and Task 3
  (`risk_reward_split`) — different functions, no shared lines.
- **Sequential from there:** Task 4 (wiring `risk_reward_split` into the API)
  needs Task 3's function to exist. Tasks 5–7 (store computeds) need Tasks
  2–4's fields on the wire. Tasks 8–11 (template) all edit
  `analytics.ts` and must run in that order — each is a distinct region of
  the same file, but two agents editing one file concurrently silently
  clobber each other, so these are one lane regardless of file-region
  independence.
- **Task 12 (full-suite verification) runs last, alone**, after everything
  above has landed.

---

# Phase 1 — The bug fix

### Task 1: Fix the five broken-column value fallbacks

- [ ] **Write the failing test.** New file
  `frontend/src/app/workspaces/analytics/analytics.columns.spec.ts`:

  ```ts
  import { describe, expect, it } from 'vitest';

  import {
    BreakdownRow, DecileRow, DriftRow, StrategyRow, TierRow,
  } from '../../stores/analytics.store';
  import {
    breakdownColumns, DECILE_COLUMNS, DRIFT_COLUMNS, STRATEGY_COLUMNS, TIER_COLUMNS,
  } from './analytics.columns';

  /* Each of these five columns is a plain-text column with no `cell`
   * template. `DataTable.text()` renders `column.value?.(row)` and falls
   * back to nothing else, so a column missing `value` renders `—` for
   * every row, forever -- exactly the bug this file guards against. */

  describe('analytics.columns — group-name and label columns actually render', () => {
    it('breakdownColumns renders the group key, not an em dash', () => {
      const row: BreakdownRow = {
        key: 'AAPL', n: 5, wins: 3, losses: 2, win_rate: 60,
        expectancy_r: 0.2, avg_r: 0.2, profit_factor: 1.4, total_pnl: 210,
      };
      const column = breakdownColumns('Ticker').find((c) => c.key === 'key');
      expect(column?.value?.(row)).toBe('AAPL');
    });

    it('STRATEGY_COLUMNS renders the strategy name', () => {
      const row: StrategyRow = {
        strategy: 'RSI', status: 'VALIDATED', n: 10, win_rate: 55,
        expectancy_r: 0.3, window: 'TRAIN', run_date: null, live_n: 5,
        live_wr: 50, delta_vs_oos: -5, decayed: false,
        evidence_decay: 'fresh', gate_description: null, win_rate_series: [],
      };
      const column = STRATEGY_COLUMNS.find((c) => c.key === 'strategy');
      expect(column?.value?.(row)).toBe('RSI');
    });

    it('DECILE_COLUMNS renders the decile label', () => {
      const row: DecileRow = { decile: 'D3', n: 12, win_rate: 60, expectancy_r: 0.2 };
      const column = DECILE_COLUMNS.find((c) => c.key === 'decile');
      expect(column?.value?.(row)).toBe('D3');
    });

    it('TIER_COLUMNS renders the design band', () => {
      const row: TierRow = {
        tier: 'A', n: 4, win_rate: 70, expectancy_r: 0.4,
        expected_band: '>=80', ok: true,
      };
      const column = TIER_COLUMNS.find((c) => c.key === 'expected_band');
      expect(column?.value?.(row)).toBe('>=80');
    });

    it('DRIFT_COLUMNS renders the strategy name', () => {
      const row: DriftRow = {
        strategy: 'MACD', oos_n: 20, oos_wr: 65, live_n: 8,
        live_wr: 40, delta_wr: -25, drift_alert: true,
      };
      const column = DRIFT_COLUMNS.find((c) => c.key === 'strategy');
      expect(column?.value?.(row)).toBe('MACD');
    });
  });
  ```

- [ ] **Run it, confirm every case fails** with `expect(received).toBe(expected)`
  where `received` is `undefined` (not `'AAPL'`/`'RSI'`/etc.) — that failure
  shape is the bug, not a fixture mistake. `cd frontend && npx vitest run
  src/app/workspaces/analytics/analytics.columns.spec.ts`
- [ ] **Fix all five**, in `frontend/src/app/workspaces/analytics/
  analytics.columns.ts`:
  - `breakdownColumns()`'s first entry: `{ key: 'key', header: label, value: (r) => r.key }`
  - `STRATEGY_COLUMNS`: `{ key: 'strategy', header: 'Strategy', value: (r) => r.strategy }`
  - `DECILE_COLUMNS`: `{ key: 'decile', header: 'Score decile', value: (r) => r.decile }`
  - `TIER_COLUMNS`: `{ key: 'expected_band', header: 'Design band', value: (r) => r.expected_band }`
  - `DRIFT_COLUMNS`: `{ key: 'strategy', header: 'Strategy', value: (r) => r.strategy }`
- [ ] **Run the test again, confirm all five pass.**
- [ ] Commit: `git add frontend/src/app/workspaces/analytics/analytics.columns.ts frontend/src/app/workspaces/analytics/analytics.columns.spec.ts && git commit -m "fix(ui): analytics tables render their group/label column instead of --"`

---

# Phase 2 — Backend: bucket rework and the new dimension

### Task 2: Rebucket holding period from calendar days to hours

- [ ] **Update the failing assertions first.** In `tests/analytics/
  test_metrics_derived.py`, `test_holding_period_split_buckets_by_days_held`
  currently reads:

  ```python
  def test_holding_period_split_buckets_by_days_held():
      trades = _year_of_trades()
      split = {b["bucket"]: b for b in holding_period_split(trades)}
      # 10, 10, 10 days land in 8-30d; 20 days lands there too.
      assert split["8-30d"]["n"] == 4
      assert split["0-2d"]["n"] == 0
      # Each bucket reports its own win rate, so the UI can show where the edge is.
      assert split["8-30d"]["win_rate"] == 50.0
  ```

  Change it to the new bucket names — all four trades (10, 10, 20, 10 days
  held) now fall into the `2d+` overflow bucket:

  ```python
  def test_holding_period_split_buckets_by_days_held():
      trades = _year_of_trades()
      split = {b["bucket"]: b for b in holding_period_split(trades)}
      # 10, 10, 20, 10 days all land in the 2d+ overflow bucket.
      assert split["2d+"]["n"] == 4
      assert split["0h-2h"]["n"] == 0
      assert split["2d+"]["win_rate"] == 50.0
  ```

  Add a new test proving the hour bands actually bucket sub-day holds, right
  below it:

  ```python
  def test_holding_period_split_buckets_intraday_holds_by_hour():
      trades = [
          _t("2024-01-01T09:30:00", "2024-01-01T10:30:00", 100.0, 105.0),      # 1h  -> 0h-2h
          _t("2024-01-01T09:30:00", "2024-01-01T12:30:00", 100.0, 95.0,
             status="loss"),                                                    # 3h  -> 2h-4h
          _t("2024-01-01T09:30:00", "2024-01-01T16:30:00", 100.0, 105.0),      # 7h  -> 4h-8h
          _t("2024-01-01T09:30:00", "2024-01-02T08:30:00", 100.0, 105.0),      # 23h -> 8h-24h
          _t("2024-01-01T09:30:00", "2024-01-02T15:30:00", 100.0, 105.0),      # 30h -> 1d-2d
      ]
      split = {b["bucket"]: b for b in holding_period_split(trades)}
      assert split["0h-2h"]["n"] == 1
      assert split["2h-4h"]["n"] == 1
      assert split["4h-8h"]["n"] == 1
      assert split["8h-24h"]["n"] == 1
      assert split["1d-2d"]["n"] == 1
      assert split["2d+"]["n"] == 0
  ```

- [ ] **Run both, confirm they fail** — the renamed-bucket test fails with a
  `KeyError` (`"2d+"` does not exist yet); the new intraday test fails the
  same way. `python scripts/dev/testrun.py file tests/analytics/test_metrics_derived.py`
- [ ] **Fix:** in `swingbot/core/analytics/metrics.py`, replace `_HOLDING_BUCKETS`
  (currently `("0-2d", 0.0, 2.0), ("3-7d", 2.0, 7.0), ("8-30d", 7.0, 30.0),
  ("31d+", 30.0, float("inf"))`) with:

  ```python
  _HOLDING_BUCKETS = (
      ("0h-2h",  0.0,   2 / 24),
      ("2h-4h",  2 / 24, 4 / 24),
      ("4h-8h",  4 / 24, 8 / 24),
      ("8h-24h", 8 / 24, 1.0),
      ("1d-2d",  1.0,   2.0),
      ("2d+",    2.0,   float("inf")),
  )
  ```

  No other line in `holding_period_split()` or `_holding_days()` changes —
  both already operate on calendar days as a float, so this is purely a
  table edit.
- [ ] **Run the file's tests again, confirm all pass**, including every
  *other* existing test in the file (the fixture-wide `_year_of_trades()`
  suite must still hold).
- [ ] **Update the two other tests still asserting the old bucket names.**
  In `tests/admin/test_api_analytics.py`,
  `test_holding_split_reports_every_bucket_even_when_empty`:

  ```python
  def test_holding_split_reports_every_bucket_even_when_empty(seed, logged_in):
      seed(trades=_year())
      buckets = {b["bucket"] for b in _perf(logged_in)["holding_period_split"]}
      assert buckets == {"0h-2h", "2h-4h", "4h-8h", "8h-24h", "1d-2d", "2d+"}
  ```

  In `tests/admin/test_api_analytics.py`,
  `test_distributions_and_series_are_present_and_scoped` asserts only
  `"holding_period_split": list` (unchanged) — no edit needed there.
- [ ] Run: `python scripts/dev/testrun.py file tests/analytics/test_metrics_derived.py`
  and `python scripts/dev/testrun.py file tests/admin/test_api_analytics.py`
- [ ] Commit: `git add swingbot/core/analytics/metrics.py tests/analytics/test_metrics_derived.py tests/admin/test_api_analytics.py && git commit -m "feat(bot): rebucket holding-period split from calendar days to hours"`

### Task 3: New `risk_reward_split()` — win rate by planned R:R

**Produces** (consumed by Task 4): `risk_reward_split(closed: list[dict]) ->
list[dict]`, returning one dict per bucket shaped exactly like
`holding_period_split`'s rows — `{"bucket": str, "n": int, "win_rate": float
| None, "avg_return_pct": float | None}` — over the fixed bucket set
`<1.5, 1.5-2, 2-3, 3-4, 4+`, every bucket present even at `n=0`.

- [ ] **Write the failing tests** in `tests/analytics/test_metrics_derived.py`:

  ```python
  def test_risk_reward_split_buckets_by_planned_ratio():
      trades = [
          {**_t("2024-01-01", "2024-01-05", 100.0, 110.0), "risk_reward_ratio": 1.5},
          {**_t("2024-02-01", "2024-02-05", 100.0, 95.0, status="loss"),
           "risk_reward_ratio": 1.8},
          {**_t("2024-03-01", "2024-03-05", 100.0, 110.0), "risk_reward_ratio": 2.5},
          {**_t("2024-04-01", "2024-04-05", 100.0, 110.0), "risk_reward_ratio": 5.0},
      ]
      split = {b["bucket"]: b for b in risk_reward_split(trades)}
      assert split["1.5-2"]["n"] == 2
      assert split["1.5-2"]["win_rate"] == 50.0
      assert split["2-3"]["n"] == 1
      assert split["4+"]["n"] == 1
      # No trade below the account's own gate -- the bucket still reports,
      # at n=0, never dropped.
      assert split["<1.5"]["n"] == 0
      assert split["<1.5"]["win_rate"] is None


  def test_risk_reward_split_is_empty_on_no_trades():
      assert risk_reward_split([]) == []


  def test_risk_reward_split_ignores_a_trade_with_no_recorded_ratio():
      trades = [_t("2024-01-01", "2024-01-05", 100.0, 110.0)]  # no risk_reward_ratio key
      split = {b["bucket"]: b for b in risk_reward_split(trades)}
      assert sum(b["n"] for b in split.values()) == 0
  ```

  Add `risk_reward_split` and `holding_period_split` (already there) to the
  file's existing `from swingbot.core.analytics.metrics import (...)` block.
- [ ] **Run, confirm `ImportError: cannot import name 'risk_reward_split'`.**
  `python scripts/dev/testrun.py file tests/analytics/test_metrics_derived.py`
- [ ] **Implement**, in `swingbot/core/analytics/metrics.py`, right below
  `holding_period_split` (mirroring its exact shape and its "every bucket
  reported even at n=0" contract):

  ```python
  _RISK_REWARD_BUCKETS = (
      ("<1.5", 0.0, 1.5),
      ("1.5-2", 1.5, 2.0),
      ("2-3",   2.0, 3.0),
      ("3-4",   3.0, 4.0),
      ("4+",    4.0, float("inf")),
  )


  def risk_reward_split(closed: list[dict]) -> list[dict]:
      """Trades bucketed by the R:R ratio they were PLANNED at (`risk_reward_ratio`,
      set at entry) -- not the realized R-multiple outcome, which is close to
      circular (an R > 0 trade is definitionally a win, so bucketing by outcome
      would read near-100%/near-0% and say nothing). `<1.5` is the account's own
      `MIN_RISK_REWARD_RATIO` gate default; a non-empty `<1.5` bucket is itself a
      finding, not noise.

      Every bucket is reported even at n=0, on `holding_period_split`'s rule.
      A trade with no recorded ratio is excluded from every bucket, exactly like
      a trade with unparseable dates in `holding_period_split`.
      """
      if not closed:
          return []
      out = []
      for name, lo, hi in _RISK_REWARD_BUCKETS:
          members = []
          for t in closed:
              rr = t.get("risk_reward_ratio")
              if isinstance(rr, (int, float)) and lo <= rr < hi:
                  members.append(t)
          rets = [r for r in (trade_return_pct(t) for t in members) if r is not None]
          out.append({"bucket": name, "n": len(members),
                      "win_rate": win_rate(members),
                      "avg_return_pct": round(sum(rets) / len(rets), 4) if rets else None})
      return out
  ```

  Note the half-open `lo <= rr < hi` (not `<=` on both ends like
  `holding_period_split`) — `_RISK_REWARD_BUCKETS`' edges are shared between
  adjacent buckets (`1.5-2`'s `hi` is `2-3`'s `lo`), so a trade at exactly
  `2.0` must land in exactly one bucket, not two. The last bucket's `hi` is
  `inf`, so its own upper bound never excludes anything.
- [ ] **Run again, confirm all three pass**, plus the whole file (no
  regression in `holding_period_split`'s own tests).
  `python scripts/dev/testrun.py file tests/analytics/test_metrics_derived.py`
- [ ] Commit: `git add swingbot/core/analytics/metrics.py tests/analytics/test_metrics_derived.py && git commit -m "feat(bot): add risk_reward_split -- win rate by planned R:R at entry"`

### Task 4: Wire `risk_reward_split` into `/api/v1/analytics/performance`

**Consumes:** `m.risk_reward_split(scoped)` from Task 3.
**Produces** (consumed by Task 5): a `"risk_reward_split"` key in the
`/api/v1/analytics/performance` JSON body, same shape as
`"holding_period_split"`.

- [ ] **Update the shape assertions first.** In `tests/admin/
  test_api_v1_analytics.py`, `test_performance_top_level_shape`:

  ```python
  assert_shape(logged_in.get("/api/v1/analytics/performance").get_json(), {
      "totals": dict, "relocated": dict, "win_rate": NULLABLE_NUMBER,
      "expectancy_r": NULLABLE_NUMBER, "by_confidence": dict,
      "range": dict, "derived": dict, "distributions": dict,
      "rolling_returns": list, "holding_period_split": list,
      "risk_reward_split": list,
      "calendar": list, "cumulative_by_strategy": dict, "benchmark": dict,
  })
  ```

  In `tests/admin/test_api_analytics.py`,
  `test_distributions_and_series_are_present_and_scoped`, add
  `"risk_reward_split": list,` to that file's parallel `assert_shape` call
  (same key list, same file already found at that test).
- [ ] **Run, confirm `AssertionError` on the missing key.**
  `python scripts/dev/testrun.py file tests/admin/test_api_v1_analytics.py`
- [ ] **Wire it.** In `swingbot/admin/api_v1/analytics.py`'s
  `analytics_performance()`, add one line to the returned dict, directly
  below `"holding_period_split": m.holding_period_split(scoped),`:

  ```python
      "risk_reward_split": m.risk_reward_split(scoped),
  ```
- [ ] **Run again, confirm both pass.**
  `python scripts/dev/testrun.py file tests/admin/test_api_v1_analytics.py`
  and `python scripts/dev/testrun.py file tests/admin/test_api_analytics.py`
- [ ] Commit: `git add swingbot/admin/api_v1/analytics.py tests/admin/test_api_v1_analytics.py tests/admin/test_api_analytics.py && git commit -m "feat(bot): serve risk_reward_split from /analytics/performance"`

---

# Phase 3 — Frontend store: the new computeds

### Task 5: Add `risk_reward_split` to the wire type, holding-period + R:R histograms

**Consumes:** `performance()?.holding_period_split` (existing field, new
bucket names as of Task 2), `performance()?.risk_reward_split` (new field
from Task 4, `HoldingBucket[]` shape).
**Produces** (consumed by Task 8): `AnalyticsStore.holdingPeriodHistogram:
Signal<HistogramBin[]>`, `AnalyticsStore.riskRewardHistogram:
Signal<HistogramBin[]>`.

- [ ] **Add the field to the wire type.** In `frontend/src/app/api/models.ts`,
  `AnalyticsPerformance` (currently ending `holding_period_split:
  HoldingBucket[];` … `benchmark: { spy_cum: Record<string, number> };`),
  add directly below `holding_period_split`:

  ```ts
  /** Win rate bucketed by the R:R ratio the trade was PLANNED at, not the
   *  realized outcome — see risk_reward_split's own docstring server-side.
   *  Same shape as holding_period_split: every bucket present, win_rate
   *  null (never 0) when empty. */
  risk_reward_split: HoldingBucket[];
  ```

- [ ] **Update every fixture that types itself as (or spreads into)
  `AnalyticsPerformance`** so the build still compiles:
  - `frontend/src/app/stores/analytics.store.spec.ts`'s `PERFORMANCE`
    constant — add `risk_reward_split: [],` directly below its existing
    `holding_period_split: [...]` field. That field's own two rows still
    read `'0-2d'`/`'8-30d'` — relabel them to `'0h-2h'`/`'2d+'` while here so
    the fixture matches what the API now actually sends (no test asserts
    these specific two strings from the base fixture, so this is a
    same-shape rename, not a behaviour change).
  - `frontend/src/app/workspaces/analytics/analytics.spec.ts`'s inline
    performance fixture — add `risk_reward_split: [],` directly below its
    `holding_period_split: [],` line.
  - `frontend/src/app/stores/analytics.snapshot.spec.ts`'s own `PERFORMANCE`
    constant needs **no edit** — it is a loose object literal (not typed as
    `AnalyticsPerformance`) with no `holding_period_split` field at all;
    this file's `open()` helper flushes it untyped, so it does not
    participate in this interface at all. Confirm this before skipping it:
    `grep -n "holding_period_split" frontend/src/app/stores/analytics.snapshot.spec.ts`
    should return nothing.
- [ ] **Write the failing tests**, in `frontend/src/app/stores/
  analytics.store.spec.ts`, alongside the existing `monthHistogram` test:

  ```ts
  it('exposes a holding-period win-rate histogram with sample size in the label', () => {
    tick();
    respondPerformance({ holding_period_split: [
      { bucket: '0h-2h', n: 0, win_rate: null, avg_return_pct: null },
      { bucket: '2h-4h', n: 3, win_rate: 66.7, avg_return_pct: 1.1 },
    ] });

    expect(store.holdingPeriodHistogram()).toEqual([
      { label: '0h-2h (n=0)', count: 0 },
      { label: '2h-4h (n=3)', count: 66.7 },
    ]);
  });

  it('exposes a planned-R:R win-rate histogram with sample size in the label', () => {
    tick();
    respondPerformance({ risk_reward_split: [
      { bucket: '<1.5', n: 0, win_rate: null, avg_return_pct: null },
      { bucket: '1.5-2', n: 4, win_rate: 50, avg_return_pct: 0.4 },
    ] });

    expect(store.riskRewardHistogram()).toEqual([
      { label: '<1.5 (n=0)', count: 0 },
      { label: '1.5-2 (n=4)', count: 50 },
    ]);
  });
  ```

- [ ] **Run, confirm both fail** with "holdingPeriodHistogram is not a
  function" / "riskRewardHistogram is not a function".
  `cd frontend && npx vitest run src/app/stores/analytics.store.spec.ts`
- [ ] **Implement**, in `frontend/src/app/stores/analytics.store.ts`. Delete
  the existing `holdingSplit: computed(() => performance()?.
  holding_period_split ?? []),` (its one caller, the template `<dl>`, goes
  away in Task 8) and replace it with two computeds in the same
  `withComputed` block (the one destructuring `performance` — where
  `holdingSplit` already lives):

  ```ts
  /** Win rate per holding-period band, as a bar the same shape every other
   *  distribution chart on this workspace uses. The label carries the
   *  sample size because a zero-height bar means two different things —
   *  "nobody held this long" and "held this long, lost every time" — and
   *  the bar height alone cannot tell them apart. */
  holdingPeriodHistogram: computed<HistogramBin[]>(() =>
    (performance()?.holding_period_split ?? []).map((b) => ({
      label: `${b.bucket} (n=${b.n})`,
      count: b.win_rate ?? 0,
    }))),

  /** Win rate per planned-R:R band — see risk_reward_split's own docstring
   *  for why this is the ratio at entry, not the realized outcome. */
  riskRewardHistogram: computed<HistogramBin[]>(() =>
    (performance()?.risk_reward_split ?? []).map((b) => ({
      label: `${b.bucket} (n=${b.n})`,
      count: b.win_rate ?? 0,
    }))),
  ```

- [ ] **Run again, confirm both pass**, and confirm nothing else referenced
  `holdingSplit` (a full-file grep for `holdingSplit` should now return only
  this deleted line's absence — it must be zero results outside this task's
  own diff).
  `cd frontend && npx vitest run src/app/stores/analytics.store.spec.ts`
- [ ] Commit: `git add frontend/src/app/api/models.ts frontend/src/app/stores/analytics.store.ts frontend/src/app/stores/analytics.store.spec.ts frontend/src/app/stores/analytics.snapshot.spec.ts frontend/src/app/workspaces/analytics/analytics.spec.ts && git commit -m "feat(ui): holding-period and planned-R:R win-rate histograms"`

### Task 6: Direction and day-of-week win-rate histograms, zero-filled

**Consumes:** `snapshot()?.by?.direction` / `?.by?.dow` (existing fields,
`aggregate.py`'s `direction`/`dow` dimensions — no backend change), the
module-private `toBreakdownRows()` helper already defined in
`analytics.store.ts`.
**Produces** (consumed by Task 9): `AnalyticsStore.directionHistogram:
Signal<HistogramBin[]>`, `AnalyticsStore.dowHistogram: Signal<HistogramBin[]>`.

- [ ] **Write the failing tests**, in `frontend/src/app/stores/
  analytics.snapshot.spec.ts` (this data comes from `snapshot()`, so it
  belongs beside `breakdownRows`'s own tests, not in `analytics.store.spec.ts`):

  ```ts
  it('exposes a direction win-rate histogram, Long above Short, zero-filled when one side never traded', () => {
    open({
      ...SNAPSHOT,
      by: { ...SNAPSHOT.by, direction: [
        { key: 'bullish', n: 6, wins: 4, losses: 2, win_rate: 66.7, expectancy_r: 0.3,
          avg_r: 0.3, profit_factor: 1.8, total_pnl: 300 },
      ] },
    });

    expect(store.directionHistogram()).toEqual([
      { label: 'Long (n=6)', count: 66.7 },
      { label: 'Short (n=0)', count: 0 },
    ]);
  });

  it('exposes a day-of-week win-rate histogram in calendar order, not busiest-first', () => {
    open({
      ...SNAPSHOT,
      by: { ...SNAPSHOT.by, dow: [
        // Deliberately out of calendar order, the way stats_by's own
        // busiest-first sort would actually deliver them.
        { key: 'Wednesday', n: 5, wins: 3, losses: 2, win_rate: 60, expectancy_r: 0.2,
          avg_r: 0.2, profit_factor: 1.5, total_pnl: 150 },
        { key: 'Monday', n: 2, wins: 1, losses: 1, win_rate: 50, expectancy_r: 0.1,
          avg_r: 0.1, profit_factor: 1.1, total_pnl: 20 },
      ] },
    });

    expect(store.dowHistogram().map((b) => b.label)).toEqual([
      'Monday (n=2)', 'Tuesday (n=0)', 'Wednesday (n=5)', 'Thursday (n=0)',
      'Friday (n=0)', 'Saturday (n=0)', 'Sunday (n=0)',
    ]);
    expect(store.dowHistogram()[0].count).toBe(50);   // Monday
    expect(store.dowHistogram()[2].count).toBe(60);   // Wednesday
  });
  ```

- [ ] **Run, confirm both fail** with "directionHistogram is not a
  function" / "dowHistogram is not a function".
  `cd frontend && npx vitest run src/app/stores/analytics.snapshot.spec.ts`
- [ ] **Implement**, in `frontend/src/app/stores/analytics.store.ts`. Add a
  module-level order table and zero-fill helper near `toBreakdownRows`
  (same file, so no new export needed):

  ```ts
  /** Wire key -> display label, in the order the chart renders them. Direction
   *  arrives as `bullish`/`bearish` on the wire (`aggregate.py`'s own
   *  extractor) -- `Long`/`Short` is how every other direction cue in this SPA
   *  already reads (`direction-arrow.ts`). */
  const DIRECTION_ORDER: readonly [string, string][] = [
    ['bullish', 'Long'],
    ['bearish', 'Short'],
  ];

  const DOW_ORDER = [
    'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday',
  ] as const;

  /** Every category in `order` renders, even one with no rows at all — a
   *  category that never occurs is a measured answer (the bot doesn't trade
   *  weekends), not a gap to hide. Mirrors holding_period_split's own rule,
   *  applied client-side because these two dimensions come from the generic
   *  by-dimension block, which drops a key entirely when no trade falls in it. */
  function zeroFilledHistogram(
    rows: BreakdownRow[],
    order: readonly (readonly [string, string])[],
  ): HistogramBin[] {
    const byKey = new Map(rows.map((r) => [r.key, r]));
    return order.map(([key, label]) => {
      const row = byKey.get(key);
      return { label: `${label} (n=${row?.n ?? 0})`, count: row?.win_rate ?? 0 };
    });
  }
  ```

  Then, in the `withComputed` block that already destructures `snapshot`
  (the one containing `breakdownRows`/`breakdownLabel`), add directly below
  `breakdownLabel`:

  ```ts
  /** All-time, like the by-segment table it sits beside — not scoped by the
   *  date-range control. See the spec's reasoning for why this and
   *  dowHistogram are all-time while holdingPeriodHistogram/riskRewardHistogram
   *  are range-scoped. */
  directionHistogram: computed<HistogramBin[]>(() =>
    zeroFilledHistogram(
      toBreakdownRows((snapshot()?.by?.['direction'] ?? []) as unknown[]),
      DIRECTION_ORDER,
    )),

  dowHistogram: computed<HistogramBin[]>(() =>
    zeroFilledHistogram(
      toBreakdownRows((snapshot()?.by?.['dow'] ?? []) as unknown[]),
      DOW_ORDER.map((day) => [day, day] as const),
    )),
  ```

- [ ] **Run again, confirm both pass.**
  `cd frontend && npx vitest run src/app/stores/analytics.snapshot.spec.ts`
- [ ] Commit: `git add frontend/src/app/stores/analytics.store.ts frontend/src/app/stores/analytics.snapshot.spec.ts && git commit -m "feat(ui): direction and day-of-week win-rate histograms, zero-filled"`

---

# Phase 4 — Frontend template

### Task 7: Swap "By holding period" from a `<dl>` to a histogram

**Consumes:** `store.holdingPeriodHistogram()` (Task 5), `store.derived()`
(existing, for the reference line).

- [ ] In `frontend/src/app/workspaces/analytics/analytics.ts`'s template,
  replace the existing "By holding period" panel:

  ```html
  <sb-panel heading="By holding period">
    <!-- Every band renders, including empty ones: "the edge is all in
         8-30d" is only legible next to the bands that are empty. -->
    <dl>
      @for (band of store.holdingSplit(); track band.bucket) {
        <div>
          <dt>{{ band.bucket }}</dt>
          <dd class="num">
            {{ fmtCount(band.n) }} · {{ fmtRate(band.win_rate) }}
          </dd>
        </div>
      }
    </dl>
  </sb-panel>
  ```

  with:

  ```html
  <sb-panel heading="By holding period">
    <!-- Every band renders, including empty ones: "the edge is all in 2d+"
         is only legible next to the bands that are empty. n is folded into
         each bar's label because a zero-height bar cannot say on its own
         whether nobody held this long or everybody who did lost. -->
    <sb-histogram
      [bins]="store.holdingPeriodHistogram()"
      [max]="100"
      [referenceLine]="store.derived().win_rate"
    />
  </sb-panel>
  ```

- [ ] There is no test to write for this step alone — `analytics.spec.ts`
  does not assert on this panel's markup (confirmed by grep before writing
  this plan). Verification is Task 11's full-suite run and the
  already-passing `store.holdingPeriodHistogram()` unit tests from Task 5.
- [ ] Commit: `git add frontend/src/app/workspaces/analytics/analytics.ts && git commit -m "feat(ui): render By holding period as a win-rate bar chart"`

### Task 8: Add "By direction", "By day of week" and "By planned R:R" panels

**Consumes:** `store.directionHistogram()`, `store.dowHistogram()` (Task 6),
`store.riskRewardHistogram()` (Task 5), `store.winRate()` (existing,
all-time reference line for the two all-time charts).

- [ ] In `analytics.ts`'s template, add the R:R panel to the "Distributions"
  section, directly below the existing "By month" panel's closing `</div>`
  and immediately before `<h2 class="section">Over time</h2>` — Task 9
  removes that heading and everything through its section, so run this task
  before Task 9 or the anchor line will already be gone; if Task 9 has
  already landed, insert in the same place, now immediately before `<h2
  class="section">By segment</h2>` instead:

  ```html
  <div class="panels">
    <sb-panel heading="By planned R:R">
      <!-- The ratio the trade was PLANNED at, not the realized R-multiple
           outcome -- bucketing by outcome is close to circular (an R > 0
           trade is definitionally a win). -->
      <sb-histogram
        [bins]="store.riskRewardHistogram()"
        [max]="100"
        [referenceLine]="store.derived().win_rate"
      />
    </sb-panel>
  </div>
  ```

- [ ] Add the direction and day-of-week panels to the "By segment" section,
  directly below `<h2 class="section">By segment</h2>` and before the
  existing `<sb-panel heading="By confidence level" ...>`:

  ```html
  <div class="panels">
    <sb-panel heading="By direction">
      <!-- All-time, like the picker table below -- not scoped by the
           date-range control. -->
      <sb-histogram
        [bins]="store.directionHistogram()"
        [max]="100"
        [referenceLine]="store.winRate()"
      />
    </sb-panel>

    <sb-panel heading="By day of week">
      <sb-histogram
        [bins]="store.dowHistogram()"
        [max]="100"
        [referenceLine]="store.winRate()"
      />
    </sb-panel>
  </div>
  ```

  These three panels are inside the same `sb-async` block the "By month"
  and "By confidence level" panels already sit in respectively — no new
  `sb-async` wrapper needed.
- [ ] No new component-level test for the template wiring itself, same
  reasoning as Task 7 — the underlying computeds are already covered.
- [ ] Commit: `git add frontend/src/app/workspaces/analytics/analytics.ts && git commit -m "feat(ui): add By direction, By day of week and By planned R:R charts"`

### Task 9: Remove "Over time" and its dead store/component code

- [ ] **Delete the template section**, in `analytics.ts` — the whole block
  from `<h2 class="section">Over time</h2>` through the closing `</div>` of
  the "Rolling returns"/"Cumulative return by strategy" `<div class="panels">`,
  i.e. everything currently between the "By month" `</div>` and `<h2
  class="section">By segment</h2>`:

  ```html
  <h2 class="section">Over time</h2>
  @if (store.equitySeries().length) {
    <div class="panels">
      <sb-panel heading="Account balance">
        <sb-line-chart [series]="store.balanceWithBenchmark()" [valueFormat]="fmtLineValue" />
        <p class="series-note">
          {{ store.equitySeries().length }} points ·
          {{ seriesRange(store.equitySeries()) }}
        </p>
      </sb-panel>

      <sb-panel heading="Drawdown">
        <sb-line-chart [series]="drawdownSeriesForChart()" [valueFormat]="fmtLineValue" />
        <p class="series-note">
          Peak-to-trough, as a share of the running high. Higher is worse.
        </p>
      </sb-panel>
    </div>
  }
  <div class="panels">
    <sb-panel heading="Rolling returns">
      <sb-line-chart [series]="store.rollingReturnsChart()" [valueFormat]="fmtLineValue" />
    </sb-panel>
    <sb-panel heading="Cumulative return by strategy">
      @if (store.cumulativeByStrategyChart().length) {
        <sb-line-chart [series]="store.cumulativeByStrategyChart()" [valueFormat]="fmtLineValue" />
      } @else {
        <p class="stale">No strategies with closed trades yet.</p>
      }
    </sb-panel>
  </div>
  ```

  becomes nothing — delete the block entirely. What now precedes `<h2
  class="section">By segment</h2>` is either the "By month" panel's closing
  `</div>` (if Task 8 has not yet landed) or Task 8's "By planned R:R" panel
  (if it has) — either is correct; this task only removes the "Over time"
  block itself and touches nothing on either side of it.
- [ ] **Delete the now-dead component code**, in `analytics.ts`:
  - The `drawdownSeriesForChart` computed:
    ```ts
    protected readonly drawdownSeriesForChart = computed<LineChartSeries[]>(() => [
      { name: 'Drawdown', points: this.store.drawdownSeries() },
    ]);
    ```
  - `fmtLineValue`: `protected readonly fmtLineValue = (value: number): string => \`${value.toFixed(2)}%\`;`
  - `seriesRange(series: { date: string }[]): string { ... }` (its whole body)
  - The `LineChart, LineChartSeries` import from `'../../ui/line-chart'`
    (confirm no other symbol from that module is still used in the file
    before removing the whole import line — grep `LineChart` in the file
    after the template deletion above; if the import line has no remaining
    reference, delete it).
- [ ] **Delete the now-dead store code**, in `frontend/src/app/stores/
  analytics.store.ts`: the `equitySeries`, `drawdownSeries`,
  `benchmarkSeries`, `cumulativeByStrategy` computeds, the whole
  `withComputed(({ equitySeries, benchmarkSeries }) => ({ balanceWithBenchmark: ... }))`
  block, the whole `withComputed(({ cumulativeByStrategy }) => ({
  cumulativeByStrategyChart: ... }))` block, `rollingReturnsChart`, and the
  now-unused `toSeries()` function and `SeriesPoint` interface (grep both
  names in the file after the computed deletions above — if the only
  remaining references are the deleted computeds themselves, remove them
  too). Remove the `LineChartSeries` import if nothing else in the file
  still uses it.
- [ ] **Delete their spec coverage:**
  - `frontend/src/app/stores/analytics.store.spec.ts`: the tests
    `'sorts the benchmark and per-strategy series it is handed'`,
    `'overlays the SPY benchmark on the account-balance series when present'`,
    `'omits the SPY series entirely when the benchmark fetch was unavailable'`,
    `'exposes rolling returns as a single-series line chart'`,
    `'exposes cumulative-by-strategy as one series per strategy'`.
  - `frontend/src/app/stores/analytics.snapshot.spec.ts`: the tests
    `'flattens the equity curve and the drawdown series to one point shape'`,
    `'drops a series point that is missing a date or a value'`.
- [ ] **Run the full frontend suite for this workspace and store**, since
  this task touches the most files of any in this plan:
  `cd frontend && npx vitest run src/app/workspaces/analytics src/app/stores/analytics.store.spec.ts src/app/stores/analytics.snapshot.spec.ts`
  — expect every remaining test to pass and zero references to any deleted
  symbol (a leftover reference fails the build, not just a test).
- [ ] Commit: `git add frontend/src/app/workspaces/analytics/analytics.ts frontend/src/app/stores/analytics.store.ts frontend/src/app/stores/analytics.store.spec.ts frontend/src/app/stores/analytics.snapshot.spec.ts && git commit -m "refactor(ui): remove Over time section and its dead store code"`

---

# Phase 5 — Verification

### Task 10: Full-suite verification

- [ ] `python scripts/dev/testrun.py full` — dispatch via the `test-runner`
  subagent so the ~1150 progress lines never reach the controller's
  context. Green means `0 failed` and `0 xfailed`; a changed passed/skipped
  count alone is not a failure (this plan is expected to change counts —
  new tests were added in Tasks 2, 3, 5, 6, and the two bucket-name tests
  in Task 2 changed what they assert).
- [ ] `cd frontend && npm test` — this plan touches the frontend more than
  the backend; per this repo's convention the full-suite-once rule applies
  to whichever suite(s) the plan's own files touch, not Python only.
- [ ] A red result in either is where the fixing starts, not a reason to
  re-run either suite wholesale.
- [ ] This is the only full run of either suite in this plan — every earlier
  task verified with its own narrow file/spec run.


## Close-out

**Complete 2026-08-29.** All ten delivered tasks were implemented and merged
to `main` in `e1a83aa` (`merge(v63): add analytics distribution charts`). The
full frontend suite passed (83 files, 1,626 tests), and the full Python suite
completed with exit code 0. The plan worktree and merged branch were removed.
