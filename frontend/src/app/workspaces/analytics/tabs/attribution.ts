import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';

import { AnalyticsByDimensionRow } from '../../../api/models';
import { AnalyticsStore, BREAKDOWN_DIMENSIONS } from '../../../stores/analytics.store';
import { ConnectionStore } from '../../../stores/connection.store';
import { BarList, BarListMode, BarRow } from '../../../ui/bar-list';
import { DataTable } from '../../../ui/data-table/data-table';
import { DotPlot, DotPoint } from '../../../ui/dot-plot';
import { Select } from '../../../ui/form-controls';
import { pct } from '../../../ui/format';
import { HeatCell, HeatGrid, HeatRamp } from '../../../ui/heat-grid';
import { Panel } from '../../../ui/layout';
import { PanelError } from '../../../ui/panel-error';
import { PanelHeader } from '../../../ui/panel-header';
import { Segmented, SegmentOption } from '../../../ui/segmented';
import { Waterfall, WaterfallStep } from '../../../ui/waterfall';
import { dimensionColumns } from '../analytics.columns';

type Measure = 'exp_r' | 'total_r' | 'win_rate';
type HeatMeasure = 'exp_r' | 'win_rate' | 'n';

/** The server's `null` reaches every one of these unchanged (spec v94 H1) --
 *  a thin cell is withheld, never computed or defaulted to 0 here. */
function measureValue(
  row: Pick<AnalyticsByDimensionRow, 'exp_r' | 'total_r' | 'win_rate'>, measure: Measure,
): number | null {
  return measure === 'exp_r' ? row.exp_r : measure === 'total_r' ? row.total_r : row.win_rate;
}

/**
 * v94 Attribution -- where the edge comes from.
 *
 * Four questions, four visual forms, deliberately not one form repeated four
 * times (spec v94 D7/D11): which strategies produced the R (a waterfall,
 * ordered by contribution), whether that edge holds up at the sample sizes
 * behind it (a dot plot against N, never a bar chart that would hide a
 * one-trade "100%"), where it concentrates across strategy x horizon (a heat
 * grid), and how it splits by the dimensions a trader actually plans around.
 *
 * One `sb-segmented` drives every measure-scoped panel below it (dot plot,
 * the three fixed bar lists) -- a second, third and fourth toggle saying the
 * same thing would be four controls that could disagree with each other.
 * The heat grid's own cell figure (`store.heatCell()`) and the waterfall's
 * total-R contribution are independent by construction: a waterfall mixing
 * ExpR and win-rate bars would sum to a number nobody asked for, and the
 * heat grid already carries its own reliability floor per cell.
 */
