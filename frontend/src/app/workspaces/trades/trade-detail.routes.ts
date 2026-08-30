import { inject } from '@angular/core';
import { Routes } from '@angular/router';
import { onEvents, routeData } from '../../routing/route-metadata';
import { resolveRoute } from '../../routing/route-resolver';
import { ChartStore } from '../../stores/chart.store';
import { TradeDetailStore } from '../../stores/trade-detail.store';
export const tradeDetailRoutes: Routes = [{ path: '', providers: [TradeDetailStore, ChartStore], runGuardsAndResolvers: 'always', data: routeData('Trade', onEvents('trades', 'journal')), resolve: { ready: resolveRoute((route) => { const store = inject(TradeDetailStore); store.setId(route.paramMap.get('id')!, false); return store.resolve(); }) }, loadComponent: () => import('./trade-detail').then((m) => m.TradeDetail) }];