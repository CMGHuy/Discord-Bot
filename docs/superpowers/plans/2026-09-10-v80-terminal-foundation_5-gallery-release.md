# v80 — Terminal foundation, part 5: gallery, verification, release

Part of `2026-09-10-v80-terminal-foundation_0-index.md`. Read its Global
Constraints before starting any task here.

# Phase 4 — Gallery, verification, release

## Parallelisation

- **Sequential throughout.**
  - **F25** waits for all of Group A (F4–F20): the gallery consumes every
    component, and `gallery.spec.ts` goes green only once it renders all of them.
  - **F26** waits for F25 and F23: it walks the finished gallery and the
    finished chart palette.
  - **F27** waits for F26: the one full run covers any fix the walk produced.
  - **F28** comes last: a version bump goes after green, and the regeneration
    after the bump.

---

### Task F25: The gallery is the reference for every D4 component

**Files:**
- Modify: `frontend/src/app/workspaces/gallery/gallery.ts`
- Test: `frontend/src/app/workspaces/gallery/gallery.spec.ts`

**Interfaces:**
- Consumes everything Group A produced:
  - `ButtonVariant` with `danger-icon` (F4), the nine `ChipTone`s (F6);
  - `EmptyStateComponent.reason` (F11), `SectionHead`'s `[back]`/`[status]` slots (F12);
  - `FilterBar.shown`/`total` (F13), `held()` (F14);
  - `Segmented`/`SegmentOption` (F15), `Figure`/`FigureStrip` (F16);
  - `PanelGrid` (F17), `Status` (F18), `Hint` (F19), `PnlCell` (F20);
  - v77's `trash` icon.
- Produces: nothing a later task consumes. It turns the `renders sb-…`
  cases red since F15 back to green.

- [ ] **Step 1: Write the failing tests**

Append to `frontend/src/app/workspaces/gallery/gallery.spec.ts`:

```ts
describe('the gallery is the v80 D6 reference', () => {
  it("shows every button variant, including v77's danger-icon", () => {
    for (const variant of ['primary', 'secondary', 'danger', 'ghost', 'icon', 'danger-icon', 'link', 'chip', 'segment']) {
      expect(GALLERY).toContain(`'${variant}'`);
    }
  });

  it('shows all nine chip tones', () => {
    for (const tone of ['neutral', 'good', 'warn', 'info', 'q1', 'q2', 'q3', 'q4', 'q5']) {
      expect(GALLERY).toContain(`'${tone}'`);
    }
  });

  it('shows every status shape and both panel-grid tracks', () => {
    for (const needle of ["'PENDING'", "'ACTIVE'", "'PARTIAL'", "'CLOSED'", 'track="narrow"', 'track="wide"']) {
      expect(GALLERY).toContain(needle);
    }
  });

  it('shows both empty-state reasons', () => {
    expect(GALLERY).toContain('reason="measured-zero"');
    expect(GALLERY).toContain('reason="no-data-yet"');
  });

  it('renders the new components in both registers', () => {
    expect(GALLERY).toContain("'register-presentation'");
    expect(GALLERY).toContain("'register-instrument'");
  });
});
```

Inside the existing `describe('the gallery renders', …)` block, after `mounts without throwing`, add:

```ts
  it('renders one row per cell-contract case, with minutes in every Held value', () => {
    const fixture = TestBed.createComponent(Gallery);
    fixture.detectChanges();
    const table = (fixture.nativeElement as HTMLElement).querySelector('.cell-contracts')!;
    const rows = [...table.querySelectorAll('tbody tr.row')];
    const cell = (row: Element, selector: string) =>
      row.querySelector(selector)!.textContent!.replace(/\s+/g, ' ').trim();

    expect(rows).toHaveLength(4);
    expect(rows.map((r) => r.querySelector('td:last-child')!.textContent!.trim()))
      .toEqual(['4d 2h 15m', '4d 0h 5m', '3h 0m', '45m']);
    expect(cell(rows[0], 'sb-direction-arrow')).toBe('▲');
    expect(cell(rows[1], 'sb-direction-arrow')).toBe('▼');
    expect(cell(rows[0], 'sb-pnl-cell')).toBe('+4.20% (+9.80 €)');
    expect(cell(rows[2], 'sb-pnl-cell')).toBe('+0.40%');
    expect(cell(rows[3], 'sb-pnl-cell')).toBe('—');
    expect(cell(rows[0], 'sb-confidence-cell')).toBe('Lv4 · 78');
    expect(cell(rows[2], 'sb-confidence-cell')).toBe('Lv5');
    expect(cell(rows[0], 'sb-plan-cell')).toContain('→');
  });
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `(cd frontend && npx ng test --watch=false --include='**/gallery.spec.ts')`

Expected: FAIL.
- The `renders sb-segmented`, `sb-figure`, `sb-figure-strip`,
  `sb-panel-grid`, `sb-status`, `sb-hint` and `sb-pnl-cell` cases fail, as
  they have since F15–F20.
- Every `v80 D6` case fails.
- The cell-contract mount test fails on a null `.cell-contracts`.

- [ ] **Step 3: Implement**

In `frontend/src/app/workspaces/gallery/gallery.ts`, replace the import block
(from `import { ChangeDetectionStrategy, Component, signal } from '@angular/core';`
through `import { StatusIndicator } from '../../ui/status-indicator';`) with:

```ts
import { ChangeDetectionStrategy, Component, TemplateRef, computed, signal, viewChild } from '@angular/core';

