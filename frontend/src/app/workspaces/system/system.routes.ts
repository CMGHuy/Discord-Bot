import { inject } from '@angular/core';
import { ActivatedRouteSnapshot, Routes } from '@angular/router';

import { RefreshPredicate, routeData } from '../../routing/route-metadata';
import { resolveRoute } from '../../routing/route-resolver';
import { SystemStore, SystemTab, systemTabFrom } from '../../stores/system.store';

const systemTab = (route: ActivatedRouteSnapshot): SystemTab =>
  systemTabFrom(route.queryParamMap.get('tab'));

/** Scan and Providers both move with every scan (v195 §5.1: scan health and
 *  the provider rows are written per scan), so both refresh on `scan` and
 *  `bot`. Logs has no event and refreshes by its button. */
export const refreshOnSystem: RefreshPredicate = (event, route) => {
  switch (systemTab(route)) {
    case 'settings': return event === 'settings';
    case 'scan':
    case 'providers': return event === 'scan' || event === 'bot';
    default: return false;
  }
};

export const systemRoutes: Routes = [{
  path: '', providers: [SystemStore], runGuardsAndResolvers: 'always',
  data: routeData('System', refreshOnSystem),
  resolve: { ready: resolveRoute((route) => inject(SystemStore).resolveTab(systemTab(route))) },
  loadComponent: () => import('./system').then((m) => m.System),
}];
