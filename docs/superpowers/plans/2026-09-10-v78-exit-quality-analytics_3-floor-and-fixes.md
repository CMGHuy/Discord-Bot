# v78 — Part 3: Floor rollout and fixes (tasks D1…E1)

> Part of `2026-09-10-v78-exit-quality-analytics_0-index.md`. **Read the
> index's Global Constraints before starting any task here.** D1 and D2 edit
> `analytics.store.ts` and `analytics.ts` — the files every Phase C task
> deliberately avoids. **One writer. Do not run these beside anything.**

**Spec:** `docs/superpowers/specs/2026-09-10-v78-exit-quality-analytics-design.md`

## Part 3 exit criteria

1. No rate chart or table on the Analytics workspace states a percentage for a
   cell below `MIN_CELL_N`; each shows `n` and says the rate was withheld.
2. The SPA nowhere hard-codes `20` — the floor arrives in the payload.
3. The Calibration tab's level table renders the rows `level_calibration`
   actually produced.
4. The group-by picker offers no dimension `stats_by` cannot resolve.
5. Task E1: both suites green in one run.

## One deliberate deviation from the spec

The spec (§3.5) says a sub-floor cell "keeps its bar in a muted *insufficient
sample* treatment". **D1 draws no bar at all instead**, and says why in the
label.

The reason: a muted bar still encodes the unsupported rate *in its length*,
which is precisely the claim being withheld — a reader compares bar lengths
before reading any label, so a 100%-length muted bar on `n=3` still asserts
"best day of the week". A zero-length bar with `Saturday (n=7 — below 20,
rate withheld)` keeps the category visible, which is what v63's contract
actually requires, and withholds the claim completely. It also needs no new
input on `histogram.ts`, so no existing chart's rendering changes.

Recorded here rather than silently implemented, and the spec's §3.5 wording
should be amended in the commit that closes v78.

---

# Phase D — Floor and fixes

### Task D1: The floor at zeroFilledHistogram

**Files:**
- Modify: `frontend/src/app/stores/analytics.store.ts:358-366` (`zeroFilledHistogram`)
  and its two consumers, `directionHistogram` (`:607`) and `dowHistogram` (`:612`)
- Test: `frontend/src/app/workspaces/analytics/analytics.spec.ts`

**Interfaces:**
- Consumes: `minCellN` (C1).
- Produces: `rateOrWithheld(n, rate, floor)` exported from
  `analytics.store.ts`. D2 consumes it at four more call sites.

`zeroFilledHistogram` is the single choke point for the direction and
day-of-week charts, and its `count: row?.win_rate ?? 0` is exactly what renders
a three-trade cell as a full-height bar today. Production's `by.dow` has 6
groups of which 1 is under the floor, and `by.badge` has `VALIDATED` at `n=18` —
under 20, and currently drawn as a confident number.

- [ ] **Step 1: Write the failing tests**

Append to `frontend/src/app/workspaces/analytics/analytics.spec.ts`:

```typescript
import { rateOrWithheld } from '../../stores/analytics.store';

describe('the thin-cell floor', () => {
  it('passes a rate through at or above the floor', () => {
    expect(rateOrWithheld(20, 53.5, 20)).toEqual({ count: 53.5, withheld: false });
  });

  it('withholds the rate below the floor', () => {
    expect(rateOrWithheld(7, 100, 20)).toEqual({ count: 0, withheld: true });
  });

  it('treats an absent cell as withheld rather than a zero rate', () => {
    // v63's contract keeps the category rendered at n=0; what must not
    // happen is a 0% bar reading as "this category always loses".
    expect(rateOrWithheld(0, null, 20)).toEqual({ count: 0, withheld: true });
  });

  it('never hard-codes the floor -- it comes from the payload', () => {
    expect(rateOrWithheld(15, 60, 10)).toEqual({ count: 60, withheld: false });
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npm test -- --include src/app/workspaces/analytics/analytics.spec.ts`
Expected: FAIL — `rateOrWithheld` is not exported.

- [ ] **Step 3: Write the implementation**

In `frontend/src/app/stores/analytics.store.ts`, add above
`zeroFilledHistogram`:

```typescript
/**
 * One rate, one decision: quote it or refuse to.
 *
 * Below `floor` trades a percentage is noise, and a bar is worse than a
 * number because a reader compares lengths before reading labels. So the
 * bar goes to zero and the caller labels the cell with its n instead. The
 * category itself still renders -- v63's contract requires every category
 * present even at n=0; what it does not require is a claim.
 *
 * The floor is passed in, never read from a constant here: it is served as
 * `min_cell_n` so the backend stays its single source (index constraint).
 */
export function rateOrWithheld(
  n: number, rate: number | null | undefined, floor: number,
): { count: number; withheld: boolean } {
  if (n < floor || rate == null) return { count: 0, withheld: true };
  return { count: rate, withheld: false };
}
```

