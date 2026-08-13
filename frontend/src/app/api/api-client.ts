import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import {
  AnalyticsCalibration,
  AnalyticsPerformance,
  AnalyticsRegistry,
  AnalyticsSnapshot,
  AnalyticsStrategies,
  BotRestartResult,
  OhlcvResponse,
  ClearResult,
  Cockpit,
  Collection,
  Health,
  Identity,
  Job,
  JobList,
  JobStarted,
  KillswitchResult,
  LogClearResult,
  Logs,
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

  /* -- session --------------------------------------------------------- */

  /** Not auth-guarded server-side: this is the "am I logged in" question the
   *  SPA asks at boot, and a 401 would make it unanswerable. */
  session(): Observable<Identity> {
    return this.http.get<Identity>(`${this.base}/session`);
  }

  login(username: string, password: string): Observable<Identity> {
    return this.http.post<Identity>(`${this.base}/session`, { username, password });
  }

  logout(): Observable<Identity> {
    return this.http.delete<Identity>(`${this.base}/session`);
  }

  health(): Observable<Health> {
    return this.http.get<Health>(`${this.base}/health`);
  }

  /* -- cockpit --------------------------------------------------------- */

  cockpit(): Observable<Cockpit> {
    return this.http.get<Cockpit>(`${this.base}/cockpit`);
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

  analyticsPerformance(): Observable<AnalyticsPerformance> {
    return this.http.get<AnalyticsPerformance>(`${this.base}/analytics/performance`);
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

  /* -- jobs and tuning proposals ---------------------------------------- */

  jobs(): Observable<JobList> {
    return this.http.get<JobList>(`${this.base}/jobs`);
  }

  job(id: string): Observable<Job> {
    return this.http.get<Job>(`${this.base}/jobs/${encodeURIComponent(id)}`);
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

  /* -- universe -------------------------------------------------------- */

  tickers(): Observable<TickerList> {
    return this.http.get<TickerList>(`${this.base}/universe/tickers`);
  }

  /** Always a list, single add included: the endpoint absorbs both, and two
   *  client methods over one endpoint is how the two grow different
   *  validation. */
  addTickers(tickers: string[]): Observable<TickerAddResult> {
    return this.http.post<TickerAddResult>(`${this.base}/universe/tickers`, { tickers });
  }

  removeTicker(symbol: string): Observable<TickerRemoveResult> {
    return this.http.delete<TickerRemoveResult>(
      `${this.base}/universe/tickers/${encodeURIComponent(symbol)}`,
    );
  }

  suggestTickers(q: string): Observable<TickerSuggestions> {
    return this.http.get<TickerSuggestions>(`${this.base}/universe/suggest`, {
      params: { q },
    });
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
      { settings },
    );
  }

  /** Returns the diff that was written, NOT the settings document — the
   *  form reloads through `settings()` so it re-reads what is on disk. */
  saveSettings(settings: Record<string, unknown>): Observable<SettingsSaveResult> {
    return this.http.put<SettingsSaveResult>(`${this.base}/system/settings`, { settings });
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
      `${this.base}/system/preferences`, { preferences },
    );
  }

  /* -- market ---------------------------------------------------------- */

  ohlcv(ticker: string, params: Record<string, unknown> = {}): Observable<OhlcvResponse> {
    return this.http.get<OhlcvResponse>(
      `${this.base}/market/ohlcv/${encodeURIComponent(ticker)}`,
      { params: toParams(params) },
    );
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
