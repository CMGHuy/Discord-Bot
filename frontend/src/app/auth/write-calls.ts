/**
 * The v207 spec's "SPA inventory" as code: every mutating `ApiClient` method and
 * the gate that keeps a viewer from reaching it. The server is the real boundary
 * (viewers get 403 on writes); this list only proves no write control was
 * forgotten. A new mutating `ApiClient` method fails `write-calls.spec.ts` until
 * it gets a row here.
 *
 * - `public` — sign-in/out; every principal may call it.
 * - `admin-route` — called only from System (route-guarded by `adminGuard`) and its stores.
 * - `if-admin` — its control renders inside `*ifAdmin`.
 * - `hidden-tab` — its only UI is the Analytics Tuning tab, which viewers never see.
 * - `store-no-save` — the store skips the call for viewers.
 */
export type WriteGate = 'public' | 'admin-route' | 'if-admin' | 'hidden-tab' | 'store-no-save';

export const WRITE_CALLS: Readonly<Record<string, WriteGate>> = {
  login: 'public',                 // session.store
  logout: 'public',                // session.store
  refreshMarket: 'if-admin',       // <sb-market-refresh>; live-values.store
  closeTrade: 'if-admin',          // trade-actions.ts <- trades.ts rows, trade-detail.ts, dashboard row-actions
  cancelTrade: 'if-admin',         // same callers as closeTrade
  deleteTrade: 'if-admin',         // same callers as closeTrade
  closeOpenTrades: 'if-admin',     // dashboard.ts header menu, data-action="close-all"
  clearOpenTrades: 'if-admin',     // trades.ts data-action="clear-open" (trades.store)
  clearTradeHistory: 'if-admin',   // trades.ts data-action="clear-history" (trades.store)
  setTradeNote: 'if-admin',        // trade-detail.ts #trade-note (read-only text for viewers)
  startTuneJob: 'hidden-tab',      // analytics.store <- Tuning tab
  createProposal: 'hidden-tab',    // analytics.store <- Tuning tab
  deleteProposal: 'hidden-tab',    // analytics.store <- Tuning tab
  addTickers: 'if-admin',          // watchlist.ts add box
  removeTicker: 'if-admin',        // watchlist.ts remove + confirm
  setKillswitch: 'if-admin',       // risk.ts .kill-actions Engage / Release
  previewSettings: 'admin-route',  // system.store <- settings tab
  saveSettings: 'admin-route',     // system.store <- settings tab
  importSettings: 'admin-route',   // system.store <- settings tab
  clearLogs: 'admin-route',        // system.store <- system.ts
  triggerScan: 'admin-route',      // system.store <- scan-tab.ts
  stopScan: 'admin-route',         // system.store <- scan-tab.ts
  pauseScan: 'admin-route',        // system.store <- scan-tab.ts
  resumeScan: 'admin-route',       // system.store <- scan-tab.ts
  restartBot: 'admin-route',       // system.store <- system.ts
  savePreferences: 'store-no-save', // preferences.store (V207-11)
  createUser: 'admin-route',        // users.store <- System -> Users tab (V207-17)
  setUserDisabled: 'admin-route',   // users.store <- System -> Users tab
  resetUserPassword: 'admin-route', // users.store <- System -> Users tab
  deleteUser: 'admin-route',        // users.store <- System -> Users tab
};

export const GATED_CALLERS: Readonly<Partial<Record<WriteGate, readonly string[]>>> = {
  'admin-route': [
    'stores/system.store.ts', 'stores/users.store.ts', 'stores/versions.store.ts',
    'workspaces/system/', 'workspaces/versions/',
  ],
  'hidden-tab': ['stores/analytics.store.ts', 'workspaces/analytics/tabs/tuning.ts'],
  'store-no-save': ['stores/preferences.store.ts'],
};
