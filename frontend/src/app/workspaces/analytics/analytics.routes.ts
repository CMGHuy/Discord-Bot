import { inject } from '@angular/core';
import { ActivatedRouteSnapshot, Routes } from '@angular/router';

import { RefreshPredicate, routeData } from '../../routing/route-metadata';
import { resolveRoute } from '../../routing/route-resolver';
import { AnalyticsStore } from '../../stores/analytics.store';
import { scopeFromParams } from './scope-url';

/** The URL is the whole state of this workspace (spec v94 D2): the tab, the
 *  scope and the unit all come from the query string, so a reload and a
 *  shared link land on exactly the same figures. */
const analyticsState = (route: ActivatedRouteSnapshot) => scopeFromParams(route.queryParamMap);

const refreshOnAnalytics: RefreshPredicate = (event, route) =>
  analyticsState(route).tab === 'tuning' ? event === 'jobs' : event === 'analytics';

export const analyticsRoutes: Routes = [{
  path: '', providers: [AnalyticsStore], runGuardsAndResolvers: 'always',
  data: routeData('Analytics', refreshOnAnalytics),
  resolve: {
    ready: resolveRoute((route) => {
      const store = inject(AnalyticsStore);
      const { tab, scope, unit } = analyticsState(route);
      store.hydrate(scope, unit);          // sets state without firing a request
      return store.resolveTab(tab);
    }),
  },
  loadComponent: () => import('./analytics').then((m) => m.Analytics),
}];
