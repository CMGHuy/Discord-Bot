import { ChangeDetectionStrategy, Component, signal } from '@angular/core';

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
import { Checkbox, Select, SelectOption, TextInput } from '../../ui/form-controls';
import { Histogram, HistogramBin } from '../../ui/histogram';
import { Icon, IconName } from '../../ui/icon';
import { ControlRow, Drawer, Panel, Tab, TabBar } from '../../ui/layout';
import { LineChartSeries } from '../../ui/line-chart';
import { LineChart } from '../../ui/line-chart';
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
    Histogram,
    Icon,
    LineChart,
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
  `,
  styles: `
    :host { display: grid; gap: var(--space-20); padding: var(--space-20); }
    h1 { margin: 0; font-size: var(--text-title); font-weight: 600; }
    sb-panel { display: block; }
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
