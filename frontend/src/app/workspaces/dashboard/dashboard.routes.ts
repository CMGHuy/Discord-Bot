import { inject } from '@angular/core';
import { Routes } from '@angular/router';

import { onEvents, routeData } from '../../routing/route-metadata';
import { resolveRoute } from '../../routing/route-resolver';
import { rerunExceptQueryParam } from '../../routing/route-rerun';
import { DashboardStore } from '../../stores/dashboard.store';

export const dashboardRoutes: Routes = [{
  path: '',
  providers: [DashboardStore],
  // v179 §6b.8: 'always', except a change to the trade drawer's own
  // parameter (dashboard.ts TRADE_PARAM) -- opening a trade fetches nothing.
  runGuardsAndResolvers: rerunExceptQueryParam('trade'),
  data: routeData('Dashboard', onEvents()),
  resolve: { ready: resolveRoute(() => inject(DashboardStore).resolve()) },
  loadComponent: () => import('./dashboard').then((m) => m.Dashboard),
}];