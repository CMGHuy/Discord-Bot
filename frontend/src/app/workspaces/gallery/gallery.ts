import { ChangeDetectionStrategy, Component, signal } from '@angular/core';

import { ChartResponse } from '../../api/models';
import { Async, AsyncEmptyReason } from '../../ui/async';
import { Button } from '../../ui/button';
import { ChartContainer } from '../../ui/chart-container';
import { TradeChart } from '../../ui/chart/trade-chart';
import { Chip, ChipTone, QualityChip, qualityTone } from '../../ui/chip';
import { ChipRow } from '../../ui/chip-row';
import { ColumnPickerComponent } from '../../ui/column-picker';
import { ConfidenceCell } from '../../ui/confidence-cell';
import { ConfirmDialog } from '../../ui/confirm-dialog';
import { DataTable } from '../../ui/data-table/data-table';
import { ColumnDef, PageSpec } from '../../ui/data-table/data-table.types';
import { DirectionArrow } from '../../ui/direction-arrow';
import { EmptyStateComponent } from '../../ui/empty-state';
import { FilterBar, FilterChip, FilterChips } from '../../ui/filter-bar';
import { Flash } from '../../ui/flash';
import { money, num, pct, rMultiple, signed } from '../../ui/format';
import { Checkbox, Select, SelectOption, TextInput } from '../../ui/form-controls';
import { Histogram, HistogramBin } from '../../ui/histogram';
import { Icon, IconName } from '../../ui/icon';
import { ControlRow, Drawer, Panel, Tab, TabBar } from '../../ui/layout';
import { LineChartSeries } from '../../ui/line-chart';
import { LineChart } from '../../ui/line-chart';
import { Magnitude } from '../../ui/magnitude';
import { MetricCard } from '../../ui/metric-card';
import { MetricChip } from '../../ui/metric-chip';
import { PaginationComponent } from '../../ui/pagination';
import { PlanCell } from '../../ui/plan-cell';
import { PlanLifecycleDiagram } from '../../ui/plan-lifecycle-diagram';
import { RowLink } from '../../ui/row-link';
import { SectionHead } from '../../ui/section-head';
import { Sparkline } from '../../ui/sparkline';
import { StatusCell, StatusCellRow } from '../../ui/status-cell';
import { StatusIndicator } from '../../ui/status-indicator';

interface GalleryRow {
  id: string;
  ticker: string;
  pnl: number;
}

/**
 * `/ui` -- every shared primitive, every variant, side by side.
 *
 * The only surface on which the elevation ladder, the numeric law and the
 * chart ramp can be seen together and judged as one system: reviewing them
 * one workspace at a time is how inconsistency survives review. Ships in
 * the production bundle behind the same auth guard as every workspace --
 * a gallery that only exists in dev rots, because nothing fails when it
 * does. Reachable by URL only; not in the sidebar (v54 Task 5's wave).
 */
