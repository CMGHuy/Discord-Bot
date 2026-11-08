/** v208 — the Benchmark tab. API numbers are percentages; this tab only formats them.
 * Null is —, never 0%. */
import { ChangeDetectionStrategy, Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';

import { AnalyticsStore, BENCHMARK_RANGES } from '../../../stores/analytics.store';
import { EmptyStateComponent } from '../../../ui/empty-state';
import { PanelError } from '../../../ui/panel-error';
import { Segmented } from '../../../ui/segmented';
import { AnalyticsBenchmark, BenchmarkDailyRow, BenchmarkEstimate, BenchmarkIndexKey, BenchmarkKey, BenchmarkPoint, BenchmarkRange, BenchmarkSeriesStats, BenchmarkStat, BenchmarkVs } from '../../../api/models';
import { MINUS } from '../../../ui/format';
import { ConnectionStore } from '../../../stores/connection.store';
import { LineChart, LineChartSeries } from '../../../ui/line-chart';
import { ExposureStrip } from '../../../ui/exposure-strip';
import { StatTile, StatTone } from '../../../ui/stat-tile';
import { Panel } from '../../../ui/layout';
import { PanelHeader } from '../../../ui/panel-header';
import { DataTable } from '../../../ui/data-table/data-table';
import { ColumnDef } from '../../../ui/data-table/data-table.types';

export const SERIES_ORDER: readonly BenchmarkKey[] = ['bot_account', 'bot_deployed', 'SPY', 'QQQ', '^IXIC', '^DJI'];
export const CHIP_LABELS: Record<BenchmarkKey, string> = {
  bot_account: 'Bot · account', bot_deployed: 'Bot · deployed', SPY: 'SPY', QQQ: 'QQQ',
  '^IXIC': 'Nasdaq Comp. (price)', '^DJI': 'Dow (price)',
};
export const DEFAULT_VISIBLE: readonly BenchmarkKey[] = ['bot_account', 'bot_deployed', 'SPY', 'QQQ'];
export const POLL_MS = 300_000;
export const SERIES_TOKENS: Record<BenchmarkKey, string> = {
  bot_account: '--accent', bot_deployed: '--accent', SPY: '--chart-2', QQQ: '--chart-3',
  '^IXIC': '--chart-4', '^DJI': '--chart-5',
};
export const PAPER_LINE = 'Paper trades only. Returns are pre-tax and exclude fees and slippage; '
  + 'indexes are buy-and-hold. Not a recommendation or forecast.';
export const MIXED_BANNER = 'Benchmark assumes a USD account trading USD stocks — figures may be mixed-currency';
export const DEPLOYED_LABEL = 'on capital in trades — not account return';
export const UNREALISED = 'unrealised · paper';
export const EMPTY_BARS = 'No benchmark data yet';
export const STALE_BARS = 'Benchmarks not updating — refresher is off';

export function signedPct(value: number | null, dp = 2): string {
  if (value === null) return '—';
  if (value === 0) return `${(0).toFixed(dp)}%`;
  return `${value > 0 ? '+' : MINUS}${Math.abs(value).toFixed(dp)}%`;
}

export function etClock(iso: string): string {
  return new Intl.DateTimeFormat('en-GB', {
    timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).format(new Date(iso));
}

export function stateStamp(payload: AnalyticsBenchmark): string {
  const today = payload.today;
  if (!today?.session) return 'no session yet';
  if (payload.session_state === 'open' && !today.final) return `as of ${etClock(payload.as_of)} ET`;
  return `${today.session} · final`;
}

export interface TodayCell { key: BenchmarkKey; label: string; value: string; caption: string | null; }

export function todayCells(payload: AnalyticsBenchmark): TodayCell[] {
  const lines = payload.today?.lines;
  if (!lines) return [];
  return SERIES_ORDER.flatMap((key) => {
    const line = lines[key];
    if (!line) return [];
    const liveBot = key.startsWith('bot_') && payload.session_state === 'open' && !line.final;
    return [{ key, label: CHIP_LABELS[key], value: signedPct(line.pct), caption: liveBot ? UNREALISED : null }];
  });
}

export function statusNote(payload: AnalyticsBenchmark): string | null {
  if (payload.benchmarks_status === 'empty') return EMPTY_BARS;
  if (payload.benchmarks_status === 'stale') return STALE_BARS;
  return null;
}

export function isMixedCurrency(payload: AnalyticsBenchmark): boolean {
  return payload.account_currency !== 'USD' || payload.mixed_tickers.length > 0;
}


export const ALPHA_CELLS_HINT = '1 of 24 cells';
export interface BenchmarkTile {
  label: string; value: string; sample: number | null; hint: string;
  secondary: string | null; tone: StatTone; bold: boolean;
}
export interface BenchmarkStatGroup {
  key: BenchmarkKey; label: string; note: string | null; tiles: BenchmarkTile[];
}

function signTone(value: number | null): StatTone {
  if (value === null || value === 0) return 'neutral';
  return value > 0 ? 'pos' : 'neg';
}

function money(value: number, currency: string): string {
  return `${value < 0 ? MINUS : ''}${currency}${Math.abs(value).toLocaleString('en-US', {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  })}`;
}

function tile(label: string, stat: BenchmarkStat, format: (value: number) => string,
              hint: string, tone: StatTone = 'neutral'): BenchmarkTile {
  return { label, value: stat.value === null ? '—' : format(stat.value), sample: stat.n,
    hint, secondary: stat.value === null ? stat.reason : null, tone, bold: false };
}

function returnTiles(stats: BenchmarkSeriesStats): BenchmarkTile[] {
  return [
    tile('Total', stats.total_pct, signedPct, 'Compounded over the sessions used (N).', signTone(stats.total_pct.value)),
    tile('Max drawdown', stats.max_dd_pct, signedPct, 'Largest peak-to-trough fall of the cumulative line.',
      stats.max_dd_pct.value !== null && stats.max_dd_pct.value < 0 ? 'neg' : 'neutral'),
  ];
}

function sharpeTile(stats: BenchmarkSeriesStats): BenchmarkTile {
  return tile('Sharpe (rf = 0)', stats.sharpe, (v) => v.toFixed(2), 'Annualised (252), rf = 0, sample std.');
}

function botTiles(stats: BenchmarkSeriesStats, currency: string): BenchmarkTile[] {
  const drawdown = stats.money_dd ?? { value: null, n: stats.total_pct.n, reason: null };
  const streak = { value: stats.losing_streak ?? null, n: stats.total_pct.n, reason: null };
  return [...returnTiles(stats),
    tile(`Drawdown (${currency})`, drawdown, (v) => money(v, currency), 'Largest peak-to-trough fall in account money.',
      drawdown.value !== null && drawdown.value < 0 ? 'neg' : 'neutral'),
    tile('Losing streak', streak, (v) => `${v} sessions`, 'Longest run of losing sessions.'), sharpeTile(stats)];
}

function betaText(value: number, estimate: BenchmarkEstimate): string {
  return `β ${value.toFixed(2)}${estimate.se == null ? '' : ` ± ${estimate.se.toFixed(2)}`}`;
}

function alphaTile(alpha: BenchmarkEstimate): BenchmarkTile {
  const hint = alpha.headline
    ? 'Headline cell: SPY over the whole live book. Annualised Jensen alpha, rf = 0; indicative, not evidence of edge.'
    : `${ALPHA_CELLS_HINT}: annualised Jensen alpha, rf = 0; indicative, not evidence of edge.`;
  return { ...tile('Alpha (rf = 0)', alpha,
    (v) => `α ${signedPct(v, 1)}${alpha.t == null ? '' : ` (t ${alpha.t.toFixed(1)})`}`, hint), bold: !!alpha.headline };
}

function indexTiles(stats: BenchmarkSeriesStats, key: BenchmarkIndexKey, vs: BenchmarkVs | undefined): BenchmarkTile[] {
  const tiles = [...returnTiles(stats), sharpeTile(stats)];
  if (!vs) return tiles;
  return [...tiles,
    tile(`Lead vs ${CHIP_LABELS[key]}`, vs.lead_pp, (v) => signedPct(v).replace('%', ' pp'),
      "Bot · account total minus this index's total; descriptive, not evidence of edge.", signTone(vs.lead_pp.value)),
    tile('Beta', vs.beta, (v) => betaText(v, vs.beta),
      'OLS slope of Bot · account daily returns on this index, ± standard error.'), alphaTile(vs.alpha)];
}

function groupNote(key: BenchmarkKey, stats: BenchmarkSeriesStats): string | null {
  if (key === 'bot_account') return null;
  if (key === 'bot_deployed') {
    return DEPLOYED_LABEL + (typeof stats.approx_share === 'number' ? ` · ${stats.approx_share.toFixed(0)}% approx.` : '');
  }
  return key === 'SPY' || key === 'QQQ' ? 'total return' : 'price only';
}

export function statGroups(p: AnalyticsBenchmark, visible: ReadonlySet<string>, currency: string): BenchmarkStatGroup[] {
  return SERIES_ORDER.flatMap((key) => {
    const stats = p.stats[key];
    if (!visible.has(key) || !stats) return [];
    const tiles = key === 'bot_account' || key === 'bot_deployed'
      ? botTiles(stats, currency) : indexTiles(stats, key, p.vs[key]);
    return [{ key, label: CHIP_LABELS[key], note: groupNote(key, stats), tiles }];
  });
}

export function pointFlag(pt: BenchmarkPoint): string | undefined {
  const parts = [pt.missing && 'missing session', pt.span > 1 && `covers ${pt.span} sessions`,
    pt.proxy && 'proxy ETF', pt.approx && 'exposure approximate', pt.clipped && 'clipped at −100%'];
  return parts.filter(Boolean).join(' · ') || undefined;
}

export function chartSeries(p: AnalyticsBenchmark, visible: ReadonlySet<string>): LineChartSeries[] {
  return SERIES_ORDER.flatMap((key) => {
    const series = p.series.find((s) => s.key === key);
    if (!visible.has(key) || !series) return [];
    return [{ name: CHIP_LABELS[key], color: SERIES_TOKENS[key], ...(key === 'bot_deployed' ? { dashed: true } : {}),
      points: series.points.map((pt) => ({ date: pt.date, value: pt.missing ? null : pt.cum_pct,
        day: pt.day_pct, flag: pointFlag(pt) })) }];
  });
}

export function chartDates(series: LineChartSeries[]): string[] {
  return [...new Set(series.flatMap((s) => s.points.map((p) => p.date)))].sort();
}

export function markerNotes(p: AnalyticsBenchmark): string[] {
  return p.markers.map((m) => `Base balance changed on ${m.date}: that session is left out of every stat and the account line carries flat.`);
}

export function stripLine(p: AnalyticsBenchmark): string {
  return `${p.range.sessions_n} sessions, paper book — beta/alpha are indicative, not evidence of edge.`;
}

export const INDEX_KEYS: readonly BenchmarkIndexKey[] = ['SPY', 'QQQ', '^IXIC', '^DJI'];
export const CAPTURE_FORMULA = 'Σ bot return on index-up days ÷ Σ index return on those days (sum ratio, not the geometric form)';
export const DOWN_FORMULA = 'Σ bot return on index-down days ÷ Σ index return on those days (sum ratio, not the geometric form); flat days excluded';
export const TAX_LINE = 'Swing turnover is taxed as short-term gains, so after-tax results would differ from this chart.';
export const FOOTNOTE: readonly string[] = [
  'SPY and QQQ are total return (dividends reinvested); Nasdaq Comp. and Dow are price indexes without dividends.',
  'Bot · account is the main-ledger paper equity, cash included: the Dashboard’s daily close. '
    + 'Bot · deployed is trade P&L on capital in trades — not account return.',
  'A missing bot session shows —, never 0%: the index is compounded over the same span and the pair is left out of '
    + 'beta, alpha, Sharpe, capture and Beat?.',
  'Days sourced from a proxy ETF (ONEQ, DIA) are marked in the chart tooltip.',
  TAX_LINE,
];

function dailyDate(row: BenchmarkDailyRow): string {
  if (row.missing) return `${row.date} · no bot sample`;
  return row.span > 1 ? `${row.date} · covers ${row.span} sessions` : row.date;
}

export function dailyColumns(capture: string): ColumnDef<BenchmarkDailyRow>[] {
  return [
    { key: 'date', header: 'Date', value: dailyDate },
    ...SERIES_ORDER.map((key) => ({ key, header: CHIP_LABELS[key], numeric: true,
      value: (row: BenchmarkDailyRow) => signedPct(row.lines[key] ?? null) })),
    { key: 'exposure', header: 'Exposure', numeric: true,
      value: (row) => row.exposure_pct === null ? '—' : `${row.exposure_pct.toFixed(1)}%` },
    { key: 'open', header: 'Open', numeric: true, value: (row) => row.open_n ?? '—' },
    { key: 'beat', header: `Beat? (vs ${CHIP_LABELS[capture as BenchmarkIndexKey]})`,
      value: (row) => row.beat === null ? '—' : row.beat ? 'Yes' : 'No' },
  ];
}

export function dailyVisible(visible: ReadonlySet<string>): string[] {
  return ['date', ...SERIES_ORDER.filter((key) => visible.has(key)), 'exposure', 'open', 'beat'];
}

export function captureTiles(p: AnalyticsBenchmark): BenchmarkTile[] {
  const c = p.capture;
  return [
    { ...tile('Up capture', c.up_pct, (v) => `${v.toFixed(1)}%`, CAPTURE_FORMULA), sample: c.up_n },
    { ...tile('Down capture', c.down_pct, (v) => `${v.toFixed(1)}%`, DOWN_FORMULA), sample: c.down_n },
    { ...tile('Capture ratio', c.ratio, (v) => `${v.toFixed(2)}×`, 'Up capture ÷ down capture.'), sample: c.up_n + c.down_n },
  ];
}

export function beatLine(p: AnalyticsBenchmark): string {
  const { index, beat } = p.capture;
  return `Bot · account beat ${CHIP_LABELS[index]} on ${beat.up_beat} of ${beat.up_days} up days and ${beat.down_beat} of ${beat.down_days} down days — descriptive, not evidence of edge.`;
}

@Component({
  selector: 'sb-benchmark-tab',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Segmented, PanelError, EmptyStateComponent, LineChart, ExposureStrip, StatTile, Panel, PanelHeader, DataTable],
  template: `
    @if (store.benchmarkError(); as error) {
      <sb-panel-error [message]="error" (retry)="store.reload('benchmark')" />
    }
    @if (data(); as p) {
      @if (mixed()) { <p class="banner" role="status">{{ mixedBanner }}</p> }
      <section class="today" aria-label="Today">
        <header><h2>Today</h2><span class="stamp">{{ stamp() }}</span></header>
        <div class="cells">
          @for (c of cells(); track c.key) {
            <div class="cell" [attr.data-key]="c.key">
              <span class="label">{{ c.label }}</span>
              <span class="value num" [class.pos]="(p.today?.lines?.[c.key]?.pct ?? 0) > 0"
                    [class.neg]="(p.today?.lines?.[c.key]?.pct ?? 0) < 0">{{ c.value }}</span>
              @if (c.caption) { <span class="caption">{{ c.caption }}</span> }
            </div>
          }
        </div>
      </section>
      <p class="paper">{{ paperLine }}</p>
      <div class="range">
        <sb-segmented label="Range" [options]="rangeOptions" [value]="selectedRange()"
                      (valueChange)="pickRange($any($event))" />
        @if (p.range.clamped) { <span class="clamp">Live book since {{ p.range.live_since }}</span> }
      </div>
      <div class="chips" role="group" aria-label="Lines">
        @for (key of seriesOrder; track key) {
          <button type="button" [attr.data-key]="key" [attr.aria-pressed]="visible().has(key)" (click)="toggle(key)">
            <i class="swatch" [class.dashed]="key === 'bot_deployed'" [style.border-top-color]="'var(' + tokens[key] + ')'"> </i>
            <span class="label">{{ labels[key] }}</span>
            @if (key === 'bot_deployed') { <span class="sub">{{ deployedLabel }}</span> }
          </button>
        }
      </div>
      @if (p.benchmarks_status === 'empty') {
        <sb-empty-state [title]="emptyBars" reason="measured-zero" hint="Index bars arrive after the refresher's first cycle." />
      }
      @if (p.benchmarks_status === 'stale') {
        <p class="stale" role="status">{{ staleBars }} · last stored session {{ p.benchmarks_last_session }}</p>
      }
      @if (p.benchmarks_status !== 'empty') {
<section class="stats" aria-label="Range statistics">
  @for (g of statTiles(); track g.key) {
    <div class="group">
      <h3>{{ g.label }} @if (g.note) { <span class="note">{{ g.note }}</span> }</h3>
      <div class="tiles">@for (t of g.tiles; track t.label) {
        <div class="tile" [class.bold]="t.bold">
          <sb-stat-tile [label]="t.label" [value]="t.value" [sample]="t.sample" [tone]="t.tone" [hint]="t.hint" [secondary]="t.secondary" />
        </div>
      }</div>
    </div>
  }
  <p class="strip-line">{{ stripLine(p) }}</p>
</section>
<sb-panel class="chart">
  <sb-panel-header title="Cumulative return" [n]="p.range.sessions_n"
    hint="Every line rebased to 0% at the close before the range starts. SPY and QQQ are total return; Nasdaq Comp. and Dow are price only. Tap or hover for each line's cumulative and day %." />
  <sb-line-chart [series]="chart()" [valueFormat]="pctFmt" [hoverDetail]="true" [zeroLine]="true" />
  <sb-exposure-strip [dates]="dates()" [bars]="bars()" />
  <p class="exposure-caption">Exposure: share of equity in open trades per session (faded bars: approximate).</p>
  @if (markerNotes(p).length) { <ul class="markers">@for (m of markerNotes(p); track m) { <li>{{ m }}</li> }</ul> }
</sb-panel>
<sb-panel class="daily">
  <sb-panel-header title="Daily comparison" [n]="p.range.sessions_n"
    hint="Newest first. Beat?: this session's return was higher, not evidence of edge. A row covering several sessions compares the same span on both sides; a missing bot session shows —." />
  <sb-data-table [rows]="p.daily" [columns]="dailyCols()" [visible]="dailyShown()" [rowKey]="dailyKey"
    clientPaging="analytics.benchmark.daily" [emptyState]="{ title: 'No sessions in this range' }" />
  @if (p.daily_has_more) {
    <button type="button" class="more" [disabled]="store.benchmarkLoadingMore()" (click)="store.loadMoreBenchmarkDaily()">Load older sessions</button>
  }
</sb-panel>
<sb-panel class="capture">
  <sb-panel-header title="Up/down capture" [n]="p.capture.up_n + p.capture.down_n" [hint]="captureFormula" />
  <sb-segmented label="Capture vs" [options]="captureOptions" [value]="store.benchmarkCapture()"
    (valueChange)="store.setBenchmarkCapture($event)" />
  <div class="tiles">@for (t of captureTiles(p); track t.label) {
    <sb-stat-tile [label]="t.label" [value]="t.value" [sample]="t.sample" [tone]="t.tone" [hint]="t.hint" [secondary]="t.secondary" />
  }</div>
  <p class="beat">{{ beatLine(p) }}</p>
</sb-panel>
<footer class="footnote">@for (line of footnote; track line) { <p>{{ line }}</p> }</footer>
      }
    }
  `,
  styles: `
    :host { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--space-14); }
    .today .cells { display: grid; grid-template-columns: repeat(auto-fit, minmax(8.5rem, 1fr)); gap: var(--space-10); }
    .cell { display: grid; gap: 2px; }
    .chips { display: flex; flex-wrap: wrap; gap: var(--space-6); }
    .chips button { min-height: 44px; padding: 0 var(--space-10); border: 1px solid var(--border); border-radius: var(--panel-radius); background: var(--surface); color: var(--text-secondary); text-align: left; }
    .chips button[aria-pressed="true"] { border-color: var(--accent); color: var(--text); }
    .swatch { display: inline-block; width: 14px; border-top: 2px solid; margin-right: var(--space-6); vertical-align: middle; }
    .swatch.dashed { border-top-style: dashed; }
    .sub, .caption, .clamp, .stamp { font-size: var(--text-micro); color: var(--text-faint); }
    .sub { display: block; }
    .paper { margin: 0; font-size: var(--text-chip); color: var(--text-secondary); }
    .banner, .stale { margin: 0; font-size: var(--text-chip); color: var(--warn); }
    .range { display: grid; gap: var(--space-6); }
    .pos { color: var(--pos); }
    .neg { color: var(--neg); }
    .stats { display: grid; gap: var(--space-10); }
    .group h3 { margin: 0; font-size: var(--text-chip); color: var(--text); }
    .note { font-weight: normal; color: var(--text-faint); margin-left: var(--space-6); }
    .tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr)); gap: var(--space-10); }
    .tile.bold { outline: 1px solid var(--accent); border-radius: var(--panel-radius); --figure-weight: 700; }
    .strip-line, .exposure-caption, .markers { margin: 0; font-size: var(--text-micro); color: var(--text-faint); }
    .markers { padding-left: var(--space-14); }
    .more{min-height:44px;margin-top:var(--space-10);padding:0 var(--space-14);border:1px solid var(--border);border-radius:var(--panel-radius);background:var(--surface);color:var(--text)}
    .beat{margin:var(--space-10) 0 0;font-size:var(--text-chip);color:var(--text-secondary)}
    .footnote{display:grid;gap:var(--space-4)}
    .footnote p{margin:0;font-size:var(--text-micro);color:var(--text-faint)}
    @media (max-width:639px){.tiles{grid-template-columns:repeat(2,minmax(0,1fr))}.today .cells{grid-template-columns:repeat(2,minmax(0,1fr))}}
  `,
})
export class BenchmarkTab {
  readonly store = inject(AnalyticsStore);
  readonly connection = inject(ConnectionStore);
  private readonly router = inject(Router);
  readonly data = computed(() => this.store.benchmark());
  readonly visible = signal(new Set<string>(DEFAULT_VISIBLE));
  readonly seriesOrder = SERIES_ORDER;
  readonly labels = CHIP_LABELS;
  readonly tokens = SERIES_TOKENS;
  readonly mixedBanner = MIXED_BANNER;
  readonly paperLine = PAPER_LINE;
  readonly deployedLabel = DEPLOYED_LABEL;
  readonly emptyBars = EMPTY_BARS;
  readonly staleBars = STALE_BARS;
  readonly rangeOptions = BENCHMARK_RANGES.map((r) => ({ value: r, label: r }));
  readonly selectedRange = computed(() => this.store.scope().from || this.store.scope().to ? '' : this.store.benchmarkRange());
  readonly mixed = computed(() => { const p = this.data(); return p ? isMixedCurrency(p) : false; });
  readonly stamp = computed(() => { const p = this.data(); return p ? stateStamp(p) : ''; });
  readonly statTiles = computed(() => {
    const p = this.data();
    return p ? statGroups(p, this.visible(), this.connection.currency()) : [];
  });
  readonly chart = computed(() => { const p = this.data(); return p ? chartSeries(p, this.visible()) : []; });
  readonly dates = computed(() => chartDates(this.chart()));
  readonly bars = computed(() => (this.data()?.exposure ?? []).map(({ date, pct, approx }) => ({ date, pct, approx })));
  readonly dailyCols = computed(() => dailyColumns(this.store.benchmarkCapture()));
  readonly dailyShown = computed(() => dailyVisible(this.visible()));
  readonly dailyKey = (row: BenchmarkDailyRow) => row.date;
  readonly captureOptions = INDEX_KEYS.map((key) => ({ value: key, label: CHIP_LABELS[key] }));
  readonly captureFormula = CAPTURE_FORMULA;
  readonly captureTiles = captureTiles;
  readonly beatLine = beatLine;
  readonly footnote = FOOTNOTE;
  readonly pctFmt = (v: number) => signedPct(v);
  readonly stripLine = stripLine;
  readonly markerNotes = markerNotes;
  readonly cells = computed(() => { const p = this.data(); return p ? todayCells(p) : []; });

  constructor() {
    const timer = setInterval(() => this.poll(), POLL_MS);
    inject(DestroyRef).onDestroy(() => clearInterval(timer));
  }

  toggle(key: string): void {
    const next = new Set(this.visible());
    if (next.has(key)) next.delete(key); else next.add(key);
    this.visible.set(next);
  }

  pickRange(range: BenchmarkRange): void {
    if (this.store.scope().from || this.store.scope().to) {
      this.store.setScope({ from: null, to: null });
      this.router.navigate([], { queryParams: { from: null, to: null }, queryParamsHandling: 'merge', replaceUrl: true });
    }
    this.store.setBenchmarkRange(range);
  }

  poll(): void {
    if (this.data()?.session_state === 'open' && document.visibilityState === 'visible') this.store.refreshBenchmark();
  }
}