Change `zeroFilledHistogram` to take the floor and apply it:

```typescript
function zeroFilledHistogram(
  rows: BreakdownRow[],
  order: readonly (readonly [string, string])[],
  floor: number,
): HistogramBin[] {
  const byKey = new Map(rows.map((row) => [row.key, row]));
  return order.map(([key, label]) => {
    const row = byKey.get(key);
    const n = row?.n ?? 0;
    const { count, withheld } = rateOrWithheld(n, row?.win_rate, floor);
    return {
      label: withheld
        ? `${label} (n=${n} — below ${floor}, rate withheld)`
        : `${label} (n=${n})`,
      count,
    };
  });
}
```

Pass `minCellN()` at both call sites — `directionHistogram` (`:607`) and
`dowHistogram` (`:612`).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npm test -- --include src/app/workspaces/analytics/analytics.spec.ts`
Expected: PASS. Existing specs in this file that assert dow/direction bar
labels will need their expected strings updated — that is the intended
behaviour change, not a regression.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/stores/analytics.store.ts \
        frontend/src/app/workspaces/analytics/analytics.spec.ts
git commit -m "fix(v78): withhold a win rate below MIN_CELL_N instead of drawing it"
```

---

### Task D2: The floor on the heatmap and the three tables

**Files:**
- Modify: `frontend/src/app/workspaces/analytics/analytics.ts` — the
  strategy×horizon heatmap cells, the generic Group-by table, the
  By-confidence table, and the Calibration level table
- Test: `frontend/src/app/workspaces/analytics/analytics.spec.ts`

**Interfaces:**
- Consumes: `rateOrWithheld` (D1), `store.minCellN()` (C1).
- Produces: nothing later tasks consume.

The heatmap is the worst offender: 46 strategies × 10 horizons is 460 cells
over 782 production trades — a mean of 1.7 trades per cell — so nearly every
cell is currently a coloured claim about almost nothing. `level_calibration`
is the second: it has **no floor of its own** (`calibration.py:64-78` always
emits 5 rows regardless of `n`), which is why fixing D3 and applying this
floor belong in the same plan.

Every one of these four surfaces shows a rate beside an `n` it already has, so
this task adds no data — only the refusal.

- [ ] **Step 1: Write the failing tests**

Append to `analytics.spec.ts`:

```typescript
describe('the floor across every rate surface', () => {
  it('renders a thin heatmap cell as its n, not a colour-weighted rate', () => {
    const el = renderAnalytics({
      strategies: {
        strategies: [],
        heatmap: {
          strategies: ['RSI'], horizons: ['4w'],
          cells: [{ strategy: 'RSI', horizon: '4w', n: 2, win_rate: 100 }],
        },
      },
      exitQuality: { min_cell_n: 20 },
    });
    const cell = el.querySelector('[data-heat-cell]');
    expect(cell?.textContent).toContain('2');
    expect(cell?.textContent).not.toContain('100');
  });

  it('withholds a group-by row rate below the floor but keeps the row', () => {
    const el = renderAnalytics({
      breakdown: [{ key: 'GLW', n: 4, wins: 4, losses: 0, win_rate: 100,
                    expectancy_r: 1.2, profit_factor: null, total_pnl: 40, total_r: 4.8 }],
      exitQuality: { min_cell_n: 20 },
    });
    const text = el.textContent ?? '';
    expect(text).toContain('GLW');
    expect(text).toContain('n=4');
    expect(text).not.toContain('100.0%');
  });
});
```

`renderAnalytics` is this spec file's existing harness — reuse it rather than
building a second one; match its option names to the ones already in the file.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npm test -- --include src/app/workspaces/analytics/analytics.spec.ts`
Expected: FAIL — the thin cell still renders `100`.

- [ ] **Step 3: Write the implementation**

For each of the four surfaces in `analytics.ts`, replace the direct rate
render with the guarded one. The heatmap cell becomes:

```html
<td [attr.data-heat-cell]="true"
    [style.--heat]="cellWithheld(cell) ? '0' : cell.win_rate"
    [class.thin]="cellWithheld(cell)"
    [attr.title]="cellWithheld(cell)
      ? 'n=' + cell.n + ' — below ' + store.minCellN() + ', rate withheld'
      : cell.win_rate + '% on n=' + cell.n">
  {{ cellWithheld(cell) ? 'n=' + cell.n : (cell.win_rate | number: '1.0-0') }}