@Component({
  selector: 'sb-gallery',
  changeDetection: ChangeDetectionStrategy.OnPush,
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
    FilterBar,
    FilterChips,
    Flash,
    Histogram,
    Icon,
    LineChart,
    Magnitude,
    MetricCard,
    MetricChip,
    Panel,
    PaginationComponent,
    PlanCell,
    PlanLifecycleDiagram,
    QualityChip,
    RowLink,
    SectionHead,
    Select,
    Sparkline,
    StatusCell,
    StatusIndicator,
    TabBar,
    TextInput,
    TradeChart,
  ],
  template: `
    <h1>UI gallery</h1>

    <!-- -- buttons ------------------------------------------------------ -->
    <sb-section-head [heading]="'Buttons'" [level]="2" />
    <sb-panel>
      <sb-control-row>
        @for (variant of buttonVariants; track variant) {
          <button sb-button [variant]="variant" type="button">{{ variant }}</button>
        }
      </sb-control-row>
      <p class="section-help">Hover any button above to see its hover state.</p>
      <sb-control-row>
        <button sb-button variant="primary" type="button" [disabled]="true">disabled</button>
        <button sb-button variant="secondary" type="button" [disabled]="true">disabled</button>
        <button sb-button variant="primary" type="button" [loading]="true">loading</button>
      </sb-control-row>
    </sb-panel>

    <!-- -- form controls -------------------------------------------------- -->
    <sb-section-head [heading]="'Form controls'" [level]="2" />
    <sb-panel>
      <sb-control-row>
        @for (type of textInputTypes; track type) {
          <sb-text-input [type]="type" [label]="type" placeholder="value" />
        }
      </sb-control-row>
      <sb-control-row>
        <sb-select label="Select" placeholder="Pick one" [options]="selectOptions" />
        <sb-checkbox label="Checked" [checked]="true" />
        <sb-checkbox label="Unchecked" [checked]="false" />
        <sb-checkbox label="Disabled" [checked]="false" [disabled]="true" />
        <sb-checkbox topLabel="Top label" label="With top label" [checked]="true" />
      </sb-control-row>
    </sb-panel>

    <!-- -- chips ----------------------------------------------------------- -->
    <sb-section-head [heading]="'Chips'" [level]="2" />
    <sb-panel>
      <sb-chip-row>
        @for (tone of chipTones; track tone) {
          <sb-chip [label]="tone" [tone]="tone" />
        }
        @for (level of [1, 2, 3, 4, 5]; track level) {
          <sb-quality-chip [value]="level" [label]="'Lv' + level" />
        }
      </sb-chip-row>
    </sb-panel>

    <!-- -- composites ------------------------------------------------------ -->
    <sb-section-head [heading]="'Composites'" [level]="2" />
    <sb-panel heading="sb-section-head, both levels">
      <sb-section-head heading="Level 1 heading" [level]="1" />
      <sb-section-head heading="Level 2 heading" [level]="2" />
    </sb-panel>
    <sb-panel heading="sb-row-link">
      <sb-row-link [link]="['/ui']">AAPL</sb-row-link>
    </sb-panel>
    <sb-panel heading="sb-control-row / sb-filter-bar">
      <sb-filter-bar [activeCount]="1">
        <sb-filter-chips [chips]="filterChips" [selected]="'open'" />
      </sb-filter-bar>
    </sb-panel>
    <sb-panel heading="sb-tab-bar">
      <sb-tab-bar [tabs]="tabs" [active]="activeTab()" (activeChange)="activeTab.set($event)" />
    </sb-panel>
    <sb-panel heading="sb-drawer">
      <button sb-button variant="secondary" type="button" (click)="drawerOpen.set(true)">
        Open drawer
      </button>
      <sb-drawer [open]="drawerOpen()" heading="Drawer" (closed)="drawerOpen.set(false)">
        <p>Drawer content.</p>
      </sb-drawer>
    </sb-panel>
    <sb-panel heading="sb-confirm-dialog">
      <button sb-button variant="danger" type="button" (click)="confirmOpen.set(true)">
        Open confirm dialog
      </button>
      <sb-confirm-dialog
        [open]="confirmOpen()"
        title="Delete this?"
        consequence="This cannot be undone."
        (confirmed)="confirmOpen.set(false)"
        (cancelled)="confirmOpen.set(false)"
      />
    </sb-panel>

    <!-- -- elevation (v54 Task 29) ------------------------------------------
         The four levels side by side, so the ladder reads as a ramp rather
         than one surface judged in isolation. L3 uses the real global
         .elev-overlay class -- the same one every floating surface in this
         app takes (Task 23). L0-L2 have no reusable class of their own
         (sb-panel's own .panel rule is scoped to its own component by
         Angular's style encapsulation and cannot be borrowed here), so all
         three are local demo-only styles built straight from the tokens. -->
    <sb-section-head [heading]="'Elevation'" [level]="2" />
    <sb-panel heading="L0-L3, judged as a ramp">
      <sb-control-row>
        <div class="elev-step level-0">L0<br />bg</div>
        <div class="elev-step level-1">L1<br />surface</div>
        <div class="elev-step level-2">L2<br />surface-raised</div>
        <div class="elev-step elev-overlay">L3<br />overlay</div>
      </sb-control-row>
    </sb-panel>

    <!-- -- numerics (v54 Task 29) -------------------------------------------
         One row per case format.ts's own docstring names -- positive,
         negative, zero, absent -- across every signed/unsigned formatter,
         so a regression in any one (wrong glyph, absence rendered as zero)
         is visible at a glance rather than only in a unit test's assertion
         text. sb-magnitude sits beside R, its real home (Task 28). -->
    <sb-section-head [heading]="'Numerics'" [level]="2" />
    <sb-panel heading="num / pct / R / signed / money -- positive, negative, zero, absent">
      <table class="numerics-demo">
        <thead>
          <tr>
            <th>Case</th>
            <th class="num">num</th>
            <th class="num">pct</th>
            <th class="num">R</th>
            <th class="num">signed</th>
            <th class="num">money</th>
          </tr>
        </thead>
        <tbody>
          @for (c of numericCases; track c.label) {
            <tr>
              <td>{{ c.label }}</td>
              <td class="num">{{ fmtNum(c.value) }}</td>
              <td class="num">{{ fmtPct(c.value) }}</td>
              <td class="num">
                {{ fmtR(c.value) }}
                <sb-magnitude [value]="c.value" [max]="3" />
              </td>
              <td class="num">{{ fmtSigned(c.value) }}</td>
              <td class="num">{{ fmtMoney(c.value) }}</td>
            </tr>
          }
        </tbody>
      </table>
    </sb-panel>

    <!-- -- sb-async: all four branches side by side ------------------------ -->
    <sb-section-head [heading]="'sb-async -- all four states'" [level]="2" />
    <sb-panel>
      <sb-control-row>
        <button sb-button variant="chip" type="button" [class.on]="asyncDemo() === 'content'"
                (click)="asyncDemo.set('content')">content</button>
        <button sb-button variant="chip" type="button" [class.on]="asyncDemo() === 'loading'"
                (click)="asyncDemo.set('loading')">loading</button>
        <button sb-button variant="chip" type="button" [class.on]="asyncDemo() === 'error'"
                (click)="asyncDemo.set('error')">error</button>
        <button sb-button variant="chip" type="button" [class.on]="asyncDemo() === 'no-data-yet'"
                (click)="asyncDemo.set('no-data-yet')">empty: no-data-yet</button>
        <button sb-button variant="chip" type="button" [class.on]="asyncDemo() === 'measured-zero'"
                (click)="asyncDemo.set('measured-zero')">empty: measured-zero</button>
      </sb-control-row>
      <sb-async
        [loading]="asyncDemo() === 'loading'"
        [error]="asyncDemo() === 'error' ? 'Request failed' : null"
        [empty]="asyncDemo() === 'no-data-yet' || asyncDemo() === 'measured-zero'"
        [emptyReason]="asyncEmptyReason()"
        emptyTitle="No rows"
        emptyHint="Try a different filter."
        [skeletonRows]="3"
        [skeletonCols]="4"
      >
        <p>Loaded content.</p>
      </sb-async>
    </sb-panel>

    <!-- -- empty state ------------------------------------------------------ -->
    <sb-section-head [heading]="'Empty state'" [level]="2" />
    <sb-panel>
      <sb-control-row>
        <sb-empty-state title="No results" />
        <sb-empty-state title="No results" hint="Widen the date range." />
      </sb-control-row>
    </sb-panel>

    <!-- -- data cells and status --------------------------------------------- -->
    <sb-section-head [heading]="'Data cells and status'" [level]="2" />
    <sb-panel>
      <sb-control-row>
        <sb-status-cell [row]="statusCellRow" />
        <sb-status-indicator status="active" [current]="105" [entry]="100" [stop]="95" [target]="120" />
        <sb-direction-arrow direction="bullish" />
        <sb-direction-arrow direction="bearish" />
        <sb-confidence-cell [level]="4" [score]="81" direction="bullish" />
        <sb-plan-cell [entry]="100" [target]="120" [stop]="95" [trigger]="null" />
      </sb-control-row>
      <sb-control-row>
        <sb-magnitude [value]="2.1" [max]="4" style="width: 80px" />
        <sb-magnitude [value]="-1.3" [max]="4" style="width: 80px" />
        <sb-magnitude [value]="null" [max]="4" style="width: 80px" />
      </sb-control-row>
    </sb-panel>

    <!-- -- metrics and charts -------------------------------------------------- -->
    <sb-section-head [heading]="'Metrics and charts'" [level]="2" />
    <sb-panel>
      <sb-control-row>
        <sb-metric-card label="Expectancy" [value]="0.21" unit="R" [tone]="'pnl'" />
        <sb-metric-chip label="Win rate" [value]="54.2" unit="%" [decimals]="1" />
      </sb-control-row>
      <sb-sparkline [points]="sparklinePoints" label="Trend" />
      <sb-histogram [bins]="histogramBins" />
      <sb-line-chart [series]="lineChartSeries" />
      <sb-chart-container [loading]="false" [error]="null" [hasData]="true" [height]="200" caption="AAPL -- daily">
        <sb-trade-chart [data]="null" />
      </sb-chart-container>
    </sb-panel>

    <!-- -- charts -- one shared chrome (v54 D5) -------------------------------- -->
    <sb-section-head [heading]="'Charts'" [level]="2" />
    <p class="section-help">
      The same eight-point series, drawn four ways. Not every chart draws every
      chrome element -- the sparkline deliberately has none (axis, grid, ticks and
      tooltip all read as noise at that size), the line chart and histogram draw no
      axis or grid line -- but wherever an element IS drawn, it reads from the same
      CHART_CHROME tokens: axis/tooltip border <code>--border-strong</code>, grid
      <code>--border</code>, tick text <code>--text-muted</code> /
      <code>--text-micro</code>, tooltip surface <code>--surface-overlay</code>.
      Only the trade chart draws all four.
    </p>
    <sb-panel heading="Sparkline (no chrome by design)">
      <sb-sparkline [points]="chartComparisonSeries" label="Comparison series" />
    </sb-panel>
    <sb-panel heading="Histogram (bin labels as axis text; counts stay body text)">
      <sb-histogram [bins]="chartComparisonBins" />
    </sb-panel>
    <sb-panel heading="Line chart (tooltip only)">
      <sb-line-chart [series]="chartComparisonLineSeries" />
    </sb-panel>
    <sb-panel heading="Trade chart (axis, grid, tick text and tooltip)">
      <sb-chart-container [loading]="false" [error]="null" [hasData]="true" [height]="200" caption="Comparison series -- OHLCV, not the raw closes the other three panels show">
        <sb-trade-chart [data]="chartComparisonTradeData" />
      </sb-chart-container>
    </sb-panel>

    <!-- -- icons -------------------------------------------------------------- -->
    <sb-section-head [heading]="'Icons'" [level]="2" />
    <sb-panel>
      <sb-control-row>
        @for (name of iconNames; track name) {
          <sb-icon [name]="name" />
        }
      </sb-control-row>
    </sb-panel>

    <!-- -- lifecycle diagram ---------------------------------------------------- -->
    <sb-section-head [heading]="'Plan lifecycle'" [level]="2" />
    <sb-panel>
      <sb-plan-lifecycle-diagram />
    </sb-panel>

    <!-- -- table, pagination, column picker --------------------------------------- -->
    <sb-section-head [heading]="'Table, pagination, column picker'" [level]="2" />
    <sb-panel>
      <sb-column-picker
        tableId="gallery-demo"
        [columns]="pickableColumns"
        [defaults]="['ticker', 'pnl']"
        [visible]="['ticker', 'pnl']"
        density="full"
      />
      <sb-data-table
        [rows]="tableRows"
        [columns]="tableColumns"
        [visible]="['ticker', 'pnl']"
        [rowKey]="rowKey"
      />
      <sb-pagination [pagination]="pageSpec" />
    </sb-panel>

    <!-- -- v54 _5: accessibility and motion ---------------------------------------- -->
    <sb-section-head [heading]="'Accessibility and motion'" [level]="2" />
    <sb-panel heading="[sbFlash] -- motion that means something">
      <p class="section-help">
        Fires only when the bound value actually changes -- not on first
        render, not on a re-render reporting the same number.
      </p>
      <sb-control-row>
        <button sb-button variant="secondary" type="button" (click)="bumpFlashDemo()">
          Change the value
        </button>
        <span class="num flash-demo" [sbFlash]="flashDemo()">{{ fmtSigned(flashDemo()) }}</span>
      </sb-control-row>
    </sb-panel>

    <sb-panel heading="One live region per workspace">
      <p class="section-help">
        sb-async's one polite live region, carrying a caller-supplied summary
        rather than a running commentary.
      </p>
      <sb-control-row>
        <button sb-button variant="secondary" type="button" (click)="bumpAnnounceDemo()">
          Push an update
        </button>
      </sb-control-row>
      <sb-async
        [loading]="false"
        [error]="null"
        [empty]="false"
        emptyReason="no-data-yet"
        emptyTitle="unused"
        [announce]="announceDemo() > 0 ? announceDemo() + ' update(s) announced' : null"
      >
        <p class="section-help">
          A screen reader hears "{{ announceDemo() }} update(s) announced" once
          per push, politely -- never once per cell.
        </p>
      </sb-async>
    </sb-panel>

    <sb-panel heading="Focus trap (drawer and dialog)">
      <p class="section-help">
        Tab wraps within the panel; closing returns focus to whatever opened
        it. The plain sb-drawer demo above already carries this -- this is
        a second, self-contained instance for this section.
      </p>
      <sb-control-row>
        <button sb-button variant="secondary" type="button" (click)="a11yDrawerOpen.set(true)">
          Open focus-trap demo
        </button>
      </sb-control-row>
      <sb-drawer
        [open]="a11yDrawerOpen()"
        heading="Focus trap demo"
        (closed)="a11yDrawerOpen.set(false)"
      >
        <p>Tab cycles between the two buttons below and back; Escape or Close
           returns focus to the button that opened this panel.</p>
        <sb-control-row>
          <button sb-button type="button">First</button>
          <button sb-button type="button">Last</button>
        </sb-control-row>
      </sb-drawer>
    </sb-panel>
  `,
  styles: `
    :host { display: grid; gap: var(--space-20); padding: var(--space-20); }
    h1 { margin: 0; font-size: var(--text-title); font-weight: 600; }
    sb-panel { display: block; }

    /* -- elevation demo (v54 Task 29) -- L0-L2 straight from the tokens;
       L3 is the real global .elev-overlay class, not reimplemented here. */
    .elev-step {
      display: grid; place-items: center;
      width: 96px; height: 64px; text-align: center;
      font-size: var(--text-micro); color: var(--text-secondary);
      border-radius: var(--radius);
    }
    .elev-step.level-0 { background: var(--bg); }
    .elev-step.level-1 { background: var(--surface); border: 1px solid var(--border); }
    .elev-step.level-2 { background: var(--surface-raised); border: 1px solid var(--border); }

    /* -- numerics demo (v54 Task 29) -- .num right-aligns/monos each
       formatted cell (same class every real table cell takes); the header
       cells take it too so the unit-in-header column lines up over its
       own right-aligned figures below it. */
    .numerics-demo { border-collapse: collapse; }
    .numerics-demo th, .numerics-demo td {
      padding: var(--space-6) var(--space-10);
      text-align: left;
    }
    .numerics-demo th.num, .numerics-demo td.num { text-align: right; }
    .numerics-demo thead th {
      color: var(--text-secondary); font-size: var(--text-micro);
      border-bottom: 1px solid var(--border);
    }
    .numerics-demo sb-magnitude { display: inline-block; width: 48px; margin-left: var(--space-8); }
  `,
})
export class Gallery {
  protected readonly buttonVariants: (
    'primary' | 'secondary' | 'danger' | 'ghost' | 'icon' | 'chip' | 'segment' | 'link'
  )[] = ['primary', 'secondary', 'danger', 'ghost', 'icon', 'chip', 'segment', 'link'];

