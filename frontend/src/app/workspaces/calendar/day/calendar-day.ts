import { ChangeDetectionStrategy, Component, computed, inject, input, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import {
  CalendarTrade,
  DayBreakdownDimension,
  DayBreakdownRow,
  DayContext,
  DayDelta,
  SparkSeries,
} from '../../../api/models';
import { CalendarDayStore, DaySort } from '../../../stores/calendar-day.store';
import { ConnectionStore } from '../../../stores/connection.store';
import { EmptyStateComponent } from '../../../ui/empty-state';
import { ABSENT, money, rMultiple } from '../../../ui/format';
import { Panel, Tab, TabBar } from '../../../ui/layout';
import { SegmentOption, Segmented } from '../../../ui/segmented';
import { StatTile } from '../../../ui/stat-tile';
import { monthLabel } from '../calendar.helpers';
import { ONE_DAY_CAVEAT, PAPER_CAPTION, R_TOOLTIP, legsSampleNote } from './day-copy';
import { DayTradeCard } from './day-trade-card';
import { WIN_RATE_MIN_N, monthOf, ordinal, percentileView } from './month-context';

/* v165 D5 -- one P&L calendar day as a page: the drawer's tiles, how the day
 * compares (D2), what drove it (D3), and every row as a card with its
 * sparkline (D1/D4). The drawer stays the quick preview. D7 governs every
 * word and colour here: paper caption always, N beside every comparison,
 * comparison figures in neutral text. */

const UTC_DAY = (date: string): Date => {
  const [year, month, day] = date.split('-').map(Number);
  return new Date(Date.UTC(year, month - 1, day));
};

/** "Wednesday, August 5, 2026", in UTC so the viewer's zone never shifts it. */
export function longDate(date: string): string {
  return UTC_DAY(date).toLocaleDateString('en-US', {
    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric', timeZone: 'UTC',
  });
}

export function weekdayName(date: string): string {
  return UTC_DAY(date).toLocaleDateString('en-US', { weekday: 'long', timeZone: 'UTC' });
}

export interface MonthLine {
  path: string;
  marker: { x: number; y: number } | null;
  /** Where 0 sits, so a month under water reads as one. */
  zeroY: number | null;
}

const LINE_PAD = 3;
const round2 = (value: number): number => Math.round(value * 100) / 100;

/** The month's running P&L as a path, 0 always inside the domain. */
export function monthLineGeometry(
  curve: { date: string; value: number }[],
  dayIndex: number,
  width = 240,
  height = 56,
): MonthLine {
  if (curve.length === 0) return { path: '', marker: null, zeroY: null };
  const values = [0, ...curve.map((p) => p.value)];
  const min = Math.min(...values);
  const span = Math.max(...values) - min;
  const y = (v: number) =>
    round2(span === 0 ? height / 2 : height - LINE_PAD - ((v - min) / span) * (height - 2 * LINE_PAD));
  const last = curve.length - 1;
  const points = curve.map((p, i) => ({ x: last === 0 ? width / 2 : round2((i / last) * width), y: y(p.value) }));
  const path = points.length === 1
    ? `M 0.00 ${points[0].y.toFixed(2)} L ${width.toFixed(2)} ${points[0].y.toFixed(2)}`
    : points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(2)} ${p.y.toFixed(2)}`).join(' ');
  return { path, marker: points[dayIndex] ?? null, zeroY: y(0) };
}

/** D7 / financial-advisor 6: win% on fewer than five rows is noise. */
export function breakdownWinRate(row: DayBreakdownRow): string {
  if (row.n < WIN_RATE_MIN_N || row.win_rate === null) return ABSENT;
  return `${row.win_rate.toFixed(0)}%`;
}

const TABS: Tab[] = [
  { id: 'strategy', label: 'Strategy' },
  { id: 'horizon', label: 'Horizon' },
  { id: 'direction', label: 'Direction' },
  { id: 'exit_reason', label: 'Exit' },
];

const SORTS: SegmentOption[] = [
  { value: 'pnl', label: 'P&L' },
  { value: 'r', label: 'R' },
  { value: 'closed', label: 'Close time' },
  { value: 'ticker', label: 'Ticker' },
];

function sign(value: number | null): 'pos' | 'neg' | null {
  if (value === null || value === 0) return null;
  return value > 0 ? 'pos' : 'neg';
}

@Component({
  selector: 'sb-calendar-day',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DayTradeCard, EmptyStateComponent, Panel, RouterLink, Segmented, StatTile, TabBar],
  host: { class: 'register-presentation' },
  template: `
    <header class="day-head">
      <a class="back" [routerLink]="['/calendar']" [queryParams]="backParams()">← Calendar{{ backMonth() }}</a>
      <h2 class="long-date">{{ title() }}</h2>
      <nav class="steps" aria-label="Trading days">
        @if (store.prevDay(); as prev) {
          <a class="prev" [routerLink]="['/calendar', prev]" [queryParams]="store.filterParams()">‹ prev day</a>
        } @else {
          <span class="prev off">‹ prev day</span>
        }
        @if (store.nextDay(); as next) {
          <a class="next" [routerLink]="['/calendar', next]" [queryParams]="store.filterParams()">next day ›</a>
        } @else {
          <span class="next off">next day ›</span>
        }
      </nav>
    </header>
    <p class="caption">{{ caption }}</p>
    @if (store.error(); as message) {
      <p class="stale" role="status">{{ message }}</p>
    }

    @if (store.day(); as day) {
      <div class="tiles">
        <sb-stat-tile label="Total" [value]="r(day.total_r)" [sample]="day.trade_count" [attr.title]="rTooltip" />
        <sb-stat-tile label="Total P&L" [value]="ccy(day.total_ccy)" [sample]="day.trade_count" />
        <sb-stat-tile label="Win rate" [value]="winRate(day.win_rate)" [sample]="day.trade_count" />
        <sb-stat-tile label="Winners" [value]="day.winners.toString()" [sample]="day.trade_count" tone="pos" />
        <sb-stat-tile label="Losers" [value]="day.losers.toString()" [sample]="day.trade_count" tone="neg" />
        <sb-stat-tile label="Average trade" [value]="r(day.avg_trade_r)" [sample]="day.trade_count" [attr.title]="rTooltip" />
        <sb-stat-tile label="Worst drawdown" [value]="r(day.worst_drawdown_r)" [sample]="day.trade_count" tone="neg" [attr.title]="rTooltip" />
      </div>
      <p class="r-note">{{ rTooltip }}</p>
      @if (store.hasLegs()) {
        <p class="sample-note">{{ legsNote(day.trade_count) }}</p>
      }

      <div class="panels">
        <sb-panel heading="How this day compares">
          <dl class="compare">
            <div><dt>Among trading days</dt><dd class="percentile">{{ percentile(day.context) }}</dd></div>
            <div><dt>In the month</dt><dd class="rank">{{ rankText() }}</dd></div>
            <div><dt>vs average day</dt><dd class="vs-day">{{ delta(day.context.vs_avg_day) }}</dd></div>
            <div><dt class="vs-weekday-label">vs average {{ weekday() }}</dt><dd class="vs-weekday">{{ delta(day.context.vs_weekday_avg) }}</dd></div>
          </dl>
          <p class="caveat">{{ caveat }}</p>
        </sb-panel>
        <sb-panel heading="Month so far" class="month-panel">
          @if (monthLine(); as line) {
            <svg class="month-line" viewBox="0 0 240 56" width="100%" height="56" preserveAspectRatio="none" aria-hidden="true">
              @if (line.zeroY !== null) {
                <line class="zero" x1="0" x2="240" [attr.y1]="line.zeroY" [attr.y2]="line.zeroY" />
              }
              <path class="curve" [attr.d]="line.path" />
              @if (line.marker; as m) {
                <circle class="marker" r="3" [attr.cx]="m.x" [attr.cy]="m.y" />
              }
            </svg>
          }
          <p class="mtd">
            Month to date
            <span class="mtd-pnl" [class.pos]="mtdSign() === 'pos'" [class.neg]="mtdSign() === 'neg'">{{ ccy(store.monthCtx()?.mtdPnl ?? null) }}</span>
            ·
            <span class="mtd-r" [title]="rTooltip">{{ r(store.monthCtx()?.mtdR ?? null) }}</span>
          </p>
          <p class="rank">{{ rankText() }}</p>
        </sb-panel>
      </div>

      <sb-panel heading="What drove it">
        <sb-tab-bar [tabs]="tabs" [active]="dimension()" (activeChange)="setDimension($event)" />
        <div class="table-wrap"><table class="breakdown">
          <thead>
            <tr>
              <th>{{ dimensionLabel() }}</th>
              <th class="num">n</th>
              <th class="num">P&amp;L</th>
              <th class="num r-head" [title]="rTooltip">R</th>
              <th class="num">Win %</th>
              <th aria-hidden="true"></th>
            </tr>
          </thead>
          <tbody>
            @for (row of breakdownRows(); track row.key) {
              <tr class="breakdown-row">
                <th scope="row" class="key">{{ row.key }}</th>
                <td class="num">{{ row.n }}</td>
                <td class="num" [class.pos]="signOf(row.pnl_amount) === 'pos'" [class.neg]="signOf(row.pnl_amount) === 'neg'">{{ ccy(row.pnl_amount) }}</td>
                <td class="num" [class.pos]="signOf(row.r) === 'pos'" [class.neg]="signOf(row.r) === 'neg'">{{ r(row.r) }}</td>
                <td class="num win" [class.withheld]="breakdownWinRate(row) === absent" [attr.title]="breakdownWinRate(row) === absent ? winNote : null">{{ breakdownWinRate(row) }}</td>
                <td class="bar" aria-hidden="true"><span class="fill" [class.pos]="signOf(row.pnl_amount) === 'pos'" [class.neg]="signOf(row.pnl_amount) === 'neg'" [style.width.%]="barWidth(row)"></span></td>
              </tr>
            }
          </tbody>
        </table></div>
        <p class="win-note">{{ winNote }}</p>
      </sb-panel>

      <sb-panel [heading]="'Trades (' + day.trade_count + ')'" class="trades-panel">
        <sb-segmented panel-actions label="Sort trades" [options]="sorts" [value]="store.sort()" (valueChange)="setSort($event)" />
        @for (trade of store.trades(); track trade.trade_id + ':' + trade.leg_index) {
          <sb-day-trade-card [trade]="trade" [series]="seriesFor(trade)" />
        }
      </sb-panel>
    } @else if (store.empty()) {
      <sb-empty-state [title]="emptyTitle()" hint="Step to a neighbouring trading day, or widen the filters." />
    } @else if (store.loading()) {
      <p class="day-loading">Loading...</p>
    }
  `,
  styles: `
    :host { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--section-gap); }
    .day-head { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-14); }
    .back, .steps a, .steps .off { display: inline-flex; align-items: center; min-height: 44px; padding-inline: var(--space-4); }
    .back { color: var(--text-secondary); text-decoration: none; }
    .back:hover, .back:focus-visible { color: var(--text); text-decoration: underline; }
    .long-date { margin: 0; font-size: var(--text-h2, 1.25rem); font-weight: 600; }
    .steps { display: inline-flex; gap: var(--space-10); margin-left: auto; }
    .steps a { color: var(--accent); text-decoration: none; }
    .steps .off { color: var(--text-secondary); text-decoration: line-through; }
    .caption, .sample-note, .caveat, .r-note, .win-note { margin: 0; color: var(--text-secondary); font-size: var(--text-table); }
    .stale { margin: 0; color: var(--warn); font-size: var(--text-table); }
    .tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: var(--space-8); }
    .panels { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--space-14); }
    @media (max-width: 639px) { .panels { grid-template-columns: minmax(0, 1fr); } }
    /* D7: comparison figures stay in the neutral text colour. */
    .compare { display: grid; gap: var(--space-8); margin: 0 0 var(--space-10); }
    .compare div { display: flex; justify-content: space-between; gap: var(--space-10); }
    .compare dt { color: var(--text-secondary); }
    .compare dd { margin: 0; color: var(--text); font-family: var(--font-mono); text-align: right; }
    .month-line { display: block; margin-bottom: var(--space-8); }
    .month-line .zero { stroke: var(--border-strong); stroke-dasharray: 2 2; }
    .month-line .curve { fill: none; stroke: var(--text-secondary); stroke-width: 1.5; vector-effect: non-scaling-stroke; }
    .month-line .marker { fill: var(--accent); }
    .mtd { margin: var(--space-4) 0 0; font-size: var(--text-table); }
    .month-panel .rank { margin: 0; padding-top: var(--space-4); font-size: var(--text-table); }
    .mtd span { font-family: var(--font-mono); }
    .table-wrap { overflow-x: auto; }
    .breakdown { width: 100%; margin-top: var(--space-10); border-collapse: collapse; font-size: var(--text-table); }
    .breakdown th, .breakdown td { padding: var(--space-4) var(--space-6); text-align: left; }
    .breakdown .num { text-align: right; font-family: var(--font-mono); }
    .breakdown .r-head { cursor: help; }
    .breakdown .win.withheld { color: var(--text-secondary); }
    .breakdown .bar { width: 30%; }
    .breakdown .fill { display: block; height: 8px; border-radius: var(--radius-sm); background: var(--text-faint); }
    .breakdown .fill.pos { background: var(--pos); }
    .breakdown .fill.neg { background: var(--neg); }
    .day-loading { margin: 0; color: var(--text-secondary); }
  `,
})
export class CalendarDayPage {
  readonly store = inject(CalendarDayStore);
  private readonly connection = inject(ConnectionStore);

  /** The raw `:date` param, kept for the empty-state wording. */
  readonly date = input<string>();

  protected readonly caption = PAPER_CAPTION;
  protected readonly caveat = ONE_DAY_CAVEAT;
  protected readonly rTooltip = R_TOOLTIP;
  protected readonly absent = ABSENT;
  protected readonly winNote = '— : win % withheld, fewer than 5 rows';
  protected readonly tabs = TABS;
  protected readonly sorts = SORTS;
  protected readonly breakdownWinRate = breakdownWinRate;
  protected readonly legsNote = legsSampleNote;
  protected readonly signOf = sign;

  protected readonly dimension = signal<DayBreakdownDimension>('strategy');

  protected readonly title = computed(() => {
    const date = this.store.date();
    return date ? longDate(date) : (this.date() ?? '');
  });
  protected readonly weekday = computed(() => {
    const date = this.store.date();
    return date ? weekdayName(date) : 'weekday';
  });
  protected readonly monthName = computed(() => {
    const date = this.store.date();
    return date ? monthLabel(monthOf(date)) : null;
  });
  protected readonly backMonth = computed(() => (this.monthName() ? ` · ${this.monthName()}` : ''));
  protected readonly backParams = computed(() => {
    const date = this.store.date();
    return { ...(date ? { month: monthOf(date) } : {}), ...this.store.filterParams() };
  });
  protected readonly emptyTitle = computed(
    () => `No closed trades on ${this.date() ?? ''} under this filter`,
  );

  protected readonly rankText = computed(() => {
    const ctx = this.store.monthCtx();
    if (!ctx || ctx.rank === null) return ABSENT;
    return `${ordinal(ctx.rank)} best of ${ctx.rankOf} days in ${this.monthName()}`;
  });
  protected readonly monthLine = computed(() => {
    const ctx = this.store.monthCtx();
    return ctx && ctx.curve.length ? monthLineGeometry(ctx.curve, ctx.dayIndex) : null;
  });
  protected readonly mtdSign = computed(() => sign(this.store.monthCtx()?.mtdPnl ?? null));

  protected readonly dimensionLabel = computed(
    () => TABS.find((tab) => tab.id === this.dimension())?.label ?? '',
  );
  protected readonly breakdownRows = computed<DayBreakdownRow[]>(
    () => this.store.day()?.breakdown[this.dimension()] ?? [],
  );
  private readonly maxAbsPnl = computed(() =>
    Math.max(0, ...this.breakdownRows().map((row) => Math.abs(row.pnl_amount ?? 0))),
  );

  protected setDimension(id: string): void {
    this.dimension.set(id as DayBreakdownDimension);
  }

  protected setSort(value: string): void {
    this.store.setSort(value as DaySort);
  }

  protected barWidth(row: DayBreakdownRow): number {
    const max = this.maxAbsPnl();
    return max === 0 || row.pnl_amount === null ? 0 : (Math.abs(row.pnl_amount) / max) * 100;
  }

  protected seriesFor(trade: CalendarTrade): SparkSeries | null | undefined {
    return this.store.sparklines()?.series[`${trade.trade_id}:${trade.leg_index}`];
  }

  protected percentile(context: DayContext): string {
    return percentileView(context.percentile, context.history_days).text;
  }

  /** Neutral text by design (D7): the sign is in the figure, not a colour. */
  protected delta(value: DayDelta): string {
    if (value.pnl_amount === null && value.r === null) return ABSENT;
    return `${this.ccy(value.pnl_amount)} · ${this.r(value.r)}`;
  }

  protected ccy(value: number | null): string {
    return money(value, this.connection.currency(), 2);
  }

  protected r(value: number | null): string {
    return rMultiple(value);
  }

  protected winRate(value: number | null): string {
    return value === null ? ABSENT : `${value.toFixed(0)}%`;
  }
}
