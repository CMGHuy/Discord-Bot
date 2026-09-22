# Analytics Workspace Redesign (v94) — Part 4: The six tab components

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or superpowers:executing-plans. Header, constraints and prerequisite in `_0-index.md`. **Spec:** `docs/superpowers/specs/2026-09-17-v94-analytics-workspace-redesign-design.md` §3.6–§3.10.

# Phase 4 — Tabs

Every tab component: `frontend/src/app/workspaces/analytics/tabs/<name>.ts` + `<name>.spec.ts`, standalone, `OnPush`, `inject(AnalyticsStore)`, **no HTTP of its own** — it binds to store signals only. Keep each file under ~400 lines; if one grows past that, split a section into `tabs/sections/<name>.ts` rather than compressing it.

**Every panel on every tab follows the same four-part shape** (spec D4, H4):

```html
<sb-panel>
  <sb-panel-header title="…" [n]="store.scopeN()" [hint]="'…'" [total]="moneyTotal()"
                   [tableable]="true" [(tableOpen)]="…" />
  @if (store.<panel>Error(); as err) {
    <sb-panel-error [message]="err" (retry)="store.reload('<panel>')" />
  } @else if (<no rows>) {
    <sb-empty-state title="No closed trades in this scope" reason="measured-zero" />
  } @else {
    <!-- the chart -->
    @if (tableOpen) { <sb-data-table … /> }
  }
</sb-panel>
```

A panel that is not scoped passes `[allTime]="true"` and omits `[n]`.

## Parallelisation (this phase)

- **Group C (parallel):** T1, T2, T3, T4, T5, T6 — one component file + one spec each, all *reading* the same store.
  - **Two exceptions, and they are the only writers:** T2 also edits `stores/analytics.store.ts` (+`analytics.columns.ts`) to add three by-dimension slices, and T3 also edits `swingbot/admin/api_v1/analytics.py` (+its test) to add `hold_points`. No other task in this group writes either file, so the group stays safe — but **T2 must finish and commit before T7 starts**, since T7 deletes dead store code.
- **Sequential last:** T7 — deletes the old templates and dead store code, and touches every file the group created only if a stub remains.

## Exit criteria

Six tabs render from store signals; every panel has an error surface and a Table view; no rate renders for a cell the server nulled; `npm test -- --include src/app/workspaces/analytics/tabs/<each>.spec.ts` green; `analytics.ts` is a shell under ~150 lines and the two `sections/` files are gone.

---

### Task T1: Overview tab

**Files:**
- Modify (from stub): `frontend/src/app/workspaces/analytics/tabs/overview.ts`
- Create: `frontend/src/app/workspaces/analytics/tabs/overview.spec.ts`

**Interfaces:**
- Consumes: `store.performance()`, `store.equityCurve()`, `store.unit()`, `store.scopeN()`, their error signals, `inUnit`/`alwaysMoney`/`unitLabel` (S3), `ConnectionStore.currency()`.
- Produces: `<sb-overview-tab>`; internal computeds `kpiTiles()`, `equitySeries()`, `drawdownSeries()`, `benchmarkSeries()`, `outcomeSegments()`, `rBins()`, `monthlyBars()`.

**Layout (spec §3.6):** KPI row → equity + drawdown panes (shared x-axis) beside outcome share bar → R distribution beside monthly strip.

- [ ] **Step 1: Failing spec**

