import { inject } from '@angular/core';
import { ActivatedRouteSnapshot, Routes } from '@angular/router';

import { RefreshPredicate, routeData } from '../../routing/route-metadata';
import { resolveRoute } from '../../routing/route-resolver';
import { AnalyticsStore, AnalyticsTab } from '../../stores/analytics.store';

const analyticsTab = (route: ActivatedRouteSnapshot): AnalyticsTab => {
  const tab = route.queryParamMap.get('tab');
  return tab === 'strategies' || tab === 'calibration' || tab === 'tuning' || tab === 'plans'
    ? tab : 'performance';
};

const refreshOnAnalytics: RefreshPredicate = (event, route) =>
  analyticsTab(route) === 'tuning' ? event === 'jobs' : event === 'analytics';

export const analyticsRoutes: Routes = [{
  path: '', providers: [AnalyticsStore], runGuardsAndResolvers: 'always',
  data: routeData('Analytics', refreshOnAnalytics),
  resolve: { ready: resolveRoute((route) => inject(AnalyticsStore).resolveTab(analyticsTab(route))) },
  loadComponent: () => import('./analytics').then((m) => m.Analytics),
}];