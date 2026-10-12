import { inject } from '@angular/core';
import { Routes } from '@angular/router';

import { onEvents, routeData } from '../../routing/route-metadata';
import { resolveRoute } from '../../routing/route-resolver';
import { ResearchStore, filtersFromParams } from '../../stores/research.store';

/** The filters are the query string (so a filtered view is a link), which
 *  makes every filter change a navigation. The resolver therefore re-applies
 *  the filters each time but fetches only once per visit. No server event
 *  refreshes this page: the ledger and the registry change only on a deploy. */
export const researchRoutes: Routes = [{
  path: '',
  providers: [ResearchStore],
  runGuardsAndResolvers: 'always',
  data: routeData('Research', onEvents()),
  resolve: {
    ready: resolveRoute((route) => {
      const store = inject(ResearchStore);
      store.hydrate(filtersFromParams(route.queryParamMap));
      return store.ensureLoaded();
    }),
  },
  loadComponent: () => import('./research').then((m) => m.Research),
}];