```ts
import { provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { AnalyticsStore } from '../../../stores/analytics.store';
import { ConnectionStore } from '../../../stores/connection.store';
import { PreferencesStore } from '../../../stores/preferences.store';
import { OverviewTab } from './overview';

/* The store is stubbed down to the signals this tab reads: a tab component
 * owns no HTTP (spec v94 D12), so its spec asserts rendering, not fetching. */
function storeStub(over: Record<string, unknown> = {}) {
  const base = {
    unit: signal('r'), scopeN: signal(312), tableOpen: signal({}),
    performance: signal({
      totals: { total: 40, open: 6, closed: 34 }, win_rate: 53.5, win_rate_n: 34,
      expectancy_r: -0.136, expectancy_n: 34, derived: { total_return_pct: 4.2 },
      distributions: { returns: [], r_multiples: [{ lo: -1, hi: 0, count: 12 }] },
      calendar: [{ month: '2026-08', return_pct: 1.2, pnl: 240, n: 20 }],
      rolling_wr: [], rolling_exp_r: [], relocated: {}, by_confidence: {},
      scope: {}, n: 312,
    }),
    performanceError: signal(null),
    equityCurve: signal({
      points: [{ date: '2026-08-01', cum_r: 1, drawdown_r: 0, cum_pnl: 70, cum_pct: 0.7 },
               { date: '2026-08-02', cum_r: 0.5, drawdown_r: 0.5, cum_pnl: 40, cum_pct: 0.4 }],
      points_n: 2, as_of: '2026-08-02', benchmark: { spy_indexed: [] }, scope: {}, n: 2,
    }),
    equityCurveError: signal(null),
    setTableOpen: () => {}, reload: () => {},
  };
  return { ...base, ...over };
}

function render(over: Record<string, unknown> = {}) {
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      { provide: AnalyticsStore, useValue: storeStub(over) },
      { provide: ConnectionStore, useValue: { currency: signal('$') } },
      { provide: PreferencesStore, useValue: { values: () => ({}), update: () => {} } },
    ],
  });
  const fixture = TestBed.createComponent(OverviewTab);
  fixture.detectChanges();
  return { fixture, el: fixture.nativeElement as HTMLElement };
}

describe('OverviewTab', () => {
  beforeEach(() => TestBed.resetTestingModule());

  it('shows six KPI tiles, each with the money line whatever the unit', () => {
    const { el } = render();
    expect(el.querySelectorAll('sb-stat-tile').length).toBeGreaterThanOrEqual(6);
    const text = el.textContent as string;
    for (const label of ['Total R', 'ExpR', 'Win rate', 'Profit factor', 'Max drawdown', 'Sharpe']) {
      expect(text).toContain(label);
    }
    expect(el.querySelectorAll('.secondary').length).toBeGreaterThan(0);
  });

  it('draws equity and drawdown as two panes, not a toggle', () => {
    const { el } = render();
    expect(el.querySelectorAll('sb-line-chart').length).toBeGreaterThanOrEqual(2);
    expect(el.textContent).toContain('Drawdown');
    expect(el.querySelector('sb-segmented[aria-label="Equity view"]')).toBeNull();
  });

  it('renders outcome as one share bar, never a donut', () => {
    const { el } = render();
    expect(el.querySelector('sb-share-bar')).not.toBeNull();
    expect(el.querySelector('sb-donut')).toBeNull();
  });

  it('replaces a failed panel with a retry surface, not an empty chart', () => {
    const { el } = render({ equityCurve: signal(null), equityCurveError: signal('The admin is not responding.') });
    expect(el.querySelector('sb-panel-error')).not.toBeNull();
    expect(el.textContent).toContain('Could not load');
  });
});
```

Run: `cd frontend && npm test -- --include src/app/workspaces/analytics/tabs/overview.spec.ts` → FAIL.

- [ ] **Step 2: Implement** — the component's shape:

