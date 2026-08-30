import { inject } from '@angular/core';
import { Routes } from '@angular/router';
import { onEvents, routeData } from '../../routing/route-metadata';
import { resolveRoute } from '../../routing/route-resolver';
import { CalendarStore } from '../../stores/calendar.store';
export const calendarRoutes: Routes = [{ path: '', providers: [CalendarStore], runGuardsAndResolvers: 'always', data: routeData('Calendar', onEvents('trades')), resolve: { ready: resolveRoute(() => inject(CalendarStore).resolve()) }, loadComponent: () => import('./calendar').then((m) => m.Calendar) }];