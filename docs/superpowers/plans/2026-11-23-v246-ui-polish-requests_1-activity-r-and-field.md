# v246 — UI polish, Plan A of five: requests — Part 1: Recent activity R, whole-R buckets, `sb-field`

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V246-3" -A 400 <this file>`).

**Spec:** [2026-11-23-v246-ui-polish-filters-charts-interactions-design.md](../specs/2026-11-23-v246-ui-polish-filters-charts-interactions-design.md) §A1 (Recent activity), §A2 (the `sb-field` rule and date ranges), §A3 (the R-distribution sentence), and the A rows of "Error, empty and edge states" and "Testing".
**Index:** [2026-11-23-v246-ui-polish-requests_0-index.md](2026-11-23-v246-ui-polish-requests_0-index.md) — Goal, Global Constraints, Parallelisation, the task ledger and the binding `## Handoff` decisions live there; every task below implicitly includes them.

Tasks: V246-1 (Recent activity), V246-2 (whole-R buckets, the one backend task), V246-3 (`sb-field` and the width tokens), V246-4 (the label drop in `sb-select` / `sb-text-input`, `sb-date-range` as one field).

V246-1, V246-2 and V246-3 touch disjoint files and may run in either order; V246-4 needs V246-3 (`SB_FIELD`, `--sb-control-w`, `--field-m`). All frontend commands run from the worktree root with `cd frontend &&`; `--include` paths are relative to `frontend/`.

---

# Phase 1 — Recent activity and the R distribution

### Task V246-1: Recent activity shows the signed R only; accessible name keeps the status; cost-basis hint

**Model:** haiku — a one-string change in a pure function, one `aria-label` binding and one hint sentence, all with tests written out below.