```ts
@Component({
  selector: 'sb-overview-tab',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel, PanelHeader, PanelError, EmptyState, StatTile, LineChart, ShareBar, Histogram, BarList, DataTable],
  template: `
    <div class="kpi-row">
      @for (tile of kpiTiles(); track tile.label) {
        <sb-stat-tile [label]="tile.label" [value]="tile.value" [secondary]="tile.money"
                      [sample]="tile.sample" [trend]="tile.trend" [hint]="tile.hint" />
      }
    </div>

    <div class="panels">
      <sb-panel>
        <sb-panel-header title="Equity" [n]="store.scopeN()" [total]="equityMoney()"
          hint="Cumulative {{ unitLabel() }} per closed trade, ordered by close date. A day with no closes is not a flat day: the x-axis is the sequence of trades, dated." />
        @if (store.equityCurveError(); as err) {
          <sb-panel-error [message]="err" (retry)="store.reload('equityCurve')" />
        } @else if (!points().length) {
          <sb-empty-state title="No closed trades in this scope" reason="measured-zero" />
        } @else {
          <sb-line-chart [series]="equitySeries()" [referenceLine]="0" [valueFormat]="format()" />
          <h4 class="pane-label">Drawdown</h4>
          <sb-line-chart [series]="drawdownSeries()" [valueFormat]="format()" />
          @if (unit() === 'pct' && benchmarkSeries().length) {
            <p class="note">SPY indexed to the range start, for context.</p>
          } @else if (unit() !== 'pct') {
            <p class="note">SPY appears in % mode only — an R curve and a price index share no axis.</p>
          }
        }
      </sb-panel>

      <sb-panel>
        <sb-panel-header title="Outcome" [n]="store.scopeN()"
          hint="Win = TP1 touched. Average win and loss are means of the R-multiples on each side." />
        @if (store.performanceError(); as err) {
          <sb-panel-error [message]="err" (retry)="store.reload('performance')" />
        } @else {
          <sb-share-bar label="Outcome" [segments]="outcomeSegments()" />
          <dl class="pairs">
            <div><dt>Avg win</dt><dd>{{ avgWin() }}</dd></div>
            <div><dt>Avg loss</dt><dd>{{ avgLoss() }}</dd></div>
            <div><dt>Payoff</dt><dd>{{ payoff() }}</dd></div>
            <div><dt>Streaks</dt><dd>{{ streaksText() }}</dd></div>
          </dl>
        }
      </sb-panel>

      <sb-panel>
        <sb-panel-header title="R distribution" [n]="store.scopeN()" [tableable]="true"
          [(tableOpen)]="rTableOpen"
          hint="Every closed trade's realised R. The shape is the finding: a cluster of small losses with a tail of larger wins is a different book from a symmetric one." />
        …histogram, then @if (rTableOpen()) { <sb-data-table … /> }
      </sb-panel>

      <sb-panel>
        <sb-panel-header title="By month" [n]="store.scopeN()" [tableable]="true" [(tableOpen)]="monthTableOpen"
          hint="Realised result per calendar month of the scoped book. The day grid lives on the Calendar workspace." />
        …signed sb-bar-list, then a link: <a routerLink="/calendar">Open the calendar</a>
      </sb-panel>
    </div>
  `,
})
```

`kpiTiles()` — six tiles, each `{ label, value: inUnit(values, unit, currency), money: alwaysMoney(values, currency), sample, trend, hint }`:

| Tile | `r` | `pct` | `money` | sample |
|---|---|---|---|---|
| Total R | sum of `r_multiples` — from `equityCurve().points.at(-1).cum_r` | `derived.total_return_pct` | `points.at(-1).cum_pnl` | `points_n` |
| ExpR | `performance().expectancy_r` | `derived.avg_win_pct`-free: reuse `expectancy_r` and suppress in `%` (show `—`) | mean `cum_pnl`/n | `expectancy_n` |
| Win rate | `win_rate` (always a %) | same | same | `win_rate_n` |
| Profit factor | `derived`/`performance` profit factor (unitless) | same | same | `scopeN()` |
| Max drawdown | `max(points.drawdown_r)` | `derived` max drawdown % if present | max drawdown in currency from `cum_pnl` peaks | `points_n` |
| Sharpe | `derived.sharpe_ann` | same | same | `scopeN()` |

Where a unit does not apply, the tile shows `—` in the headline and still shows its money line. **`trend`** is the last 30 `cum_r` deltas for Total R and `rolling_wr`'s last 30 win rates for Win rate; `null` for the rest.

`outcomeSegments()`: `[{ label: 'Wins', count: wins, tone: 'pos' }, { label: 'Losses', count: losses, tone: 'neg' }]` from `performance().relocated` (v93 keeps `wins`/`losses` there) or from `byDimension`; if neither is present, `[]` and the share bar prints "no observations".

