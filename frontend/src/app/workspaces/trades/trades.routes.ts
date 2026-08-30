import { inject } from '@angular/core';
import { ActivatedRouteSnapshot, Routes } from '@angular/router';
import { onEvents, routeData } from '../../routing/route-metadata';
import { resolveRoute } from '../../routing/route-resolver';
import { DEFAULT_PER_PAGE, TradesStore } from '../../stores/trades.store';
import { TradeQuery } from '../../api/models';

const queryFor = (route: ActivatedRouteSnapshot): TradeQuery => ({
  page: Number(route.queryParamMap.get('page') ?? 1) || 1,
  per_page: Number(route.queryParamMap.get('per_page') ?? DEFAULT_PER_PAGE) || DEFAULT_PER_PAGE,
  sort: route.queryParamMap.get('sort') ?? undefined,
  status: route.queryParamMap.get('status') ?? undefined,
  ticker: route.queryParamMap.get('ticker') ?? undefined,
});
export const tradesRoutes: Routes = [{ path: '', providers: [TradesStore], runGuardsAndResolvers: 'always', data: routeData('Trades', onEvents('trades')), resolve: { ready: resolveRoute((route) => { const store = inject(TradesStore); store.setQuery(queryFor(route)); return store.resolve(); }) }, loadComponent: () => import('./trades').then((m) => m.Trades) }];