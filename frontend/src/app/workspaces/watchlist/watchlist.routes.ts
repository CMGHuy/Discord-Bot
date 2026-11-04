import { inject } from '@angular/core';
import { Routes } from '@angular/router';
import { onEvents, routeData } from '../../routing/route-metadata';
import { startRoute } from '../../routing/route-resolver';
import { WatchlistStore } from '../../stores/watchlist.store';
export const watchlistRoutes: Routes = [{ path: '', providers: [WatchlistStore], runGuardsAndResolvers: 'always', data: routeData('Watchlist', onEvents('watchlist')), resolve: { ready: startRoute(() => inject(WatchlistStore).resolve()) }, loadComponent: () => import('./watchlist').then((m) => m.Watchlist) }];