@Component({
  selector: 'sb-attribution-tab',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel, PanelHeader, PanelError, Waterfall, DotPlot, HeatGrid, BarList, DataTable, Segmented, Select],
  template: `
    <div class="controls">
      <sb-segmented label="Measure" [options]="measureOptions" [value]="store.measure()"
                    (valueChange)="store.setMeasure($any($event))" />
    </div>

    <div class="panels">
      <sb-panel>
        <sb-panel-header title="Contribution" [n]="store.scopeN()"
          hint="Total R contributed by each strategy across the scope, largest magnitude first. The eight biggest name their strategy; the rest fold into Other rather than adding a ninth colour nothing else uses." />
        @if (store.strategiesError(); as error) {
          <sb-panel-error [message]="error" (retry)="store.reload('strategies')" />
        } @else {
          <sb-waterfall [steps]="waterfallSteps()" />
        }
      </sb-panel>

      <sb-panel>
        <sb-panel-header [title]="measureLabel() + ' vs sample size'" [n]="store.scopeN()"
          hint="Each point is one strategy. A hollow point sits below the reliability floor -- its value is withheld, never computed from too few trades." />
        @if (store.byDimensionError(); as error) {
          <sb-panel-error [message]="error" (retry)="store.reload('byDimension')" />
        } @else {
          <sb-dot-plot [points]="dotPoints()" [floor]="dotFloor()" [yLabel]="measureLabel()" [format]="measureFormat()" />
        }
      </sb-panel>

      <sb-panel>
        <sb-panel-header title="Strategy x horizon" [n]="store.scopeN()"
          hint="Cell colour ramps from worst to best across the grid; a dotted cell sits below the reliability floor and shows only its trade count." />
        @if (store.heatGridError(); as error) {
          <sb-panel-error [message]="error" (retry)="store.reload('heatGrid')" />
        } @else {
          <sb-heat-grid [rows]="store.heatGrid()?.rows ?? []" [cols]="store.heatGrid()?.cols ?? []"
                        [cells]="heatCells()" [ramp]="heatRamp()" [floor]="heatFloor()" [foldedRow]="foldedRow()" />
        }
      </sb-panel>

      <sb-panel>
        <sb-panel-header title="By horizon" [n]="store.scopeN()" />
        @if (store.byHorizonError(); as error) {
          <sb-panel-error [message]="error" (retry)="store.reload('byHorizon')" />
        } @else {
          <sb-bar-list [rows]="horizonBars()" [mode]="barMode()" [format]="measureFormat()"
                       [withheldFloor]="store.byHorizon()?.min_cell_n ?? null" />
        }
      </sb-panel>

      <sb-panel>
        <sb-panel-header title="By direction" [n]="store.scopeN()" />
        @if (store.byDirectionError(); as error) {
          <sb-panel-error [message]="error" (retry)="store.reload('byDirection')" />
        } @else {
          <sb-bar-list [rows]="directionBars()" [mode]="barMode()" [format]="measureFormat()"
                       [withheldFloor]="store.byDirection()?.min_cell_n ?? null" />
        }
      </sb-panel>

      <sb-panel>
        <sb-panel-header title="By day of week" [n]="store.scopeN()" />
        @if (store.byDowError(); as error) {
          <sb-panel-error [message]="error" (retry)="store.reload('byDow')" />
        } @else {
          <sb-bar-list [rows]="dowBars()" [mode]="barMode()" [format]="measureFormat()"
                       [withheldFloor]="store.byDow()?.min_cell_n ?? null" />
        }
      </sb-panel>

      <sb-panel>
        <sb-panel-header title="By month" [n]="store.scopeN()" />
        @if (store.performanceError(); as error) {
          <sb-panel-error [message]="error" (retry)="store.reload('performance')" />
        } @else {
          <sb-bar-list [rows]="monthBars()" mode="signed" [format]="pctFormat" />
        }
      </sb-panel>
    </div>

    <sb-panel>
      <sb-panel-header [title]="store.breakdownLabel() + ' breakdown'" [n]="store.scopeN()" />
      <div class="breakdown-controls">
        <sb-select label="Group by" [options]="breakdownOptions" [value]="store.breakdown()"
                   (valueChange)="store.setBreakdown($event)" />
      </div>
      @if (store.byDimensionError(); as error) {
        <sb-panel-error [message]="error" (retry)="store.reload('byDimension')" />
      } @else {
        <sb-data-table [rows]="dimensionRows()" [columns]="dimensionCols()" [visible]="dimensionVisible()"
                       [rowKey]="dimensionRowKey" />
      }
    </sb-panel>
  `,
  styles: `
    :host { display: grid; gap: var(--space-14); }
    .controls { display: flex; }
    .panels { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--space-14); }
    .breakdown-controls { margin: 0 0 var(--space-10); }
    @media (max-width: 639px) { .panels { grid-template-columns: 1fr; } }
  `,
})
export class AttributionTab {
  readonly store = inject(AnalyticsStore);
  private readonly connection = inject(ConnectionStore);

  protected readonly measureOptions: SegmentOption[] = [
    { value: 'exp_r', label: 'ExpR' },
    { value: 'total_r', label: 'Total R' },
    { value: 'win_rate', label: 'Win rate' },
  ];
  protected readonly breakdownOptions = BREAKDOWN_DIMENSIONS.map((d) => ({ value: d.value, label: d.label }));

