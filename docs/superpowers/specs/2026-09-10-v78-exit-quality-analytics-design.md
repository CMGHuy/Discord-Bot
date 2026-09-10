# v78 — Exit-quality analytics

**Version:** ui 1.12.0 · bot 1.6.2
**Bump:** bot patch · ui minor — a new endpoint and an aggregation module the
Discord path never reads (patch), and a Performance tab that gains a whole
section a user looks at daily (minor). Numbers resolved at close-out from
`VERSION.json`.
**Edge:** none (integrity) — these charts measure, they do not trade. They are
however the instrument that would source a future `harvest` plan; see §1.

## 1. Why

Measured off the Hetzner production book on 2026-09-10 (read-only aggregate
probe over `/opt/swing-bot/data`, N=782 closed, 2026-07-06 → 2026-09-09):

| | |
|---|---|
| Win rate | 53.5% |
| **Expectancy** | **−0.136R** |
| Profit factor | 0.727 |

The live book is net negative, and `source` shows **624 of 782 trades (80%) are
confluence-sourced** — the one population `docs/claude/edge-priorities.md`
already records as negative (53.5% / −0.171R, N=4641). That is not this spec's
problem to fix. What *is* this spec's problem: the bot already records, per
closed trade, how far price ran in your favour, how much heat the trade took,
and what fraction of the available move was actually banked — and **nothing on
the Analytics workspace ever aggregates any of it.**

Two figures from the same probe, both invisible in the product today:

- `exit_efficiency` on winners: n=324, **median 0.429**, p10 0.079, p90 0.956.
  A typical winner banks under half the move available to it.
- `hold_by_outcome`: avg winner 0.31d vs avg loser 0.64d — **losers are held
  ~2.1× longer than winners** (n=352 / n=212).

Journal coverage supports both: `mfe_r` 93.9%, `mae_r` 94.4%,
`exit_efficiency` 88.0% of 591 rows. Median `holding_days` is ~0.08d (about two
hours) against horizons labelled 2w–9m, so realized holds do not resemble plan
intent either.

**These numbers are 2026-09-10 measurements, quoted to justify building the
instrument. This spec measures nothing and pre-registers nothing.** No default
changes, no gate moves, no pre-registration is opened or re-run.

## 2. What already exists (do not rebuild)

| Already shipped | Where |
|---|---|
| `exit_reason_split` — 9 fixed buckets, `n`/`share_pct`/`total_r`/`avg_r`/`win_rate` | `metrics.py:758` — **consumed only by the Discord weekly digest** (`insights.py:99`) |
| `hold_by_outcome` — winner/loser hold, `ratio`, `severity`, both `n`s | `metrics.py:804` — **digest only** (`insights.py:110`) |
| `compute_mfe_mae` → `{mfe_r, mae_r, exit_efficiency}` | `mfe_mae.py:26`, written into every journal row (`journal.py:199-201`) |
| `histogram(values, bins)` → `{lo, hi, count}` | `metrics.py` |
| `stats_by(closed, dimension)` → `StatRow[]` over 9 dimensions | `aggregate.py:71`, `DIMENSIONS` at `:93` |
| Win-rate bars, R-mult/return histograms, month, holding-period, planned-R:R, direction, day-of-week, strategy×horizon heatmap, group-by table | `workspaces/analytics/analytics.ts` |

So the backend work here is **exposure plus one new module**, not a new
statistics layer. Three test files already cover the functions being exposed:
`tests/analytics/test_metrics_exit_reasons.py`,
`test_metrics_hold_by_outcome.py`, `test_mfe_mae.py`.

## 3. Design

### 3.1 `swingbot/core/analytics/exit_quality.py` (new)

Journal-derived aggregates. Pure functions taking `entries: list[dict]` as a
parameter — **never loading**, matching `core/edge/stops.py`, whose
`mae_informed_stop_mult` and `mfe_informed_tp2_r` both take entries in. The
caller uses the seam at `core/planning/params.py:52`:

```python
from swingbot.core.analytics.journal import JournalStore
JournalStore().entries()            # journal.py:51, newest-first
JournalStore().entries(outcome="win")
```

