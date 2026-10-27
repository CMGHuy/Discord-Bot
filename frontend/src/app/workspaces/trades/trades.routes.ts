import { inject } from '@angular/core';
import { ActivatedRouteSnapshot, Routes } from '@angular/router';
import { onEvents, routeData } from '../../routing/route-metadata';
import { resolveRoute } from '../../routing/route-resolver';
import { PreferencesStore } from '../../stores/preferences.store';
import { TradesStore } from '../../stores/trades.store';
import { TradeQuery } from '../../api/models';
import { ViewportService } from '../../ui/breakpoints';
import { PER_PAGE_OPTIONS, perPageForApi, readTablePerPage } from '../../ui/table-prefs';
import { TRADES_TABLE_ID } from './trades.columns';

/** An offered per-page choice spelled in the URL, else null. Digits only:
 *  `Number('')` is 0, which is "All", and an empty `?per_page=` must not ask
 *  for 200 rows. */
function urlPerPage(raw: string | null): number | null {
  if (raw === null || !/^\d+$/.test(raw)) return null;
  const value = Number(raw);
  return (PER_PAGE_OPTIONS as readonly number[]).includes(value) ? value : null;
}

/**
 * The request the resolver sends. `per_page` is the value the component
 * shows: the URL's when it names an offered choice, else `savedPerPage` (the
 * saved choice for this table and device class). Either way `perPageForApi`
 * turns "All" (0) into the API's 200-row cap.
 *
 * v194 B2: this used to read `Number(raw ?? 10) || 10`, which turned "All"
 * into 10 rows under a pager that said "All", and never read the saved
 * choice at all.
 */
export const queryFor = (route: ActivatedRouteSnapshot, savedPerPage: number): TradeQuery => ({
  page: Number(route.queryParamMap.get('page') ?? 1) || 1,
  per_page: perPageForApi(urlPerPage(route.queryParamMap.get('per_page')) ?? savedPerPage),
  sort: route.queryParamMap.get('sort') ?? undefined,
  status: route.queryParamMap.get('status') ?? undefined,
  ticker: route.queryParamMap.get('ticker') ?? undefined,
});

/** The saved per-page choice, read the way `tablePerPage` reads it for the
 *  component. `resolveRoute` resolves preferences before this runs. */
function savedPerPage(): number {
  const preferences = inject(PreferencesStore);
  const viewport = inject(ViewportService);
  return readTablePerPage(preferences.values(), TRADES_TABLE_ID, viewport.isNarrow());
}

export const tradesRoutes: Routes = [{
  path: '',
  providers: [TradesStore],
  runGuardsAndResolvers: 'always',
  data: routeData('Trades', onEvents('trades')),
  resolve: {
    ready: resolveRoute((route) => {
      const store = inject(TradesStore);
      store.setQuery(queryFor(route, savedPerPage()), false);
      return store.resolve();
    }),
  },
  loadComponent: () => import('./trades').then((m) => m.Trades),
}];