  protected readonly measureLabel = computed(
    () => this.measureOptions.find((o) => o.value === this.store.measure())?.label ?? 'ExpR');
  protected readonly measureFormat = computed<(v: number) => string>(
    () => (this.store.measure() === 'win_rate' ? (v: number) => `${v.toFixed(1)}%` : (v: number) => `${v.toFixed(2)}R`));
  protected readonly pctFormat = (v: number) => pct(v);
  /** A win rate is a level against a 0-100 scale, not a signed delta from
   *  zero -- the same distinction `rate()` draws against `signed()`
   *  elsewhere on this workspace. ExpR and total R stay 'signed': centred
   *  on zero is exactly what a positive/negative R contribution is. */
  protected readonly barMode = computed<BarListMode>(() => (this.store.measure() === 'win_rate' ? 'rate' : 'signed'));

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

  protected readonly dotPoints = computed<DotPoint[]>(() => {
    const measure = this.store.measure();
    return (this.store.byDimension()?.rows ?? []).map((r) => ({
      label: r.key, n: r.n, value: measureValue(r, measure),
    }));
  });
  protected readonly dotFloor = computed(() => this.store.byDimension()?.min_cell_n ?? 20);

  private pickHeat(cell: { exp_r: number | null; win_rate: number | null; n: number }): number | null {
    const which: HeatMeasure = this.store.heatCell();
    return which === 'exp_r' ? cell.exp_r : which === 'win_rate' ? cell.win_rate : cell.n;
  }
  protected readonly heatRamp = computed<HeatRamp>(() => (this.store.heatCell() === 'exp_r' ? 'diverging' : 'sequential'));
  protected readonly heatFloor = computed(() => this.store.heatGrid()?.min_cell_n ?? 20);
  protected readonly heatCells = computed<HeatCell[]>(() =>
    (this.store.heatGrid()?.cells ?? []).map((c) => ({ r: c.r, c: c.c, n: c.n, value: this.pickHeat(c) })));
  protected readonly foldedRow = computed(() => {
    const folded = this.store.heatGrid()?.folded;
    if (!folded || folded.cells.length === 0) return null;
    return {
      label: `+${folded.n_strategies} more`,
      cells: folded.cells.map((c) => ({ c: c.c, n: c.n, value: this.pickHeat(c) })),
    };
  });

  private toBars(rows: readonly AnalyticsByDimensionRow[] | undefined): BarRow[] {
    const measure = this.store.measure();
    return (rows ?? []).map((r) => {
      const value = measureValue(r, measure);
      return { label: r.key, value, n: r.n, withheld: value === null };
    });
  }
  protected readonly horizonBars = computed<BarRow[]>(() => this.toBars(this.store.byHorizon()?.rows));
  protected readonly directionBars = computed<BarRow[]>(() => this.toBars(this.store.byDirection()?.rows));
  protected readonly dowBars = computed<BarRow[]>(() => this.toBars(this.store.byDow()?.rows));
  /** Month reuses `performance().calendar` via the store's own `monthBars()`
   *  (a % return, not measure-scoped) -- that data is already on hand, so a
   *  fourth `/by-dimension` fetch would only duplicate it. */
  protected readonly monthBars = computed<BarRow[]>(() => this.store.monthBars());

  protected readonly dimensionRows = computed<AnalyticsByDimensionRow[]>(() => this.store.byDimension()?.rows ?? []);
  protected readonly dimensionCols = computed(() => dimensionColumns(
    this.store.breakdownLabel(), this.store.unit(), this.connection.currency(),
    this.store.byDimension()?.min_cell_n ?? 20,
  ));
  /** `badge`/`soak` are present only for some dimensions (`dim=strategy` in
   *  particular) -- shown only when a row on screen actually carries one,
   *  rather than as a column of dashes for the other nine. */
  protected readonly dimensionVisible = computed<string[]>(() => {
    const rows = this.dimensionRows();
    const visible = ['key', 'n', 'win_rate', 'exp_r', 'total_r', 'total_pnl', 'avg_win_r', 'avg_loss_r'];
    if (rows.some((r) => r.badge !== undefined)) visible.push('badge');
    if (rows.some((r) => r.soak !== undefined)) visible.push('soak');
    return visible;
  });
  protected readonly dimensionRowKey = (r: AnalyticsByDimensionRow) => r.key;
}