The `relocated` metrics that used to have their own panel (wins, losses, avg realised %, best trade %, worst trade %, avg holding days) are **not dropped** (spec §3.6): wins/losses are the share bar; avg realised %, best and worst trade % and avg holding days go in the Outcome panel's `<dl class="pairs">` and in its Table view. Assert their presence in the spec — this is the assertion inherited from `analytics.store.spec.ts`'s header (S4 Step 8).

- [ ] **Step 3: Run the spec → PASS. Commit**

```bash
git add frontend/src/app/workspaces/analytics/tabs/overview.ts frontend/src/app/workspaces/analytics/tabs/overview.spec.ts
git commit -m "feat(v94): Overview tab -- KPI row with money lines, equity over drawdown, outcome share bar"
```

---

### Task T2: Attribution tab

**Files:**
- Modify (from stub): `tabs/attribution.ts`; Create: `tabs/attribution.spec.ts`
- Modify: `frontend/src/app/workspaces/analytics/analytics.columns.ts` (add `dimensionColumns(label, unit, currency, floor)` returning `ColumnDef<AnalyticsByDimensionRow>[]`; keep `breakdownColumns` until T7 removes its last caller)

**Interfaces:**
- Consumes: `store.byDimension()`, `store.heatGrid()`, `store.strategies()`, `store.performance()`, `store.measure()`, `store.heatCell()`, `store.breakdown()`, their errors; `sb-waterfall`, `sb-dot-plot`, `sb-heat-grid`, `sb-bar-list`, `sb-data-table`.
- Produces: `<sb-attribution-tab>`; computeds `waterfallSteps()`, `dotPoints()`, `heatCells()`, `foldedRow()`, `horizonBars()`, `directionBars()`, `dowBars()`, `monthBars()`, `dimensionRows()`.

- [ ] **Step 1: Failing spec** (same stub pattern as T1)

```ts
  it('folds past the top eight into Other and never invents a ninth hue', () => {
    const { fixture } = render({ strategies: signal({ contribution: Array.from({ length: 12 },
      (_, i) => ({ strategy: `S${i}`, total_r: 12 - i, n: 30 })), cumulative: {}, strategies: [], scope: {}, n: 360 }) });
    const steps = fixture.componentInstance['waterfallSteps']();
    expect(steps.length).toBe(9);
    expect(steps.at(-1)!.label).toBe('Other (4)');
    expect(steps.at(-1)!.value).toBe(12 - 8 + (12 - 9) + (12 - 10) + (12 - 11));
  });

  it('draws withheld cells blank and passes the floor to the dot plot', () => {
    const { el, fixture } = render({
      byDimension: signal({ rows: [{ key: 'MACD', n: 9, exp_r: null, win_rate: null, total_r: 1.2,
                                     total_pnl: 100, wins: 5, losses: 4, avg_win_r: null, avg_loss_r: null }],
                            min_cell_n: 20, as_of: null, scope: {}, n: 9 }),
    });
    expect(fixture.componentInstance['dotPoints']()[0].value).toBeNull();
    expect(el.querySelector('sb-dot-plot')).not.toBeNull();
    const table = el.textContent as string;
    expect(table).not.toMatch(/\b\d+\.\d%/);            // no rate printed for a withheld row
  });

  it('one measure toggle drives every panel', () => {
    const { el } = render({ measure: signal('total_r') });
    expect(el.querySelectorAll('sb-segmented').length).toBe(1);
  });
```

- [ ] **Step 2: Implement**

`waterfallSteps()`:

```ts
  /** Top eight by |total R| plus one `Other` step (spec v94 D7/D11): a ninth
   *  categorical slot would be a generated hue, which is indistinguishable
   *  under CVD from one already in use. */
  protected readonly waterfallSteps = computed<WaterfallStep[]>(() => {
    const rows = [...(this.store.strategies()?.contribution ?? [])]
      .filter((c) => c.total_r !== null)
      .sort((a, b) => Math.abs(b.total_r!) - Math.abs(a.total_r!));
    const top = rows.slice(0, 8).map((c) => ({ label: c.strategy, value: c.total_r!, n: c.n }));
    const rest = rows.slice(8);
    if (rest.length) {
      top.push({ label: `Other (${rest.length})`, value: rest.reduce((r, c) => r + c.total_r!, 0),
                 n: rest.reduce((n, c) => n + c.n, 0) });
    }
    return top;
  });
```