**Files:**
- Modify: `frontend/src/app/workspaces/dashboard/panels/activity.ts:56-58` (the closed row's `detail`)
- Modify: `frontend/src/app/workspaces/dashboard/panels/activity.spec.ts:27-35` (the wording test) and add one test
- Modify: `frontend/src/app/workspaces/dashboard/panels/recent-activity.ts` (button `aria-label`, `rowName()`)
- Modify: `frontend/src/app/workspaces/dashboard/panels/recent-activity.spec.ts:116` (fixture) and add a `describe`
- Modify: `frontend/src/app/workspaces/dashboard/panels/panel-help.ts:19-20` (`PANEL_HELP.recentActivity`)
- Test: `frontend/src/app/workspaces/dashboard/panels/panel-help.spec.ts` (one added test)

**Interfaces:**
- Consumes: `rMultiple(value)` from `ui/format.ts` (true minus, two decimals, `+` for gains, unsigned zero: `rMultiple(0) === '0.00R'`); `dateTime` from `ui/format.ts` (already imported, bound as `fmt`).
- Produces: nothing a later task reads. `ActivityEvent` keeps its shape; only the `detail` text of a closed row changes.

**Why each piece.** Spec §A1: `SOFI Closed at −1.00R` repeats what the status icon already shows, so a closed row with an R shows just the R, coloured by sign by the existing `.detail.pos` / `.detail.neg` rules (sign only, never a verdict word). A closed row **without** an R keeps the word `Closed`, so the row is never blank. Opened rows (`at 204.46`) and cancelled rows are unchanged. The `button.event-hit` has no accessible name of its own today (the status word lives only on the icon's `aria-label`), so dropping the visible word would leave a screen reader with "SOFI −1.00R". The button gets an explicit `aria-label`: `"<ticker> <kind>, <detail>, <time>"` — `"SOFI closed, −1.00R, …"` — plus `", now <Status>"` when the row has since moved to a status other than the one its event implies (an opened event for a plan that is now Partial), because an `aria-label` on the button hides the icon's own label. The trade drawer's "Closed at" field (`trade-drawer.ts:90`) is a price label, not this text, and stays.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/app/workspaces/dashboard/panels/activity.spec.ts`, replace the test at lines 27-35 (`'words a close with the true minus for a loss, plain for zero, plus for a gain'`) with these two tests:

```ts
  it('shows a close as the signed R alone: true minus for a loss, plain for zero, plus for a gain (v246 §A1)', () => {
    const detail = (r: number) => deriveActivity([
      row({ status: 'CLOSED', closed_at: '2026-09-11T16:20:00Z', r_multiple: r }),
    ]).find((e) => e.kind === 'closed')!.detail;
    expect(detail(-0.3)).toBe('−0.30R');
    expect(detail(-0.3)).not.toContain('-');
    expect(detail(-0.3)).not.toContain('Closed');
    expect(detail(0)).toBe('0.00R');
    expect(detail(1.5)).toBe('+1.50R');
  });

  it('keeps the word Closed for a close with no R, so the row is never blank (v246 §A1)', () => {
    for (const r of [null, undefined]) {
      const event = deriveActivity([
        row({ status: 'CLOSED', closed_at: '2026-09-11T16:20:00Z', r_multiple: r }),
      ]).find((e) => e.kind === 'closed')!;
      expect(event.detail).toBe('Closed');
      expect(event.r).toBeNull();
    }
  });
```

In `frontend/src/app/workspaces/dashboard/panels/recent-activity.spec.ts`, change the closed fixture's detail at line 116 from `detail: 'Closed at +1.20R'` to `detail: '+1.20R'`, then append this `describe` at the end of the file (`SOURCE`, `TestBed`, `provideRouter` and `provideZonelessChangeDetection` are already imported or declared at the top of the file):

```ts
describe('recent activity row names (v246 §A1)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(), provideRouter([])],
    });
  });

  const ROWS = [
    { kind: 'closed', at: '2026-09-11T14:00:00Z', ticker: 'SOFI', direction: 'bullish', status: 'CLOSED',
      detail: '−1.00R', r: -1, id: 's:closed', tradeId: 's' },
    { kind: 'closed', at: '2026-09-11T13:00:00Z', ticker: 'HOOD', direction: 'bullish', status: 'CLOSED',
      detail: 'Closed', r: null, id: 'h:closed', tradeId: 'h' },
    { kind: 'opened', at: '2026-09-11T12:00:00Z', ticker: 'ASTS', direction: 'bearish', status: 'PARTIAL',
      detail: 'at 60.54', r: null, id: 'a:opened', tradeId: 'a' },
    { kind: 'opened', at: '2026-09-11T11:00:00Z', ticker: 'NVDA', direction: 'bullish', status: 'ACTIVE',
      detail: 'at 120.10', r: null, id: 'n:opened', tradeId: 'n' },
  ];

  function mount() {
    const f = TestBed.createComponent(RecentActivity);
    f.componentRef.setInput('events', ROWS);
    f.detectChanges();
    return f.nativeElement as HTMLElement;
  }

  function names(): string[] {
    return [...mount().querySelectorAll<HTMLButtonElement>('button.event-hit')]
      .map((b) => b.getAttribute('aria-label') ?? '');
  }

  it('keeps the status word in the accessible name although the row no longer prints it', () => {
    const [sofi] = names();
    expect(sofi.startsWith('SOFI closed, −1.00R, ')).toBe(true);
  });

  it('names a close with no R once, not "closed, Closed"', () => {
    const hood = names()[1];
    expect(hood.startsWith('HOOD closed, ')).toBe(true);
    expect(hood).not.toContain('Closed');
  });

  it('says where an opened plan stands now when it has moved on, and only then', () => {
    const [, , asts, nvda] = names();
    expect(asts.startsWith('ASTS opened, at 60.54, ')).toBe(true);
    expect(asts.endsWith(', now Partial')).toBe(true);
    expect(nvda).not.toContain('now');
  });

  it('prints the signed R alone and colours it by sign only, never by a verdict class', () => {
    const detail = mount().querySelector('.detail')!;
    expect(detail.textContent!.trim()).toBe('−1.00R');
    expect(detail.classList).toContain('neg');
    expect(SOURCE).not.toMatch(/class\.(win|loss)/);
  });
});
```

In `frontend/src/app/workspaces/dashboard/panels/panel-help.spec.ts`, append inside the `describe('dashboard tooltip copy (A4 audit)', …)` block:

```ts
  it('says the Recent activity R is pre-tax and before modelled frictions (v246 §A1)', () => {
    expect(PANEL_HELP.recentActivity).toContain('pre-tax and before modelled frictions');
  });
```

- [ ] **Step 2: Run the specs to verify they fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/dashboard/panels/activity.spec.ts --include src/app/workspaces/dashboard/panels/recent-activity.spec.ts --include src/app/workspaces/dashboard/panels/panel-help.spec.ts`
Expected: FAIL — `expected 'Closed at −0.30R' to be '−0.30R'`, the row-name tests read `''` (the button has no `aria-label`), and the hint test does not find `pre-tax and before modelled frictions`.

- [ ] **Step 3: Implement**

In `frontend/src/app/workspaces/dashboard/panels/activity.ts`, replace lines 56-58:

```ts
        detail: cancelled
          ? 'Plan cancelled before filling'
          // v246 §A1: the status icon already says "closed"; the row shows
          // the signed R alone. No R -> the word, so the row is never blank.
          : (row.r_multiple != null ? rMultiple(row.r_multiple) : 'Closed'),
```

In `frontend/src/app/workspaces/dashboard/panels/recent-activity.ts`:

1. Under the `STATUS_LABEL` map (after line 21) add:

```ts
/** The event's own verb, for the row's accessible name (v246 §A1). */
const KIND_WORD: Record<ActivityEvent['kind'], string> = {
  opened: 'opened',
  closed: 'closed',
  cancelled: 'cancelled',
};

/** The status each kind implies; a row whose current status differs has
 *  moved on since the event, and its name says so. */
const KIND_STATUS: Record<ActivityEvent['kind'], string> = {
  opened: 'Open',
  closed: 'Closed',
  cancelled: 'Cancelled',
};
```

2. On the row button (lines 37-38) add the binding, so the opening tag reads:

```html
              <button type="button" class="event-hit" aria-haspopup="dialog"
                      [attr.aria-label]="rowName(event)"
                      (click)="eventActivate.emit(event)">
```

3. In the class, after `statusLabel()`, add:

```ts
  /** The row's accessible name: "SOFI closed, −1.00R, <time>". The button's
   *  aria-label replaces its children's names, so the status word and the
   *  time the row shows are both carried here (v246 §A1). A close with no R
   *  prints "Closed" as its detail; the name says "closed" once. */
  protected rowName(event: ActivityEvent): string {
    const parts = [`${event.ticker} ${KIND_WORD[event.kind]}`];
    if (event.detail && event.detail !== 'Closed') parts.push(event.detail);
    parts.push(this.fmt(event.at));
    const status = this.statusLabel(event);
    if (status !== KIND_STATUS[event.kind]) parts.push(`now ${status}`);
    return parts.join(', ');
  }
```

The `.detail` span, its `[class.pos]` / `[class.neg]` bindings and its CSS stay exactly as they are: colour by sign, no verdict word.

In `frontend/src/app/workspaces/dashboard/panels/panel-help.ts`, replace lines 19-20:

```ts
  recentActivity:
    'The latest events on your trade plans, newest first: entries, partial exits, exits and cancellations. '
    + 'A closed row shows its result in R, pre-tax and before modelled frictions, the same basis as the '
    + 'figures above.',
```

- [ ] **Step 4: Run the specs to verify they pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/dashboard/panels/activity.spec.ts --include src/app/workspaces/dashboard/panels/recent-activity.spec.ts --include src/app/workspaces/dashboard/panels/panel-help.spec.ts`
Expected: PASS, 0 failed.

Then check nothing else asserted the old wording: `git grep -n "Closed at" -- frontend/src` lists only `trade-drawer.ts` (the price label) and its spec. A hit anywhere else is a test to update in this task.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/dashboard/panels/activity.ts frontend/src/app/workspaces/dashboard/panels/activity.spec.ts frontend/src/app/workspaces/dashboard/panels/recent-activity.ts frontend/src/app/workspaces/dashboard/panels/recent-activity.spec.ts frontend/src/app/workspaces/dashboard/panels/panel-help.ts frontend/src/app/workspaces/dashboard/panels/panel-help.spec.ts
git commit -m "feat(v246): Recent activity shows the signed R alone; row keeps its status in the accessible name" -m "A closed row with no R still reads Closed. The panel hint states the R is pre-tax and before modelled frictions."
```

### Task V246-2: R distribution on whole-R edges: `histogram(..., whole_r=True)` for `r_multiples` only; labels by lower edge (bot patch)

**Model:** sonnet — a backend opt-in mode with a frozen golden file to hand-edit and a frontend label change; several files, one clear rule.

**Files:**
- Modify: `swingbot/core/analytics/metrics.py:870-889` (`histogram` gains `whole_r`, new helper `_whole_r_histogram`)
- Modify: `swingbot/core/analytics/page_bodies.py:197` (`r_multiples` passes `whole_r=True`)
- Modify: `tests/analytics/test_metrics_derived.py` (after line 230, the histogram block) — see the note below on the ledger's file names
- Modify: `tests/admin_snapshots/golden/performance_main.json` (the `distributions.r_multiples` array only)
- Modify: `frontend/src/app/workspaces/analytics/tabs/overview.ts:419-423` (`rBins` label), `:440` (`rColumns` range text)
- Modify: `frontend/src/app/workspaces/analytics/tabs/overview.spec.ts` (one added `describe`)

**Ledger note (files).** The index ledger lists `tests/analytics/test_metrics_ratios.py`, `tests/analytics/test_snapshots.py` and `tests/admin_snapshots/golden/analytics_snapshot.json` for this task. Read against the code: the existing `histogram` tests live in `tests/analytics/test_metrics_derived.py:214-231` (imported there at line 12), so the new tests go beside them; `analytics_snapshot.json` stores `r_multiples` as the **raw list of R values** (`snapshots.py:78`, `metrics.r_multiples(closed)`), not as buckets, so neither it nor `test_snapshots.py` changes. No other task touches these files.

**Interfaces:**
- Consumes: `metrics.r_multiples(scoped) -> list[float]` (unchanged); frontend `signed(value, decimals)` from `ui/format.ts` (true minus, `+` for a gain, unsigned zero; already imported in `overview.ts` line 12).
- Produces: `metrics.histogram(values: list[float], *, bins: int = 20, whole_r: bool = False) -> list[dict]`. With `whole_r=True` the rows are `{lo: int, hi: int, count: int}`, `hi == lo + 1`, from `floor(min)` to `floor(max) + 1`, empty interior buckets kept, `bins` ignored. `distributions.r_multiples` in `/api/v1/analytics/performance` uses it; `distributions.returns` and `exit_quality` keep the default mode byte-identical. Frontend `rBins` labels are the lower edge: `−5R`, `0R`, `+1R`. V246-15 later edits other parts of `overview.ts` and `overview.spec.ts`.

**Why.** Spec §A3: the R distribution is labelled at odd centres (−4.9R, −3.9R) because the server cuts `[min, max]` into 12 equal widths. Handoff decision 1: an opt-in whole-R mode on `metrics.histogram`, used only by the R-distribution payload; the default and its two other callers do not change. Decision 11: the range is `floor(min)` to `floor(max) + 1`, step 1, empty interior buckets kept; no tail clamp, so an outlier shows as its own bucket. Bucket `[k, k+1)` holds `k <= r < k+1`, so `2.0` lands in `[2, 3)` and `−1.6` in `[−2, −1)`. The `{lo, hi, count}` shape is unchanged (no schema change; `schema-evolution.md` does not apply). The golden files are frozen (`record_golden.write` refuses to overwrite, V204-1), so the one changed array is edited by hand.

- [ ] **Step 1: Write the failing backend tests**

Append to `tests/analytics/test_metrics_derived.py`, directly after `test_histogram_of_a_single_repeated_value_does_not_divide_by_zero` (line 230):

```python
def test_histogram_default_mode_is_unchanged_by_whole_r():
    """v246: the equal-width mode `returns` and `exit_quality` use stays byte-identical."""
    values = [-1.6, 2.0, -0.35, 0.4, 0.4]
    expected = [
        {"lo": -1.6, "hi": -0.7, "count": 1},
        {"lo": -0.7, "hi": 0.2, "count": 1},
        {"lo": 0.2, "hi": 1.1, "count": 2},
        {"lo": 1.1, "hi": 2.0, "count": 1},
    ]
    assert histogram(values, bins=4) == expected
    assert histogram(values, bins=4, whole_r=False) == expected


def test_histogram_whole_r_puts_buckets_on_whole_r_edges():
    h = histogram([-1.6, -0.35, 0.4, 0.4, 2.0], whole_r=True)
    assert h == [
        {"lo": -2, "hi": -1, "count": 1},
        {"lo": -1, "hi": 0, "count": 1},
        {"lo": 0, "hi": 1, "count": 2},
        {"lo": 1, "hi": 2, "count": 0},   # empty interior bucket kept
        {"lo": 2, "hi": 3, "count": 1},   # 2.0 is the lower edge of [2, 3)
    ]
    assert all(isinstance(b["lo"], int) and isinstance(b["hi"], int) for b in h)


def test_histogram_whole_r_ignores_bins():
    values = [-0.5, 0.5, 1.5]
    assert histogram(values, bins=2, whole_r=True) == histogram(values, bins=50, whole_r=True)
    assert len(histogram(values, bins=2, whole_r=True)) == 3


def test_histogram_whole_r_keeps_an_outlier_in_its_own_bucket():
    h = histogram([-1.0, -0.2, 6.3], whole_r=True)
    assert [b["lo"] for b in h] == [-1, 0, 1, 2, 3, 4, 5, 6]
    assert h[-1] == {"lo": 6, "hi": 7, "count": 1}
    assert sum(b["count"] for b in h) == 3


def test_histogram_whole_r_edge_cases():
    assert histogram([], whole_r=True) == []
    assert histogram([1.0, 1.0], whole_r=True) == [{"lo": 1, "hi": 2, "count": 2}]
    assert histogram([-0.0], whole_r=True) == [{"lo": 0, "hi": 1, "count": 1}]
    assert histogram([-3.0], whole_r=True) == [{"lo": -3, "hi": -2, "count": 1}]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/analytics/test_metrics_derived.py`
Expected: FAIL — `TypeError: histogram() got an unexpected keyword argument 'whole_r'` in the five new tests; the old histogram tests pass.

- [ ] **Step 3: Implement the backend mode**

In `swingbot/core/analytics/metrics.py`, replace `histogram` (lines 870-889) with the two functions below (`math` is already imported at line 15):

```python
def histogram(values: list[float], *, bins: int = 20, whole_r: bool = False) -> list[dict]:
    """Equal-width buckets spanning [min, max], as `{lo, hi, count}` rows.

    Empty interior buckets are KEPT. A histogram that drops them silently
    redraws its own x-axis and turns a bimodal distribution into a flat one.
    An empty input is an empty list, not `bins` zero-count rows -- "no data"
    and "all buckets empty" are different statements.

    `whole_r=True` (v246, the R distribution only): unit buckets on whole
    edges instead -- see `_whole_r_histogram`. `bins` is ignored there.
    """
    if whole_r:
        return _whole_r_histogram(values)
    if not values or bins < 1:
        return []
    lo, hi = min(values), max(values)
    if hi == lo:
        # Degenerate range: one bucket holding everything beats dividing by 0.
        return [{"lo": round(lo, 6), "hi": round(hi, 6), "count": len(values)}]
    width = (hi - lo) / bins
    counts = [0] * bins
    for v in values:
        counts[min(int((v - lo) / width), bins - 1)] += 1   # top edge -> last bucket
    return [{"lo": round(lo + i * width, 6), "hi": round(lo + (i + 1) * width, 6),
             "count": c} for i, c in enumerate(counts)]


def _whole_r_histogram(values: list[float]) -> list[dict]:
    """Unit buckets `[k, k+1)` from floor(min) to floor(max) + 1 (v246).

    Integer edges, so the chart labels each bucket by its lower edge
    (-5R, 0R, +1R) instead of an odd centre. Empty interior buckets are
    kept, like the equal-width mode, and nothing is clamped: an outlier
    gets its own bucket rather than being folded into a neighbour.
    """
    if not values:
        return []
    start = math.floor(min(values))
    counts = [0] * (math.floor(max(values)) + 1 - start)
    for v in values:
        counts[math.floor(v) - start] += 1
    return [{"lo": start + i, "hi": start + i + 1, "count": c} for i, c in enumerate(counts)]
```

In `swingbot/core/analytics/page_bodies.py`, change line 197 only:

```python
            "r_multiples": m.histogram(m.r_multiples(scoped), whole_r=True),
```

Line 196 (`"returns": m.histogram(returns, bins=12),`) and `exit_quality.py:95` stay as they are.

- [ ] **Step 4: Run the unit tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/analytics/test_metrics_derived.py`
Expected: PASS, 0 failed.

Run: `python scripts/dev/complexity_gate.py`
Expected: no new finding (`histogram` gains one branch, `_whole_r_histogram` is 3).

- [ ] **Step 5: Update the frozen golden payload by hand**

The golden book's closed trades are six at −1.6R and six at +2.0R, so whole-R buckets run from `floor(−1.6) = −2` to `floor(2.0) + 1 = 3`. Rewrite only `distributions.r_multiples` in `tests/admin_snapshots/golden/performance_main.json`, keeping the writer's exact format (`record_golden.write`: `json.dumps(..., indent=2, sort_keys=True) + "\n"`), with this one-off script run from the worktree root (do not commit the script):

```bash
python - <<'EOF'
import json
from pathlib import Path

path = Path("tests/admin_snapshots/golden/performance_main.json")
body = json.loads(path.read_text("utf-8"))
body["distributions"]["r_multiples"] = [
    {"count": 6, "hi": -1, "lo": -2},
    {"count": 0, "hi": 0, "lo": -1},
    {"count": 0, "hi": 1, "lo": 0},
    {"count": 0, "hi": 2, "lo": 1},
    {"count": 6, "hi": 3, "lo": 2},
]
path.write_bytes((json.dumps(body, indent=2, sort_keys=True) + "\n").encode("utf-8"))
EOF
git diff --stat tests/admin_snapshots/golden/performance_main.json
```

Expected: one file changed, and `git diff` shows a single hunk inside `"r_multiples"`. If the diff touches anything else (float reprints, key order, line endings), revert the file with `git checkout -- tests/admin_snapshots/golden/performance_main.json` and make the same edit by hand in an editor instead. `distributions.returns` must not change.

- [ ] **Step 6: Run the golden parity test**

This test reaches the local Postgres test database: if this session has not synced the replica yet, run `/replicate-prod-db` first (one shared `swing-db` container, port 56789).

Run: `python scripts/dev/testrun.py file tests/admin_snapshots/test_golden_today.py`
Expected: PASS, 0 failed — `test_today_matches_golden` now matches the integer edges, `returns` still matches its frozen equal-width buckets, and `test_golden_files_are_never_overwritten` still passes (the file was edited, not re-recorded).

Run: `python scripts/dev/testrun.py file tests/admin/test_api_analytics.py`
Expected: PASS (it asserts the `distributions` shape only, `{"returns": list, "r_multiples": list}`).

- [ ] **Step 7: Write the failing frontend test**

Append to `frontend/src/app/workspaces/analytics/tabs/overview.spec.ts` (after the last `describe`; `render`, `signal` and `TestBed` are already in the file):

```ts
describe('R distribution on whole-R edges (v246 §A3)', () => {
  beforeEach(() => TestBed.resetTestingModule());

  const BUCKETS = [
    { lo: -5, hi: -4, count: 1 },
    { lo: -1, hi: 0, count: 4 },
    { lo: 0, hi: 1, count: 3 },
    { lo: 1, hi: 2, count: 2 },
  ];

  function withBuckets() {
    return render({
      performance: signal({
        totals: { total: 40, open: 6, closed: 34 }, win_rate: 53.5, win_rate_n: 34,
        expectancy_r: -0.136, expectancy_n: 34, derived: { total_return_pct: 4.2 },
        distributions: { returns: [], r_multiples: BUCKETS },
        calendar: [], rolling_wr: [], rolling_exp_r: [], relocated: {}, by_confidence: {},
        scope: {}, n: 312,
      }),
    });
  }

  it('labels each bucket by its lower edge: true minus, plus for a gain, bare zero', () => {
    const { fixture } = withBuckets();
    expect(fixture.componentInstance.rBins().map((b) => b.label)).toEqual(['−5R', '−1R', '0R', '+1R']);
    expect(fixture.componentInstance.rBins().map((b) => b.count)).toEqual([1, 4, 3, 2]);
  });

  it('marks only the buckets below zero as negative', () => {
    const { fixture } = withBuckets();
    const tab = fixture.componentInstance;
    expect(tab.rBins().map((b) => tab.negativeBin(b))).toEqual([true, true, false, false]);
  });

  it('prints the table range with the true minus, never a hyphen', () => {
    const { fixture } = withBuckets();
    const range = fixture.componentInstance['rColumns'].find((c) => c.key === 'range')!;
    expect(range.value(BUCKETS[0])).toBe('−5R to −4R');
    expect(range.value(BUCKETS[2])).toBe('0R to +1R');
    expect(String(range.value(BUCKETS[0]))).not.toContain('-');
  });
});
```

- [ ] **Step 8: Run it to verify it fails**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/analytics/tabs/overview.spec.ts`
Expected: FAIL — labels read `'−5.0R'`, `'0.0R'`, `'1.0R'`; the range reads `'-5R to -4R'`.

- [ ] **Step 9: Implement the frontend labels**

In `frontend/src/app/workspaces/analytics/tabs/overview.ts`, replace `rBins` (lines 419-423):

```ts
  /** v246 §A3: the server buckets R on whole edges ([−5, −4) …), so each
   *  bucket is labelled by its lower edge: "−5R", "0R", "+1R". `signed`
   *  prints the true minus and leaves zero unsigned, so a bucket starting
   *  at zero is never marked negative by `negativeBin`. */
  readonly rBins = computed(() => (this.store.performance()?.distributions.r_multiples ?? [])
    .map((b) => ({ label: `${signed(b.lo, 0)}R`, count: b.count })));
```

and the `range` column at line 440:

```ts
    { key: 'range', header: 'R range', value: (row) => `${signed(row.lo, 0)}R to ${signed(row.hi, 0)}R` },
```

If `fixed` is no longer used anywhere in `overview.ts` after this edit, drop it from the `ui/format` import on line 12 (`git grep -n "fixed(" -- frontend/src/app/workspaces/analytics/tabs/overview.ts` decides; today `relocatedRows` still uses it).

- [ ] **Step 10: Run it to verify it passes**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/analytics/tabs/overview.spec.ts`
Expected: PASS, 0 failed.

- [ ] **Step 11: Commit (two scoped commits)**

```bash
git add swingbot/core/analytics/metrics.py swingbot/core/analytics/page_bodies.py tests/analytics/test_metrics_derived.py tests/admin_snapshots/golden/performance_main.json
git commit -m "feat(v246): R distribution buckets on whole-R edges (histogram whole_r mode, r_multiples only)" -m "returns and exit_quality keep the equal-width mode byte-identical; the frozen golden's r_multiples array is edited by hand."
git add frontend/src/app/workspaces/analytics/tabs/overview.ts frontend/src/app/workspaces/analytics/tabs/overview.spec.ts
git commit -m "feat(v246): label R-distribution buckets by their lower edge with the true minus"
```


# Phase 2 — `sb-field`

### Task V246-3: `sb-field` and the `--field-s/m/l` width tokens

**Model:** sonnet — a new standalone component with an injection token and CSS-source specs; the contract is fixed by the ledger and written out below.

**Files:**
- Create: `frontend/src/app/ui/field.ts`
- Create: `frontend/src/app/ui/field.spec.ts`
- Modify: `frontend/src/styles/tokens.css:311` (three tokens after `--control-h: 28px;`)
- Modify: `frontend/src/app/ui/tokens.spec.ts:84` (`REQUIRED` list) and the `'design tokens'` describe (one added test)

**Interfaces:**
- Consumes: `--control-h`, `--space-4` (`styles/tokens.css`); the global `.sb-label` caption style (`frontend/src/styles.css:118`); `resolveToken(name)` from `frontend/src/app/ui/testing/resolve-token.ts` (throws on an unknown token).
- Produces (final, consumed by V246-4 and V246-7..V246-11):
  - `export type FieldSize = 's' | 'm' | 'l' | 'auto';`
  - `export interface FieldContext { readonly label: Signal<string>; }`
  - `export const SB_FIELD = new InjectionToken<FieldContext>('SB_FIELD');`
  - `export class Field` (selector `sb-field`): `readonly label = input<string>('')`, `readonly size = input<FieldSize>('m')`, `readonly fullRow = input<boolean>(false)`; provides `SB_FIELD` (itself) to its projected content.
  - Host: attribute `data-size="<size>"`, class `no-label` when `label()` is empty, class `full-row` when `fullRow()`. CSS custom property `--sb-control-w` = `var(--field-s|m|l)` by size, `100%` below 640px (except `auto`), reset to the guaranteed-invalid value for `auto` (controls fall back to their own width).
  - Tokens `--field-s: 136px`, `--field-m: 176px`, `--field-l: 240px` (not raised in the touch block: heights grow on touch, widths do not).
  - Markup a consumer writes: `<sb-field label="Strategy" size="m"><sb-select … /></sb-field>`; in `sb-toolbar` the `sb-field` carries `slot="<id>"` (brief Trap 3).

**Why.** Spec §A2: a select with a label above it is taller than a control without one, so a centred bar puts their boxes at different heights. One wrapper owns the label line for every control in a bar; with no label the line keeps its height as an `aria-hidden` filler, so every field in a bar is the same height and the controls' bottoms line up. Handoff decision 2: the field owns the label and the wrapped control drops its own (V246-4 does that half), so the field's visible label is `aria-hidden` and the control keeps the accessible name. Decision 10: the inputs are `label`, `size`, `fullRow`; `size='auto'` is for month arrows and segmented groups, which have no width token; `fullRow` carries "controls that take a full row below 640px drop the empty label filler". Widths, chosen from the widest current option text at 16px touch control text (`--text-control`): S fits a short select such as "Any horizon" or "Confidence" (≈ 95px of text + 8px padding each side + ≈ 20px chevron), M fits a native date input (`dd/mm/yyyy` + picker icon) or "Any strategy", L fits a free-text search with room for a ticker list; all three sit on the 8px grid. Below 640px a field fills its row or grid cell instead (spec "Phone": equal widths, not "each select as wide as its text").

- [ ] **Step 1: Write the failing token test**

In `frontend/src/app/ui/tokens.spec.ts`, add three names to `REQUIRED` directly after `'--control-h',` (line 84):

```ts
  // v246 §A2: the widths of an sb-field in a filter bar
  '--field-s',
  '--field-m',
  '--field-l',
```

and add this test inside `describe('design tokens', …)`, after `'sizes controls with a single height token'`:

```ts
  it('sizes bar fields S < M < L in px, and the touch block leaves widths alone (v246 §A2)', () => {
    const px = (name: string) => Number(CSS.match(new RegExp(`^\\s*${name}:\\s*(\\d+)px;`, 'm'))?.[1]);
    expect(px('--field-s')).toBe(136);
    expect(px('--field-m')).toBe(176);
    expect(px('--field-l')).toBe(240);
    const at = CSS.indexOf('@media (pointer: coarse), (max-width: 1023px)');
    const touch = CSS.slice(at, CSS.indexOf('\n}\n', at));
    expect(touch).toContain('--control-h: 44px');
    expect(touch).not.toContain('--field-');
  });
```

- [ ] **Step 2: Write the failing component spec**

Create `frontend/src/app/ui/field.spec.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { Component, inject, provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { Field, FieldSize, SB_FIELD } from './field';
import { resolveToken } from './testing/resolve-token';

const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/field.ts'), 'utf8');
const PHONE = SOURCE.match(/@media \(max-width: 639px\) \{([\s\S]*?)\n {4}\}/)?.[1] ?? '';

/** Stands in for sb-select / sb-text-input: reads the field context the way they will (V246-4). */
@Component({ selector: 'sb-probe', template: '{{ ctx?.label() ?? "none" }}' })
class Probe {
  readonly ctx = inject(SB_FIELD, { optional: true });
}

@Component({
  imports: [Field, Probe],
  template: `
    <sb-field [label]="label()" [size]="size()" [fullRow]="fullRow()">
      <sb-probe id="probe" />
    </sb-field>
  `,
})
class Host {
  readonly label = signal('Strategy');
  readonly size = signal<FieldSize>('m');
  readonly fullRow = signal(false);
}

function host(setup: (h: Host) => void = () => {}) {
  const f = TestBed.createComponent(Host);
  setup(f.componentInstance);
  f.detectChanges();
  const el = f.nativeElement as HTMLElement;
  return { f, el, field: el.querySelector('sb-field') as HTMLElement };
}

describe('Field (v246 §A2)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('draws the label line above the projected control', () => {
    const { field } = host();
    const label = field.querySelector('.field-label')!;
    expect(label.textContent!.trim()).toBe('Strategy');
    expect(label.classList).toContain('sb-label');
    expect(field.firstElementChild).toBe(label);
    expect(field.querySelector('#probe')).not.toBeNull();
  });

  it('keeps an empty label line as an aria-hidden filler, so every field in a bar is one height', () => {
    const { field } = host((h) => h.label.set(''));
    const filler = field.querySelector('.field-label')!;
    expect(filler.classList).toContain('filler');
    expect(filler.textContent).toBe(' ');
    expect(filler.getAttribute('aria-hidden')).toBe('true');
    expect(field.classList).toContain('no-label');
  });

  it('hides its visible label from assistive tech: the wrapped control carries the name', () => {
    const { field } = host();
    expect(field.querySelector('.field-label')!.getAttribute('aria-hidden')).toBe('true');
    expect(field.classList).not.toContain('no-label');
  });

  it('hands its label to the projected control through SB_FIELD, and follows changes', () => {
    const { f, el } = host();
    expect(el.querySelector('#probe')!.textContent).toBe('Strategy');
    f.componentInstance.label.set('Horizon');
    f.detectChanges();
    expect(el.querySelector('#probe')!.textContent).toBe('Horizon');
  });

  it('provides no field context outside a field', () => {
    const probe = TestBed.createComponent(Probe);
    probe.detectChanges();
    expect(probe.componentInstance.ctx).toBeNull();
    expect((probe.nativeElement as HTMLElement).textContent).toBe('none');
  });

  it('exposes its size as data-size, M by default, and its full-row flag as a class', () => {
    const bare = TestBed.createComponent(Field);
    bare.detectChanges();
    expect((bare.nativeElement as HTMLElement).getAttribute('data-size')).toBe('m');

    const { field } = host((h) => { h.size.set('auto'); h.fullRow.set(true); });
    expect(field.getAttribute('data-size')).toBe('auto');
    expect(field.classList).toContain('full-row');
  });

  it('maps each size to its width token and leaves auto to the control', () => {
    expect(SOURCE).toMatch(/:host\(\[data-size='s'\]\) \{ --sb-control-w: var\(--field-s\); \}/);
    expect(SOURCE).toMatch(/:host\(\[data-size='m'\]\) \{ --sb-control-w: var\(--field-m\); \}/);
    expect(SOURCE).toMatch(/:host\(\[data-size='l'\]\) \{ --sb-control-w: var\(--field-l\); \}/);
    expect(SOURCE).toMatch(/:host\(\[data-size='auto'\]\) \{ --sb-control-w: initial; \}/);
  });

  it('stacks label over control with the shared gap, never centring them', () => {
    const rule = SOURCE.match(/\n {4}:host \{[^}]*\}/)?.[0] ?? '';
    expect(rule).toContain('flex-direction: column');
    expect(rule).toContain('gap: var(--space-4)');
    expect(rule).toContain('min-width: 0');
    expect(rule).not.toContain('align-items: center');
  });

  it('fills its row or cell below 640px, and a full-row field drops its empty filler there', () => {
    expect(PHONE).toMatch(/:host\(:not\(\[data-size='auto'\]\)\) \{ --sb-control-w: 100%; \}/);
    expect(PHONE).toMatch(/:host\(\.full-row\) \{[^}]*width: 100%/);
    expect(PHONE).toMatch(/:host\(\.full-row\.no-label\) \.field-label \{ display: none; \}/);
  });

  it('reads real width tokens', () => {
    expect(resolveToken('--field-s')).toBe('136px');
    expect(resolveToken('--field-m')).toBe('176px');
    expect(resolveToken('--field-l')).toBe('240px');
  });
});
```

- [ ] **Step 3: Run both specs to verify they fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/field.spec.ts --include src/app/ui/tokens.spec.ts`
Expected: FAIL — `field.spec.ts` cannot resolve `./field`; `tokens.spec.ts` fails `defines --field-s` (and `-m`, `-l`) and the new width test.

- [ ] **Step 4: Add the tokens**

In `frontend/src/styles/tokens.css`, directly after the line `  --control-h: 28px;` (line 311), insert:

```css

  /* v246 §A2: the width of an sb-field in a filter bar (ui/field.ts sets
   * --sb-control-w from these). Chosen from the widest current option text
   * at the 16px touch control text: S a short select ("Any horizon",
   * "Confidence"), M a native date input or "Any strategy", L a free-text
   * search. The touch block below raises heights only, never these; below
   * 640px a field fills its row or grid cell instead. */
  --field-s: 136px;
  --field-m: 176px;
  --field-l: 240px;
```

- [ ] **Step 5: Create the component**

Create `frontend/src/app/ui/field.ts`:

```ts
import {
  ChangeDetectionStrategy, Component, InjectionToken, Signal, forwardRef, input,
} from '@angular/core';

/** S a short select (Horizon, Direction), M a date or Strategy, L a free-text
 *  search; `auto` for month arrows and segmented groups, which size themselves. */
export type FieldSize = 's' | 'm' | 'l' | 'auto';

/** What a control inside a field reads: the field's label, so the control can
 *  drop its own visible label and keep the accessible name (v246 Handoff 2). */
export interface FieldContext {
  readonly label: Signal<string>;
}

export const SB_FIELD = new InjectionToken<FieldContext>('SB_FIELD');

/**
 * One control in a filter bar, with its label line above it (v246 §A2).
 *
 * The label line is always there: with no label it is an aria-hidden filler
 * one caption line tall, so every field in a bar is the same height and the
 * bars (flex-end, V246-6) line the controls up along their bottom edge. The
 * visible label is aria-hidden because the wrapped control carries the
 * accessible name: `sb-select` and `sb-text-input` read `SB_FIELD` and name
 * themselves from it (V246-4). One label path per bar.
 *
 * Width: the field sets `--sb-control-w` from the size token, and the
 * controls size themselves from it. Below 640px the field fills its row or
 * grid cell instead; a `fullRow` field (month arrows, a segmented group)
 * takes the whole row there and drops an empty filler line.
 *
 * In `sb-toolbar` the field, not the control, carries `slot="<id>"`.
 */
@Component({
  selector: 'sb-field',
  changeDetection: ChangeDetectionStrategy.OnPush,
  providers: [{ provide: SB_FIELD, useExisting: forwardRef(() => Field) }],
  host: {
    '[attr.data-size]': 'size()',
    '[class.no-label]': '!label()',
    '[class.full-row]': 'fullRow()',
  },
  template: `
    @if (label(); as text) {
      <span class="sb-label field-label" aria-hidden="true">{{ text }}</span>
    } @else {
      <span class="sb-label field-label filler" aria-hidden="true">&nbsp;</span>
    }
    <ng-content />
  `,
  styles: `
    :host {
      display: inline-flex;
      flex-direction: column;
      gap: var(--space-4);
      min-width: 0;
      max-width: 100%;
    }
    :host([data-size='s']) { --sb-control-w: var(--field-s); }
    :host([data-size='m']) { --sb-control-w: var(--field-m); }
    :host([data-size='l']) { --sb-control-w: var(--field-l); }
    /* Guaranteed-invalid: a control's var(--sb-control-w, auto) falls back. */
    :host([data-size='auto']) { --sb-control-w: initial; }
    @media (max-width: 639px) {
      :host { display: flex; }
      :host(:not([data-size='auto'])) { --sb-control-w: 100%; }
      :host(.full-row) { flex: 1 1 100%; width: 100%; }
      :host(.full-row.no-label) .field-label { display: none; }
    }
  `,
})
export class Field implements FieldContext {
  readonly label = input<string>('');
  readonly size = input<FieldSize>('m');
  readonly fullRow = input<boolean>(false);
}
```

- [ ] **Step 6: Run both specs to verify they pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/field.spec.ts --include src/app/ui/tokens.spec.ts`
Expected: PASS, 0 failed.

If the phone-block regex in `field.spec.ts` finds nothing, check that the `@media` block's closing brace sits on its own line indented four spaces (`\n    }`), the same shape `control-bar.spec.ts:77` reads.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/ui/field.ts frontend/src/app/ui/field.spec.ts frontend/src/styles/tokens.css frontend/src/app/ui/tokens.spec.ts
git commit -m "feat(v246): sb-field wraps a bar control with a fixed-height label line; --field-s/m/l width tokens" -m "SB_FIELD hands the label to the wrapped control; the field sets --sb-control-w, 100% below 640px."
```

### Task V246-4: `sb-select` / `sb-text-input` drop their visible label inside `sb-field`; `sb-date-range` as one field (M + M inline, 50/50 below 640px)

**Model:** sonnet — three existing shared controls read an optional injection token; accessible-name precedence and CSS-source specs are spelled out below.

**Files:**
- Modify: `frontend/src/app/ui/form-controls.ts` (`Select` lines 22-78, `TextInput` lines 80-128 plus its class body)
- Modify: `frontend/src/app/ui/form-controls.spec.ts` (one added `describe`)
- Modify: `frontend/src/app/ui/date-range.ts` (whole file, 65 lines)
- Modify: `frontend/src/app/ui/date-range.spec.ts` (one added `describe`)

**Interfaces:**
- Consumes (from V246-3): `SB_FIELD`, `FieldContext`, `Field` (`sb-field`) from `frontend/src/app/ui/field.ts`; the `--sb-control-w` custom property the field sets; the `--field-m` token.
- Produces (consumed by V246-7..V246-10):
  - `Select` / `TextInput` inject `SB_FIELD` optionally. **Inside a field** they render no `.sb-label`, carry host class `in-field`, and set `aria-label` = own `label()` || `ariaLabel()` || field `label()` (attribute removed when all three are empty). **Outside a field** nothing changes: the visible `<label>` names the control and `aria-label` is `label() ? null : ariaLabel()`, as today.
  - `select` and `input` width `var(--sb-control-w, auto)`: the field's size token, 100% of the field below 640px, native width standalone.
  - `DateRange`: no new inputs. Both inputs `width: var(--field-m)`, `height: var(--control-h)`; below 640px the host is full width and the inputs split it `flex: 1 1 0`. Inside a labelled field the inputs are named `"<field label> from"` / `"<field label> to"` (`"Opened from"`); otherwise `"From date"` / `"To date"` as today.
  - Consumer markup for a date range (V246-7 "Opened", V246-9 "Range"): `<sb-field label="Opened" size="auto" [fullRow]="true"><sb-date-range … /></sb-field>` — `auto` because the range sizes its own two inputs; `fullRow` so it takes the whole row below 640px.

**Why.** Handoff decision 2: `sb-field` owns the label, so a control inside it draws none of its own (wrapping today's `sb-select label="Strategy"` in a labelled field would print two captions). Its `label` input stays for standalone use (System settings, drawers, forms), and the control still has an accessible name: the field's visible caption is `aria-hidden` (V246-3), so the name has to land on the control. Spec §A2 "Date ranges": `sb-date-range` becomes one field with one label, From and To inline at M width each with the dash between, and below 640px the field takes the full row and From / To split it 50/50 — the fix for the Analytics range clipping its second date at 390. The host class `in-field` makes the control block-level inside the field, so `width: 100%` below 640px resolves against the field's cell instead of the inline label's own content.

- [ ] **Step 1: Write the failing form-controls tests**

In `frontend/src/app/ui/form-controls.spec.ts`, add `Component` to the `@angular/core` import (line 4 becomes `import { Component, provideZonelessChangeDetection } from '@angular/core';`), add `import { Field } from './field';` under the `./form-controls` import, and append at the end of the file:

```ts
const OPTIONS = [{ value: 'rsi', label: 'RSI' }];

@Component({
  imports: [Field, Select, TextInput],
  template: `
    <sb-field id="f-strategy" label="Strategy" size="m">
      <sb-select id="strategy" label="Strategy" [options]="options" />
    </sb-field>
    <sb-field id="f-ticker" label="Ticker" size="l">
      <sb-text-input id="ticker" placeholder="AAPL" />
    </sb-field>
    <sb-field id="f-bare" size="s">
      <sb-select id="bare" [options]="options" ariaLabel="Horizon filter" />
    </sb-field>
    <sb-field id="f-origin" label="Origin" size="s">
      <sb-select id="origin" [options]="options" ariaLabel="Plan origin" />
    </sb-field>
    <sb-field id="f-empty" size="s">
      <sb-select id="empty" [options]="options" />
    </sb-field>
    <sb-select id="standalone" label="Strategy" [options]="options" />
  `,
})
class InField {
  readonly options = OPTIONS;
}

describe('v246 §A2: controls inside sb-field', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  function mount(): HTMLElement {
    const f = TestBed.createComponent(InField);
    f.detectChanges();
    return f.nativeElement as HTMLElement;
  }

  const control = (el: HTMLElement, id: string) =>
    el.querySelector(`#${id} select, #${id} input`) as HTMLElement;

  it('draws one label per field: the field\'s, never the control\'s own', () => {
    const el = mount();
    for (const id of ['f-strategy', 'f-ticker', 'f-origin']) {
      expect(el.querySelectorAll(`#${id} .sb-label`)).toHaveLength(1);
      expect(el.querySelector(`#${id} .sb-label`)!.classList).toContain('field-label');
    }
  });

  it('names the control by its own label, then its ariaLabel, then the field\'s label', () => {
    const el = mount();
    expect(control(el, 'strategy').getAttribute('aria-label')).toBe('Strategy');
    expect(control(el, 'ticker').getAttribute('aria-label')).toBe('Ticker');
    expect(control(el, 'bare').getAttribute('aria-label')).toBe('Horizon filter');
    expect(control(el, 'origin').getAttribute('aria-label')).toBe('Plan origin');
  });

  it('drops the aria-label attribute rather than printing an empty one when nothing names the control', () => {
    expect(control(mount(), 'empty').hasAttribute('aria-label')).toBe(false);
  });

  it('marks a control inside a field, and only there', () => {
    const el = mount();
    expect(el.querySelector('#strategy')!.classList).toContain('in-field');
    expect(el.querySelector('#ticker')!.classList).toContain('in-field');
    expect(el.querySelector('#standalone')!.classList).not.toContain('in-field');
  });

  it('leaves a standalone control exactly as before: its own visible label, no aria-label', () => {
    const el = mount();
    expect(el.querySelector('#standalone .sb-label')!.textContent!.trim()).toBe('Strategy');
    expect(control(el, 'standalone').hasAttribute('aria-label')).toBe(false);
  });

  it('sizes the select and the input from the field\'s width, native width standalone', () => {
    const block = (selector: string, from: string) => {
      const at = SOURCE.indexOf(from);
      return SOURCE.slice(at).match(new RegExp(`\\n {4}${selector} \\{[^}]*\\}`))?.[0] ?? '';
    };
    expect(block('select', "selector: 'sb-select'")).toContain('width: var(--sb-control-w, auto)');
    expect(block('input', "selector: 'sb-text-input'")).toContain('width: var(--sb-control-w, auto)');
    expect(SOURCE.match(/:host\(\.in-field\) \{ display: block;/g)?.length ?? 0).toBe(2);
    expect(SOURCE.match(/:host\(\.in-field\) \.field \{ display: flex; \}/g)?.length ?? 0).toBe(2);
  });
});
```

- [ ] **Step 2: Write the failing date-range tests**

In `frontend/src/app/ui/date-range.spec.ts`, change the imports at the top to:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { Component, provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { DateRange } from './date-range';
import { Field } from './field';
```

(the old separate `TestBed` and `provideZonelessChangeDetection` import lines go), and append at the end of the file:

```ts
const RANGE_SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/date-range.ts'), 'utf8');
const RANGE_PHONE = RANGE_SOURCE.match(/@media \(max-width: 639px\) \{([\s\S]*?)\n {4}\}/)?.[1] ?? '';

@Component({
  imports: [Field, DateRange],
  template: `
    <sb-field [label]="label()" size="auto" [fullRow]="true">
      <sb-date-range [from]="from" [to]="null" (changed)="last = $event" />
    </sb-field>
  `,
})
class RangeInField {
  readonly label = signal('Opened');
  readonly from = '2026-04-01';
  last: unknown = null;
}

describe('DateRange as one field (v246 §A2)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  function mount(label = 'Opened') {
    const f = TestBed.createComponent(RangeInField);
    f.componentInstance.label.set(label);
    f.detectChanges();
    const el = f.nativeElement as HTMLElement;
    return { f, from: el.querySelector('input.from') as HTMLInputElement, to: el.querySelector('input.to') as HTMLInputElement };
  }

  it('names both bounds after the field\'s one label', () => {
    const { from, to } = mount();
    expect(from.getAttribute('aria-label')).toBe('Opened from');
    expect(to.getAttribute('aria-label')).toBe('Opened to');
  });

  it('keeps its own bound names in a field with no label', () => {
    const { from, to } = mount('');
    expect(from.getAttribute('aria-label')).toBe('From date');
    expect(to.getAttribute('aria-label')).toBe('To date');
  });

  it('still emits both bounds from inside a field', () => {
    const { f, to } = mount();
    to.value = '2026-04-28';
    to.dispatchEvent(new Event('change'));
    expect(f.componentInstance.last).toEqual({ from: '2026-04-01', to: '2026-04-28' });
  });

  it('draws From and To at M width and the shared control height', () => {
    const rule = RANGE_SOURCE.match(/\n {4}input \{[^}]*\}/)?.[0] ?? '';
    expect(rule).toContain('width: var(--field-m)');
    expect(rule).toContain('height: var(--control-h)');
    expect(rule).toContain('min-width: 0');
  });

  it('takes the full row below 640px and splits it 50/50 between From and To', () => {
    expect(RANGE_PHONE).toMatch(/:host \{ display: block; width: 100%; \}/);
    expect(RANGE_PHONE).toMatch(/\.field \{ display: flex; \}/);
    expect(RANGE_PHONE).toMatch(/input \{ flex: 1 1 0; width: auto; \}/);
  });
});
```

- [ ] **Step 3: Run both specs to verify they fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/form-controls.spec.ts --include src/app/ui/date-range.spec.ts`
Expected: FAIL — two `.sb-label` per field (the field's and the select's), no `in-field` class, `aria-label` null on `#strategy` and `#ticker`, `'From date'` where `'Opened from'` is expected, and the CSS-source tests find no `--sb-control-w` / `--field-m`. The pre-existing tests in both files still pass.

- [ ] **Step 4: Implement `sb-select` and `sb-text-input`**

In `frontend/src/app/ui/form-controls.ts`:

1. Replace line 1 and add the field import:

```ts
import { ChangeDetectionStrategy, Component, computed, inject, input, model } from '@angular/core';

import { FieldContext, SB_FIELD } from './field';
```

2. After the `SelectOption` interface (line 20) add the shared naming rule:

```ts
/** The accessible name of a select or text input (v246 Handoff 2).
 *  Outside an sb-field nothing changes: the visible <label> names the
 *  control, and aria-label is used only when there is no label. Inside a
 *  field the field draws the (aria-hidden) caption, so the control names
 *  itself: its own label, else its ariaLabel, else the field's label;
 *  null removes the attribute rather than printing an empty one. */
function controlName(field: FieldContext | null, label: string | null, ariaLabel: string): string | null {
  if (!field) return label ? null : ariaLabel;
  return label || ariaLabel || field.label() || null;
}
```

3. In `Select`'s `@Component`, add `host: { '[class.in-field]': 'inField' },` after `changeDetection`, and change the template's label block and `aria-label` binding:

```html
    <label class="field">
      @if (visibleLabel(); as text) {
        <span class="sb-label">{{ text }}</span>
      }
      <select
        [value]="value()"
        [disabled]="disabled()"
        [attr.aria-label]="accessibleName()"
        (change)="value.set($any($event.target).value)"
      >
```

(the `<option>` loop and the closing tags stay as they are).

4. In `Select`'s styles, replace the `.field` line (line 46) and add `width` to the `select` rule so the start of the styles reads:

```css
    .field { display: inline-flex; flex-direction: column; gap: var(--space-4); }
    /* v246: inside an sb-field the control is block-level, so a width of
       100% (below 640px) resolves against the field, not its own content. */
    :host(.in-field) { display: block; min-width: 0; }
    :host(.in-field) .field { display: flex; }
```

and inside `select { … }` add, directly after `height: var(--control-h);`:

```css
      /* The field's size token (ui/field.ts); native width standalone. */
      width: var(--sb-control-w, auto);
      max-width: 100%;
```

5. In `class Select`, after `readonly disabled = input(false);` add:

```ts
  private readonly field = inject(SB_FIELD, { optional: true });
  /** Inside an sb-field the field draws the one label (v246 Handoff 2). */
  protected readonly inField = this.field !== null;
  protected readonly visibleLabel = computed(() => (this.inField ? null : this.label()));
  protected readonly accessibleName = computed(() => controlName(this.field, this.label(), this.ariaLabel()));
```

6. In `TextInput`'s `@Component`, add the same `host: { '[class.in-field]': 'inField' },`; in its template replace `@if (label(); as text) {` with `@if (visibleLabel(); as text) {` and `[attr.aria-label]="label() ? null : ariaLabel()"` with `[attr.aria-label]="accessibleName()"`.

7. In `TextInput`'s styles, after the `.field { … max-width: 100%; }` line (line 108) add:

```css
    /* v246: see sb-select above. */
    :host(.in-field) { display: block; min-width: 0; }
    :host(.in-field) .field { display: flex; }
```

and inside `input { … }`, keep `min-width: 0;` as the first declaration (the v179 test at `form-controls.spec.ts:75-88` reads it there) and add directly after `height: var(--control-h);`:

```css
      /* The field's size token (ui/field.ts); native width standalone. */
      width: var(--sb-control-w, auto);
```

8. In `class TextInput`, after `readonly step = input<number | null>(null);` add the same four members as in step 5:

```ts
  private readonly field = inject(SB_FIELD, { optional: true });
  /** Inside an sb-field the field draws the one label (v246 Handoff 2). */
  protected readonly inField = this.field !== null;
  protected readonly visibleLabel = computed(() => (this.inField ? null : this.label()));
  protected readonly accessibleName = computed(() => controlName(this.field, this.label(), this.ariaLabel()));
```

`Checkbox` is not touched (it is never a bar control in Plan A).

- [ ] **Step 5: Implement `sb-date-range`**

Replace `frontend/src/app/ui/date-range.ts` from line 1 through the end of the `styles` block and the class (the docblock at lines 3-16 stays, with the paragraph below appended to it before its closing `*/`):

```ts
import { ChangeDetectionStrategy, Component, computed, inject, input, output } from '@angular/core';

import { SB_FIELD } from './field';
```

Append to the docblock:

```ts
 *
 * v246 §A2: one field. In a bar it sits in `<sb-field label="Opened"
 * size="auto" [fullRow]="true">`: one caption, From and To inline at M
 * width with the dash between, and below 640px the whole row split 50/50.
 * The inputs take their names from the field's label ("Opened from").
```

Template and styles:

```ts
@Component({
  selector: 'sb-date-range',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <span class="field">
      <input
        type="date"
        class="from"
        [attr.aria-label]="fromName()"
        [value]="from() ?? ''"
        (change)="emit($any($event.target).value || null, to())"
      />
      <span class="sep" aria-hidden="true">–</span>
      <input
        type="date"
        class="to"
        [attr.aria-label]="toName()"
        [attr.min]="from()"
        [value]="to() ?? ''"
        (change)="emit(from(), $any($event.target).value || null)"
      />
    </span>
  `,
  styles: `
    :host { display: inline-block; max-width: 100%; }
    .field { display: inline-flex; align-items: center; gap: var(--space-6); }
    .sep { color: var(--text-muted); }
    input {
      min-width: 0;
      width: var(--field-m);
      height: var(--control-h);
      padding: 0 var(--space-8);
      background: var(--surface);
      border: 1px solid var(--control-border);
      border-radius: var(--control-radius);
      color: var(--text);
      font: inherit;
      font-size: var(--text-control);
    }
    input:hover { border-color: var(--text-muted); }
    input:focus-visible { outline: 1px solid var(--accent); outline-offset: 1px; }
    @media (max-width: 639px) {
      :host { display: block; width: 100%; }
      .field { display: flex; }
      input { flex: 1 1 0; width: auto; }
    }
  `,
})
export class DateRange {
  readonly from = input<string | null>(null);
  readonly to = input<string | null>(null);
  readonly changed = output<{ from: string | null; to: string | null }>();

