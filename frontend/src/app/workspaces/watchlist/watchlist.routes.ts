import { inject } from '@angular/core';
import { Routes } from '@angular/router';
import { onEvents, routeData } from '../../routing/route-metadata';
import { resolveRoute } from '../../routing/route-resolver';
import { WatchlistStore } from '../../stores/watchlist.store';
export const watchlistRoutes: Routes = [{ path: '', providers: [WatchlistStore], runGuardsAndResolvers: 'always', data: routeData('Watchlist', onEvents('watchlist')), resolve: { ready: resolveRoute(() => inject(WatchlistStore).resolve()) }, loadComponent: () => import('./watchlist').then((m) => m.Watchlist) }];