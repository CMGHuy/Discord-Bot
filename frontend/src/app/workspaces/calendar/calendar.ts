import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';

import { CalendarDay, CalendarTrade, CalendarWeekday } from '../../api/models';
import { CalendarMetric, CalendarStore } from '../../stores/calendar.store';
import { ConnectionStore } from '../../stores/connection.store';
import { Button } from '../../ui/button';
import { ABSENT, money, rMultiple } from '../../ui/format';
import { Drawer, Panel } from '../../ui/layout';
import { MetricCard } from '../../ui/metric-card';
import { Select } from '../../ui/form-controls';
import { GridCell, monthLabel, monthMatrix } from './calendar.helpers';

/** Monday-first, matching `monthMatrix` and the API's weekday breakdown. */
const WEEKDAY_HEADS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

@Component({
  selector: 'sb-calendar',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Button, Drawer, MetricCard, Panel, Select],
  // Provided on the component: created on entry, destroyed on exit, so the
  // workspace cannot hold a stale month while you are looking elsewhere.
  providers: [CalendarStore],
  template: `
    <header class="head">
      <h1>Calendar</h1>
      @if (store.error(); as message) {
        <span class="stale" role="status">{{ message }}</span>
      }
    </header>

    <div class="controls">
      <div class="months">
        <button sb-button type="button" variant="ghost"
                (click)="store.stepMonth(-1)" aria-label="Previous month">‹</button>
        <span class="month">{{ label() }}</span>
        <button sb-button type="button" variant="ghost"
                (click)="store.stepMonth(1)" aria-label="Next month">›</button>
      </div>

      <div class="metric" role="group" aria-label="Metric">
        @for (option of metrics(); track option.value) {
          <button
            type="button"
            [class.active]="store.metric() === option.value"
            (click)="store.setMetric(option.value)"
          >
            {{ option.label }}
          </button>
        }
      </div>

      <sb-select
        label="Strategy"
        placeholder="Any strategy"
        [options]="store.strategyOptions()"
        [value]="store.strategy()"
        (valueChange)="store.setStrategy($event)"
      />
      <sb-select
        label="Horizon"
        placeholder="Any horizon"
        [options]="store.horizonOptions()"
        [value]="store.horizon()"
        (valueChange)="store.setHorizon($event)"
      />
    </div>

    <div class="totals">
      <sb-metric-card
        label="Net this month"
        [value]="store.metric() === 'r' ? (store.totals()?.net_r ?? null) : (store.totals()?.net_pnl_amount ?? null)"
        [unit]="store.metric() === 'r' ? 'R' : currency()"
        [tone]="totalsTone()"
      />
      <sb-metric-card label="Trades" [value]="store.totals()?.trade_count ?? null" [decimals]="0" />
      <sb-metric-card label="Win rate" [value]="store.totals()?.win_rate ?? null" unit="%" [decimals]="1" />
    </div>

    <div class="callouts">
      <sb-panel heading="Best day">
        <p class="callout">{{ extremeLabel(store.bestDay()) }}</p>
      </sb-panel>
      <sb-panel heading="Worst day">
        <p class="callout">{{ extremeLabel(store.worstDay()) }}</p>
      </sb-panel>
      <sb-panel heading="Current streak">
        <p class="callout">{{ streakLabel() }}</p>
      </sb-panel>
    </div>

    <sb-panel [flush]="true">
      <div class="grid" role="grid" [attr.aria-label]="label()">
        <!-- NOT class="week": the grid tests assert every \`.week\` holds
             exactly 7 \`.cell\` children, and a header row sharing that class
             would contribute a row of zero. -->
        <div class="weekhead" role="row">
          @for (head of weekdayHeads; track head) {
            <div class="head-cell" role="columnheader">{{ head }}</div>
          }
        </div>
        @for (week of weeks(); track week[0].date) {
          <div class="week" role="row">
            @for (cell of week; track cell.date) {
              <div
                class="cell"
                role="gridcell"
                [attr.data-date]="cell.date"
                [class.outside]="!cell.inMonth"
                [class.weekend]="cell.weekend"
                [class.pos]="intensity(cell) > 0"
                [class.neg]="intensity(cell) < 0"
                [style.--heat]="magnitude(cell)"
              >
                <span class="dom">{{ cell.dayOfMonth }}</span>
                @if (dayFor(cell); as day) {
                  <button type="button" class="value" (click)="store.selectDay(day.date)">
                    {{ display(day) }}
                    <span class="n">{{ day.trade_count }}</span>
                  </button>
                }
              </div>
            }
          </div>
        }
      </div>
    </sb-panel>

    <sb-panel heading="By weekday (all history)">
      <table class="dow">
        <thead>
          <tr><th>Day</th><th class="num">Avg</th><th class="num">Win rate</th><th class="num">n</th></tr>
        </thead>
        <tbody>
          @for (weekday of store.weekdays(); track weekday.weekday) {
            <tr class="dow-row">
              <th scope="row">{{ weekday.weekday }}</th>
              <td class="num">{{ weekdayValue(weekday) }}</td>
              <td class="num">{{ weekdayWinRate(weekday) }}</td>
              <td class="num">{{ weekday.trade_count }}</td>
            </tr>
          }
        </tbody>
      </table>
    </sb-panel>

    <sb-drawer
      [open]="store.selectedDay() !== null"
      [heading]="store.selectedDay() ?? ''"
      (closed)="store.closeDay()"
    >
      @if (store.dayLoading()) {
        <p class="day-loading">Loading...</p>
      } @else if ((store.dayTrades() ?? []).length === 0) {
        <p class="day-empty">No closed trades on this day under the current filter.</p>
      } @else {
        @for (trade of store.dayTrades() ?? []; track trade.trade_id) {
          <article class="day-row">
            <header>
              <strong>{{ trade.ticker }}</strong>
              <span class="meta">{{ trade.strategy }} · {{ trade.horizon }}</span>
              <span class="amount" [class.pos]="(trade.pnl_amount ?? 0) >= 0"
                    [class.neg]="(trade.pnl_amount ?? 0) < 0">
                {{ tradeValue(trade) }}
              </span>
            </header>
            <p class="meta">
              {{ trade.outcome }} · {{ rLabel(trade.r_multiple) }}
              @if (trade.mfe_r !== null) { · MFE {{ rLabel(trade.mfe_r) }} }
              @if (trade.mae_r !== null) { · MAE {{ rLabel(trade.mae_r) }} }
            </p>
            @if (trade.auto_lesson; as lesson) {
              <p class="lesson">{{ lesson }}</p>
            }
            @if (trade.tags.length) {
              <p class="tags">
                @for (tag of trade.tags; track tag) {
                  <span class="tag">{{ tag }}</span>
                }
              </p>
            }
          </article>
        }
      }
    </sb-drawer>
  `,
  styles: `
    /* No backticks in here: these styles live in a TS template literal. */
    :host { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--space-20); }
    .head { display: flex; align-items: baseline; gap: var(--space-14); }
    h1 { margin: 0; font-size: var(--text-title); font-weight: 600; }
    .stale { color: var(--warn); font-size: var(--text-table); }

    .controls {
      display: flex;
      flex-wrap: wrap;
      align-items: flex-end;
      gap: var(--space-14);
    }
    .months { display: flex; align-items: center; gap: var(--space-8); }
    .month { min-width: 10ch; font-weight: 600; }

    .metric { display: inline-flex; border: 1px solid var(--border); border-radius: var(--radius); }
    .metric button {
      height: var(--control-h);
      padding: 0 var(--space-10);
      background: none;
      border: 0;
      color: var(--text-secondary);
      font: inherit;
      cursor: pointer;
    }
    .metric button.active { background: var(--surface-raised); color: var(--text); }

    .totals { display: flex; flex-wrap: wrap; gap: var(--space-14); }
    .callouts {
      display: grid;
      gap: var(--space-14);
      grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr));
    }
    .callout { margin: 0; font-family: var(--font-mono); font-size: var(--text-table); }

    .grid { display: grid; }
    .week, .weekhead { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); }
    .head-cell {
      padding: var(--space-6);
      color: var(--text-secondary);
      font-size: var(--text-micro);
      font-weight: 600;
      letter-spacing: 0.1em;
      text-align: center;
      text-transform: uppercase;
    }
    .cell {
      display: flex;
      flex-direction: column;
      gap: var(--space-4);
      min-height: 4.5rem;
      padding: var(--space-6);
      border-top: 1px solid var(--border);
      border-left: 1px solid var(--border);
    }
    .week .cell:last-child { border-right: 1px solid var(--border); }
    .dom { color: var(--text-secondary); font-size: var(--text-micro); }
    .outside .dom { color: var(--text-faint); }

    /* Weekends carry no closes, ever. Hatching them says "not a trading day"
       rather than "a trading day that happened to be quiet" -- the same
       distinction the payload makes by omitting empty days. */
    .weekend { background: var(--surface-sunken, transparent); }
    .weekend .dom { color: var(--text-faint); }

    /* Signed ramp off --heat (0..1), the same [style.--heat] + color-mix
       mechanism the Analytics win-rate heatmap uses. Green/red are reserved
       for P&L direction, which is exactly what this grid shows. */
    .cell.pos { background: color-mix(in srgb, var(--pos) calc(var(--heat, 0) * 55%), transparent); }
    .cell.neg { background: color-mix(in srgb, var(--neg) calc(var(--heat, 0) * 55%), transparent); }

    .value {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: var(--space-6);
      padding: 0;
      background: none;
      border: 0;
      color: var(--text);
      font: inherit;
      font-family: var(--font-mono);
      font-size: var(--text-table);
      cursor: pointer;
      text-align: left;
    }
    .value:hover { text-decoration: underline; }
    .value:focus-visible { outline: 1px solid var(--accent); outline-offset: 1px; }
    .n { color: var(--text-secondary); font-size: var(--text-micro); }

    .dow { width: 100%; border-collapse: collapse; font-size: var(--text-table); }
    .dow th, .dow td { padding: var(--space-6) var(--space-10); border-bottom: 1px solid var(--border); }
    .dow thead th {
      color: var(--text-secondary);
      font-size: var(--text-micro);
      font-weight: 600;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      text-align: left;
    }
    .dow .num { font-family: var(--font-mono); text-align: right; }

    .day-row { padding: var(--space-10) 0; border-bottom: 1px solid var(--border); }
    .day-row header { display: flex; align-items: baseline; gap: var(--space-8); }
    .day-row .amount { margin-left: auto; font-family: var(--font-mono); }
    .day-row .amount.pos { color: var(--pos); }
    .day-row .amount.neg { color: var(--neg); }
    .day-row .meta { margin: var(--space-4) 0 0; color: var(--text-secondary); font-size: var(--text-micro); }
    .lesson { margin: var(--space-6) 0 0; font-size: var(--text-table); }
    .tags { display: flex; flex-wrap: wrap; gap: var(--space-4); margin: var(--space-6) 0 0; }
    .tag {
      padding: 0 var(--space-6);
      background: var(--surface-raised);
      border-radius: var(--radius);
      color: var(--text-secondary);
      font-size: var(--text-micro);
    }
    .day-empty, .day-loading { margin: 0; color: var(--text-secondary); font-size: var(--text-table); }
  `,
})
export class Calendar {
  readonly store = inject(CalendarStore);
  private readonly connection = inject(ConnectionStore);