import { ChartResponse } from '../../api/models';
import { Async, AsyncEmptyReason } from '../../ui/async';
import { Button, ButtonVariant } from '../../ui/button';
import { ChartContainer } from '../../ui/chart-container';
import { TradeChart } from '../../ui/chart/trade-chart';
import { Chip, ChipTone, QualityChip, qualityTone } from '../../ui/chip';
import { ChipRow } from '../../ui/chip-row';
import { ColumnPickerComponent } from '../../ui/column-picker';
import { ConfidenceCell } from '../../ui/confidence-cell';
import { ConfirmDialog } from '../../ui/confirm-dialog';
import { DataTable } from '../../ui/data-table/data-table';
import { ColumnDef, PageSpec, RowContext } from '../../ui/data-table/data-table.types';
import { DirectionArrow } from '../../ui/direction-arrow';
import { EmptyStateComponent } from '../../ui/empty-state';
import { Figure, FigureStrip } from '../../ui/figure';
import { FilterBar, FilterChip, FilterChips } from '../../ui/filter-bar';
import { Flash } from '../../ui/flash';
import { held, money, num, pct, rMultiple, signed } from '../../ui/format';
import { Checkbox, Select, SelectOption, TextInput } from '../../ui/form-controls';
import { Hint } from '../../ui/hint';
import { Histogram, HistogramBin } from '../../ui/histogram';
import { Icon, IconName } from '../../ui/icon';
import { ControlRow, Drawer, Panel, Tab, TabBar } from '../../ui/layout';
import { LineChartSeries } from '../../ui/line-chart';
import { LineChart } from '../../ui/line-chart';
import { Magnitude } from '../../ui/magnitude';
import { MetricCard } from '../../ui/metric-card';
import { MetricChip } from '../../ui/metric-chip';
import { PaginationComponent } from '../../ui/pagination';
import { PanelGrid } from '../../ui/panel-grid';
import { PlanCell } from '../../ui/plan-cell';
import { PlanLifecycleDiagram } from '../../ui/plan-lifecycle-diagram';
import { PnlCell } from '../../ui/pnl-cell';
import { RowLink } from '../../ui/row-link';
import { SectionHead } from '../../ui/section-head';
import { SegmentOption, Segmented } from '../../ui/segmented';
import { Sparkline } from '../../ui/sparkline';
import { Status } from '../../ui/status';
import { StatusCell, StatusCellRow } from '../../ui/status-cell';
import { StatusIndicator } from '../../ui/status-indicator';
```

After the `GalleryRow` interface, add:

```ts
/** One row of the v80 D6 cell-contract table. */
interface ContractRow {
  id: string;
  ticker: string;
  direction: 'bullish' | 'bearish';
  entry: number | null;
  target: number;
  stop: number;
  trigger: number | null;
  pnlPct: number | null;
  pnlAmount: number | null;
  level: number | null;
  score: number | null;
  heldHours: number;
}
```

Replace the component's `imports: [ … ],` array with:

```ts
  imports: [
    Async,
    Button,
    ChartContainer,
    Checkbox,
    Chip,
    ChipRow,
    ColumnPickerComponent,
    ConfidenceCell,
    ConfirmDialog,
    ControlRow,
    DataTable,
    DirectionArrow,
    Drawer,
    EmptyStateComponent,
    Figure,
    FigureStrip,
    FilterBar,
    FilterChips,
    Flash,
    Hint,
    Histogram,
    Icon,
    LineChart,
    Magnitude,
    MetricCard,
    MetricChip,
    Panel,
    PaginationComponent,
    PanelGrid,
    PlanCell,
    PlanLifecycleDiagram,
    PnlCell,
    QualityChip,
    RowLink,
    SectionHead,
    Segmented,
    Select,
    Sparkline,
    Status,
    StatusCell,
    StatusIndicator,
    TabBar,
    TextInput,
    TradeChart,
  ],