</td>
```

with, on the component class:

```typescript
  protected cellWithheld = (cell: { n: number; win_rate: number | null }): boolean =>
    rateOrWithheld(cell.n, cell.win_rate, this.store.minCellN()).withheld;
```

Apply the same predicate in the Group-by table's win-rate cell, the
By-confidence table's win-rate cell, and the Calibration level table's rate
cell — each rendering `n=<n>` in place of the percentage when withheld, and
keeping every other column (`n`, `wins`, `losses`, `total_r`, P&L) untouched.
Those columns are counts and sums; they are honest at any sample and the floor
does not apply to them.

Add to `analytics.ts`'s styles:

```css
    .thin { color: var(--text-muted); font-variant-numeric: tabular-nums; }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npm test -- --include src/app/workspaces/analytics/analytics.spec.ts`
Expected: PASS. Also run
`npm test -- --include src/app/workspaces/analytics/analytics.columns.spec.ts`
— it asserts table columns and may pin the win-rate cell's text.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/analytics/analytics.ts \
        frontend/src/app/workspaces/analytics/analytics.spec.ts
git commit -m "fix(v78): apply MIN_CELL_N to the heatmap and the three rate tables"
```

---

### Task D3: The calibration level table has never rendered

**Files:**
- Modify: `swingbot/admin/api_v1/analytics.py:275-280` (`analytics_calibration`)
- Modify: `frontend/src/app/api/models.ts` (`AnalyticsCalibration`)
- Modify: `frontend/src/app/stores/analytics.store.ts` and
  `frontend/src/app/workspaces/analytics/analytics.ts` (the reader)
- Test: `tests/admin/test_api_v1_analytics.py`

**Interfaces:**
- Consumes: `calibration.level_calibration` output as written by
  `snapshots.py:54`.
- Produces: `GET /analytics/calibration` gains a `levels` key; `tiers` is
  retired.

`snapshots.py:54` writes `calibration["levels"]`. The route reads
`calibration.get("tiers", [])` (`analytics.py:277`). Nothing has ever written
`tiers`, so the Calibration tab's table has rendered empty for its whole life —
against five rows of real production data.

The fix serves `levels` under the name `levels` rather than keeping the
`tiers` spelling alive: `tier` as a dimension was **retired deliberately in
v32** (`aggregate.py:88-91`), so the misnomer would be preserving a decision
that was already reversed.

- [ ] **Step 1: Write the failing test**

Append to `tests/admin/test_api_v1_analytics.py`:

```python
def test_calibration_serves_the_levels_the_snapshot_actually_writes(client, auth_headers, monkeypatch):
    """Regression: the route read "tiers" while snapshots.py:54 wrote
    "levels", so this table was empty for its entire life."""
    import swingbot.admin.api_v1.analytics as mod

    monkeypatch.setattr(mod, "_snapshot", lambda fresh=False: {
        "calibration": {"deciles": [], "drift": [],
                        "levels": [{"level": 3, "n": 40, "win_rate": 61.0}]},
    })
    body = client.get("/api/v1/analytics/calibration", headers=auth_headers).get_json()
    assert body["levels"] == [{"level": 3, "n": 40, "win_rate": 61.0}]
    assert "tiers" not in body
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/admin/test_api_v1_analytics.py -k calibration_serves -v`
Expected: FAIL — `KeyError: 'levels'`.

- [ ] **Step 3: Write the implementation**

In `swingbot/admin/api_v1/analytics.py`:

```python
    return jsonify({
        "deciles": calibration.get("deciles", []),
        # v78: was calibration.get("tiers"), which snapshots.py has never
        # written -- it writes "levels" (snapshots.py:54). This table was
        # empty from the day it shipped. Serving it as "levels" rather than
        # restoring the "tiers" spelling: v32 retired "tier" as a dimension
        # (aggregate.py:88-91), so the old name would preserve a reversed
        # decision.
        "levels": calibration.get("levels", []),
        "drift": calibration.get("drift", []),
    })
```

Rename `tiers` → `levels` in the `AnalyticsCalibration` interface in
`models.ts`, in the store's calibration computed, and in the Calibration tab's
template in `analytics.ts`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_analytics.py`
then `cd frontend && npm test -- --include src/app/workspaces/analytics/analytics.spec.ts`
Expected: PASS both.

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/api_v1/analytics.py tests/admin/test_api_v1_analytics.py \
        frontend/src/app/api/models.ts frontend/src/app/stores/analytics.store.ts \
        frontend/src/app/workspaces/analytics/analytics.ts
git commit -m "fix(v78): serve the calibration levels the snapshot writes"
```