| Function | Returns |
|---|---|
| `efficiency_histogram(entries, bins=10)` | `histogram` bins over `exit_efficiency`, **winners only** |
| `mae_histogram(entries, bins=10)` | bins over `mae_r`, **winners only** (§3.2) |
| `mfe_mae_points(entries)` | `[{mae_r, mfe_r, r_realized, outcome, ticker, strategy}]`, all outcomes |
| `coverage(entries)` | `{field: {non_null, total, pct}}` for `mfe_r`, `mae_r`, `exit_efficiency` |

`efficiency_histogram` gets a clean `[0, 1]` domain for free: `exit_efficiency`
is `r_real / mfe_r` clamped to `[-5, 1]` and `None` when `mfe_r <= 0`
(`mfe_mae.py`), so on a *winner* both terms are positive and the value lands in
`(0, 1]`. No clamping, no overflow bucket. Negative efficiency only arises on
losses, which this histogram excludes.

### 3.2 Winners-only is doctrine, not a shortcut

`core/edge/stops.py:19-29` already aggregates MAE winners-only, and says why:

> a LOSER's MAE is by definition at least the stop it hit, so feeding losers in
> would ratchet stops wider on exactly the trades that should have been cut.

`mae_histogram` inherits that rule and cites it in its docstring. The
**scatter is the deliberate exception** — plotting losers beside winners is the
entire diagnostic there, and it sets no stop. `stops.py`'s own floor is
`MIN_SAMPLE = 40` (`stops.py:14`); the aggregate histograms report their `n` and
defer suppression to §3.5 rather than inventing a second floor.

### 3.3 `GET /analytics/exit-quality` (new route)

A separate route rather than more keys on `/analytics/performance`: the page
already runs three independent fetches each with its own `sb-async`, and a
~555-point scatter payload has no business on the main performance call.

```
{ exit_reasons: [...9 rows...], hold_by_outcome: {...},
  efficiency: {bins: [...], median, n}, mae: {bins: [...], n},
  scatter: [...], coverage: {...}, min_cell_n: 20 }
```

Follows `analytics.py`'s stated contract — *"this route selects and assembles,
it does not derive"* — and carries the same strict unknown-parameter guard the
other routes use (`analytics.py`'s `unknown = set(request.args) - {...}` →
400). **It takes no parameters**, so the guard rejects every one. All-time
only; date-range scoping is a non-goal (§5).

### 3.4 Two honesty rules the payload must preserve

**`None` is not `0`.** `exit_reason_split` returns `avg_r`/`win_rate` as `None`
for an empty bucket, and its docstring says why: *"'no trades exited this way'
and 'they all lost' must not look the same."* `hold_by_outcome` returns
`ratio`/`severity` as `None` unless **both** sides independently clear
`MIN_TRADES_FOR_RATIO = 5` (`metrics.py:328`). Every renderer in §3.6 must draw
absence, never a zero.

**Missing data is stated, not dropped.** `exit_efficiency` is null on 12% of
journal rows and `mae_r` on 5.6%. The `coverage` block is rendered as a caption
under each affected chart ("520 of 591 closed trades carry efficiency data"). A
chart that silently drops an eighth of the book is the same class of defect as a
rate quoted on n=3.

### 3.5 The thin-cell floor

Production has **46 strategy cells of which 36 hold fewer than 20 trades**, and
66 ticker cells of which 53 do. Strategy×horizon is 460 cells over 782 trades —
mean 1.7 per cell — so the existing win-rate heatmap is already a noise field,
and `zeroFilledHistogram` (`analytics.store.ts:360`) renders a 3-trade cell as a
full-height bar via `count: row?.win_rate ?? 0`.

One shared constant, **seeded from the floor this repo already uses** —
`DRIFT_LIVE_N_FLOOR = 20` (`calibration.py:79`) — exported as `MIN_CELL_N` from
`aggregate.py` and served in payloads as `min_cell_n` so the SPA never
hard-codes it.

Below the floor a cell keeps its bar in a muted "insufficient sample"
treatment and **replaces the numeric rate with `n=7`**. Muted rather than
hidden: the category must stay visible (v63's contract requires every category
rendered even at n=0), and shape-at-a-glance is worth keeping — what is
withheld is the *claim*, not the row.

`zeroFilledHistogram` is the single choke point for the direction and
day-of-week charts. The heatmap cells, the group-by table, the by-confidence
table and the level-calibration table each need the same treatment applied
locally. Note `level_calibration` has **no floor of its own** (`calibration.py:64-78`
always emits 5 rows regardless of `n`), which is exactly why fixing §3.7 and
adding this floor belong in one plan.

