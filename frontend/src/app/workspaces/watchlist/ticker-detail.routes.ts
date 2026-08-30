import { inject } from '@angular/core';
import { Routes } from '@angular/router';
import { onEvents, routeData } from '../../routing/route-metadata';
import { resolveRoute } from '../../routing/route-resolver';
import { ChartStore } from '../../stores/chart.store';
import { TradesStore } from '../../stores/trades.store';
import { TICKER_TRADES_CAP } from './ticker-detail';
export const tickerDetailRoutes: Routes = [{ path: '', providers: [TradesStore, ChartStore], runGuardsAndResolvers: 'always', data: routeData('Ticker', onEvents('scan', 'trades', 'watchlist')), resolve: { ready: resolveRoute((route) => { const store = inject(TradesStore); store.setQuery({ ticker: route.paramMap.get('symbol')!, sort: '-opened_at', page: 1, per_page: TICKER_TRADES_CAP }, false); return store.resolve(); }) }, loadComponent: () => import('./ticker-detail').then((m) => m.TickerDetail) }];