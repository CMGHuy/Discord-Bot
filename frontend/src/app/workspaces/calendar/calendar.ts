import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';

import { CalendarDay, CalendarTrade, CalendarWeekday } from '../../api/models';
import { CalendarMetric, CalendarStore } from '../../stores/calendar.store';
import { ConnectionStore } from '../../stores/connection.store';
import { asyncInputs, Async } from '../../ui/async';
import { Button } from '../../ui/button';
import { ABSENT, money, rMultiple } from '../../ui/format';
import { ControlRow, Drawer, Panel } from '../../ui/layout';
import { Freshness } from '../../ui/freshness';
import { MetricCard } from '../../ui/metric-card';
import { Select } from '../../ui/form-controls';
import { SectionHead } from '../../ui/section-head';
import { StatTile } from '../../ui/stat-tile';
import { cellValue, GridCell, monthLabel, monthMatrix } from './calendar.helpers';

/** Monday-first, matching `monthMatrix` and the API's weekday breakdown. */
const WEEKDAY_HEADS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

@Component({
  selector: 'sb-calendar',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Button, ControlRow, Drawer, MetricCard, Panel, SectionHead, Select, StatTile, Async, Freshness],
  // v54 D1: "how am I doing this month?" -- hero totals, room to breathe --
  // so this workspace defaults to the presentation register. On the host
  // (a static class, not a template wrapper) because :host IS the grid
  // container the register's variables need to reach.
  host: { class: 'register-presentation' },
  // Provided on the component: created on entry, destroyed on exit, so the
  // workspace cannot hold a stale month while you are looking elsewhere.
  template: `
    <sb-section-head>
      <!-- Kept unconditional (unlike Dashboard/Trades): "By weekday (all
           history)" below stays outside the sb-async wrap -- it answers a
           different, all-time question that a THIS MONTH empty state must
           not gate -- and has no error surface of its own, so this remains
           its only one. Duplicates the wrapped panels' own error/stale
           display on a first-load failure; accepted the same way Risk does. -->
      @if (store.error(); as message) {
        <span actions class="stale" role="status">{{ message }}</span>
      }
    </sb-section-head>

    <sb-control-row>
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
            sb-button
            variant="segment"
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
    </sb-control-row>

    <sb-async
      [loading]="async().loading"
      [error]="async().error"
      [empty]="async().empty"
      [staleAsOf]="async().staleAsOf"
      emptyReason="measured-zero"
      emptyTitle="No closed trades this month"
      emptyHint="Pick another month, or widen the filters."
      [skeletonRows]="6"
      [skeletonCols]="7"
      (retry)="store.load()"
    >
      <!-- One row for every summary figure -- the live-month totals and the
           month-over-month stats used to split across two separate rows
           (one above the grid, one below) for no reason tied to what they
           mean; auto-fit wraps to a second row on its own once width runs
           out, rather than a hardcoded per-row count. -->
      <div class="totals">
        <sb-metric-card
          label="Net this month"
          [value]="totalValue()"
          [unit]="totalUnit()"
          [tone]="totalsTone()"
        />
        <sb-metric-card label="Trades" [value]="store.totals()?.trade_count ?? null" [decimals]="0" />
        <sb-metric-card label="Win rate" [value]="store.totals()?.win_rate ?? null" unit="%" [decimals]="1" />
        <sb-stat-tile label="Month total" [value]="monthTotal()" [sample]="monthDays().length" />
        <sb-stat-tile label="Winning days" [value]="winningDaysLabel()" [sample]="monthDays().length" tone="pos" />
        <sb-stat-tile label="Average day" [value]="averageDay()" [sample]="monthDays().length" />
        <sb-stat-tile label="Best day" [value]="monthExtreme('best')" [sample]="monthDays().length" tone="pos" />
        <sb-stat-tile label="Worst day" [value]="monthExtreme('worst')" [sample]="monthDays().length" tone="neg" />
      </div>

      <!-- The day-detail pane that used to sit beside this grid duplicated
           the drawer below word for word (same store signals, same fields)
           and, unselected, only ever said "Select a day to inspect its
           trades" -- a permanent half-empty box for what the drawer already
           covers the moment a day is actually clicked. Removed rather than
           kept in sync twice. -->
      <sb-panel [flush]="true">
        <sb-freshness [at]="store.data()?.as_of ?? null" />
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
                  [class.selected]="store.selectedDay() === cell.date"
                  [style.--heat]="magnitude(cell)"
                >
                  <span class="dom">{{ cell.dayOfMonth }}</span>
                  @if (dayFor(cell); as day) {
                    <button sb-button variant="link" type="button" class="value"
                            [attr.aria-pressed]="store.selectedDay() === day.date"
                            (click)="store.selectDay(day.date)">
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
    </sb-async>

    <!-- All-time, not this-month: deliberately outside the sb-async above
         so a THIS MONTH empty state cannot hide it (see the section-head
         comment). Degrades safely via weekdays()'s own [] default before
         the first load. -->
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
      } @else if (store.dayDetail() === null) {
        <p class="day-empty">No closed trades on this day under the current filter.</p>
      } @else if (store.dayDetail()!.trades.length === 0) {
        <p class="day-empty">No closed trades on this day under the current filter.</p>
      } @else if (store.dayDetail(); as detail) {
        <div class="day-summary">
          <sb-stat-tile label="Total" [value]="rLabel(detail.total_r)" [sample]="detail.trade_count" />
          <sb-stat-tile label="Winners" [value]="detail.winners.toString()" [sample]="detail.trade_count" tone="pos" />
          <sb-stat-tile label="Losers" [value]="detail.losers.toString()" [sample]="detail.trade_count" tone="neg" />
          <sb-stat-tile label="Average trade" [value]="rLabel(detail.avg_trade_r)" [sample]="detail.trade_count" />
          <sb-stat-tile label="Worst drawdown" [value]="rLabel(detail.worst_drawdown_r)" [sample]="detail.trade_count" tone="neg" />
        </div>
        <div class="day-leaders">
          <section class="contributors">
            <h3>Contributors</h3>
            @if (detail.contributors.length) {
              @for (row of detail.contributors; track $index) { <p>{{ row.ticker }} · {{ rLabel(row.r) }}</p> }
            } @else { <p>Nothing gained today.</p> }
          </section>
          <section class="detractors">
            <h3>Detractors</h3>
            @if (detail.detractors.length) {
              @for (row of detail.detractors; track $index) { <p>{{ row.ticker }} · {{ rLabel(row.r) }}</p> }
            } @else { <p>Nothing lost money today.</p> }
          </section>
        </div>
        @for (trade of detail.trades; track trade.trade_id) {
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
    /* No backticks in here: these styles live in a TS template literal.
       v54: gap reads --register-pad, set by the register-presentation class
       on this same host element (above) -- --space-20 was this rule's own
       literal before, and register-presentation's rung is the same value,
       so this changes nothing visually while making the rhythm follow the
       register instead of a hardcoded token. */
    :host { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--register-pad); }

    /* The month stepper: two buttons with the month between them. Centred
       rather than bottom-aligned like the controls around it, because the
       month is running text and sb-control-row's answer is for controls. */
    .months { display: flex; align-items: center; gap: var(--space-8); }
    .month { min-width: 10ch; font-weight: 600; }

    .metric { display: inline-flex; border: 1px solid var(--border); border-radius: var(--radius); }
    /* padding/border override the segment variant's defaults for a
       tighter two-cell toggle; the variant owns colour, weight and the
       active-cell background is our own since this pair has no divider. */
    .metric button {
      padding: 0 var(--space-10);
      border: 0;
    }
    .metric button.active { background: var(--surface-raised); color: var(--text); }

    /* One row, same auto-fit-to-140px card language as Dashboard's Trading
       Performance grid; wraps to a second row on its own once eight cards
       stop fitting, rather than a hardcoded per-row count. */
    .totals { display: grid; gap: var(--space-14); grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); }

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
    .cell.selected { outline: 2px solid var(--accent); outline-offset: -2px; }

    /* align-items/padding/colour/font override the link variant's defaults
       -- a data figure, not a coloured hyperlink; the variant owns the
       hover underline. */
    .value {
      align-items: baseline;
      justify-content: space-between;
      padding: 0;
      border: 0;
      color: var(--text);
      font: inherit;
      font-family: var(--font-mono);
      font-size: var(--text-table);
    }
    .value:focus-visible { outline-offset: 1px; }
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
    .day-summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: var(--space-8); margin-bottom: var(--space-14); }
    .day-leaders { display: grid; grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr)); gap: var(--space-14); margin-bottom: var(--space-14); }
    .day-leaders h3 { margin: 0 0 var(--space-6); font-size: var(--text-micro); text-transform: uppercase; letter-spacing: 0.08em; }
    .day-leaders p { margin: var(--space-4) 0; color: var(--text-secondary); font-family: var(--font-mono); font-size: var(--text-table); }
  `,
})
export class Calendar {
  readonly store = inject(CalendarStore);
  private readonly connection = inject(ConnectionStore);