  protected readonly weekdayHeads = WEEKDAY_HEADS;

  /** The account's own symbol, never a literal `$` -- see `MetricCard`'s
   *  note. An admin running a euro account must not read euro figures
   *  labelled in dollars. */
  protected readonly currency = computed(() => this.connection.currency());

  /** The toggle's two choices. Computed rather than a module constant so
   *  the money side is labelled with the account's currency. */
  protected readonly metrics = computed<{ value: CalendarMetric; label: string }[]>(() => [
    { value: 'money', label: this.currency() },
    { value: 'r', label: 'R' },
  ]);

  protected readonly label = computed(() => monthLabel(this.store.month()));
  protected readonly weeks = computed<GridCell[][]>(() =>
    monthMatrix(this.store.month()),
  );

  /** `plain` while there is nothing to colour, so a loading strip is not
   *  briefly green; `pnl` is the only tone allowed to go green or red, and
   *  it takes its sign from the value itself. */
  protected readonly totalsTone = computed(() => {
    const totals = this.store.totals();
    const value =
      this.store.metric() === 'r' ? totals?.net_r : totals?.net_pnl_amount;
    if (value === null || value === undefined) return 'plain' as const;
    return 'pnl' as const;
  });

  /** The day behind a cell, or null. Cells outside the month and weekends
   *  never resolve: a close cannot land on either, so offering a click
   *  target would promise a drawer that must come back empty. */
  protected dayFor(cell: GridCell): CalendarDay | null {
    if (!cell.inMonth || cell.weekend) return null;
    return this.store.dayIndex().get(cell.date) ?? null;
  }

