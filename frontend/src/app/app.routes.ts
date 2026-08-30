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
  { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
  // SR4: the workspace was `/cockpit` until 2026-08-13. The `**` route below
  // would already send a bare `/cockpit` here, but only by treating it as a
  // typo — this says it is a rename, and it is the pair to `spa.py` keeping
  // `cockpit` in WORKSPACES so the server serves index.html for it at all.
  // Both come out at NG57.
  { path: 'cockpit', pathMatch: 'full', redirectTo: 'dashboard' },
  {
    path: 'dashboard',
    canMatch: [authGuard],
    loadChildren: () => import('./workspaces/dashboard/dashboard.routes').then((m) => m.dashboardRoutes),
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
    path: 'calendar',
    canMatch: [authGuard],
    loadChildren: () => import('./workspaces/calendar/calendar.routes').then((m) => m.calendarRoutes),
  },
  {
    path: 'watchlist',
    canMatch: [authGuard],
    loadChildren: () => import('./workspaces/watchlist/watchlist.routes').then((m) => m.watchlistRoutes),
  },
  {
    path: 'watchlist/:symbol',
    canMatch: [authGuard],
    loadComponent: () =>
      import('./workspaces/watchlist/ticker-detail').then((m) => m.TickerDetail),
  },
  // SR5: the workspace was `/universe` until 2026-08-13. The `:symbol` form
  // is why these are explicit rather than left to the `**` route below —
  // that would send `/universe/AAPL` to the Dashboard and drop the symbol.
  { path: 'universe', pathMatch: 'full', redirectTo: 'watchlist' },
  { path: 'universe/:symbol', redirectTo: 'watchlist/:symbol' },
  {
    path: 'risk',
    canMatch: [authGuard],
    loadChildren: () => import('./workspaces/risk/risk.routes').then((m) => m.riskRoutes),
  },
  {
    path: 'system',
    canMatch: [authGuard],
    loadComponent: () => import('./workspaces/system/system').then((m) => m.System),
  },
  {
    path: 'versions',
    canMatch: [authGuard],
    loadChildren: () => import('./workspaces/versions/versions.routes').then((m) => m.versionsRoutes),
  },
  {
    path: 'ui',
    canMatch: [authGuard],
    title: 'UI gallery',
    loadComponent: () => import('./workspaces/gallery/gallery').then((m) => m.Gallery),
  },
  // A typo'd URL lands on the Dashboard rather than a blank outlet. There is
  // no 404 view: with six destinations and no external links into the app,
  // a dedicated not-found page would be a page nobody ever means to reach.
  { path: '**', redirectTo: 'dashboard' },
];
