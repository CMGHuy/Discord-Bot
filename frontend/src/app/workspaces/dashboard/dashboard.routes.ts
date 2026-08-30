import { inject } from '@angular/core';
import { Routes } from '@angular/router';

import { onEvents, routeData } from '../../routing/route-metadata';
import { resolveRoute } from '../../routing/route-resolver';
import { DashboardStore } from '../../stores/dashboard.store';

export const dashboardRoutes: Routes = [{
  path: '',
  providers: [DashboardStore],
  runGuardsAndResolvers: 'always',
  data: routeData('Dashboard', onEvents('account', 'trades')),
  resolve: { ready: resolveRoute(() => inject(DashboardStore).resolve()) },
  loadComponent: () => import('./dashboard').then((m) => m.Dashboard),
}];