import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';

import {
  AnalyticsPartials, PartialsBreakdownRow, PartialsBucket, PartialsDimension, PartialsHoldStage,
} from '../../../api/models';
import { AnalyticsStore } from '../../../stores/analytics.store';
import { BarList, BarRow } from '../../../ui/bar-list';
import { EmptyStateComponent } from '../../../ui/empty-state';
import { Histogram, HistogramBin } from '../../../ui/histogram';
import { Panel } from '../../../ui/layout';
import { LineChart, LineChartSeries } from '../../../ui/line-chart';
import { PanelError } from '../../../ui/panel-error';
import { PanelHeader } from '../../../ui/panel-header';
import { SegmentOption, Segmented } from '../../../ui/segmented';
import { ShareBar, ShareSegment } from '../../../ui/share-bar';
import { StatTile, StatTone } from '../../../ui/stat-tile';
import { StripGroup, StripPlot } from '../../../ui/strip-plot';
import { Waterfall, WaterfallStep } from '../../../ui/waterfall';

/* v142 — Partials: does the runner earn its keep, and where would a different
 * TP2 or split have landed? Descriptive only: the live book is a small,
 * non-pre-registered sample, so nothing on this tab is a gate. Every figure
 * is computed server-side (`swingbot/core/analytics/partials.py`); the
 * helpers below only shape it for the existing chart primitives. */

export interface PartialsTile {
  label: string; value: string; sample: number | null; tone: StatTone; hint: string; hero: boolean;
}

const STAGES: Record<string, string> = {
  filled: 'Filled', tp1: 'Hit TP1', runner_closed: 'Runner closed', tp2: 'Hit TP2',
};
const BUCKETS: Record<PartialsBucket, { label: string; tone: NonNullable<ShareSegment['tone']> }> = {
  tp2: { label: 'TP2', tone: 'pos' }, trail: { label: 'Trail', tone: 'accent' },
  floor: { label: 'Floor', tone: 'neg' }, stall: { label: 'Stall', tone: 'warn' },
  time: { label: 'Time', tone: 'warn' }, manual: { label: 'Manual', tone: 'muted' },
  no_tp2: { label: 'No TP2', tone: 'muted' }, open: { label: 'Open', tone: 'muted' },
  other: { label: 'Unrecorded', tone: 'warn' },
};
const HOLDS: [PartialsHoldStage, string][] = [
  ['entry_tp1', 'Entry → TP1'], ['tp1_exit', 'TP1 → exit'], ['entry_exit', 'Entry → exit'],
];
export const DIMENSIONS: SegmentOption[] = [
  { value: 'strategy', label: 'Strategy' }, { value: 'horizon', label: 'Horizon' },
  { value: 'side', label: 'Side' }, { value: 'month', label: 'Month' },
];
const GIVEBACK_BIN = 0.5;

