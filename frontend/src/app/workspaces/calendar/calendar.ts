import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';
import { RouterLink } from '@angular/router';

import { CalendarDay, CalendarTrade, CalendarWeekday } from '../../api/models';
import { CalendarMetric, CalendarStore } from '../../stores/calendar.store';
import { ConnectionStore } from '../../stores/connection.store';
import { asyncInputs, Async } from '../../ui/async';
import { Button } from '../../ui/button';
import { Hint } from '../../ui/hint';
import { Viewport, ViewportService } from '../../ui/breakpoints';
import { ABSENT, dateTime, money, rMultiple } from '../../ui/format';
import { ControlRow, Drawer, Panel } from '../../ui/layout';
import { isInline } from '../../ui/priority';
import { Select } from '../../ui/form-controls';
import { Page } from '../../ui/page';
import { MIN_SAMPLE_N, PERFORMANCE_CAVEAT, StatTile, StatTone } from '../../ui/stat-tile';
import { StatStrip } from '../../ui/stat-strip';
import { cellValue, GridCell, localIsoDate, monthLabel, monthMatrix } from './calendar.helpers';
import { fxMissingText } from '../analytics/scope-bar';
import { PAPER_CAPTION, legsSampleNote } from './day/day-copy';
import { LEG_HINT_TEXT, legLabel } from '../trades/leg-label';

/** Monday-first, matching `monthMatrix` and the API's weekday breakdown. */
const WEEKDAY_HEADS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

/** Metrics whose sign means up or down; a count or a rate never does. */
const SIGNED_METRICS: ReadonlySet<CalendarMetric> = new Set<CalendarMetric>(['r', 'currency']);