`dotPoints()`: `store.byDimension()?.rows.map(r => ({ label: r.key, n: r.n, value: measureValue(r) }))` where `measureValue` reads `exp_r`, `total_r` or `win_rate` per `store.measure()` — and **returns the server's `null` unchanged**; never substitutes 0.

`heatCells()` / `foldedRow()`: map `store.heatGrid()`'s cells picking `exp_r`, `win_rate` or `n` per `store.heatCell()`; ramp `diverging` for `exp_r`, `sequential` otherwise; `floor` from `heatGrid()?.min_cell_n ?? 20`.

Bars: horizon from a `by-dimension?dim=horizon` fetch is one extra request; instead read `store.byDimension()` when `breakdown() === 'horizon'` and otherwise derive the four fixed bar lists from `performance()`'s existing splits where available — **simplest correct choice: fetch them.** Add to S4's `loadAttribution` three more `fetch(api.analyticsByDimension('horizon'|'direction'|'dow', s()), …)` into three new slice fields `byHorizon`, `byDirection`, `byDow`, each with its own error. Do that as **Step 2a of this task**, editing `analytics.store.ts` and its spec (it is the only task that needs it, so it does not belong in Phase 3).

`dimensionColumns(label, unit, currency, floor)` in `analytics.columns.ts`: columns `key` (labelled `label`), `n`, `win_rate` (`rate()`, em dash when null), `exp_r` (`expectancy()`), `total_r`, `total_pnl` (`money()`), `avg_win_r`, `avg_loss_r`, plus `badge` and `soak` cells rendered only when the rows carry them. A `null` rate renders `ABSENT` with a `title="withheld: n < {floor}"`.

- [ ] **Step 3: Spec → PASS. Commit**

```bash
git add frontend/src/app/workspaces/analytics/tabs/attribution.ts frontend/src/app/workspaces/analytics/tabs/attribution.spec.ts frontend/src/app/workspaces/analytics/analytics.columns.ts frontend/src/app/stores/analytics.store.ts frontend/src/app/stores/analytics.store.spec.ts
git commit -m "feat(v94): Attribution tab -- contribution waterfall, ExpR-vs-N dot plot, readable heat grid"
```

---

### Task T3: Execution tab

**Files:** Modify (from stub): `tabs/execution.ts`; Create: `tabs/execution.spec.ts`

**Interfaces:**
- Consumes: `store.exitQuality()`, `store.journal()`, `store.performance()` (holding-period and R:R splits), errors; `sb-strip-plot`, `sb-share-bar`, `sb-histogram`, `sb-scatter`, `sb-bar-list`, `sb-inline-md`.
- Produces: `<sb-execution-tab>`; computeds `verdictStrip()`, `efficiencyBins()`, `maeBins()`, `scatterPoints()`, `holdGroups()`, `exitReasonSegments()`, `coverageText()`.

- [ ] **Step 1: Failing spec**