  /** -1..+1 for the cell's day, 0 for a cell with no day. */
  protected intensity(cell: GridCell): number {
    const day = this.dayFor(cell);
    return day ? this.store.signedIntensity(day) : 0;
  }

  /** The 0..1 the CSS ramp consumes; sign is carried by the class instead. */
  protected magnitude(cell: GridCell): number {
    return Math.abs(this.intensity(cell));
  }

  /** The cell's number, formatted for the metric on show. */
  protected display(day: CalendarDay): string {
    if (this.store.metric() === 'r') return rMultiple(day.net_r);
    return day.net_pnl_amount === null
      ? ABSENT
      : money(day.net_pnl_amount, this.currency(), 0);
  }

  /** `"50%"`, or ABSENT at n=0 -- never `"0%"`, which would read as a real
   *  all-losses weekday rather than as no data. */
  protected weekdayWinRate(weekday: CalendarWeekday): string {
    return weekday.win_rate === null ? ABSENT : `${weekday.win_rate.toFixed(0)}%`;
  }

  /** A weekday's average, in the metric on show. */
  protected weekdayValue(weekday: CalendarWeekday): string {
    if (this.store.metric() === 'r') return rMultiple(weekday.avg_r);
    return weekday.avg_pnl_amount === null
      ? ABSENT
      : money(weekday.avg_pnl_amount, this.currency(), 2);
  }

  /** "2026-08-05 · -90 €" -- the date is the point, so it leads. */
  protected extremeLabel(day: CalendarDay | null): string {
    if (!day) return ABSENT;
    return `${day.date} · ${this.display(day)}`;
  }

  /** One trade's headline figure, in the metric on show -- so the drawer
   *  and the cell that opened it never disagree about units. */
  protected tradeValue(trade: CalendarTrade): string {
    if (this.store.metric() === 'r') return rMultiple(trade.r_multiple);
    return trade.pnl_amount === null
      ? ABSENT
      : money(trade.pnl_amount, this.currency(), 2);
  }

  protected rLabel(value: number | null): string {
    return rMultiple(value);
  }

  /** "1 losing day", or ABSENT when there is no run to report. */
  protected streakLabel(): string {
    const streak = this.store.streak();
    if (!streak || streak.direction === null || streak.days === 0) return ABSENT;
    const unit = streak.days === 1 ? 'day' : 'days';
    return `${streak.days} ${streak.direction} ${unit}`;
  }
}