  protected readonly textInputTypes: ('text' | 'search' | 'number' | 'password' | 'date')[] = [
    'text', 'search', 'number', 'password', 'date',
  ];

  protected readonly selectOptions: SelectOption[] = [
    { value: 'a', label: 'Option A' },
    { value: 'b', label: 'Option B' },
  ];

  protected readonly chipTones: ChipTone[] = ['neutral', 'q1', 'q2', 'q3', 'q4', 'q5'];

  protected readonly filterChips: FilterChip[] = [
    { value: 'open', label: 'Open', count: 3 },
    { value: 'closed', label: 'Closed', count: 12 },
  ];

  protected readonly tabs: Tab[] = [
    { id: 'one', label: 'One' },
    { id: 'two', label: 'Two' },
  ];
  protected readonly activeTab = signal('one');

  protected readonly drawerOpen = signal(false);
  protected readonly confirmOpen = signal(false);

  /* -- v54 _5: accessibility and motion -------------------------------- */

  protected readonly flashDemo = signal(0);
  /** Alternates the sign so every click is a real change -- sbFlash ignores
   *  a re-render that reports the same value. */
  protected bumpFlashDemo(): void {
    this.flashDemo.update((v) => (v <= 0 ? v + 1 : -v));
  }

  protected readonly announceDemo = signal(0);
  protected bumpAnnounceDemo(): void {
    this.announceDemo.update((v) => v + 1);
  }