```ts
  it('leads with the four-number verdict before any chart', () => {
    const { el } = render();
    const strip = el.querySelector('.verdict')!;
    expect(strip.textContent).toContain('0.43');        // efficiency median
    expect(strip.textContent).toContain('0.48');        // disposition ratio
    expect(strip.textContent).toContain('coverage');
    expect(el.querySelector('.verdict')!.compareDocumentPosition(el.querySelector('sb-histogram')!))
      .toBe(Node.DOCUMENT_POSITION_FOLLOWING);
  });

  it('shows unrecorded exits as their own segment, never hidden', () => {
    const { fixture } = render({ exitQuality: signal({
      exit_reasons: [{ reason: 'tp1', n: 40 }, { reason: 'other', n: 60 }],
      unmapped_reasons: [{ status: 'closed', text: '', n: 60 }],
      hold_by_outcome: { avg_winner_days: 0.31, avg_loser_days: 0.64, ratio: 0.48, severity: 'low', n_winners: 212, n_losers: 352 },
      efficiency: { bins: [], n: 324, median: 0.429 }, mae: { bins: [], n: 300, median: -0.4 },
      scatter: [], coverage: { mfe_r: { non_null: 555, total: 591, pct: 93.9 } }, min_cell_n: 20, scope: {}, n: 591 }) });
    const segs = fixture.componentInstance['exitReasonSegments']();
    expect(segs.find((s: any) => s.label === 'unrecorded')?.count).toBe(60);
  });

  it('draws hold time by outcome as two strips, not a sentence', () => {
    const { el } = render();
    expect(el.querySelector('sb-strip-plot')).not.toBeNull();
    expect(el.querySelectorAll('sb-donut').length).toBe(0);
  });
```

- [ ] **Step 2: Implement**

`verdictStrip()` returns four `{ label, value, hint }`: exit-efficiency median (`efficiency.median`, `n`), disposition ratio (`hold_by_outcome.ratio` with `severity`), hold winners vs losers (`avg_winner_days` / `avg_loser_days`), journal coverage (the min `pct` across `coverage`, named). Rendered as a `<dl class="verdict">` **above** every chart.

`exitReasonSegments()`: map `exit_reasons` to segments, renaming the `other` bucket to `unrecorded` when `unmapped_reasons` accounts for it, tone `warn`; everything else `accent`/`pos`/`neg` by reason family. The count is never merged into another segment.

`holdGroups()`: the API gives averages, not per-trade holds. Render the strip plot from `hold_by_outcome`'s two averages as **two single-value strips with an explicit note** — *or*, better and preferred: add `hold_points: {outcome, days}[]` to `/analytics/exit-quality` in Part 1's B6. **Do that**: append to B6's payload `"hold_points": [{"outcome": resolve_outcome(t), "days": holding_days(t)} …]` capped at 2,000 rows, and add the matching test. If the executing session finds B6 already merged, make this a one-step follow-up commit in this task (`feat(v94): hold_points for the execution strip plot`), touching `analytics.py` and `test_api_v1_analytics.py`.

Journal panel keeps `sb-inline-md` for digest and lessons, with its own `sb-panel-error` on `store.journalError()`.

- [ ] **Step 3: Spec → PASS. Commit**

```bash
git add frontend/src/app/workspaces/analytics/tabs/execution.ts frontend/src/app/workspaces/analytics/tabs/execution.spec.ts swingbot/admin/api_v1/analytics.py tests/admin/test_api_v1_analytics.py
git commit -m "feat(v94): Execution tab -- exit-quality verdict first, unrecorded exits visible, hold time as strips"
```

---

### Task T4: Edge tab

**Files:** Modify (from stub): `tabs/edge.ts`; Create: `tabs/edge.spec.ts`

**Interfaces:**
- Consumes: `store.performance().rolling_wr` / `.rolling_exp_r`, `store.strategies()` (registry rows + `cumulative`), `store.calibration()`, errors; `sb-line-chart`, `sb-small-multiples`, `sb-data-table`, `sb-histogram`, `sb-chip`.
- Produces: `<sb-edge-tab>`; computeds `rollingWrSeries()`, `rollingExpRSeries()`, `strategyPanes()`, `registryRows()`, `decileBins()`, `decayAlerts()`.

- [ ] **Step 1: Failing spec**

