import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';

import { CalendarDay } from '../../api/models';
import { CalendarMetric, CalendarStore } from '../../stores/calendar.store';
import { Button } from '../../ui/button';
import { ABSENT, money, rMultiple } from '../../ui/format';
import { Panel } from '../../ui/layout';
import { Select } from '../../ui/form-controls';
import { GridCell, monthLabel, monthMatrix } from './calendar.helpers';

/** Monday-first, matching `monthMatrix` and the API's weekday breakdown. */
const WEEKDAY_HEADS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

const METRICS: { value: CalendarMetric; label: string }[] = [
  { value: 'money', label: '$' },
  { value: 'r', label: 'R' },
];

@Component({
  selector: 'sb-calendar',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Button, Panel, Select],
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
        @for (option of metrics; track option.value) {
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
  `,
})
export class Calendar {
  readonly store = inject(CalendarStore);

  protected readonly weekdayHeads = WEEKDAY_HEADS;
  protected readonly metrics = METRICS;

  protected readonly label = computed(() => monthLabel(this.store.month()));
  protected readonly weeks = computed<GridCell[][]>(() =>
    monthMatrix(this.store.month()),
  );

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
    return day.net_pnl_amount === null ? ABSENT : money(day.net_pnl_amount, '$', 0);
  }
}
