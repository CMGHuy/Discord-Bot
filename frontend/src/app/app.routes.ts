import { Routes } from '@angular/router';

import { authGuard } from './shell/auth.guard';

/**
 * Six workspaces, plus the two detail views that hang off them.
 *
 * Every one is `loadComponent`, so a workspace's component and (from Phase
 * 4) its store arrive together and only when visited. That is what makes
 * the bundle grow with usage rather than with the feature list.
 *
 * `canMatch` rather than `canActivate` on the guard: canMatch runs before
 * the loader, so an unauthenticated navigation never downloads the chunk.
 *
 * Trades list state -- filters, sort, page -- belongs in query parameters,
 * not in the store alone (spec v13 Decision 5). A filtered view has to
 * survive a reload and be pasteable, and routing it through the URL makes
 * the store's query slice a projection of something durable rather than a
 * fourth copy of the truth. That lands with the real Trades workspace
 * (NG42); the route shape here is what allows it.
 */
export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'cockpit' },
  {
    path: 'cockpit',
    canMatch: [authGuard],
    loadComponent: () => import('./workspaces/cockpit/cockpit').then((m) => m.Cockpit),
  },
  {
    path: 'trades',
    canMatch: [authGuard],
    loadComponent: () => import('./workspaces/trades/trades').then((m) => m.Trades),
  },
  {
    // Before nothing and after nothing in particular -- Angular matches in
    // order, but 'trades/:id' cannot shadow 'trades' since the latter has no
    // parameter. Kept adjacent so the pair reads as one workspace.
    path: 'trades/:id',
    canMatch: [authGuard],
    loadComponent: () =>
      import('./workspaces/trades/trade-detail').then((m) => m.TradeDetail),
  },
  {
    path: 'analytics',
    canMatch: [authGuard],
    loadComponent: () =>
      import('./workspaces/analytics/analytics').then((m) => m.Analytics),
  },
  {
    path: 'universe',
    canMatch: [authGuard],
    loadComponent: () => import('./workspaces/universe/universe').then((m) => m.Universe),
  },
  {
    path: 'universe/:symbol',
    canMatch: [authGuard],
    loadComponent: () =>
      import('./workspaces/universe/ticker-detail').then((m) => m.TickerDetail),
  },
  {
    path: 'risk',
    canMatch: [authGuard],
    loadComponent: () => import('./workspaces/risk/risk').then((m) => m.Risk),
  },
  {
    path: 'system',
    canMatch: [authGuard],
    loadComponent: () => import('./workspaces/system/system').then((m) => m.System),
  },
  // A typo'd URL lands on the Cockpit rather than a blank outlet. There is
  // no 404 view: with six destinations and no external links into the app,
  // a dedicated not-found page would be a page nobody ever means to reach.
  { path: '**', redirectTo: 'cockpit' },
];
