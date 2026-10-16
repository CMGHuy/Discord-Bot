import { inject } from '@angular/core';
import { Routes } from '@angular/router';
import { map } from 'rxjs';

import { onEvents, routeData } from '../../routing/route-metadata';
import { resolveRoute } from '../../routing/route-resolver';
import { CalendarDayStore } from '../../stores/calendar-day.store';
import { CalendarStore } from '../../stores/calendar.store';

export const calendarRoutes: Routes = [
  {
    path: '',
    pathMatch: 'full',
    providers: [CalendarStore],
    runGuardsAndResolvers: 'always',
    data: routeData('Calendar', onEvents('trades')),
    resolve: { ready: resolveRoute(() => inject(CalendarStore).resolve()) },
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