---

### Task D4: Remove the dead tier group-by option

**Files:**
- Modify: `frontend/src/app/workspaces/analytics/analytics.ts` (the Group-by
  picker's option list)
- Test: `frontend/src/app/workspaces/analytics/analytics.spec.ts`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing.

`stats_by` raises `ValueError` on an unknown dimension (`aggregate.py:77-78`)
and `tier` is not in `DIMENSIONS` (`:92-93`) — v32 retired it, with the reason
recorded in the comment above the tuple: `confidence` already covers "group
trades by a quality classification" and is the number that actually gates
whether an alert fires. So the picker offers a choice that cannot resolve.
v63 filed this as a follow-up and it is still broken.

**Remove the option, do not restore the dimension.** Restoring it would revive
a decision v32 made deliberately.

- [ ] **Step 1: Write the failing test**

Append to `analytics.spec.ts`:

```typescript
it('offers no group-by dimension the backend cannot resolve', () => {
  // aggregate.DIMENSIONS, as of v78. stats_by raises ValueError on
  // anything else, and "tier" was retired in v32.
  const supported = ['strategy', 'horizon', 'badge', 'confidence',
                     'direction', 'dow', 'month', 'ticker', 'source'];
  const el = renderAnalytics({ exitQuality: { min_cell_n: 20 } });
  const options = [...el.querySelectorAll('[data-groupby-option]')]
    .map((o) => (o.getAttribute('value') ?? o.textContent ?? '').trim());
  expect(options.length).toBeGreaterThan(0);
  for (const option of options) expect(supported).toContain(option);
});
```

If the picker's options carry no `data-groupby-option` attribute today, add it
in Step 3 — the test needs a stable hook, and the attribute is the smallest one.

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- --include src/app/workspaces/analytics/analytics.spec.ts`
Expected: FAIL — `Expected [...] to contain 'tier'` inverted, i.e. the
assertion trips on the `tier` option.

- [ ] **Step 3: Write the implementation**

Delete the `tier` entry from the Group-by picker's option list in
`analytics.ts`, and add `data-groupby-option` to the rendered option element.
Leave a one-line comment where it was:

```typescript
// "tier" removed in v78: retired from aggregate.DIMENSIONS in v32, so
// stats_by("tier") raises. Filed by v63; the option never resolved.
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- --include src/app/workspaces/analytics/analytics.spec.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/analytics/analytics.ts \
        frontend/src/app/workspaces/analytics/analytics.spec.ts
git commit -m "fix(v78): drop the group-by option retired in v32"
```

---

# Phase E — Verification

### Task E1: Full-suite verification

**Files:** none — this task only runs and fixes.

This is the plan's **single** full-suite gate, covering A1 through D4. Neither
suite has been run in full at any earlier point, by design.

- [ ] **Step 1: Run the Python suite once**

Run: `python scripts/dev/testrun.py full` — or dispatch the `test-runner`
subagent so ~1150 progress lines stay out of the session's context.
Expected: `0 failed`, `0 xfailed`. A changed *pass count* is not a failure —
this plan adds tests.

- [ ] **Step 2: Run the frontend suite once**

Run: `cd frontend && npm test`
Expected: green. This plan touched `frontend/`, so this run is mandatory, not
optional.

- [ ] **Step 3: Fix forward from whatever the runs name**

A red result here is the start of the work, not a reason to re-litigate an
earlier task. The likely failures, all expected consequences of D1/D2 rather
than bugs:

- `analytics.spec.ts` / `analytics.columns.spec.ts` specs that pin the old
  dow/direction bar labels or a thin cell's percentage — update the expected
  strings to the withheld form.
- `tests/analytics/test_snapshots.py`, if it asserts an exact `by.*` row shape
   — `total_r` is a new key (A1).
- `tests/analytics/test_aggregate.py` positional `StatRow(...)` constructions —
  `total_r` was added last with a default for exactly this reason.

- [ ] **Step 4: Confirm nothing is uncommitted**

Run: `git status --short`
Expected: clean. **This tree is shared with concurrent sessions** — if files
you did not touch appear, leave them alone and say so rather than committing
them.

- [ ] **Step 5: Commit**

```bash
git commit --allow-empty -m "chore(v78): full-suite verification"
```

Then close the plan out per `docs/claude/document-lifecycle.md`: move the spec
and all four plan files to `implemented/`, resolve `Bump: bot patch · ui minor`
against the **then-current** `VERSION.json` (never a number written here),
regenerate the version history in the same commit, and amend the spec's §3.5
wording per Part 3's recorded deviation.
