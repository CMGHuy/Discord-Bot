import { ChangeDetectionStrategy, Component, computed, input, signal } from '@angular/core';

import { Ticker } from '../../api/models';
import { Button } from '../../ui/button';
import { timeInZone } from '../../ui/format';
import { ControlRow } from '../../ui/layout';

function startOfMonth(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), 1);
}

function addMonths(d: Date, delta: number): Date {
  return new Date(d.getFullYear(), d.getMonth() + delta, 1);
}

/** Local YYYY-MM-DD -- matches next_earnings_date's own format exactly, so
 *  grouping by this key needs no parsing on either side. Deliberately NOT
 *  `date.toISOString().slice(0, 10)`, which reads the date back in UTC and
 *  would shift it a day for any viewer west of Greenwich. */
export function toDateKey(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

/** A Monday-first grid covering the given month exactly, trimmed to
 *  whichever of 4-6 weeks that month actually needs -- not a fixed 6, which
 *  would render a visibly empty trailing week for most months. */
export function buildWeeks(monthStart: Date): Date[][] {
  const year = monthStart.getFullYear();
  const month = monthStart.getMonth();
  const firstOfMonth = new Date(year, month, 1);
  const lastOfMonth = new Date(year, month + 1, 0);

  const startOffset = (firstOfMonth.getDay() + 6) % 7; // Mon=0 .. Sun=6
  const gridStart = new Date(year, month, 1 - startOffset);
  const endOffset = 6 - ((lastOfMonth.getDay() + 6) % 7);
  const gridEnd = new Date(year, month, lastOfMonth.getDate() + endOffset);

  const days: Date[] = [];
  const cursor = new Date(gridStart);
  while (cursor.getTime() <= gridEnd.getTime()) {
    days.push(new Date(cursor));
    cursor.setDate(cursor.getDate() + 1);
  }

  const weeks: Date[][] = [];
  for (let i = 0; i < days.length; i += 7) weeks.push(days.slice(i, i + 7));
  return weeks;
}

interface DayCell {
  dayOfMonth: number;
  inCurrentMonth: boolean;
  isToday: boolean;
  entries: Ticker[];
}

/**
 * Watchlist → Earnings tab: a month calendar of the watchlist's own upcoming
 * earnings dates, one cell per day.
 *
 * Deliberately reads the SAME `tickers` the Watchlist tab already loaded
 * (passed in as an input, not its own store/fetch) -- there is exactly one
 * fetch of watchlist data on this page, so a newly-added ticker's earnings
 * date appears here automatically the next time that load runs, with no
 * separate mechanism to keep in sync.
 *
 * Every date/time shown is inherently an estimate: Yahoo does not expose a
 * "confirmed by the company" flag anywhere in the data this reads
 * (`events.get_next_earnings_datetime`), and a future report date is
 * frequently extrapolated from the company's historical pattern rather than
 * officially announced. Labelled "est." on every entry rather than guessing
 * which ones are more certain.
 */
@Component({
  selector: 'sb-earnings-calendar',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Button, ControlRow],
  template: `
    <sb-control-row class="nav">
      <button sb-button variant="ghost" type="button" (click)="prevMonth()" aria-label="Previous month">←</button>
      <h2>{{ monthLabel() }}</h2>
      <button sb-button variant="ghost" type="button" (click)="nextMonth()" aria-label="Next month">→</button>
      <button sb-button variant="secondary" type="button" (click)="goToday()">Today</button>
    </sb-control-row>

    <div class="grid">
      @for (label of weekdayLabels; track label) {
        <div class="weekday">{{ label }}</div>
      }
      @for (week of weeks(); track $index) {
        @for (cell of week; track cell.dayOfMonth + '-' + $index) {
          <div class="cell" [class.dim]="!cell.inCurrentMonth" [class.today]="cell.isToday">
            <span class="day-num">{{ cell.dayOfMonth }}</span>
            @for (ticker of cell.entries; track ticker.symbol) {
              <div class="entry">
                <span class="symbol">{{ ticker.symbol }}</span>
                <span class="time">
                  {{ fmtUtc(ticker.next_earnings_datetime) }} UTC ·
                  {{ fmtBerlin(ticker.next_earnings_datetime) }} DE
                  <span class="est">est.</span>
                </span>
              </div>
            }
          </div>
        }
      }
    </div>

    @if (!tickers().length) {
      <p class="empty">Nothing on the watchlist yet — add a symbol on the Watchlist tab.</p>
    }
  `,
  styles: `
    :host { display: block; }
    .nav { margin-bottom: var(--space-14); }
    .nav h2 {
      margin: 0 var(--space-8);
      min-width: 11ch;
      color: var(--text);
      font-size: var(--text-subhead);
      font-weight: 600;
    }

    .grid {
      display: grid;
      grid-template-columns: repeat(7, minmax(0, 1fr));
      gap: 1px;
      background: var(--border);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      overflow: hidden;
    }
    .weekday {
      padding: var(--space-6) var(--space-8);
      background: var(--surface);
      color: var(--text-secondary);
      font-size: var(--text-micro);
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      text-align: center;
    }
    .cell {
      display: flex;
      flex-direction: column;
      gap: var(--space-4);
      min-height: 84px;
      padding: var(--space-6) var(--space-8);
      background: var(--bg);
    }
    /* A day outside the shown month, filling out the grid's leading/trailing
       week -- present for alignment, not for reading. */
    .cell.dim { background: var(--surface); }
    .cell.dim .day-num { color: var(--text-faint); }
    .cell.today { box-shadow: inset 0 0 0 2px var(--accent); }
    .day-num { color: var(--text-secondary); font-size: var(--text-chip); font-variant-numeric: tabular-nums; }

    .entry {
      display: flex;
      flex-direction: column;
      gap: 1px;
      padding: var(--space-4);
      background: var(--surface);
      border-radius: var(--radius-sm);
    }
    .symbol { color: var(--text); font-family: var(--font-mono); font-size: var(--text-chip); font-weight: 600; }
    .time {
      color: var(--text-secondary);
      font-size: var(--text-micro);
      font-variant-numeric: tabular-nums;
      overflow-wrap: anywhere;
    }
    .est { margin-left: var(--space-4); color: var(--text-faint); font-style: italic; }

    .empty { margin-top: var(--space-14); color: var(--text-secondary); font-size: var(--text-table); }

    @media (max-width: 720px) {
      /* A 7-column grid at phone width is a column of digits, not a
         calendar -- collapse to a plain agenda list of the days that
         actually have something on them instead of forcing the grid
         sideways. */
      .weekday { display: none; }
      .grid { display: block; background: none; border: 0; }
      .cell { display: none; }
      .cell:has(.entry) {
        display: flex;
        min-height: 0;
        margin-bottom: var(--space-8);
        border: 1px solid var(--border);
        border-radius: var(--radius);
      }
    }
  `,
})
export class EarningsCalendar {
  readonly tickers = input.required<Ticker[]>();

