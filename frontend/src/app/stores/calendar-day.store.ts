import { computed, inject } from '@angular/core';
import { patchState, signalStore, withComputed, withMethods, withState } from '@ngrx/signals';
import { Observable, catchError, forkJoin, of, tap, throwError } from 'rxjs';

import { ApiClient } from '../api/api-client';
import { ApiError } from '../api/api-error';
import {
  CalendarDaySparklines,
  CalendarDayTrades,
  CalendarTrade,
  PnlCalendar,
} from '../api/models';
import { routeRequest } from '../routing/route-request';
import {
  MonthContext,
  adjacentTradingDay,
  isIsoDate,
  monthContext,
  monthOf,
} from '../workspaces/calendar/day/month-context';
import { shiftMonth } from './calendar.store';

/* v165 D5 -- the calendar day page's data. Provided by the `calendar/:date`
 * route, never at root: each visit owns its day. */

export type DaySort = 'pnl' | 'r' | 'closed' | 'ticker';

/** Descending, nulls last -- a missing figure is never ranked as 0. */
function descNullsLast(a: number | null, b: number | null): number {
  if (a === null || b === null) return a === null ? (b === null ? 0 : 1) : -1;
  return b - a;
}

const COMPARE: Record<DaySort, (a: CalendarTrade, b: CalendarTrade) => number> = {
  pnl: (a, b) => descNullsLast(a.pnl_amount, b.pnl_amount),
  r: (a, b) => descNullsLast(a.r_multiple, b.r_multiple),
  closed: (a, b) => (a.closed_at ?? '').localeCompare(b.closed_at ?? ''),
  ticker: (a, b) => a.ticker.localeCompare(b.ticker),
};

/** Stable (ties keep the server's close order); never mutates `trades`. */
export function sortTrades(trades: CalendarTrade[], sort: DaySort): CalendarTrade[] {
  return [...trades].sort(COMPARE[sort]);
}

interface CalendarDaySlice {
  date: string | null;
  strategy: string;
  horizon: string;
  day: CalendarDayTrades | null;
  month: PnlCalendar | null;
  sparklines: CalendarDaySparklines | null;
  loading: boolean;
  error: string | null;
  /** True for a malformed date or a day with no rows under the filter. */
  empty: boolean;
  /** Nearest trading day beyond this month's grid: the day route's
   *  `prev_day` / `next_day` (v217), or one adjacent-month lookup when the
   *  route did not send the field (older backend) or the day was a 404.
   *  The month grid's own neighbour still wins (`prevDay`/`nextDay`). */
  prevEdge: string | null;
  nextEdge: string | null;
  sort: DaySort;
}

type Filters = { strategy?: string; horizon?: string };

const UNAVAILABLE = 'The admin is not responding -- these figures may be stale.';

const notFoundAsNull = (error: unknown): Observable<null> =>
  error instanceof ApiError && error.status === 404 ? of(null) : throwError(() => error);