### 3.6 Frontend

Two new primitives in `ui/`, DIY SVG, consistent with `histogram.ts` and
`line-chart.ts` — **no charting library** (v53 non-goal). Angular 21.2.21,
signal inputs, `OnPush`, matching `histogram.ts`'s shape.

| Primitive | Purpose |
|---|---|
| `ui/donut.ts` — `sb-donut` | composition of a whole: counts + share %, legend, absent≠zero |
| `ui/scatter.ts` — `sb-scatter` | MAE vs MFE, one dot per trade, coloured by outcome |

The charts land in **two new child components**, not in the 1700-line
`analytics.ts`. That file is mounted with one line each; the new sections are
independently testable, and because they are separate files their tasks
parallelise (concurrent sessions share this tree — see `document-conventions.md`
§Parallelisation).

`workspaces/analytics/sections/exit-quality.ts` — Performance tab:

| # | Chart | Type |
|---|---|---|
| P1 | Exit-reason mix, 9 fixed buckets | donut + per-reason `avg_r` column |
| P2 | Exit efficiency on winners, median marked | histogram + median chip |
| P3 | Winner vs loser hold, disposition ratio | two-row `sb-histogram` + ratio chip — **no third primitive** |
| P4 | MAE "heat taken" on winners | histogram |
| P5 | Outcome mix (win / loss / scratch / timeout) | donut |
| P6 | MAE vs MFE | scatter |

`workspaces/analytics/sections/strategy-contribution.ts` — Strategies tab:

| # | Chart | Type |
|---|---|---|
| S1 | Total R contributed per strategy — **top 12 by \|total R\|**, remainder folded into one `other (N strategies)` bar so the column still sums to the book's total R | signed horizontal bar |

**P1's `other` bucket is a feature.** `exit_reason_split` buckets into a fixed
9-tuple (`EXIT_REASONS`, `metrics.py:27`) — `tp1`, `runner_tp2`, `runner_trail`,
`runner_be`, `stop`, `scratch`, `timeout`, `reversed`, `other` — and a trade
whose `close_reason` is absent falls through to `other`. Production has no
`close_reason` on 454 of 782 closed trades, so `other` will dominate. That is
the chart doing its job: the size of `other` is a legible data-quality defect,
not a hole in the chart.

### 3.7 Two bug fixes

**`analytics.py:277` reads a key nothing writes.** `snapshots.py:54` writes
`calibration["levels"]`; the route reads `calibration.get("tiers", [])`. The
Calibration tab's tier table has therefore always rendered empty — against 5
rows of real production data. Fix: serve `levels`, and rename the response key
to `levels` with the SPA reader updated to match, rather than perpetuating a
`tier` misnomer that v32 retired.

**The dead `tier` group-by option.** `tier` is not in `DIMENSIONS`
(`aggregate.py:93`) and `stats_by` raises `ValueError` on an unknown dimension,
so the picker offers a choice that cannot resolve. v63 filed this and it is
still broken. Fix: remove the option — `tier` was retired deliberately in v32,
so restoring the dimension would be reviving a decision, not fixing a bug.

## 4. Testing

| Layer | Tests |
|---|---|
| `exit_quality.py` | new `tests/analytics/test_exit_quality.py`: winners-only filtering, null handling at each field's real coverage rate, empty input → empty (never a zero row), `(0,1]` domain on efficiency, coverage arithmetic |
| Route | `tests/admin/test_api_v1_analytics.py`: payload contract, unknown-param → 400, `None` survives serialisation as `null` |
| Bug fixes | regression test that the calibration route returns the 5 rows `level_calibration` produced; a test asserting the group-by picker offers only `DIMENSIONS` keys |
| `StatRow.total_r` | `tests/analytics/test_aggregate.py`: `total_r` is R and not currency (§6) |
| Primitives | `frontend/src/app/ui/donut.spec.ts`, `scatter.spec.ts` — absent≠zero, share sums to 100 |
| Sections | `sections/exit-quality.spec.ts`, `strategy-contribution.spec.ts` |
| Floor | extend `analytics.spec.ts`: a sub-floor row renders `n=` and no rate; an at-floor row renders the rate |

