import { inject } from '@angular/core';
import { Routes } from '@angular/router';

import { onEvents, routeData } from '../../routing/route-metadata';
import { resolveRoute } from '../../routing/route-resolver';
import { ReportsStore, tabFromParams } from '../../stores/reports.store';

/** `?tab=attribution|gates` picks the report, and each navigation fetches
 *  only that one. No server event refreshes this page: a result changes only
 *  when someone runs a report script on the VM. */
export const reportsRoutes: Routes = [{
  path: '',
  providers: [ReportsStore],
  runGuardsAndResolvers: 'always',
  data: routeData('Reports', onEvents()),
  resolve: {
    ready: resolveRoute((route) =>
      inject(ReportsStore).resolveTab(tabFromParams(route.queryParamMap))),
  },
  loadComponent: () => import('./reports').then((m) => m.Reports),
}];
