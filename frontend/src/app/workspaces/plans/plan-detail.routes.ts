import { inject } from '@angular/core';
import { Routes } from '@angular/router';
import { onEvents, routeData } from '../../routing/route-metadata';
import { resolveRoute } from '../../routing/route-resolver';
import { ChartStore } from '../../stores/chart.store';
import { TradeDetailStore } from '../../stores/trade-detail.store';

/** Mirrors `trade-detail.routes.ts`: the same route-scoped stores and the same
 *  resolver, because the plan page reads the same `GET /api/v1/trades/:id`
 *  (it already resolves plan ids). Refetches on `trades` and `journal`, so a
 *  plan that closes while the page is open redirects on the next load. */
export const planDetailRoutes: Routes = [{
  path: '',
  providers: [TradeDetailStore, ChartStore],
  runGuardsAndResolvers: 'always',
  data: routeData('Plan', onEvents('trades', 'journal')),
  resolve: {
    ready: resolveRoute((route) => {
      const store = inject(TradeDetailStore);
      store.setId(route.paramMap.get('id')!, false);
      return store.resolve();
    }),
  },
  loadComponent: () => import('./plan-detail').then((m) => m.PlanDetail),
}];