  protected readonly a11yDrawerOpen = signal(false);

  /* -- numerics (v54 Task 29) -- one row per case format.ts's own docstring
   * names: a missing value renders as an em dash, never as zero and never
   * as blank, and the two must stay visibly different from each other. */
  protected fmtNum = num;
  protected fmtPct = pct;
  protected fmtR = rMultiple;
  protected fmtSigned = signed;
  protected fmtMoney = (value: number | null) => money(value, 'USD');
  protected readonly numericCases: { label: string; value: number | null }[] = [
    { label: 'Positive', value: 2.15 },
    { label: 'Negative', value: -2.15 },
    { label: 'Zero', value: 0 },
    { label: 'Absent', value: null },
  ];

  protected readonly asyncDemo = signal<'content' | 'loading' | 'error' | 'no-data-yet' | 'measured-zero'>(
    'content',
  );
  protected readonly asyncEmptyReason = signal<AsyncEmptyReason>('no-data-yet');

  protected readonly statusCellRow: StatusCellRow = {
    status: 'active',
    progress_pct: 40,
    entry_pct: 20,
    progress_band: 'normal',
    blink_seconds: null,
    status_label: 'Active',
  };

  protected readonly sparklinePoints = [1, 3, 2, 5, 4, 6, 5, 7];
  protected readonly histogramBins: HistogramBin[] = [
    { label: '-2R', count: 3 },
    { label: '-1R', count: 8 },
    { label: '0R', count: 2 },
    { label: '+1R', count: 12 },
    { label: '+2R', count: 6 },
  ];
  protected readonly lineChartSeries: LineChartSeries[] = [
    {
      name: 'Equity',
      points: [
        { date: '2026-01-01', value: 0 },
        { date: '2026-02-01', value: 0.3 },
        { date: '2026-03-01', value: 0.2 },
        { date: '2026-04-01', value: 0.6 },
      ],
    },
  ];