  private readonly field = inject(SB_FIELD, { optional: true });
  /** "Opened from" inside a labelled field; "From date" anywhere else. */
  protected readonly fromName = computed(() => this.boundName('from', 'From date'));
  protected readonly toName = computed(() => this.boundName('to', 'To date'));

  protected emit(from: string | null, to: string | null): void {
    this.changed.emit({ from, to });
  }

  private boundName(bound: 'from' | 'to', fallback: string): string {
    const label = this.field?.label();
    return label ? `${label} ${bound}` : fallback;
  }
}
```

The dash gains `aria-hidden="true"`: the two names already say "from" and "to", so a screen reader need not read "en dash".

- [ ] **Step 6: Run both specs to verify they pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/form-controls.spec.ts --include src/app/ui/date-range.spec.ts --include src/app/ui/field.spec.ts`
Expected: PASS, 0 failed — including the pre-existing `'labels all three controls with the one shared label style'`, `'renders both bounds as native date inputs'` and the v179 `min-width: 0` test.

- [ ] **Step 7: Check the controls' other consumers are unchanged**

Nothing wraps these controls in `sb-field` yet (V246-7..V246-10 do), so every current page must render exactly as before. Run the specs of the pages that use them today:

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/trades/trades.spec.ts --include src/app/workspaces/analytics/scope-bar.spec.ts --include src/app/workspaces/calendar/calendar.spec.ts --include src/app/workspaces/watchlist/watchlist.spec.ts`
Expected: PASS, 0 failed. A failure that reads `"From date"` or a select's `aria-label` means a standalone path changed; fix `controlName` / `boundName`, never the page spec.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/app/ui/form-controls.ts frontend/src/app/ui/form-controls.spec.ts frontend/src/app/ui/date-range.ts frontend/src/app/ui/date-range.spec.ts
git commit -m "feat(v246): controls in sb-field drop their own label and keep the accessible name; sb-date-range is one field" -m "Select and text input width from --sb-control-w; date inputs at --field-m, full row split 50/50 below 640px."
```

