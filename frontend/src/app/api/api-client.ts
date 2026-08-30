import { HttpClient, HttpContext, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { SKIP_ROUTE_REFRESH } from './interceptors';

import {
  AnalyticsCalibration,
  AnalyticsJournal,
  AnalyticsPerformance,
  AnalyticsPlans,
  AnalyticsRegistry,
  AnalyticsSnapshot,
  AnalyticsStrategies,
  BotRestartResult,
  CalendarDayTrades,
  ChartResponse,
  ClearResult,
  Dashboard,
  DashboardScope,
  Collection,
  Health,
  Identity,
  Job,
  JobList,
  JobResult,
  JobStarted,
  KillswitchResult,
  LogClearResult,
  Logs,
  PnlCalendar,
  Preferences,
  Proposal,
  ProposalList,
  Risk,
  ScanCommandResult,
  ScanStatus,
  Settings,
  SettingsImportResult,
  SettingsPreview,
  SettingsSaveResult,
  Ticker,
  TickerAddResult,
  TickerList,
  TickerRemoveResult,
  TickerSuggestions,
  TradeDetail,
  TradeNote,
  TradeQuery,
  TradeRow,
  TradeJournal,
  VersionHistory,
} from './models';

/** The application's only HTTP surface.
 *
 * **Components never inject `HttpClient`, and never inject this.** Stores
 * call `ApiClient`; components read stores. The rule is what keeps refetch
 * logic in one layer -- once a component can fetch, "refetch on this event"
 * ends up implemented three times with three different loading flags.
 *
 * Every method is a thin typed wrapper over one endpoint, with no caching,
 * no merging and no retry. Freshness is the event stream's job (sub-project
 * 2): an event means refetch, and a client that cached would be the thing
 * standing between the event and the new data.
 */
@Injectable({ providedIn: 'root' })
export class ApiClient {
  private readonly http = inject(HttpClient);

  /** Relative, so it works identically behind `ng serve`'s proxy, behind
   *  Flask in the container, and behind any reverse proxy in front. */
  private readonly base = '/api/v1';
  private readonly skipRouteRefresh = { context: new HttpContext().set(SKIP_ROUTE_REFRESH, true) };

  /* -- session --------------------------------------------------------- */

  /** Not auth-guarded server-side: this is the "am I logged in" question the
   *  SPA asks at boot, and a 401 would make it unanswerable. */
  session(): Observable<Identity> {
    return this.http.get<Identity>(`${this.base}/session`);
  }

  login(username: string, password: string): Observable<Identity> {
    return this.http.post<Identity>(`${this.base}/session`, { username, password }, this.skipRouteRefresh);
  }

  logout(): Observable<Identity> {
    return this.http.delete<Identity>(`${this.base}/session`, this.skipRouteRefresh);
  }

  health(): Observable<Health> {
    return this.http.get<Health>(`${this.base}/health`);
  }

  /* -- dashboard --------------------------------------------------------- */

  /** SR58 — the scope is a query parameter, so the server does the date
   *  filtering. A client-side scope over an all-time payload could not
   *  narrow the realised figures at all. */
  dashboard(mode?: DashboardScope): Observable<Dashboard> {
    let params = new HttpParams();
    if (mode) params = params.set('mode', mode);
    return this.http.get<Dashboard>(`${this.base}/dashboard`, { params });
  }

  /* -- trades ---------------------------------------------------------- */

  trades(query: TradeQuery = {}): Observable<Collection<TradeRow>> {
    return this.http.get<Collection<TradeRow>>(`${this.base}/trades`, {
      params: toParams(query),
    });
  }

  trade(id: string): Observable<TradeDetail> {
    return this.http.get<TradeDetail>(`${this.base}/trades/${encodeURIComponent(id)}`);
  }

  closeTrade(id: string): Observable<TradeDetail> {
    return this.http.post<TradeDetail>(
      `${this.base}/trades/${encodeURIComponent(id)}/close`, {},
    );
  }

  cancelTrade(id: string): Observable<TradeDetail> {
    return this.http.post<TradeDetail>(
      `${this.base}/trades/${encodeURIComponent(id)}/cancel`, {},
    );
  }

  deleteTrade(id: string): Observable<void> {
    return this.http.delete<void>(`${this.base}/trades/${encodeURIComponent(id)}`);
  }

  clearOpenTrades(): Observable<ClearResult> {
    return this.http.post<ClearResult>(`${this.base}/trades/clear-open`, {});
  }

  clearTradeHistory(): Observable<ClearResult> {
    return this.http.post<ClearResult>(`${this.base}/trades/clear-history`, {});
  }

  setTradeNote(id: string, note: string): Observable<TradeNote> {
    return this.http.put<TradeNote>(
      `${this.base}/trades/${encodeURIComponent(id)}/note`, { note },
    );
  }

  /** SR55 — one position's excursions, tags and auto-lesson. Never 404s for
   *  an unjournaled trade; it answers `journaled: false`. */
  tradeJournal(tradeId: string): Observable<TradeJournal> {
    return this.http.get<TradeJournal>(
      `${this.base}/trades/${encodeURIComponent(tradeId)}/journal`);
  }

  /** The CSV export URL. Returned rather than fetched: the browser should
   *  download this through a normal navigation so it gets a Save dialog and
   *  the server's filename, which an XHR would throw away.
   *
   *  **Takes no query, deliberately.** It used to pass the current one, and
   *  the endpoint ignored every parameter — so a user who filtered to one
   *  ticker and clicked Export got the whole book, with nothing on screen
   *  saying so (NG54). The endpoint exports the TRADE LOG, which is not the
   *  set this collection shows: the collection joins plans and trades, and a
   *  PENDING plan has no trade to export. `status=PENDING` is not a filter
   *  the export could honour even in principle.
   *
   *  So the link stops promising a filter rather than the endpoint inventing
   *  one. Byte-parity with the Jinja route — which the acceptance gate
   *  checks — is preserved by construction. */
  tradesExportUrl(): string {
    return `${this.base}/trades/export.csv`;
  }

  /* -- analytics ------------------------------------------------------- */

  analyticsSnapshot(): Observable<AnalyticsSnapshot> {
    return this.http.get<AnalyticsSnapshot>(`${this.base}/analytics/snapshot`);
  }

  /**
   * SR54 — the range is a query parameter, for the same reason the Trades
   * filters are: it has to reach the arithmetic. A range applied client-side
   * to an all-time payload would scope the charts and leave every KPI card
   * reading all-time, which is worse than no range control at all.
   *
   * An omitted bound is omitted from the URL rather than sent empty, so the
   * server sees "unbounded" instead of having to treat `''` as unset.
   */
  analyticsPerformance(range?: { from?: string | null; to?: string | null }):
    Observable<AnalyticsPerformance> {
    let params = new HttpParams();
    if (range?.from) params = params.set('from', range.from);
    if (range?.to) params = params.set('to', range.to);
    return this.http.get<AnalyticsPerformance>(
      `${this.base}/analytics/performance`, { params });
  }

  /** SR55 — the trailing-week digest and recurring lessons. */
  analyticsJournal(): Observable<AnalyticsJournal> {
    return this.http.get<AnalyticsJournal>(`${this.base}/analytics/journal`);
  }

  analyticsStrategies(): Observable<AnalyticsStrategies> {
    return this.http.get<AnalyticsStrategies>(`${this.base}/analytics/strategies`);
  }

  analyticsCalibration(): Observable<AnalyticsCalibration> {
    return this.http.get<AnalyticsCalibration>(`${this.base}/analytics/calibration`);
  }

  analyticsRegistry(): Observable<AnalyticsRegistry> {
    return this.http.get<AnalyticsRegistry>(`${this.base}/analytics/registry`);
  }

  analyticsPlans(): Observable<AnalyticsPlans> {
    return this.http.get<AnalyticsPlans>(`${this.base}/analytics/plans`);
  }

  /* -- jobs and tuning proposals ---------------------------------------- */

  jobs(): Observable<JobList> {
    return this.http.get<JobList>(`${this.base}/jobs`);
  }

  job(id: string): Observable<Job> {
    return this.http.get<Job>(`${this.base}/jobs/${encodeURIComponent(id)}`);
  }

  /** A finished tuning job's grid — one row per parameter combination, each
   *  carrying its own `row_index` and whether it cleared the acceptance bar.
   *
   *  Returns an empty grid rather than 404ing while the job is still running,
   *  so the caller distinguishes "not finished" from "failed" by the job's own
   *  state, which it already has (SR51). */
  jobResult(id: string): Observable<JobResult> {
    return this.http.get<JobResult>(
      `${this.base}/jobs/${encodeURIComponent(id)}/result`,
    );
  }

  startTuneJob(args: Record<string, unknown>): Observable<JobStarted> {
    return this.http.post<JobStarted>(`${this.base}/jobs/tune`, args);
  }

  proposals(): Observable<ProposalList> {
    return this.http.get<ProposalList>(`${this.base}/analytics/tuning/proposals`);
  }

  createProposal(body: Record<string, unknown>): Observable<Proposal> {
    return this.http.post<Proposal>(`${this.base}/analytics/tuning/proposals`, body);
  }

  deleteProposal(filename: string): Observable<void> {
    return this.http.delete<void>(
      `${this.base}/analytics/tuning/proposals/${encodeURIComponent(filename)}`,
    );
  }

  /* -- watchlist -------------------------------------------------------- */

  tickers(): Observable<TickerList> {
    return this.http.get<TickerList>(`${this.base}/watchlist/tickers`);
  }

  /** Always a list, single add included: the endpoint absorbs both, and two
   *  client methods over one endpoint is how the two grow different
   *  validation. */
  addTickers(tickers: string[]): Observable<TickerAddResult> {
    return this.http.post<TickerAddResult>(`${this.base}/watchlist/tickers`, { tickers });
  }

  removeTicker(symbol: string): Observable<TickerRemoveResult> {
    return this.http.delete<TickerRemoveResult>(
      `${this.base}/watchlist/tickers/${encodeURIComponent(symbol)}`,
    );
  }

  suggestTickers(q: string): Observable<TickerSuggestions> {
    return this.http.get<TickerSuggestions>(`${this.base}/watchlist/suggest`, {
      params: { q },
    });
  }

  /* -- versions -------------------------------------------------------- */

  /** The ui/bot pairing history behind the Versions workspace. Served from a
   *  committed file, so it is cheap and never touches git at runtime. */
  versionHistory(): Observable<VersionHistory> {
    return this.http.get<VersionHistory>(`${this.base}/versions`);
  }

  /* -- risk ------------------------------------------------------------ */

  risk(): Observable<Risk> {
    return this.http.get<Risk>(`${this.base}/risk`);
  }

  /** Returns the killswitch alone, not the whole risk resource: rebuilding
   *  that server-side means re-clustering open positions, which fetches
   *  daily history per ticker. The `risk` event that follows is what brings
   *  the rest of the page up to date. */
  setKillswitch(on: boolean, reason?: string): Observable<KillswitchResult> {
    return this.http.post<KillswitchResult>(`${this.base}/risk/killswitch`, {
      on,
      reason,
    });
  }

  /* -- system ---------------------------------------------------------- */

  settings(): Observable<Settings> {
    return this.http.get<Settings>(`${this.base}/system/settings`);
  }

  /** Both take the CHANGED fields only, wrapped in `settings` — the server
   *  overlays them on what is on disk before diffing, so a partial body is
   *  the expected shape rather than a shortcut. The wrapper is added here
   *  and not by callers: a body posted bare is a 400 that reads like a
   *  validation error. */
  previewSettings(settings: Record<string, unknown>): Observable<SettingsPreview> {
    return this.http.post<SettingsPreview>(
      `${this.base}/system/settings/preview`,
      { settings }, this.skipRouteRefresh
    );
  }

  /** Returns the diff that was written, NOT the settings document — the
   *  form reloads through `settings()` so it re-reads what is on disk. */
  saveSettings(settings: Record<string, unknown>): Observable<SettingsSaveResult> {
    return this.http.put<SettingsSaveResult>(`${this.base}/system/settings`, { settings }, this.skipRouteRefresh);
  }

  /** A URL, not a request -- same reason as the CSV export. */
  settingsExportUrl(): string {
    return `${this.base}/system/settings/export`;
  }

  importSettings(
    body: FormData | Record<string, unknown>,
  ): Observable<SettingsImportResult> {
    return this.http.post<SettingsImportResult>(
      `${this.base}/system/settings/import`,
      body,
    );
  }

  logs(source?: string, lines?: number): Observable<Logs> {
    return this.http.get<Logs>(`${this.base}/system/logs`, {
      params: toParams({ source, lines }),
    });
  }

  logsRawUrl(source?: string): string {
    const params = toParams({ source }).toString();
    return `${this.base}/system/logs/raw${params ? `?${params}` : ''}`;
  }

  clearLogs(source?: string): Observable<LogClearResult> {
    return this.http.delete<LogClearResult>(`${this.base}/system/logs`, {
      params: toParams({ source }),
    });
  }

  scanStatus(): Observable<ScanStatus> {
    return this.http.get<ScanStatus>(`${this.base}/system/scan`);
  }

  triggerScan(): Observable<ScanCommandResult> {
    return this.http.post<ScanCommandResult>(`${this.base}/system/scan/trigger`, {});
  }

  stopScan(): Observable<ScanCommandResult> {
    return this.http.post<ScanCommandResult>(`${this.base}/system/scan/stop`, {});
  }

  pauseScan(): Observable<ScanCommandResult> {
    return this.http.post<ScanCommandResult>(`${this.base}/system/scan/pause`, {});
  }

  resumeScan(): Observable<ScanCommandResult> {
    return this.http.post<ScanCommandResult>(`${this.base}/system/scan/resume`, {});
  }

  /** 503 `unavailable` when the Docker socket is not mounted. That is not a
   *  failure to restart -- it is a deployment that cannot, which the caller
   *  must tell apart from a restart that went wrong. */
  restartBot(): Observable<BotRestartResult> {
    return this.http.post<BotRestartResult>(`${this.base}/system/bot/restart`, {});
  }

  preferences(): Observable<{ preferences: Preferences }> {
    return this.http.get<{ preferences: Preferences }>(`${this.base}/system/preferences`);
  }

  savePreferences(preferences: Preferences): Observable<{ preferences: Preferences }> {
    return this.http.put<{ preferences: Preferences }>(
      `${this.base}/system/preferences`, { preferences }, this.skipRouteRefresh
    );
  }

  /* -- market ---------------------------------------------------------- */

  /** Everything any chart draws, keyed by TICKER. The plan is an optional
   *  `trade_id` on top: its lines, its working stop and its overlays only
   *  exist relative to a position, but the candles, indicators and volume
   *  profile do not, and requiring a trade for them is what forced a second
   *  endpoint and a second chart component.
   *
   *  `trade_id` and `window` both ride through `toParams` rather than being
   *  baked into the path: an out-of-range window is a 400 the caller must
   *  see, so nothing here clamps or defaults it. */
  chart(ticker: string, params: Record<string, unknown> = {}): Observable<ChartResponse> {
    return this.http.get<ChartResponse>(
      `${this.base}/market/chart/${encodeURIComponent(ticker)}`,
      { params: toParams(params) },
    );
  }

  /** One month of daily P&L, plus the all-history context beside it. */
  calendarPnl(query: {
    month: string;
    strategy?: string;
    horizon?: string;
  }): Observable<PnlCalendar> {
    let params = new HttpParams().set('month', query.month);
    if (query.strategy) params = params.set('strategy', query.strategy);
    if (query.horizon) params = params.set('horizon', query.horizon);
    return this.http.get<PnlCalendar>(`${this.base}/calendar/pnl`, { params });
  }

  /** Every trade closed on one day. 404s for a day with no closes, which
   *  the store surfaces as an empty drawer rather than an error. */
  calendarPnlDay(query: {
    date: string;
    strategy?: string;
    horizon?: string;
  }): Observable<CalendarDayTrades> {
    let params = new HttpParams().set('date', query.date);
    if (query.strategy) params = params.set('strategy', query.strategy);
    if (query.horizon) params = params.set('horizon', query.horizon);
    return this.http.get<CalendarDayTrades>(`${this.base}/calendar/pnl/day`, {
      params,
    });
  }
}

/** Drop undefined/null/empty entries and stringify the rest.
 *
 * Empty values are dropped rather than sent as `?ticker=`, because the API
 * rejects a parameter it does not recognise but treats an empty one as
 * absent -- so sending them would work, and would put a dozen meaningless
 * pairs in every URL and in the log the SPA displays.
 */
// Takes `object` rather than Record<string, unknown>: a declared interface
// like TradeQuery has no index signature, so it is not assignable to a
// Record, and widening the callers instead would mean giving every query
// interface an index signature -- which would then accept any key at all and
// throw away the compile-time check that a filter name is one the API knows.
function toParams(query: object): HttpParams {
  let params = new HttpParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === '') continue;
    params = params.set(key, String(value));
  }
  return params;
}