```

In the template, replace:

```html
      <p class="section-help">Hover any button above to see its hover state.</p>
      <sb-control-row>
        <button sb-button variant="primary" type="button" [disabled]="true">disabled</button>
```

with:

```html
      <p class="sb-help">
        Hover any button above to see its hover state. <code>chip</code> and
        <code>segment</code> are deprecated (v80 D4): use sb-segmented.
      </p>
      <sb-control-row>
        <button sb-button variant="icon" type="button" aria-label="Menu"><sb-icon name="menu" /></button>
        <button sb-button variant="danger-icon" type="button" aria-label="Delete"><sb-icon name="trash" /></button>
      </sb-control-row>
      <sb-control-row>
        <button sb-button variant="primary" type="button" [disabled]="true">disabled</button>
```

Replace:

```html
          <sb-quality-chip [value]="level" [label]="'Lv' + level" />
        }
      </sb-chip-row>
    </sb-panel>
```

with:

```html
          <sb-quality-chip [value]="level" [label]="'Lv' + level" />
        }
      </sb-chip-row>
    </sb-panel>

    <!-- -- segmented (v80 D4) ------------------------------------------------ -->
    <sb-section-head [heading]="'Segmented'" [level]="2" />
    <sb-panel>
      <sb-segmented label="Status" [options]="segmentOptions" [(value)]="segmentValue" />
      <p class="sb-help">
        Arrow keys, Home and End move the selection. In a narrow box the
        options scroll sideways instead of clipping:
      </p>
      <div class="narrow-demo">
        <sb-segmented label="Range" [options]="rangeOptions" [(value)]="rangeValue" />
      </div>
    </sb-panel>
```

Replace:

```html
    <sb-panel heading="sb-section-head, both levels">
      <sb-section-head heading="Level 1 heading" [level]="1" />
      <sb-section-head heading="Level 2 heading" [level]="2" />
    </sb-panel>
```

with:

```html
    <sb-panel heading="sb-section-head, both levels, back and status slots">
      <sb-section-head heading="Level 1 heading" [level]="1" />
      <sb-section-head heading="Level 2 heading" [level]="2" />
      <sb-section-head heading="AAPL" [level]="1">
        <sb-row-link back [link]="['/ui']">Trades</sb-row-link>
        <span status class="num">as of 14:02 · 3 open</span>
      </sb-section-head>
    </sb-panel>
```

Replace:

```html
    <sb-panel heading="sb-control-row / sb-filter-bar">
      <sb-filter-bar [activeCount]="1">
        <sb-filter-chips [chips]="filterChips" [selected]="'open'" />
      </sb-filter-bar>
    </sb-panel>
    <sb-panel heading="sb-tab-bar">
      <sb-tab-bar [tabs]="tabs" [active]="activeTab()" (activeChange)="activeTab.set($event)" />
    </sb-panel>
```

with:

```html
    <sb-panel heading="sb-filter-bar -- counts, clear, two columns in a narrow box">
      <sb-filter-bar [activeCount]="2" [shown]="12" [total]="40">
        <sb-select label="Strategy" placeholder="Any strategy" [options]="selectOptions" />
        <sb-text-input label="Ticker" placeholder="AAPL" />
      </sb-filter-bar>
      <div class="narrow-demo">
        <sb-filter-bar [activeCount]="1">
          <sb-select label="Horizon" placeholder="All horizons" [options]="selectOptions" />
          <sb-checkbox label="Has note" [checked]="true" />
        </sb-filter-bar>
      </div>
    </sb-panel>
    <sb-panel heading="sb-filter-chips (deprecated, v80 D4: use sb-segmented)">
      <sb-filter-chips [chips]="filterChips" [selected]="'open'" />
    </sb-panel>
    <sb-panel heading="sb-tab-bar -- scrolls with an edge fade when the tabs do not fit">
      <sb-tab-bar [tabs]="tabs" [active]="activeTab()" (activeChange)="activeTab.set($event)" />
      <div class="narrow-demo">
        <sb-tab-bar [tabs]="tabs" [active]="activeTab()" (activeChange)="activeTab.set($event)" />
      </div>
    </sb-panel>
    <sb-panel heading="sb-status -- the marker's shape carries the state">
      <sb-control-row>
        @for (status of statuses; track status) {
          <sb-status [status]="status" />
        }
      </sb-control-row>
    </sb-panel>
    <sb-panel heading="sb-hint -- hover, focus or tap; Escape or a tap elsewhere closes">
      <p class="sb-help">
        Expectancy
        <sb-hint text="Average R per closed trade, after costs, pooled across strategies." label="About expectancy" />
      </p>
    </sb-panel>