```ts
  it('leads with rolling win rate and rolling ExpR on a shared axis', () => {
    const { el } = render();
    const charts = el.querySelectorAll('sb-line-chart');
    expect(charts.length).toBeGreaterThanOrEqual(2);
    expect(el.textContent).toContain('Rolling win rate');
    expect(el.textContent).toContain('Rolling ExpR');
  });

  it('draws cumulative R per strategy as small multiples with one y-domain', () => {
    const { el, fixture } = render();
    expect(el.querySelector('sb-small-multiples')).not.toBeNull();
    expect(fixture.componentInstance['strategyPanes']().length).toBeGreaterThan(0);
  });

  it('badges the calibration panels all-time', () => {
    const { el } = render();
    expect(el.textContent).toContain('all-time');
  });

  it('carries drift as a registry column, not a separate table', () => {
    const { el } = render();
    expect(el.querySelectorAll('sb-data-table').length).toBe(2);   // registry + confidence/tier
    expect(el.textContent).toContain('Drift');
  });
```

- [ ] **Step 2: Implement**

- Rolling panels: two `sb-line-chart`s, the first with `referenceLine` = the pooled win rate (`performance().win_rate`), the second with `referenceLine = 0`. Both scoped; both carry `[n]="store.scopeN()"`.
- `strategyPanes()`: `Object.entries(store.strategies()?.cumulative ?? {})` → `{ title, series: [{name, points: [{date, value: cum_r}]}], n }`, keeping only strategies whose `contribution.n >= (heatGrid()?.min_cell_n ?? 20)` and folding the rest into one `Other` pane by summing their series on shared dates.
- Registry table: existing `STRATEGY_COLUMNS` plus a `drift` column (from `store.calibration()?.drift`, matched by strategy name) and v93's `soak` column. Mark the panel `[allTime]="true"` and pass `registry_scope`.
- Calibration panels: decile histogram (`max=100`, `referenceLine=80`), confidence-level table, tier table — all `[allTime]="true"`. **Verify the tier table renders against live data**: the payload key is `levels` (writer) and an older reader looked for `tiers`; bind to `calibration().levels` and assert in the spec that a `levels` payload produces rows.

- [ ] **Step 3: Spec → PASS. Commit**

```bash
git add frontend/src/app/workspaces/analytics/tabs/edge.ts frontend/src/app/workspaces/analytics/tabs/edge.spec.ts
git commit -m "feat(v94): Edge tab -- rolling win rate and ExpR, cumulative R small multiples, registry with drift and calibration"
```

---

### Task T5: Pipeline tab

**Files:** Modify (from stub): `tabs/pipeline.ts`; Create: `tabs/pipeline.spec.ts`

**Interfaces:** Consumes `store.plans()`, `store.plansError()`. Produces `<sb-pipeline-tab>`; computeds `funnelBins()`, `badgeBins()`, `tierBins()`, `fillRateText()`.

- [ ] **Step 1: Failing spec**

```ts
  it('renders the funnel with N per stage and badges the tab all-time', () => {
    const { el } = render();
    expect(el.textContent).toContain('all-time');
    expect(el.querySelectorAll('sb-histogram').length).toBe(3);      // funnel, badges, tiers
    expect(el.textContent).toContain('posted');
  });

  it('retries the one failed fetch', () => {
    const { el } = render({ plans: signal(null), plansError: signal('boom') });
    expect(el.querySelector('sb-panel-error')).not.toBeNull();
  });
```

- [ ] **Step 2: Implement** — port the existing Plans-tab markup from `analytics.ts` (`grep -n "@case ('plans')" -A 55 frontend/src/app/workspaces/analytics/analytics.ts`) onto the four-part panel shape, with `[allTime]="true"` on each panel and stage counts in the histogram labels. No new charts.

- [ ] **Step 3: Spec → PASS. Commit**

```bash
git add frontend/src/app/workspaces/analytics/tabs/pipeline.ts frontend/src/app/workspaces/analytics/tabs/pipeline.spec.ts
git commit -m "feat(v94): Pipeline tab -- funnel, fill rate, badge and tier distribution on the new panel chrome"
```

---

### Task T6: Tuning tab

**Files:** Modify (from stub): `tabs/tuning.ts`; Create: `tabs/tuning.spec.ts`

**Interfaces:** Consumes the untouched tuning slice (`jobs`, `job`, `grid`, `proposals`, `launching`, `launchError`, `proposing`, `proposeError`, `proposeResult`) and its methods (`launch`, `propose`, `deleteProposal`, `loadJob`, `loadTuning`). Produces `<sb-tuning-tab>`.

