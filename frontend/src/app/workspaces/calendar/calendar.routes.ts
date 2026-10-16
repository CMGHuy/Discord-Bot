import { inject } from '@angular/core';
import { ActivatedRouteSnapshot, Router, Routes } from '@angular/router';
import { map, of } from 'rxjs';

import { onEvents, routeData } from '../../routing/route-metadata';
import { resolveRoute } from '../../routing/route-resolver';
import { CalendarDayStore } from '../../stores/calendar-day.store';
import { CalendarStore, CalendarUrlParams } from '../../stores/calendar.store';

const listParams = (route: ActivatedRouteSnapshot): CalendarUrlParams => ({
  month: route.queryParamMap.get('month'),
  strategy: route.queryParamMap.get('strategy'),
  horizon: route.queryParamMap.get('horizon'),
});

/** The same-URL reload RouteRefreshService makes after a `trades` event. */
const isBackgroundRefresh = (): boolean => {
  const info = inject(Router).currentNavigation()?.extras.info as { backgroundRefresh?: boolean } | undefined;
  return info?.backgroundRefresh === true;
};

export const calendarRoutes: Routes = [
  {
    path: '',
    pathMatch: 'full',
    providers: [CalendarStore],
    runGuardsAndResolvers: 'always',
    data: routeData('Calendar', onEvents('trades')),
    // v165 D6, store-driven: the store reads the URL once here and writes
    // every change back itself (replaceUrl) after making the one request for
    // it. That write is a navigation and this route runs its resolver
    // 'always', so URL == state with data loaded is a no-op -- one request
    // per filter change. A first visit, a hand-edited URL, back/forward and
    // a background refresh still load.
    resolve: {
      ready: resolveRoute((route) => {
        const store = inject(CalendarStore);
        const params = listParams(route);
        if (store.data() !== null && store.matchesUrl(params) && !isBackgroundRefresh()) {
          return of(undefined);
        }
        store.applyUrl(params);
        return store.resolve();
      }),
    },
    loadComponent: () => import('./calendar').then((m) => m.Calendar),
  },
  {
    // v165 D5: one day as a page. `:date` and the strategy/horizon query
    // params are the whole state; a malformed date resolves to the empty
    // state without a request (CalendarDayStore.setRoute).
    path: ':date',
    providers: [CalendarDayStore],
    runGuardsAndResolvers: 'always',
    data: routeData('Calendar day', onEvents('trades')),
    resolve: {
      ready: resolveRoute((route) => {
        const store = inject(CalendarDayStore);
        store.setRoute(
          route.paramMap.get('date'),
          route.queryParamMap.get('strategy'),
          route.queryParamMap.get('horizon'),
        );
        return store.resolve().pipe(map(() => undefined));
      }),
    },
    loadComponent: () => import('./day/calendar-day').then((m) => m.CalendarDayPage),
  },
];