@Component({
  selector: 'sb-calendar',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Button, ControlRow, Drawer, Hint, Panel, Page, RouterLink, Select, StatStrip, StatTile, Async],
  // v54 D1: "how am I doing this month?" -- hero totals, room to breathe --
  // so this workspace defaults to the presentation register. On the host
  // (a static class, not a template wrapper) because :host IS the grid
  // container the register's variables need to reach.
  host: { class: 'register-presentation' },
  // Provided on the component: created on entry, destroyed on exit, so the
  // workspace cannot hold a stale month while you are looking elsewhere.
  template: `
    <!-- v195 Phase 4: the route title is the page's one h1. -->
    <sb-page>
      <!-- The store's error, at the header's right. Kept unconditional:
           "By weekday (all history)" below stays outside the sb-async wrap --
           it answers a different, all-time question that a THIS MONTH empty
           state must not gate -- and has no error surface of its own, so
           this remains its only one. Duplicates the wrapped panel's own
           error/stale display on a first-load failure; accepted the same way
           Risk does. -->
      <div page-actions class="head-status">
        @if (store.error(); as message) {
          <span class="stale" role="status">{{ message }}</span>
        }
      </div>

      <!-- v195 §5.2: the scope bar holds the month and the filters only. -->
      <sb-control-row page-scope>
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

      <!-- v195 §5.2: the month's totals are the KPI strip. Shown exactly when
           the sb-async below shows its content (showTotals): not while the
           first load runs, not on a first-load error, not on a measured-zero
           month, so no invented totals ever sit beside the empty state. -->
      <div page-kpis class="month-kpis">
        @if (showTotals()) {
        <!-- v95 C5: filters plus these eight tiles pushed the month grid --
             the reason this page exists -- past 1,400px at 390px, four of
             them dimmed "thin sample" and repeating "N=<n> thin sample" four
             times over. Below md the panel collapses to calendarDigest(), one
             line standing in for all eight; a thin sample force-expands it
             instead (Guard 2) rather than hiding the warning behind a
             settled-looking digest. -->
        <sb-panel inlineFrom="md" [digest]="calendarDigest()" [problem]="calendarProblem()">
          <!-- Eight summary figures in reading order; four columns on desktop
               and tablet, two on phone, with content-sized rows. -->
          <sb-stat-strip class="totals" [cols]="4" [colsMd]="4">
            <sb-stat-tile label="Net this month" [value]="totalLabel()" [tone]="totalsTone()"
                          [sample]="monthTrades()" [about]="netAbout" />
            <sb-stat-tile label="Trades" [value]="tradesLabel()" />
            <sb-stat-tile label="Win rate" [value]="monthWinRate()" [sample]="monthTrades()" [about]="winRateAbout" />
            <sb-stat-tile label="Winning days" [value]="winningDaysLabel()" [sample]="monthDays().length" tone="pos" />
            <sb-stat-tile label="Average day" [value]="averageDay()" [sample]="monthDays().length" />
            <sb-stat-tile label="Best day" [value]="monthExtreme('best')" [sample]="monthDays().length" tone="pos" />
            <sb-stat-tile label="Worst day" [value]="monthExtreme('worst')" [sample]="monthDays().length" tone="neg" />
            <!-- The trade held longest among this month's closes: the duration,
                 its ticker beneath. A plain tile like its neighbours. -->
            <sb-stat-tile class="longest-hold" label="Longest holding time"
                          [value]="longestHoldValue()" [hint]="store.longestHold()?.ticker ?? undefined" />
          </sb-stat-strip>
        </sb-panel>
        @if (monthFxMissing() > 0) {
          <p class="fx-caveat" role="note">{{ fxText(monthFxMissing()) }}</p>
        }
        }
      </div>

      <sb-async
        page-primary
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

      <!-- The day-detail pane that used to sit beside this grid duplicated
           the drawer below word for word (same store signals, same fields)
           and, unselected, only ever said "Select a day to inspect its
           trades" -- a permanent half-empty box for what the drawer already
           covers the moment a day is actually clicked. Removed rather than
           kept in sync twice. -->
      <sb-panel [flush]="true" class="calendar-panel">
        @if (showGrid()) {
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
                    <!-- Any in-month trading day is clickable, whether or not
                         it has a day record -- a day with zero closed trades
                         shows "0", not a blank cell (2026-09-14); the drawer's
                         own empty state already reads correctly for it. -->
                    @if (cell.inMonth && !cell.weekend && cell.date <= today) {
                      <button sb-button variant="link" type="button" class="value"
                              [attr.aria-pressed]="store.selectedDay() === cell.date"
                              (click)="store.selectDay(cell.date)">
                        {{ display(dayFor(cell)) }}
                        <span class="n">{{ dayFor(cell)?.trade_count ?? 0 }}</span>
                      </button>
                    }
                  </div>
                }
              </div>
            }
          </div>
        } @else {
          <!-- v95 C6, after earnings-calendar.ts:180 (its own documented
               720px exception; this file is not exempt, so the floor is
               declared sm rather than mirrored at 720). Seven columns at
               390px gave ~44px per day for a currency figure and a count
               with no separator -- "+71" and "10" ran together as one
               number. An agenda drops empty days, which on a swing book is
               most of them, and gives each traded day a readable row. -->
          <ul class="agenda">
            @for (day of monthDays(); track day.date) {
              <li class="agenda-day" [class.selected]="store.selectedDay() === day.date">
                <!-- The whole row is the touch target (opens the same drawer
                     as a grid cell); a bare span row left phones with no way
                     to see a day's trades. -->
                <button type="button" sb-button variant="ghost" class="agenda-hit"
                        [attr.aria-pressed]="store.selectedDay() === day.date"
                        (click)="store.selectDay(day.date)">
                  <span class="agenda-date">{{ day.date }}</span>
                  <span class="agenda-value"
                        [class.pos]="store.signedIntensity(day) > 0"
                        [class.neg]="store.signedIntensity(day) < 0"
                  >{{ display(day) }}</span>
                  <span class="agenda-count">{{ day.trade_count }} trades</span>
                </button>
              </li>
            } @empty {
              <li class="agenda-day"><span class="agenda-date">No trading days this month.</span></li>
            }
          </ul>
        }
      </sb-panel>
      </sb-async>

    <!-- All-time, not this-month: deliberately outside the sb-async above
         so a THIS MONTH empty state cannot hide it (see the head-status
         comment). Degrades safely via weekdays()'s own [] default before
         the first load. -->
      <sb-panel page-secondary class="weekday-panel" heading="By weekday (all history)" [divided]="true">
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
      @if (store.selectedDay(); as day) {
        <!-- v165 D6: the drawer is the quick preview; the page is the full day. -->
        <a class="open-day" [routerLink]="['/calendar', day]" [queryParams]="dayLinkParams()">Open full day →</a>
      }
      @if (store.dayLoading()) {
        <p class="day-loading">Loading...</p>
      } @else if (store.dayDetail() === null) {
        <p class="day-empty">No closed trades on this day under the current filter.</p>
      } @else if (store.dayDetail()!.trades.length === 0) {
        <p class="day-empty">No closed trades on this day under the current filter.</p>
      } @else if (store.dayDetail(); as detail) {
        <p class="day-caption">{{ paperCaption }}</p>
        @if ((detail.fx_missing_count ?? 0) > 0) {
          <p class="fx-caveat" role="note">{{ fxText(detail.fx_missing_count!) }}</p>
        }
        <div class="day-summary">
          <sb-stat-tile label="Total" [value]="rLabel(detail.total_r)" [sample]="detail.trade_count" />
          <sb-stat-tile label="Total P&L" [value]="ccyLabel(detail.total_ccy)" [sample]="detail.trade_count" [tone]="toneOf(detail.total_ccy)" />
          <sb-stat-tile label="Win rate" [value]="winRateLabel(detail.win_rate)" [sample]="detail.trade_count" />
          <sb-stat-tile label="Winners" [value]="detail.winners.toString()" [sample]="detail.trade_count" tone="pos" />
          <sb-stat-tile label="Losers" [value]="detail.losers.toString()" [sample]="detail.trade_count" tone="neg" />
          <sb-stat-tile label="Average trade" [value]="rLabel(detail.avg_trade_r)" [sample]="detail.trade_count" />
          <sb-stat-tile label="Worst drawdown" [value]="rLabel(detail.worst_drawdown_r)" [sample]="detail.trade_count" tone="neg" />
        </div>
        @if (hasLegs(detail.trades)) {
          <p class="day-sample-note">{{ legsNote(detail.trade_count) }}</p>
        }
        <div class="day-leaders">
          <section class="contributors">
            <h3>Contributors</h3>
            @if (detail.contributors.length) {
              @for (row of detail.contributors; track $index) {
                <p class="leader pos"><span class="who">{{ row.ticker }}</span><span class="amt">{{ leaderLabel(row) }}</span></p>
              }
            } @else { <p>Nothing gained today.</p> }
          </section>
          <section class="detractors">
            <h3>Detractors</h3>
            @if (detail.detractors.length) {
              @for (row of detail.detractors; track $index) {
                <p class="leader neg"><span class="who">{{ row.ticker }}</span><span class="amt">{{ leaderLabel(row) }}</span></p>
              }
            } @else { <p>Nothing lost money today.</p> }
          </section>
        </div>
        @for (trade of detail.trades; track trade.trade_id + ':' + trade.leg_index) {
          <article class="day-row">
            <header>
              <strong>{{ trade.ticker }}</strong>
              <a class="trade-id" [routerLink]="['/trades', trade.plan_id ?? trade.trade_id]"
                 (click)="store.closeDay()">{{ shortTradeId(trade) }}</a>
              <span class="meta">{{ trade.strategy }} · {{ trade.horizon }}</span>
              <span class="amount" [class.pos]="(trade.pnl_amount ?? 0) >= 0"
                    [class.neg]="(trade.pnl_amount ?? 0) < 0">
                {{ tradeValue(trade) }}
              </span>
            </header>
            <p class="meta">Opened {{ dateTime(trade.opened_at) }} · Closed {{ dateTime(trade.closed_at) }}</p>
            <p class="meta">
              @if (legLabel(trade); as leg) {
                <span class="leg">{{ leg }}</span> <sb-hint [text]="legHint" label="About leg rows" /> ·
              }
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
    </sb-page>
  `,
  styles: `
    /* No backticks in here: these styles live in a TS template literal. */
    /* v195 Phase 4: sb-page owns the page rhythm. */
    :host { display: block; min-width: 0; }
    .head-status { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-8); }
    /* All-time, so it reads across the whole width beside nothing. */
    .weekday-panel { grid-column: 1 / -1; }

    /* The month stepper: two buttons with the month between them. Centred
       rather than bottom-aligned like the controls around it, because the
       month is running text and sb-control-row's answer is for controls. */
    .months { display: flex; align-items: center; gap: var(--space-8); }
    .month { min-width: 10ch; font-weight: 600; }

    .metric { display: inline-flex; border: 1px solid var(--border); border-radius: var(--control-radius); }
    /* padding/border override the segment variant's defaults for a
       tighter two-cell toggle; the variant owns colour, weight and the
       active-cell background is our own since this pair has no divider. */
    .metric button {
      min-width: var(--hit-min);
      padding: 0 var(--space-10);
      border: 0;
    }
    .metric button.active { background: var(--surface-raised); color: var(--text); }

    /* Exactly 4 columns, 2 below sm -- on request (2026-09-14, "at most 2
       rows"): eight tiles at four per row is two rows. v186 D3: the totals
       are one sb-stat-strip (cols 4, colsMd 4), so the strip owns those
       columns and splits the tiles with hairlines instead of framing each;
       no fixed row height and no reaching into the tiles (v179 §3.3). */

    /* The calendar table's own panel, not .totals -- on request. A plain
       class selector on the host tag works regardless of whatever sb-async
       wraps its projected content in, unlike a sibling combinator would.
       sb-page's slot gap now separates it from the strip above. */
    sb-panel.calendar-panel { display: block; }

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
    .trade-id { font-family: var(--font-mono, monospace); font-size: var(--text-caption, 12px); margin-left: var(--space-6); }
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

    /* v95 C6 -- the phone agenda, replacing the 7-column grid below sm. */
    .agenda { list-style: none; margin: 0; padding: 0; }
    .agenda-day { border-bottom: 1px solid var(--border); }
    .agenda-day.selected { outline: 2px solid var(--accent); outline-offset: -2px; }
    /* sb-button ghost supplies the paint and hover; display, alignment,
       padding, border, ink and font are overridden back so the whole row stays
       one full-width touch target (the .value link above does the same). */
    .agenda-hit {
      display: flex; align-items: baseline; justify-content: flex-start;
      gap: var(--space-10);
      width: 100%; min-height: 44px; padding: var(--space-6) var(--space-10);
      border: 0; border-radius: 0; background: transparent; color: inherit; font: inherit;
      text-align: left; cursor: pointer;
    }
    .agenda-hit:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
    .agenda-date { flex: 0 0 6rem; color: var(--text-faint); font-size: var(--text-micro); }
    .agenda-value { flex: 1 1 auto; text-align: right; font-family: var(--font-mono); color: var(--text); }
    .agenda-value.pos { color: var(--pos); }
    .agenda-value.neg { color: var(--neg); }
    .agenda-count { flex: 0 0 auto; color: var(--text-faint); font-size: var(--text-chip); }

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
      border-radius: var(--chip-radius);
      color: var(--text-secondary);
      font-size: var(--text-micro);
    }
    .day-empty, .day-loading { margin: 0; color: var(--text-secondary); font-size: var(--text-table); }
    .day-summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: var(--space-8); margin-bottom: var(--space-14); }
    .open-day { display: inline-flex; align-items: center; min-height: 44px; margin-bottom: var(--space-10); color: var(--accent); font-weight: 600; text-decoration: none; }
    .open-day:hover, .open-day:focus-visible { text-decoration: underline; }
    .day-caption, .day-sample-note { margin: 0 0 var(--space-8); color: var(--text-secondary); font-size: var(--text-micro); }
    .fx-caveat { margin: 0 0 var(--space-8); color: var(--warn); font-size: var(--text-micro); overflow-wrap: anywhere; }
    .day-leaders { display: grid; grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr)); gap: var(--space-14); margin-bottom: var(--space-14); }
    .day-leaders h3 { margin: 0 0 var(--space-6); font-size: var(--text-micro); text-transform: uppercase; letter-spacing: 0.08em; }
    .day-leaders .leader { display: flex; justify-content: space-between; gap: var(--space-8); white-space: nowrap; }
    .day-leaders .leader.pos { color: var(--pos); }
    .day-leaders .leader.neg { color: var(--neg); }
    .day-leaders p { margin: var(--space-4) 0; color: var(--text-secondary); font-family: var(--font-mono); font-size: var(--text-table); }
  `,
})
export class Calendar {
  readonly store = inject(CalendarStore);
  private readonly connection = inject(ConnectionStore);
  private readonly viewportService = inject(ViewportService);

