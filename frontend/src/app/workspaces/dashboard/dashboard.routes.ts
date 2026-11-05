import { Routes } from '@angular/router';

import { onEvents, routeData } from '../../routing/route-metadata';
import { DashboardStore } from '../../stores/dashboard.store';

// v201: no resolver. The store's `onInit` effect is the one initial load and
// `account`/`trades` events refetch it, so opening the page or the trade
// drawer issues exactly one /dashboard.
export const dashboardRoutes: Routes = [{
  path: '',
  providers: [DashboardStore],
  data: routeData('Dashboard', onEvents()),
  loadComponent: () => import('./dashboard').then((m) => m.Dashboard),
}];
