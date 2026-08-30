import { inject } from '@angular/core';
import { ActivatedRouteSnapshot, Routes } from '@angular/router';

import { RefreshPredicate, routeData } from '../../routing/route-metadata';
import { resolveRoute } from '../../routing/route-resolver';
import { SystemStore, SystemTab } from '../../stores/system.store';

const systemTab = (route: ActivatedRouteSnapshot): SystemTab => {
  const tab = route.queryParamMap.get('tab');
  return tab === 'logs' || tab === 'scan' ? tab : 'settings';
};

const refreshOnSystem: RefreshPredicate = (event, route) => {
  switch (systemTab(route)) {
    case 'settings': return event === 'settings';
    case 'scan': return event === 'scan' || event === 'bot';
    default: return false;
  }
};

export const systemRoutes: Routes = [{
  path: '', providers: [SystemStore], runGuardsAndResolvers: 'always',
  data: routeData('System', refreshOnSystem),
  resolve: { ready: resolveRoute((route) => inject(SystemStore).resolveTab(systemTab(route))) },
  loadComponent: () => import('./system').then((m) => m.System),
}];