```

Replace:

```html
      <sb-control-row>
        <sb-empty-state title="No results" />
        <sb-empty-state title="No results" hint="Widen the date range." />
      </sb-control-row>
```

with:

```html
      <sb-panel-grid track="narrow">
        <sb-empty-state title="No results" />
        <sb-empty-state title="No results" hint="Widen the date range." />
        <sb-empty-state title="No trades closed in range" reason="measured-zero" />
        <sb-empty-state title="No quotes yet" hint="The feed has not reported." reason="no-data-yet" />
      </sb-panel-grid>
```

Replace:

```html
    <sb-section-head [heading]="'Metrics and charts'" [level]="2" />
    <sb-panel>
      <sb-control-row>
```

with:

```html
    <!-- -- figures (v80 D4) ------------------------------------------------- -->
    <sb-section-head [heading]="'Figures'" [level]="2" />
    <sb-figure-strip>
      <sb-figure label="Expectancy" [value]="0.21" unit="R" tone="pnl" sub="n = 184 closed" />
      <sb-figure label="Win rate" [value]="54.2" unit="%" [decimals]="1" />
      <sb-figure label="Max drawdown" [value]="-6.4" unit="%" [decimals]="1" tone="pnl" />
      <sb-figure label="Portfolio heat" [value]="82" unit="%" [decimals]="0" tone="caution" />
      <sb-figure label="Balance" [value]="null" sub="awaiting broker sync" />
    </sb-figure-strip>

    <!-- -- panel grid (v80 D4) ---------------------------------------------- -->
    <sb-section-head [heading]="'Panel grid'" [level]="2" />
    <sb-panel-grid track="narrow">
      @for (n of [1, 2, 3, 4]; track n) {
        <sb-panel [heading]="'Narrow track ' + n"><p class="sb-help">220px minimum</p></sb-panel>
      }
    </sb-panel-grid>
    <sb-panel-grid track="wide">
      @for (n of [1, 2, 3]; track n) {
        <sb-panel [heading]="'Wide track ' + n"><p class="sb-help">320px minimum</p></sb-panel>
      }
    </sb-panel-grid>

    <sb-section-head [heading]="'Metrics and charts'" [level]="2" />
    <sb-panel>
      <p class="sb-help">sb-metric-card and sb-metric-chip are deprecated (v80 D4): use sb-figure.</p>
      <sb-control-row>
```

Replace:

```html
      <sb-pagination [pagination]="pageSpec" />
    </sb-panel>
```

with:

```html
      <sb-pagination [pagination]="pageSpec" />
    </sb-panel>

    <!-- -- v80 D6: both registers, and one row per table cell contract -------
         The cell templates come first: contractColumns() reads them through
         viewChild, and the table below must find them resolved. -->
    <ng-template #directionCell let-row><sb-direction-arrow [direction]="row.direction" /></ng-template>
    <ng-template #planCell let-row>
      <sb-plan-cell [entry]="row.entry" [target]="row.target" [stop]="row.stop" [trigger]="row.trigger" />
    </ng-template>
    <ng-template #pnlCell let-row><sb-pnl-cell [pct]="row.pnlPct" [amount]="row.pnlAmount" currency="€" /></ng-template>
    <ng-template #confidenceCell let-row><sb-confidence-cell [level]="row.level" [score]="row.score" /></ng-template>

    <sb-section-head [heading]="'Both registers, and the table cell contracts'" [level]="2" />
    <p class="sb-help">
      The same strip and table in each density. The rows follow the cell contracts: direction is
      one triangle; the plan is one column, entry → target / stop; P&L carries percent and amount;
      confidence is text; Held always shows minutes.
    </p>
    @for (register of registers; track register) {
      <div class="register-demo" [class]="register">
        <h3 class="sb-label">{{ register }}</h3>
        <sb-figure-strip>
          <sb-figure label="Open P&L" [value]="1.84" unit="%" tone="pnl" />
          <sb-figure label="Open risk" [value]="2.1" unit="R" />
          <sb-figure label="Heat" [value]="64" unit="%" [decimals]="0" tone="caution" />
        </sb-figure-strip>
        <sb-panel heading="Positions" [flush]="true">
          <sb-data-table
            class="cell-contracts"
            [rows]="contractRows"
            [columns]="contractColumns()"
            [visible]="contractVisible"
            [rowKey]="contractKey"
          />
        </sb-panel>
      </div>
    }