  /** v54 D5 -- Task 37's chrome-comparison section: the same eight-point
   *  series, shaped for each chart's own input contract, purely so their
   *  shared chrome (axis, grid, tick size/colour, tooltip) is directly
   *  comparable side by side. Not meant to be a meaningful reading of any
   *  one chart's data -- see chartComparisonBins in particular, which turns
   *  a price series into bins only for this reason. */
  protected readonly chartComparisonSeries = [102, 104, 103, 107, 105, 109, 108, 112];

  protected readonly chartComparisonBins: HistogramBin[] = [
    { label: 'Day 1', count: 102 },
    { label: 'Day 2', count: 104 },
    { label: 'Day 3', count: 103 },
    { label: 'Day 4', count: 107 },
    { label: 'Day 5', count: 105 },
    { label: 'Day 6', count: 109 },
    { label: 'Day 7', count: 108 },
    { label: 'Day 8', count: 112 },
  ];

  protected readonly chartComparisonLineSeries: LineChartSeries[] = [
    {
      name: 'Comparison',
      points: [
        { date: '2026-01-01', value: 102 },
        { date: '2026-01-02', value: 104 },
        { date: '2026-01-03', value: 103 },
        { date: '2026-01-04', value: 107 },
        { date: '2026-01-05', value: 105 },
        { date: '2026-01-06', value: 109 },
        { date: '2026-01-07', value: 108 },
        { date: '2026-01-08', value: 112 },
      ],
    },
  ];

