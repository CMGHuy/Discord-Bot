/** v208 — the Benchmark tab. API numbers are percentages; this tab only formats them.
 * Null is —, never 0%. */
import { ChangeDetectionStrategy, Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';

import { AnalyticsStore, BENCHMARK_RANGES } from '../../../stores/analytics.store';
import { EmptyStateComponent } from '../../../ui/empty-state';
import { PanelError } from '../../../ui/panel-error';
import { Segmented } from '../../../ui/segmented';
import { AnalyticsBenchmark, BenchmarkKey, BenchmarkRange } from '../../../api/models';
import { MINUS } from '../../../ui/format';

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


@Component({
  selector: 'sb-benchmark-tab',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Segmented, PanelError, EmptyStateComponent],
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
      <!-- V208-16: .stats, .chart -->
      <!-- V208-17: .daily, .capture, .footnote -->
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
    @media (max-width: 639px) { .today .cells { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
  `,
})
export class BenchmarkTab {
  readonly store = inject(AnalyticsStore);
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
