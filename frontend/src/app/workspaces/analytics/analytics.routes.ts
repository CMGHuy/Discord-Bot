import { inject } from '@angular/core';
import { ActivatedRouteSnapshot, Routes } from '@angular/router';

import { RefreshPredicate, routeData } from '../../routing/route-metadata';
import { resolveRoute } from '../../routing/route-resolver';
import { AnalyticsStore } from '../../stores/analytics.store';
import { scopeFromParams, scopePatchFromParams } from './scope-url';

/** The URL is the whole state of this workspace (spec v94 D2): the tab, the
 *  scope and the unit all come from the query string, so a reload and a
 *  shared link land on exactly the same figures.
 *
 *  Only the fields the URL actually carries, though — see
 *  `scopePatchFromParams`. What it is silent about is answered by the
 *  remembered preference the store seeded itself from. */
const analyticsState = (route: ActivatedRouteSnapshot) => scopePatchFromParams(route.queryParamMap);

/** Which event this workspace listens to depends on the tab and nothing
 *  else, so this reads the tab alone rather than resolving a whole scope
 *  patch it would throw away. */
const refreshOnAnalytics: RefreshPredicate = (event, route) =>
  scopeFromParams(route.queryParamMap).tab === 'tuning' ? event === 'jobs' : event === 'analytics';

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