  protected readonly viewMonth = signal(startOfMonth(new Date()));

  protected readonly weekdayLabels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

  protected readonly monthLabel = computed(() =>
    this.viewMonth().toLocaleDateString(undefined, { month: 'long', year: 'numeric' }));

  /** Grouped once per tickers() change, not per cell -- a 42-cell grid
   *  scanning the full ticker list per cell would be quadratic for no
   *  reason. */
  private readonly byDate = computed(() => {
    const map = new Map<string, Ticker[]>();
    for (const ticker of this.tickers()) {
      if (!ticker.next_earnings_date) continue;
      const list = map.get(ticker.next_earnings_date);
      if (list) list.push(ticker);
      else map.set(ticker.next_earnings_date, [ticker]);
    }
    return map;
  });

  protected readonly weeks = computed<DayCell[][]>(() => {
    const month = this.viewMonth();
    const todayKey = toDateKey(new Date());
    const byDate = this.byDate();
    return buildWeeks(month).map((week) =>
      week.map((day) => {
        const key = toDateKey(day);
        return {
          dayOfMonth: day.getDate(),
          inCurrentMonth: day.getMonth() === month.getMonth(),
          isToday: key === todayKey,
          entries: byDate.get(key) ?? [],
        };
      }));
  });

  protected fmtUtc(iso: string | null): string {
    return timeInZone(iso, 'UTC');
  }

  protected fmtBerlin(iso: string | null): string {
    return timeInZone(iso, 'Europe/Berlin');
  }

  protected prevMonth(): void {
    this.viewMonth.update((d) => addMonths(d, -1));
  }

  protected nextMonth(): void {
    this.viewMonth.update((d) => addMonths(d, 1));
  }

  protected goToday(): void {
    this.viewMonth.set(startOfMonth(new Date()));
  }
}