  protected readonly weekdayHeads = WEEKDAY_HEADS;

  protected readonly async = computed(() =>
    asyncInputs(this.store, { isEmpty: (data) => data.totals.trade_count === 0 }),
  );

  /** The account's own symbol, never a literal `$` -- see `MetricCard`'s
   *  note. An admin running a euro account must not read euro figures
   *  labelled in dollars. */
  protected readonly currency = computed(() => this.connection.currency());

  /** The toggle's two choices. Computed rather than a module constant so
   *  the money side is labelled with the account's currency. */
  protected readonly metrics = computed<{ value: CalendarMetric; label: string }[]>(() => [
    { value: 'currency', label: this.currency() },
    { value: 'r', label: 'R' },
    { value: 'trades', label: 'Trades' },
    { value: 'win_rate', label: 'Win rate' },
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
    const value = this.totalValue();
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
    return cellValue(day, this.store.metric()).text || ABSENT;
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

  protected totalValue(): number | null {
    const totals = this.store.totals();
    if (!totals) return null;
    switch (this.store.metric()) {
      case 'r': return totals.net_r;
      case 'currency': return totals.net_pnl_amount;
      case 'trades': return totals.trade_count;
      case 'win_rate': return totals.win_rate;
    }
  }

  protected totalUnit(): string {
    switch (this.store.metric()) {
      case 'r': return 'R';
      case 'currency': return this.currency();
      case 'win_rate': return '%';
      case 'trades': return '';
    }
  }

  /** Closed-trading days only: calendar blanks are not observations. */
  protected readonly monthDays = computed(() => this.store.days().filter((day) => day.trade_count > 0));

  protected monthTotal(): string {
    const value = this.totalValue();
    if (value === null) return ABSENT;
    if (this.store.metric() === 'r') return rMultiple(value);
    if (this.store.metric() === 'currency') return money(value, this.currency(), 2);
    if (this.store.metric() === 'win_rate') return `${value.toFixed(1)}%`;
    return `${value}`;
  }

  protected winningDaysLabel(): string {
    const days = this.monthDays();
    if (!days.length) return ABSENT;
    const wins = days.filter((day) => (day.net_r ?? day.net_pnl_amount ?? 0) > 0).length;
    return `${wins} (${((wins / days.length) * 100).toFixed(0)}%)`;
  }

  protected averageDay(): string {
    const values = this.monthDays()
      .map((day) => cellValue(day, this.store.metric()).value)
      .filter((value): value is number => value !== null);
    if (!values.length) return ABSENT;
    const value = values.reduce((sum, current) => sum + current, 0) / values.length;
    if (this.store.metric() === 'r') return rMultiple(value);
    if (this.store.metric() === 'currency') return money(value, this.currency(), 2);
    if (this.store.metric() === 'win_rate') return `${value.toFixed(1)}%`;
    return `${value.toFixed(1)}`;
  }

  protected monthExtreme(which: 'best' | 'worst'): string {
    const values = this.monthDays()
      .map((day) => cellValue(day, this.store.metric()).value)
      .filter((value): value is number => value !== null);
    if (!values.length) return ABSENT;
    const value = which === 'best' ? Math.max(...values) : Math.min(...values);
    if (this.store.metric() === 'r') return rMultiple(value);
    if (this.store.metric() === 'currency') return money(value, this.currency(), 2);
    if (this.store.metric() === 'win_rate') return `${value.toFixed(1)}%`;
    return `${value}`;
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