```

In `styles`, replace:

```css
    .numerics-demo sb-magnitude { display: inline-block; width: 48px; margin-left: var(--space-8); }
  `,
```

with:

```css
    .numerics-demo sb-magnitude { display: inline-block; width: 48px; margin-left: var(--space-8); }

    /* v80 D6 -- a phone-width box, so the container-driven layouts (filter
       bar, segmented, tab bar) show their narrow behaviour at any window size. */
    .narrow-demo { max-width: 320px; margin-top: var(--space-10); }
    .register-demo { display: grid; gap: var(--space-10); }
    .register-demo h3 { margin: 0; }
  `,
```

In the class, replace:

```ts
  protected readonly buttonVariants: (
    'primary' | 'secondary' | 'danger' | 'ghost' | 'icon' | 'chip' | 'segment' | 'link'
  )[] = ['primary', 'secondary', 'danger', 'ghost', 'icon', 'chip', 'segment', 'link'];
```

with:

```ts
  protected readonly buttonVariants: ButtonVariant[] = [
    'primary', 'secondary', 'danger', 'ghost', 'icon', 'danger-icon', 'link', 'chip', 'segment',
  ];
```

Replace:

```ts
  protected readonly chipTones: ChipTone[] = ['neutral', 'q1', 'q2', 'q3', 'q4', 'q5'];
```

with:

```ts
  protected readonly chipTones: ChipTone[] = ['neutral', 'good', 'warn', 'info', 'q1', 'q2', 'q3', 'q4', 'q5'];
```

Replace:

```ts
  protected readonly tabs: Tab[] = [
    { id: 'one', label: 'One' },
    { id: 'two', label: 'Two' },
  ];
  protected readonly activeTab = signal('one');

  protected readonly drawerOpen = signal(false);
  protected readonly confirmOpen = signal(false);
```

with:

```ts
  /** Seven tabs, so the narrow copy overflows and shows its edge fade. */
  protected readonly tabs: Tab[] = [
    { id: 'plans', label: 'Plans' },
    { id: 'strategies', label: 'Strategies' },
    { id: 'exits', label: 'Exits' },
    { id: 'regimes', label: 'Regimes' },
    { id: 'calibration', label: 'Calibration' },
    { id: 'heatmap', label: 'Heatmap' },
    { id: 'tuning', label: 'Tuning' },
  ];
  protected readonly activeTab = signal('plans');

  protected readonly drawerOpen = signal(false);
  protected readonly confirmOpen = signal(false);

  /* -- v80 D4 / D6 ---------------------------------------------------------- */

  protected readonly segmentOptions: SegmentOption[] = [
    { value: 'open', label: 'Open', count: 4 },
    { value: 'partial', label: 'Partial', count: 2 },
    { value: 'closed', label: 'Closed', count: 31 },
  ];
  protected readonly segmentValue = signal('open');
  protected readonly rangeOptions: SegmentOption[] = ['1D', '1W', '1M', '3M', '6M', 'YTD', '1Y', '2Y', '5Y', 'All']
    .map((range) => ({ value: range, label: range }));
  protected readonly rangeValue = signal('1M');

  protected readonly statuses = ['PENDING', 'ACTIVE', 'PARTIAL', 'CLOSED'];
  protected readonly registers = ['register-presentation', 'register-instrument'];
```

Replace:

```ts
  protected readonly iconNames: IconName[] = [
    'dashboard', 'trades', 'analytics', 'calendar', 'watchlist', 'risk',
    'system', 'versions', 'collapse', 'expand', 'profile', 'signout', 'menu',
  ];
```

with:

```ts
  protected readonly iconNames: IconName[] = [
    'dashboard', 'trades', 'analytics', 'calendar', 'watchlist', 'risk',
    'system', 'versions', 'collapse', 'expand', 'profile', 'signout', 'menu', 'trash',
  ];