export const CalendarDayStore = signalStore(
  withState<CalendarDaySlice>({
    date: null, strategy: '', horizon: '',
    day: null, month: null, sparklines: null,
    loading: false, error: null, empty: false,
    prevEdge: null, nextEdge: null, sort: 'pnl',
  }),
  withComputed(({ date, day, month, sort, prevEdge, nextEdge, strategy, horizon }) => ({
    trades: computed(() => sortTrades(day()?.trades ?? [], sort())),
    monthCtx: computed<MonthContext | null>(() => {
      const current = date();
      const data = month();
      return current && data ? monthContext(data.days, current) : null;
    }),
    prevDay: computed(() => {
      const current = date();
      const data = month();
      return current && data ? adjacentTradingDay(data.days, current, -1) ?? prevEdge() : null;
    }),
    nextDay: computed(() => {
      const current = date();
      const data = month();
      return current && data ? adjacentTradingDay(data.days, current, 1) ?? nextEdge() : null;
    }),
    filterParams: computed<Filters>(() => ({
      ...(strategy() ? { strategy: strategy() } : {}),
      ...(horizon() ? { horizon: horizon() } : {}),
    })),
    hasLegs: computed(() => (day()?.trades ?? []).some((t) => t.leg_total > 1)),
  })),
  withMethods((store, api = inject(ApiClient)) => {
    /** Bumped by every setRoute; each async answer compares the token its
     *  request started under, so a superseded request is dropped silently. */
    let routeToken = 0;
    const filters = (): Filters => ({
      strategy: store.strategy() || undefined,
      horizon: store.horizon() || undefined,
    });

    /** After the day, never blocking it; a late answer for a day the page
     *  has left is dropped. A failure leaves the cards on `—`. */
    const loadSparklines = (date: string, token: number): void => {
      api.calendarPnlDaySparklines({ date, ...filters() }).subscribe({
        next: (sparklines) => {
          if (token === routeToken) patchState(store, { sparklines });
        },
        error: () => undefined,
      });
    };

    /** One lookup of the adjacent month, only when this month has no
     *  trading day on that side of `date`. */
    const loadEdge = (date: string, data: PnlCalendar, step: 1 | -1, token: number): void => {
      if (adjacentTradingDay(data.days, date, step) !== null) return;
      api.calendarPnl({ month: shiftMonth(monthOf(date), step), ...filters() }).subscribe({
        next: (other) => {
          if (token !== routeToken) return;
          const edge = adjacentTradingDay(other.days, date, step);
          patchState(store, step === 1 ? { nextEdge: edge } : { prevEdge: edge });
        },
        error: () => undefined,
      });
    };

    /** v217: one side's neighbour from the day route, decided once both the
     *  day and its month have answered. A field the route did not send
     *  (`undefined`: older backend, or a 404 day with no body) falls back to
     *  one adjacent-month lookup. `null` is a measured "no trading day on
     *  that side" and is never looked up. */
    const landEdge = (
      date: string, day: CalendarDayTrades | null, month: PnlCalendar,
      step: 1 | -1, token: number,
    ): void => {
      const served = step === 1 ? day?.next_day : day?.prev_day;
      if (served === undefined) {
        loadEdge(date, month, step, token);
        return;
      }
      patchState(store, step === 1 ? { nextEdge: served } : { prevEdge: served });
    };

    const resolve = (): Observable<unknown> => {
      const date = store.date();
      const token = routeToken;
      if (date === null) {
        patchState(store, { empty: true, loading: false });
        return of(undefined);
      }
      const day$ = api.calendarPnlDay({ date, ...filters() }).pipe(
        catchError(notFoundAsNull),
        tap((day) => {
          if (token !== routeToken) return;
          patchState(store, { day, empty: day === null });
          if (day) loadSparklines(date, token);
        }),
      );
      const month$ = api.calendarPnl({ month: monthOf(date), ...filters() }).pipe(
        tap((month) => {
          if (token !== routeToken) return;
          patchState(store, { month });
        }),
      );
      // The edges are decided here, once BOTH answered: `forkJoin` has no
      // defined order between its members' taps, and whether the month
      // lookup is needed depends on the day response.
      return routeRequest(forkJoin([day$, month$]), {
        start: () => patchState(store, { loading: true, error: null }),
        next: ([day, month]) => {
          if (token !== routeToken) return;
          patchState(store, { loading: false });
          landEdge(date, day, month, -1, token);
          landEdge(date, day, month, 1, token);
        },
        error: (error) => {
          if (token !== routeToken) return;
          patchState(store, {
            loading: false,
            empty: false,
            error: error.code === 'unavailable' ? UNAVAILABLE : error.message,
          });
        },
      });
    };

    return {
      resolve,

      /** From the route: `:date` and the `strategy`/`horizon` query params. */
      setRoute(date: string | null, strategy: string | null, horizon: string | null): void {
        routeToken += 1;
        const next = isIsoDate(date) ? date : null;
        // A same-URL refresh (RouteRefreshService) keeps what is on screen:
        // stale-while-revalidate. Only a changed date or filter clears.
        if (next === store.date() && (strategy ?? '') === store.strategy()
            && (horizon ?? '') === store.horizon()) return;
        patchState(store, {
          date: next,
          strategy: strategy ?? '',
          horizon: horizon ?? '',
          day: null, month: null, sparklines: null,
          prevEdge: null, nextEdge: null, error: null, empty: false,
        });
      },

      setSort(sort: DaySort): void {
        patchState(store, { sort });
      },
    };
  }),
);