  protected readonly chartComparisonTradeData: ChartResponse = {
    ticker: 'DEMO',
    ohlcv: [
      { t: 1767225600, o: 101, h: 103, l: 100, c: 102, v: 1000 },
      { t: 1767312000, o: 102, h: 105, l: 101, c: 104, v: 1200 },
      { t: 1767398400, o: 104, h: 105, l: 102, c: 103, v: 900 },
      { t: 1767484800, o: 103, h: 108, l: 102, c: 107, v: 1500 },
      { t: 1767571200, o: 107, h: 107, l: 104, c: 105, v: 1100 },
      { t: 1767657600, o: 105, h: 110, l: 104, c: 109, v: 1700 },
      { t: 1767744000, o: 109, h: 109, l: 106, c: 108, v: 1300 },
      { t: 1767830400, o: 108, h: 113, l: 107, c: 112, v: 1600 },
    ],
    indicators: {},
    volume_profile: [],
    levels: null,
    overlays: [],
    notes: [],
    currency: '$',
  };

  protected readonly iconNames: IconName[] = [
    'dashboard', 'trades', 'analytics', 'calendar', 'watchlist', 'risk',
    'system', 'versions', 'collapse', 'expand', 'profile', 'signout', 'menu',
  ];

  protected readonly tableRows: GalleryRow[] = [
    { id: '1', ticker: 'AAPL', pnl: 42 },
    { id: '2', ticker: 'MSFT', pnl: -18 },
  ];
  protected readonly tableColumns: ColumnDef<GalleryRow>[] = [
    { key: 'ticker', header: 'Ticker', value: (row) => row.ticker },
    { key: 'pnl', header: 'P&L', value: (row) => row.pnl },
  ];
  protected readonly rowKey = (row: GalleryRow) => row.id;
  protected readonly pickableColumns = [
    { key: 'ticker', header: 'Ticker' },
    { key: 'pnl', header: 'P&L' },
  ];
  protected readonly pageSpec: PageSpec = { total: 2, page: 1, perPage: 20 };

  protected readonly qualityTone = qualityTone;
}