```

Replace the class's last member:

```ts
  protected readonly qualityTone = qualityTone;
}
```

with:

```ts
  protected readonly qualityTone = qualityTone;

  /* -- v80 D6: one table row per cell contract --------------------------------
   * The Held values are the four the contract names: 4d 2h 15m, 4d 0h 5m,
   * 3h 0m, 45m. MSFT has no amount (its cell drops the bracket); NVDA is a
   * PENDING plan: trigger underlined, nothing to price, no confidence yet. */
  private readonly directionCell = viewChild.required<TemplateRef<RowContext<ContractRow>>>('directionCell');
  private readonly planCell = viewChild.required<TemplateRef<RowContext<ContractRow>>>('planCell');
  private readonly pnlCell = viewChild.required<TemplateRef<RowContext<ContractRow>>>('pnlCell');
  private readonly confidenceCell = viewChild.required<TemplateRef<RowContext<ContractRow>>>('confidenceCell');

  protected readonly contractRows: ContractRow[] = [
    { id: 'c1', ticker: 'AAPL', direction: 'bullish', entry: 178, target: 195, stop: 170, trigger: null,
      pnlPct: 4.2, pnlAmount: 9.8, level: 4, score: 78, heldHours: 98.25 },
    { id: 'c2', ticker: 'TSLA', direction: 'bearish', entry: 250, target: 230, stop: 258, trigger: null,
      pnlPct: -1.35, pnlAmount: -6.1, level: 2, score: 41, heldHours: 96 + 5 / 60 },
    { id: 'c3', ticker: 'MSFT', direction: 'bullish', entry: 412, target: 440, stop: 401, trigger: null,
      pnlPct: 0.4, pnlAmount: null, level: 5, score: null, heldHours: 3 },
    { id: 'c4', ticker: 'NVDA', direction: 'bullish', entry: null, target: 48, stop: 40, trigger: 42.5,
      pnlPct: null, pnlAmount: null, level: null, score: null, heldHours: 0.75 },
  ];
  protected readonly contractVisible = ['ticker', 'direction', 'plan', 'pnl', 'confidence', 'held'];
  protected readonly contractKey = (row: ContractRow) => row.id;
  protected readonly contractColumns = computed<ColumnDef<ContractRow>[]>(() => [
    { key: 'ticker', header: 'Ticker', value: (row) => row.ticker, sortable: true },
    { key: 'direction', header: 'Dir', cell: this.directionCell() },
    { key: 'plan', header: 'Plan', cell: this.planCell() },
    { key: 'pnl', header: 'P&L', cell: this.pnlCell(), numeric: true, sortable: true },
    { key: 'confidence', header: 'Confidence', cell: this.confidenceCell() },
    { key: 'held', header: 'Held', value: (row) => held(row.heldHours), numeric: true },
  ]);
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `(cd frontend && npx ng test --watch=false --include='**/gallery.spec.ts' --include='**/primitives.spec.ts' --include='**/register.spec.ts' --include='**/numeric.spec.ts' --include='**/async-coverage.spec.ts')`

Expected: PASS.
- Every `renders sb-…` case is green again.
- The gallery is a call site, so the gates hold it too: no raw button,
  input or select, no hex literal, no `toFixed` in a template.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/gallery/gallery.ts frontend/src/app/workspaces/gallery/gallery.spec.ts
git commit -m "feat(v80): gallery shows every D4 component, both registers and the cell contracts"
```

---

### Task F26: Walk the gallery and the chart fixtures in a browser (gate 8)

**Files:**
- None, unless the walk finds a defect. A fix edits that task's files and
  re-runs that task's narrow test.

**Interfaces:**
- Consumes: the finished gallery (F25) and the finished chart palette (F21–F23).
- Produces: a written walk result in this task's report. Nothing a later task reads.

This is a look, not a hash check: the fixture hashes change by design.

- [ ] **Step 1: Start the admin API and the dev server**

From the worktree root, each with `run_in_background`:

```bash
python admin_ui.py
```

```bash
(cd frontend && npm start)
```

Wait until the dev server reports `localhost:4200`. `frontend/proxy.conf.json`
forwards `/api` and `/static` to the API on `:1234`.

- [ ] **Step 2: Walk `/ui` at 1440px**

Log in at `http://localhost:4200` with the admin credentials from `.env`. If
this session cannot read `.env`, ask the human partner to log in. Open
`http://localhost:4200/ui` at a 1440×900 viewport, using the Playwright MCP's
`browser_resize` if it is connected, or a desktop browser window. Check, and
write down each result:

1. The ground is `#0c0f16` and panels are `#131722`, separated by hairlines
   with no card shadows. Corners are 2px.
2. **Buttons:** primary is the fill blue with white text; secondary is a
   hairline; danger outlines red and fills on hover; `danger-icon` shows the
   trash glyph.
3. **Segmented:** the selected option sits on a blue tint, and the narrow
   copy scrolls sideways.
4. **Figure strip:** four figures on the first row and the fifth wrapped, with
   no doubled rule. Drawdown is red, Heat amber, Balance an em dash.
5. **Panel grids:** 220px and 320px tracks.
6. **Tab bar:** the narrow copy shows a right-edge fade, which moves to the
   left edge once scrolled to the end.
7. **Hint:** opens on hover, on Tab focus and on click; closes on Escape and
   on a click elsewhere.
8. **Status markers:** ring, disc, half disc, square.
9. **Empty states:** dashed boxes, with "RESULT: 0" and "AWAITING DATA" labels.
10. **Cell-contract rows, in both registers:**
    - one triangle per row, and no L/S;
    - `entry → target / stop` in one column;
    - `+4.20% (+9.80 €)`;
    - `Lv4 · 78`;
    - Held reads `4d 2h 15m`, `4d 0h 5m`, `3h 0m`, `45m`.

- [ ] **Step 3: Walk `/ui` at 390px**

Resize to 390×844 and check:

1. Buttons, selects, text inputs, pager buttons and tabs are 44px tall. Field
   text is 16px, so focusing an input does not zoom the page.
2. Every `sb-control-row` stacks to one column.
3. The filter bar is a two-column grid.
4. The figure strips show two per row at 20px.
5. Both panel grids are one column.
6. The cell-contract tables:
   - keep their `<table>`;
   - pin the Ticker column while the rest scroll sideways;
   - show a "SORT" select above the table, and choosing "P&L ↓" re-sorts
     nothing (static rows) but does not error.
7. Open the drawer: it covers the full width and its bottom edge sits above
   the browser toolbar.

- [ ] **Step 4: Render and look at one Discord chart per overlay kind**

```bash
python scripts/dev/render_chart_fixtures.py --out "$TMPDIR/v80-chart-fixtures" --verify-overlays
```

(Use the session scratchpad directory for `--out` if `$TMPDIR` is unset.)
Expected: the script reports every fixture rendered and every overlay drawn.
Open each PNG with the Read tool and check:

1. The background is `#131722` and tick labels are legible grey (`#9195a0`,
   not the old `#666666`).
2. Candles, target and stop are `#17c98e` and `#ff5470`; entry is `#4c8dff`;
   last price is amber.
3. TP2 is purple (`#a868e0`); Keltner bands are dashed grey; volume-profile
   bars are lavender (`#b39ddb`).
4. The target-side overlay is orange (`#c97a22`) and the stop-side overlay is
   teal (`#1a9db3`). Nothing is pink.
5. The disclaimer line is amber; the v2 corner tag and trendline touch
   diamonds are light grey.

- [ ] **Step 5: Stop the background processes, and fix forward**

Stop both background commands. For each defect found:
1. Fix it in the owning task's files.
2. Run that task's narrow test.
3. Commit it as `fix(v80): <what>`.

If nothing needed fixing, there is nothing to commit. Record the walk result
(the checklist above, each item pass or fail) in the task report.

---

### Task F27: Full-suite verification (gate 9)

**Files:**
- None, unless a suite is red.

**Interfaces:**
- Consumes: everything F1–F26 committed.
- Produces: the green verdict F28 requires.

- [ ] **Step 1: Run the Python suite once**

Run `python scripts/dev/testrun.py full`, or dispatch the `test-runner`
subagent so the progress lines stay out of context. Expect `0 failed`,
`0 xfailed`. `tests/charts/test_chart_theme.py` is in the slow tier, so only
this run exercises it together with everything else.

- [ ] **Step 2: Run the frontend suite once**

Run: `(cd frontend && npm test)`

Expected: every spec file passes. `ng test` intermittently dies after exactly
60 seconds with `[vitest-pool-runner]: Timeout waiting for worker to respond`
under machine load (`frontend/vitest.config.ts` records why). That is a
re-run, not a failure.

- [ ] **Step 3: Fix forward**

