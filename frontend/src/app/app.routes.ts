import { Routes } from '@angular/router';

import { adminGuard } from './auth/admin.guard';
import { authGuard } from './shell/auth.guard';

/**
 * Six destinations (v202), their section routes, and the detail views that hang off them.
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
  // v202: Trades' sections. Declared BEFORE `trades/:id`, so a section word is
  // never read as a trade id (`/trades/calendar` is not trade "calendar").
  {
    path: 'trades/calendar',
    canMatch: [authGuard],
    title: 'Calendar',
    data: { subtitle: 'P&L by day' },
    loadChildren: () => import('./workspaces/calendar/calendar.routes').then((m) => m.calendarRoutes),
  },
  {
    path: 'trades/cancels',
    canMatch: [authGuard],
    title: 'Cancels',
    data: { subtitle: "Were the bot's own cancels right?" },
    loadChildren: () => import('./workspaces/cancels/cancels.routes').then((m) => m.cancelsRoutes),
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
    // v151: one open plan, reached from a Discord alert's title link. Its
    // own route-scoped stores and resolver, like Trade Detail. spa.py's
    // WORKSPACES lists `plans` so a reload of /plans/<id> serves the SPA.
    path: 'plans/:id',
    canMatch: [authGuard],
    title: 'Plan detail',
    data: { subtitle: 'Why this plan, and how it is going' },
    loadChildren: () => import('./workspaces/plans/plan-detail.routes').then((m) => m.planDetailRoutes),
  },
  // v202: the pre-Phase-1 paths. RELATIVE redirects (no leading slash) keep
  // the query string and fragment, which Analytics' tab state and every old
  // bookmark depend on; an absolute redirect would drop both. These come out
  // at Phase 4's close-out with `cockpit` and `universe`, together with
  // their names in spa.py's WORKSPACES.
  { path: 'calendar', pathMatch: 'full', redirectTo: 'trades/calendar' },
  { path: 'calendar/:date', redirectTo: 'trades/calendar/:date' },
  { path: 'cancels', pathMatch: 'full', redirectTo: 'trades/cancels' },
  { path: 'analytics', pathMatch: 'full', redirectTo: 'insights/analytics' },
  { path: 'research', pathMatch: 'full', redirectTo: 'insights/research' },
  { path: 'reports', pathMatch: 'full', redirectTo: 'insights/reports' },
  { path: 'versions', pathMatch: 'full', redirectTo: 'system/versions' },
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
  // v202: System's Versions section, before `system` so it is matched first.
  {
    path: 'system/versions',
    // v207: System is admin-only; a viewer is sent to the Dashboard.
    canMatch: [authGuard, adminGuard],
    title: 'Versions',
    data: { subtitle: "What's deployed, and when it changed" },
    loadChildren: () => import('./workspaces/versions/versions.routes').then((m) => m.versionsRoutes),
  },
  {
    path: 'system',
    // v207: System is admin-only; a viewer is sent to the Dashboard.
    canMatch: [authGuard, adminGuard],
    title: 'System',
    data: { subtitle: 'What the bot itself is doing' },
    loadChildren: () => import('./workspaces/system/system.routes').then((m) => m.systemRoutes),
  },
  // v202: Insights has no page of its own; it opens on its first section.
  { path: 'insights', pathMatch: 'full', redirectTo: 'insights/analytics' },
  {
    path: 'insights/analytics',
    canMatch: [authGuard],
    title: 'Analytics',
    data: { subtitle: 'What already happened, measured' },
    loadChildren: () => import('./workspaces/analytics/analytics.routes').then((m) => m.analyticsRoutes),
  },
  {
    path: 'insights/research', canMatch: [authGuard], title: 'Research',
    data: { subtitle: 'Every pre-registration and its verdict' },
    loadChildren: () => import('./workspaces/research/research.routes').then((m) => m.researchRoutes),
  },
  {
    path: 'insights/reports', canMatch: [authGuard], title: 'Reports',
    data: { subtitle: 'What the measurements say about entries and gates' },
    loadChildren: () => import('./workspaces/reports/reports.routes').then((m) => m.reportsRoutes),
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