- [ ] **Step 1: Failing spec** — port the existing tuning assertions from `analytics.spec.ts` (`grep -n "tuning\|launch\|propos" frontend/src/app/workspaces/analytics/analytics.spec.ts`) into the new file, unchanged in intent, including the one that proves progress comes from the `jobs` **event**, never a timer.

- [ ] **Step 2: Implement** — move the template block (`grep -n "@case ('tuning')" -A 150 frontend/src/app/workspaces/analytics/analytics.ts`) and every member it needs (`gridColumns`, `gridKeys`, `pastJobsKeys`, `gridRowKey`, `gridPage`, `pastJobRowKey`, `pastJobsPage`, `pastJobsColumns`, `jobStateLabel`, `jobTone`, `launch`, `gridHeading`, the two confirm dialogs and their view models) into `tabs/tuning.ts`, **verbatim except for the panel chrome**. Wrap each section in `sb-panel` + `sb-panel-header` (no `n`, no all-time badge — this tab is not scoped).

- [ ] **Step 3: Spec → PASS. Commit**

```bash
git add frontend/src/app/workspaces/analytics/tabs/tuning.ts frontend/src/app/workspaces/analytics/tabs/tuning.spec.ts
git commit -m "refactor(v94): Tuning tab moved to its own component, restyled, behaviour unchanged"
```

---

### Task T7: Retire the old page

**Files:**
- Modify: `frontend/src/app/workspaces/analytics/analytics.ts` (delete every `@case` block and every member the six tabs took over; keep only the shell from S6)
- Delete: `frontend/src/app/workspaces/analytics/sections/exit-quality.ts`, `sections/exit-quality.spec.ts`, `sections/strategy-contribution.ts`, `sections/strategy-contribution.spec.ts`
- Modify: `frontend/src/app/workspaces/analytics/analytics.columns.ts` (delete `breakdownColumns` and any column set no tab imports)
- Modify: `frontend/src/app/stores/analytics.store.ts` (delete computeds and state no tab reads)
- Modify: `frontend/src/app/workspaces/analytics/analytics.spec.ts`

- [ ] **Step 1: Find every dead export**

```bash
cd frontend
for sym in breakdownColumns ExitQualitySectionComponent StrategyContributionComponent RELOCATED_METRICS DERIVED_METRICS rateBars zeroFilledBars monthBars binRMultiples; do
  echo "== $sym"; git grep -n "$sym" -- src | grep -v "analytics.columns.ts\|sections/" | head -5
done
```

Anything with no consumer outside its own definition file is dead. **Do not delete a symbol another workspace imports** — `trade-detail.store.ts` uses `analyticsStrategies()`; `dashboard.store.ts` uses `analyticsSnapshot()`.

- [ ] **Step 2: Delete** the four `sections/` files, the old `@case` blocks, and the dead symbols Step 1 named. `analytics.ts` should end at ~150 lines.

- [ ] **Step 3: Verify** — `cd frontend && npx tsc --noEmit -p tsconfig.json` → clean. Then run every analytics spec in one command:

```bash
npm test -- --include 'src/app/workspaces/analytics/**/*.spec.ts' --include src/app/stores/analytics.store.spec.ts
```

→ all PASS. (If `--include` cannot take a glob in this Angular version, run the seven files individually; do **not** substitute a bare `npm test` — Task V4 owns that.)

- [ ] **Step 4: Confirm the file shrank**

```bash
wc -l frontend/src/app/workspaces/analytics/analytics.ts frontend/src/app/workspaces/analytics/tabs/*.ts
```

Expect `analytics.ts` ≤ 160 and no tab file over ~400. A tab over 400 splits into `tabs/sections/<name>.ts` **now**, not later.

- [ ] **Step 5: Commit**

```bash
git add -A frontend/src/app/workspaces/analytics frontend/src/app/stores/analytics.store.ts
git commit -m "refactor(v94): retire the 2233-line analytics component and its two section files"
```