If either suite is red, the failures are this plan's regressions. Fix them in
the owning task's files, commit each as `fix(v80): <what>`, and re-run only
the suite that was red. This task is done when both runs are green.

---

### Task F28: Release and close-out

**Files:**
- Modify: `VERSION.json`
- Modify: `swingbot/admin/version_history.json` (regenerated)
- Modify: `docs/superpowers/plans/2026-09-10-v80-terminal-foundation_0-index.md` (closing note)
- Move: the seven `2026-09-10-v80-terminal-foundation_*.md` plan files into
  `docs/superpowers/plans/implemented/`

**Interfaces:**
- Consumes: F27's green verdict.
- Produces: `ui` and `bot` minor releases, `merge(v80)` on `main`, the worktree
  removed, and the plan off the live list.

Both lines bump by observable difference (spec, "Why this exists"). The admin
looks different on every screen (`ui minor`), and every Discord chart image
looks different (`bot minor`). The numbers are resolved now, from `main`'s
`VERSION.json`, never predicted.

- [ ] **Step 1: Bring `main` in**

From the worktree:

```bash
git merge main
```

If the merge resolved conflicts, the resolution is unrun code: run F27's two
suites once more. If it merged cleanly, do not re-run either.

- [ ] **Step 2: Resolve the version numbers**

```bash
git show main:VERSION.json
```

The new `ui` is the next minor of the `ui` shown (`X.Y.Z` → `X.(Y+1).0`), and
the same for `bot`. Get the UTC stamp:

```bash
python -c "import datetime; print(datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H-%M-%S'))"
```

- [ ] **Step 3: Commit the two releases, separately**

Set `"ui"` to the new ui number and `"ui_updated"` to the stamp in
`VERSION.json`, then:

```bash
git add VERSION.json
git commit -m "release(ui): <new ui> -- terminal foundation"
```

Set `"bot"` to the new bot number and `"bot_updated"` to a fresh stamp, then:

```bash
git add VERSION.json
git commit -m "release(bot): <new bot> -- TradingView Blue chart palette"
```

- [ ] **Step 4: Regenerate the version history after the bump commits**

```bash
python scripts/dev/build_version_matrix.py
python scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py
git add swingbot/admin/version_history.json
git commit -m "chore(ui): <new ui> -- terminal foundation; bot <new bot> -- TradingView Blue chart palette"
```

Expected: the test passes. The newest pair in `version_history.json` names
both release commits, not `"uncommitted"`.

- [ ] **Step 5: Merge into `main`**

Read the branch name off the worktree list. `EnterWorktree` prefixes
`worktree-`, so it is probably `worktree-2026-09-10-v80-terminal-foundation`:

```bash
git worktree list
```

From the main tree (`E:/Documents/Private/Projects/Discord-Bot`):

```bash
git status --short
git merge --no-ff <branch> -m "merge(v80): terminal foundation"
```

If `git status` shows uncommitted changes in files this plan touched, stop
and ask the human partner: another session owns them. After a clean merge,
run neither suite again.

- [ ] **Step 6: Remove the worktree and its branch**

```bash
git worktree remove .claude/worktrees/2026-09-10-v80-terminal-foundation
git rev-list --count main..<branch>
```

Expected: `0`. Only then:

```bash
git branch -d <branch>
```

Neither name contains `backup` or `stable`. A non-zero count means stop and ask.

- [ ] **Step 7: Close the plan out**

Append to `docs/superpowers/plans/2026-09-10-v80-terminal-foundation_0-index.md`:

```markdown
## Closed

Closed <YYYY-MM-DD>: F1–F28 done, merged as `merge(v80): terminal foundation`,
released as ui <new ui> and bot <new bot>. The spec stays at the top level of
`docs/superpowers/specs/`: Migration and Phone screens are still to be
specified from its "Follow-on specs" section, so something live still builds
from it (`docs/claude/document-lifecycle.md`).
```

Then move every part and fix the references:

```bash
git mv docs/superpowers/plans/2026-09-10-v80-terminal-foundation_*.md docs/superpowers/plans/implemented/
git grep -n "plans/2026-09-10-v80-terminal-foundation_" -- . ':!docs/superpowers/plans/implemented'
```

Re-point every hit at `plans/implemented/…`. Expected after that: the grep
prints nothing. Then:

```bash
git add -A docs/superpowers/plans
git commit -m "docs(v80): close terminal foundation plan"
```

Pushing and deploying are the human partner's call; report that both are ready.