  /** Test override — jsdom resolves no media query. */
  readonly viewportAt = input<Viewport | null>(null);
  protected readonly viewport = computed<Viewport>(
    () => this.viewportAt() ?? this.viewportService.viewport(),
  );
  /** Below sm the 7-column grid becomes a phone agenda -- v95 C6. A plain
   *  computed rather than calling `isInline` from the template: Angular
   *  resolves a bare template identifier as an instance member, not a
   *  module import. */
  protected readonly showGrid = computed(() => isInline('sm', this.viewport()));

  protected readonly weekdayHeads = WEEKDAY_HEADS;
  protected readonly today = localIsoDate(new Date());
  /** v194 B3 -- the one leg name (shared with Trades and the Dashboard). */
  protected readonly legLabel = legLabel;
  /** v194 A4: the calendar counts each realised leg (`pnl_calendar` rows). */
  protected readonly legHint = LEG_HINT_TEXT + ' On this page win rate and N count each realised leg as its own trade; Analytics counts plans.';

  protected readonly async = computed(() =>
    asyncInputs(this.store, { isEmpty: (data) => data.totals.trade_count === 0 }),
  );

  /** v195 §5.2: the KPI strip sits outside the sb-async, so it carries the
   *  same gate the sb-async applies to its content: no totals while the
   *  first load runs, on a first-load error or for a measured-zero month. A
   *  refetch failure over loaded data keeps them (asyncInputs: error null). */
  protected readonly showTotals = computed(() => {
    const state = this.async();
    return !state.loading && state.error === null && !state.empty;
  });