Per-task verification is the narrow run (`testrun.py file …` ~7s; `npm test --
--include <one spec>`). **The full suite runs once, as the plan's final task**,
covering both `testrun.py full` and `cd frontend && npm test`.

## 5. Non-goals

- **No revived over-time line charts.** v63 deleted the account-balance,
  drawdown, rolling-returns and cumulative-by-strategy line charts outright.
  Nothing here brings one back.
- **No pie on anything rate-shaped.** v30 rejected the seven by-dimension pies
  and `histogram.ts` documents why (*"a pie cannot show an ordered scale at
  all"*). The two donuts here are composition-of-a-whole, where parts sum to
  100% of the book — a different question.
- **No new charting library** (v53).
- **No date-range scoping** on the exit-quality section — all-time, labelled as
  such, consistent with the "By segment" charts it joins. Deferred, not
  forgotten.
- **No second tab-strip** inside a tab (v30 rejected).
- **Deferred from the brainstorm:** S2 (heatmap keyed on ExpR), S3 (live-vs-OOS
  dumbbell), S4 (exit-reason mix per strategy), S5 (confluence-count → outcome,
  the only item needing a genuinely new backend dimension), P7 (ticker
  concentration). Each is a clean follow-up; none is a dependency.
- **Nothing is re-measured or re-tuned.** No backtest runs, no grid, no
  registry regeneration, no default flipped.

## 6. One correction this spec carries

The brainstorm assumed `StatRow.total_pnl` was in R, making S1 free. It is
**currency** — `sum(realized_pnl_amount)` at `aggregate.py:62` — and no
per-group total-R value exists anywhere. S1 therefore needs a real backend
change: add `total_r: float | None` to `StatRow`, populated in `stats_by` from
`metrics.r_multiples(group)`. The field is additive, so `by.*` snapshot rows and
the group-by table gain a key they may ignore; the group-by table taking a
"Total R" column is a cheap bonus, not a requirement.

Two further facts corrected during spec authoring, recorded so a reader does not
re-derive them: `stats_by`'s `dow`/`month` keys are computed from **`closed_at`
in Europe/Berlin** with full day names (`aggregate.py:26,36`), not `opened_at`
in UTC — so the day-of-week chart's buckets are not the ones the production
probe printed. And `StatRow.wins`/`losses` count `t["status"] == "win"` rather
than going through `resolve_outcome`, which is a pre-existing inconsistency this
spec does not touch.

## Parallelisation

- **Sequential first: `exit_quality.py` + `MIN_CELL_N`.** Every later task
  consumes one or both. Contract dependency, not preference.
- **Then the route**, which consumes the module.
- **Group 1 (parallel):** `ui/donut.ts` and `ui/scatter.ts` — one new file
  each, no shared symbol, neither consumes the other.
- **Group 2 (parallel), after Group 1 and the route:**
  `sections/exit-quality.ts` and `sections/strategy-contribution.ts` — separate
  new files. S1's section additionally needs `StatRow.total_r`, so that backend
  change lands before this group.
- **Sequential, alone: the floor rollout.** It edits
  `analytics.store.ts`'s `zeroFilledHistogram` plus the heatmap, group-by,
  by-confidence and level-calibration renderers inside `analytics.ts` — the
  1700-line file every other frontend task deliberately avoids. One writer.
- **Group 3 (parallel):** the two §3.7 bug fixes — different files
  (`analytics.py` + the SPA calibration reader vs the group-by picker).
- **Last, alone:** full-suite verification, both suites, once.

## Success criteria

1. Exit efficiency, MAE, MFE-vs-MAE, disposition, exit-reason mix and outcome
   mix are all visible on the Performance tab; total R per strategy on the
   Strategies tab.
2. No chart renders a rate for a cell below `MIN_CELL_N`; each shows `n`
   instead, and every existing rate chart obeys the same floor.
3. Every chart fed by a partially-populated field states its coverage.
4. An empty bucket renders as absent, never as zero — asserted by test.
5. The calibration tier/level table shows the rows `level_calibration`
   produces; the group-by picker offers no dimension that cannot resolve.
6. `python scripts/dev/testrun.py full` and `cd frontend && npm test` are both
   green — `0 failed`, `0 xfailed` — in one final run.
7. `analytics.ts` is not materially longer than it is today: the new charts live
   in their own components.