export const pctText = (v: number | null): string => (v === null ? '—' : `${v.toFixed(1)}%`);
export const rText = (v: number | null): string =>
  (v === null ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(2)}R`);
const signTone = (v: number | null, pivot: number): StatTone =>
  (v === null || v === pivot ? 'neutral' : v > pivot ? 'pos' : 'neg');

export function kpiTiles(p: AnalyticsPartials): PartialsTile[] {
  const k = p.kpis;
  const held = k.median_tp1_exit_sessions === null ? '—' : `${k.median_tp1_exit_sessions} sessions`;
  return [
    { label: 'TP1 rate', value: pctText(k.tp1_rate), sample: k.tp1_rate_n, tone: 'neutral',
      hint: 'Partial trades ÷ filled trades no longer open before TP1', hero: false },
    { label: 'TP1 → TP2', value: pctText(k.tp1_tp2_rate), sample: k.tp1_tp2_n, tone: 'neutral',
      hint: 'Closed runners that reached TP2 (plans without a TP2 excluded)', hero: false },
    { label: 'Runner beat all-out', value: pctText(k.beat_all_out), sample: k.beat_all_out_n,
      tone: signTone(k.beat_all_out, 50), hint: 'Closed runners whose blended R beat closing 100% at TP1', hero: true },
    { label: 'Mean runner ΔR', value: rText(k.mean_runner_delta_r), sample: k.beat_all_out_n,
      tone: signTone(k.mean_runner_delta_r, 0), hint: 'Blended R minus all-out R, per closed runner', hero: false },
    { label: 'Median TP1 → exit', value: held, sample: k.tp1_exit_n, tone: 'neutral',
      hint: 'Trading sessions the runner was held', hero: false },
  ];
}

export function funnelRows(p: AnalyticsPartials): BarRow[] {
  const filled = p.funnel[0]?.n ?? 0;
  return p.funnel.map((step) => ({
    label: STAGES[step.stage] ?? step.stage, value: filled ? (step.n / filled) * 100 : null, n: step.n,
  }));
}

export function outcomeSegments(p: AnalyticsPartials): ShareSegment[] {
  return p.outcomes.map((o) => ({
    label: `${BUCKETS[o.bucket]?.label ?? o.bucket} ${rText(o.avg_runner_r)}`,
    count: o.n, tone: BUCKETS[o.bucket]?.tone ?? 'warn',
  }));
}

/** All-out ExpR, then what holding the runner added (or cost); the waterfall's
 *  own total bar is the actual ExpR. */
export function runnerWaterfall(p: AnalyticsPartials): WaterfallStep[] {
  const { all_out_exp_r: allOut, actual_exp_r: actual } = p.counterfactuals;
  if (allOut === null || actual === null) return [];
  return [{ label: 'All-out at TP1', value: allOut }, { label: 'Runner contribution', value: actual - allOut }];
}

/** One bar per TP2 level: the counterfactual ExpR had TP2 sat there. The
 *  actual setup is the last row, "Actual", so every level reads against it on
 *  the same signed axis (BarList draws a reference marker only in rate mode). */
export function ladderRows(p: AnalyticsPartials): BarRow[] {
  const cf = p.counterfactuals;
  const rows: BarRow[] = cf.ladder.map((row) => ({
    label: `TP2 at ${row.level_r.toFixed(1)}R`, value: row.cf_exp_r, n: row.n,
  }));
  return [...rows, { label: 'Actual', value: cf.actual_exp_r, n: p.kpis.beat_all_out_n }];
}

export function touchRows(p: AnalyticsPartials): BarRow[] {
  return p.counterfactuals.ladder.map((row) => ({ label: `${row.level_r.toFixed(1)}R`, value: row.touch_rate, n: row.n }));
}

export function splitRows(p: AnalyticsPartials): BarRow[] {
  return p.counterfactuals.split.map((row) => ({
    label: `${Math.round(row.fraction * 100)}% at TP1`, value: row.exp_r, n: row.n,
  }));
}

export function givebackBins(values: readonly number[]): HistogramBin[] {
  if (!values.length) return [];
  const bin = (v: number): number => Math.floor(v / GIVEBACK_BIN);
  const bins: HistogramBin[] = [];
  for (let i = bin(Math.min(...values)); i <= bin(Math.max(...values)); i++) {
    const from = i * GIVEBACK_BIN;
    bins.push({
      label: `${from.toFixed(1)}–${(from + GIVEBACK_BIN).toFixed(1)}R`,
      count: values.filter((v) => bin(v) === i).length,
    });
  }
  return bins;
}

export function holdGroups(p: AnalyticsPartials): StripGroup[] {
  return HOLDS.map(([stage, label]) => {
    const h = p.holds[stage];
    const iqr = h.p25 === null ? '' : ` (IQR ${h.p25}–${h.p75})`;
    return { label: `${label}${iqr}`, values: h.points, tone: 'accent' as const };
  });
}

export function monthTrend(rows: readonly PartialsBreakdownRow[]): LineChartSeries[] {
  const points = rows
    .filter((row) => row.beat_all_out !== null)
    .map((row) => ({ date: `${row.key}-01`, value: row.beat_all_out as number }));
  return [{ name: 'Runner beat all-out %', points }];
}

@Component({
  selector: 'sb-partials-tab',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel, PanelHeader, PanelError, StatTile, BarList, ShareBar, Waterfall, LineChart,
    Histogram, StripPlot, Segmented, EmptyStateComponent],
  template: `
    @if (store.partialsError(); as error) {
      <sb-panel-error [message]="error" (retry)="store.reload('partials')" />
    } @else if (data(); as p) {
      @if (p.population.partial === 0) {
        <sb-empty-state title="No partial trades in this scope" reason="measured-zero"
          hint="No filled trade reached TP1 here. Widen the date range or clear a filter." />
      } @else {
        <div class="kpis">@for (tile of tiles(); track tile.label) {
          <div class="tile" [class.hero]="tile.hero">
            <sb-stat-tile [label]="tile.label" [value]="tile.value" [sample]="tile.sample" [tone]="tile.tone" [hint]="tile.hint" />
          </div>
        }</div>
        <div class="panels">
          <sb-panel><sb-panel-header title="Funnel" [n]="p.n" hint="Share of filled trades reaching each stage." />
            <sb-bar-list [rows]="funnel()" mode="rate" [format]="pctFmt" /></sb-panel>
          <sb-panel><sb-panel-header title="Runner outcome mix" [n]="p.population.partial" hint="How each runner ended, with its average runner R." />
            <sb-share-bar label="Runner outcomes" [segments]="outcomes()" /></sb-panel>
          <sb-panel><sb-panel-header title="Does the runner pay?" [n]="p.kpis.beat_all_out_n" hint="ExpR had 100% closed at TP1, plus what holding the runner added." />
            <sb-waterfall [steps]="waterfall()" [format]="rFmt" totalLabel="Actual ExpR" /></sb-panel>
          <sb-panel><sb-panel-header title="TP2 ladder" [n]="ladderN()" hint="Counterfactual ExpR with TP2 at each R level; the last row is the actual ExpR. Below: share of runners that touched each level." />
            <sb-bar-list [rows]="ladder()" [format]="rFmt" />
            <sb-bar-list [rows]="touches()" mode="rate" [format]="pctFmt" /></sb-panel>
          <sb-panel><sb-panel-header title="Split what-if" [n]="p.kpis.beat_all_out_n" hint="ExpR had a different share been taken at TP1, from each trade's own two legs." />
            <sb-bar-list [rows]="split()" [format]="rFmt" /></sb-panel>
          <sb-panel><sb-panel-header title="Giveback" [n]="p.counterfactuals.giveback.length" hint="Best R the runner saw minus the R it banked." />
            <sb-histogram [bins]="giveback()" /></sb-panel>
          <sb-panel class="wide"><sb-panel-header title="Hold times" [n]="p.population.partial" hint="Trading sessions per stage; open runners count only before TP1." />
            <sb-strip-plot [groups]="holds()" unit=" sessions" /></sb-panel>
          <sb-panel class="wide"><sb-panel-header title="Breakdown" [n]="p.population.partial" [hint]="thinHint()" />
            <sb-segmented label="Group by" [options]="dimensions" [value]="dimension()" (valueChange)="dimension.set($any($event))" />
            @if (dimension() === 'month') { <sb-line-chart [series]="trend()" [valueFormat]="pctFmt" /> }
            <table class="breakdown">
              <thead><tr><th>{{ dimensionLabel() }}</th><th>N</th><th>TP1 rate</th><th>TP1 → TP2</th><th>Beat all-out</th><th>Mean ΔR</th><th>Median TP1 → exit</th></tr></thead>
              <tbody>@for (row of rows(); track row.key) {
                <tr [class.thin]="row.thin">
                  <td>{{ row.key }}</td><td class="num">{{ row.n }}</td><td class="num">{{ pctFmt(row.tp1_rate) }}</td>
                  <td class="num">{{ pctFmt(row.tp1_tp2_rate) }}</td><td class="num">{{ pctFmt(row.beat_all_out) }}</td>
                  <td class="num">{{ rFmt(row.mean_runner_delta_r) }}</td><td class="num">{{ row.median_tp1_exit_sessions ?? '—' }}</td>
                </tr>
              }</tbody>
            </table></sb-panel>
        </div>
        <p class="footer">{{ footer() }}</p>
      }
    }
  `,
  styles: `:host{display:grid;gap:var(--space-14)}.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(10rem,1fr));gap:var(--space-10)}.tile.hero{outline:1px solid var(--accent);border-radius:var(--radius)}.panels{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:var(--space-14)}.wide{grid-column:1/-1}.breakdown{width:100%;border-collapse:collapse;font-size:var(--text-table);margin-top:var(--space-10)}.breakdown th,.breakdown td{padding:var(--space-4) var(--space-8);text-align:left;border-bottom:1px solid var(--border)}.breakdown .num{text-align:right;font-variant-numeric:tabular-nums}.breakdown tr.thin td{color:var(--text-faint)}.footer{margin:0;font-size:var(--text-micro);color:var(--text-faint)}@media(max-width:639px){.panels{grid-template-columns:1fr}}`,
})
export class PartialsTab {
  readonly store = inject(AnalyticsStore);
  readonly data = computed(() => this.store.partials());
  readonly dimensions = DIMENSIONS;
  readonly dimension = signal<PartialsDimension>('strategy');
  readonly pctFmt = (v: number | null): string => pctText(v);
  readonly rFmt = (v: number | null): string => rText(v);

  readonly tiles = computed(() => this.shape(kpiTiles, []));
  readonly funnel = computed(() => this.shape(funnelRows, []));
  readonly outcomes = computed(() => this.shape(outcomeSegments, []));
  readonly waterfall = computed(() => this.shape(runnerWaterfall, []));
  readonly ladder = computed(() => this.shape(ladderRows, []));
  readonly ladderN = computed(() => this.data()?.counterfactuals.ladder[0]?.n ?? 0);
  readonly touches = computed(() => this.shape(touchRows, []));
  readonly split = computed(() => this.shape(splitRows, []));
  readonly giveback = computed(() => givebackBins(this.data()?.counterfactuals.giveback ?? []));
  readonly holds = computed(() => this.shape(holdGroups, []));
  readonly rows = computed(() => this.data()?.breakdowns[this.dimension()] ?? []);
  readonly trend = computed(() => monthTrend(this.data()?.breakdowns.month ?? []));
  readonly thinHint = computed(() => `Rows under N=${this.data()?.thin_n ?? 10} are dimmed: shown, not trusted.`);
  readonly dimensionLabel = computed(() => DIMENSIONS.find((d) => d.value === this.dimension())?.label ?? '');
  readonly footer = computed(() => {
    const p = this.data();
    if (!p) return '';
    const cf = p.counterfactuals;
    return `Population: ${p.population.filled} filled · ${p.population.partial} partial · `
      + `${cf.path_unavailable} closed runners without a price path · `
      + `${cf.runner_r_unavailable} manual runners without a price · live book only — not a gate.`;
  });

  /** One payload, many shapes: every panel reads the same response. */
  private shape<T>(fn: (p: AnalyticsPartials) => T, empty: T): T {
    const p = this.data();
    return p ? fn(p) : empty;
  }
}
