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

interface GalleryRow {
  id: string;
  ticker: string;
  pnl: number;
}

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

    <!-- -- composites ------------------------------------------------------ -->
    <sb-section-head [heading]="'Composites'" [level]="2" />
    <sb-panel heading="sb-section-head, both levels, back and status slots">
      <sb-section-head heading="Level 1 heading" [level]="1" />
      <sb-section-head heading="Level 2 heading" [level]="2" />
      <sb-section-head heading="AAPL" [level]="1">
        <sb-row-link back [link]="['/ui']">Trades</sb-row-link>
        <span status class="num">as of 14:02 · 3 open</span>
      </sb-section-head>
    </sb-panel>
    <sb-panel heading="sb-row-link">
      <sb-row-link [link]="['/ui']">AAPL</sb-row-link>
    </sb-panel>
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
      <sb-panel-grid track="narrow">
        <sb-empty-state title="No results" />
        <sb-empty-state title="No results" hint="Widen the date range." />
        <sb-empty-state title="No trades closed in range" reason="measured-zero" />
        <sb-empty-state title="No quotes yet" hint="The feed has not reported." reason="no-data-yet" />
      </sb-panel-grid>
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

    /* v80 D6 -- a phone-width box, so the container-driven layouts (filter
       bar, segmented, tab bar) show their narrow behaviour at any window size. */
    .narrow-demo { max-width: 320px; margin-top: var(--space-10); }
    .register-demo { display: grid; gap: var(--space-10); }
    .register-demo h3 { margin: 0; }
  `,
})
export class Gallery {
  protected readonly buttonVariants: ButtonVariant[] = [
    'primary', 'secondary', 'danger', 'ghost', 'icon', 'danger-icon', 'link', 'chip', 'segment',
  ];

  protected readonly textInputTypes: ('text' | 'search' | 'number' | 'password' | 'date')[] = [
    'text', 'search', 'number', 'password', 'date',
  ];

  protected readonly selectOptions: SelectOption[] = [
    { value: 'a', label: 'Option A' },
    { value: 'b', label: 'Option B' },
  ];

  protected readonly chipTones: ChipTone[] = ['neutral', 'good', 'warn', 'info', 'q1', 'q2', 'q3', 'q4', 'q5'];

  protected readonly filterChips: FilterChip[] = [
    { value: 'open', label: 'Open', count: 3 },
    { value: 'closed', label: 'Closed', count: 12 },
  ];

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
    'system', 'versions', 'collapse', 'expand', 'profile', 'signout', 'menu', 'trash',
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