  /** The month's closed trades: the N behind Net this month and Win rate. */
  protected readonly monthTrades = computed(() => this.store.totals()?.trade_count ?? null);

  /** v195 §5.2: every performance KPI states its basis (v194's caveat). */
  protected readonly netAbout = `The month's closed trades, summed in the metric on show. ${PERFORMANCE_CAVEAT}`;
  protected readonly winRateAbout = `Share of the month's closed trades that won. ${PERFORMANCE_CAVEAT}`;

  /** The account's own symbol, never a literal `$` -- see `MetricCard`'s
   *  note. An admin running a euro account must not read euro figures
   *  labelled in dollars. */
  protected readonly currency = computed(() => this.connection.currency());
  /** v194 B7: the month's closes the money figures left out (no exchange
   *  rate for the exit date), and the caveat copy shared with Analytics. */
  protected readonly monthFxMissing = computed(() => this.store.data()?.fx_missing_count ?? 0);
  protected readonly fxText = fxMissingText;

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

  /** Net this month's tone (v179): by sign for R and money; neutral for a
   *  trade count or a win rate -- the old metric card's `pnl` tone used to paint
   *  a 33% win rate green -- and neutral while loading, so a pending strip
   *  is not briefly coloured. */
  protected readonly totalsTone = computed<StatTone>(() => {
    const value = this.totalValue();
    if (value === null || value === undefined || value === 0) return 'neutral';
    if (!SIGNED_METRICS.has(this.store.metric())) return 'neutral';
    return value > 0 ? 'pos' : 'neg';
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

  /** The cell's number, formatted for the metric on show. "0" for a day
   *  with no day record at all (never reached the API's `days` array), the
   *  same reading `cellValue` already gives a day record with
   *  `trade_count: 0` -- both mean "nothing closed here", not "no data". */
  protected display(day: CalendarDay | null): string {
    if (!day) return '0';
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

  /** "Net this month" as text in the metric on show. sb-stat-tile never
   *  formats a number (stat-tile.ts), so the unit travels in the string --
   *  what the old metric card's [unit] and [decimals] did before v179. */
  protected totalLabel(): string {
    const value = this.totalValue();
    return value === null || value === undefined ? ABSENT : this.metricText(value);
  }

  protected tradesLabel(): string {
    const count = this.store.totals()?.trade_count;
    return count === null || count === undefined ? ABSENT : String(count);
  }

  /** One decimal, as the Win rate card showed it ("33.3%"). */
  protected monthWinRate(): string {
    const rate = this.store.totals()?.win_rate;
    return rate === null || rate === undefined ? ABSENT : `${rate.toFixed(1)}%`;
  }

  private metricText(value: number): string {
    switch (this.store.metric()) {
      case 'r': return rMultiple(value);
      case 'currency': return money(value, this.currency(), 2);
      case 'win_rate': return `${value.toFixed(1)}%`;
      case 'trades': return String(value);
    }
  }


  /** Closed-trading days only: calendar blanks are not observations. */
  protected readonly monthDays = computed(() => this.store.days().filter((day) => day.trade_count > 0));

  /** The eight tiles in one line — v95 C5. Net, count, win rate: the three a
   *  trader would read first, in the order they read them. Always in the
   *  account currency and percent, independent of the metric toggle above --
   *  a digest that changed shape with the toggle would be a different
   *  summary each time, not a stand-in for the same one. */
  protected readonly calendarDigest = computed(() => {
    const totals = this.store.totals();
    if (!totals) return ABSENT;
    const winRate = totals.win_rate === null ? ABSENT : `${totals.win_rate.toFixed(1)}%`;
    return `${money(totals.net_pnl_amount, this.currency(), 2)} · `
      + `${totals.trade_count} trades · ${winRate} win`;
  });

  /** Guard 2 (v95 §5). Every `sb-stat-tile` above already carries
   *  `[sample]="monthDays().length"` and dims itself below `MIN_SAMPLE_N`;
   *  collapsing them behind a digest that showed only the headline figures
   *  would present that same thin month as a settled one. */
  protected readonly calendarProblem = computed(() => {
    const n = this.monthDays().length;
    return n < MIN_SAMPLE_N ? `thin sample — N=${n}` : null;
  });

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

  protected readonly dateTime = dateTime;

  /** D7: the drawer's summary says what these figures are. */
  protected readonly paperCaption = PAPER_CAPTION;
  protected readonly legsNote = legsSampleNote;

  /** Only the filters that are set, so a bare day links as `/calendar/<date>`. */
  protected readonly dayLinkParams = computed(() => ({
    ...(this.store.strategy() ? { strategy: this.store.strategy() } : {}),
    ...(this.store.horizon() ? { horizon: this.store.horizon() } : {}),
  }));

  protected hasLegs(trades: CalendarTrade[]): boolean {
    return trades.some((trade) => trade.leg_total > 1);
  }

  /** Same last-six rule as the Trades list's # column, so the id on the
   *  drawer is the id on the row it links to. */
  protected shortTradeId(trade: CalendarTrade): string {
    const id = trade.plan_id ?? trade.trade_id;
    return id.length > 6 ? id.slice(-6) : id;
  }

  protected ccyLabel(value: number | null): string {
    // A no-break space keeps the amount and its currency on one line.
    return value === null ? ABSENT : money(value, this.currency(), 2).replace(' ', ' ');
  }

  protected toneOf(value: number | null): 'neutral' | 'pos' | 'neg' {
    return value === null || value === 0 ? 'neutral' : value > 0 ? 'pos' : 'neg';
  }

  /** "-155.73 €  (-1.2R)": the ticker's net money, then its net R. */
  protected leaderLabel(row: { pnl: number | null; r: number | null }): string {
    const cash = row.pnl === null ? '' : this.ccyLabel(row.pnl);
    const r = row.r === null ? '' : rMultiple(row.r);
    return [cash, r].filter(Boolean).join(' · ');
  }

  /** "12d 4h" for a hold of a day or more, "7h" under one, ABSENT when no
   *  close this month has a measurable hold. */
  protected readonly longestHoldValue = computed(() => {
    const hold = this.store.longestHold();
    if (!hold) return ABSENT;
    const whole = Math.round(hold.held_hours);
    const days = Math.floor(whole / 24);
    return days > 0 ? `${days}d ${whole % 24}h` : `${whole}h`;
  });

  protected winRateLabel(value: number | null): string {
    return value === null ? ABSENT : `${value.toFixed(0)}%`;
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
