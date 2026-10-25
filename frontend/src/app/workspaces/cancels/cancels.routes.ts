import { inject } from '@angular/core';
import { Routes } from '@angular/router';

import { onEvents, routeData } from '../../routing/route-metadata';
import { resolveRoute } from '../../routing/route-resolver';
import { RouteRequestHandlers, routeRequest } from '../../routing/route-request';
import { CancelsStore } from '../../stores/cancels.store';

/** The store records loading, data and error itself; routeRequest only keeps
 *  a non-auth failure from failing the navigation, so the page renders its
 *  error. */
const STORE_OWNS_STATE: RouteRequestHandlers<unknown> = {
  start: () => undefined, next: () => undefined, error: () => undefined,
};

/** No server event refreshes this page. Each visit reloads; the server
 *  memoises the replay until the next plan write or the next UTC hour. */
export const cancelsRoutes: Routes = [{
  path: '',
  runGuardsAndResolvers: 'always',
  data: routeData('Cancels', onEvents()),
  resolve: { ready: resolveRoute(() => routeRequest(inject(CancelsStore).load(), STORE_OWNS_STATE)) },
  loadComponent: () => import('./cancels').then((m) => m.Cancels),
}];
