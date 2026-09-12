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
    title: 'Dashboard',
    data: { subtitle: "What's happening right now" },
    loadChildren: () => import('./workspaces/dashboard/dashboard.routes').then((m) => m.dashboardRoutes),
  },
  {
    path: 'trades',
    canMatch: [authGuard],
    title: 'Trades',
    data: { subtitle: 'Every plan, filled or not' },
    loadChildren: () => import('./workspaces/trades/trades.routes').then((m) => m.tradesRoutes),
  },
  {
    // Trade Detail has its own route-scoped store and resolver.
    path: 'trades/:id',
    canMatch: [authGuard],
    title: 'Trade detail',
    data: { subtitle: 'One position, end to end' },
    loadChildren: () => import('./workspaces/trades/trade-detail.routes').then((m) => m.tradeDetailRoutes),
  },
  {
    path: 'analytics',
    canMatch: [authGuard],
    title: 'Analytics',
    data: { subtitle: 'What already happened, measured' },
    loadChildren: () => import('./workspaces/analytics/analytics.routes').then((m) => m.analyticsRoutes),
  },
  {
    path: 'calendar',
    canMatch: [authGuard],
    title: 'Calendar',
    data: { subtitle: 'P&L by day' },
    loadChildren: () => import('./workspaces/calendar/calendar.routes').then((m) => m.calendarRoutes),
  },
  {
    path: 'watchlist',
    canMatch: [authGuard],
    title: 'Watchlist',
    data: { subtitle: 'The symbols being scanned' },
    loadChildren: () => import('./workspaces/watchlist/watchlist.routes').then((m) => m.watchlistRoutes),
  },
  {
    path: 'watchlist/:symbol',
    canMatch: [authGuard],
    title: 'Ticker detail',
    data: { subtitle: 'One symbol, in depth' },
    loadChildren: () => import('./workspaces/watchlist/ticker-detail.routes').then((m) => m.tickerDetailRoutes),
  },
  // SR5: the workspace was `/universe` until 2026-08-13. The `:symbol` form
  // is why these are explicit rather than left to the `**` route below —
  // that would send `/universe/AAPL` to the Dashboard and drop the symbol.
  { path: 'universe', pathMatch: 'full', redirectTo: 'watchlist' },
  { path: 'universe/:symbol', redirectTo: 'watchlist/:symbol' },
  {
    path: 'risk',
    canMatch: [authGuard],
    title: 'Risk',
    data: { subtitle: 'Exposure, caps and the killswitch' },
    loadChildren: () => import('./workspaces/risk/risk.routes').then((m) => m.riskRoutes),
  },
  {
    path: 'system',
    canMatch: [authGuard],
    title: 'System',
    data: { subtitle: 'What the bot itself is doing' },
    loadChildren: () => import('./workspaces/system/system.routes').then((m) => m.systemRoutes),
  },
  {
    path: 'versions',
    canMatch: [authGuard],
    title: 'Versions',
    data: { subtitle: "What's deployed, and when it changed" },
    loadChildren: () => import('./workspaces/versions/versions.routes').then((m) => m.versionsRoutes),
  },
  {
    path: 'research', canMatch: [authGuard], title: 'Research',
    data: { subtitle: 'Deeper symbol research, planned' },
    loadChildren: () => import('./workspaces/stubs/research.routes').then((m) => m.researchRoutes),
  },
  {
    path: 'reports', canMatch: [authGuard], title: 'Reports',
    data: { subtitle: 'Scheduled reports and exports, planned' },
    loadChildren: () => import('./workspaces/stubs/reports.routes').then((m) => m.reportsRoutes),
  },
  {
    path: 'ui',
    canMatch: [authGuard],
    title: 'UI gallery',
    data: { subtitle: 'Every primitive, in one place' },
    loadComponent: () => import('./workspaces/gallery/gallery').then((m) => m.Gallery),
  },
  // A typo'd URL lands on the Dashboard rather than a blank outlet. There is
  // no 404 view: with six destinations and no external links into the app,
  // a dedicated not-found page would be a page nobody ever means to reach.
  { path: '**', redirectTo: 'dashboard' },
];
