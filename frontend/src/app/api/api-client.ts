import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import {
  AnalyticsCalibration,
  AnalyticsPerformance,
  AnalyticsRegistry,
  AnalyticsSnapshot,
  AnalyticsStrategies,
  Candle,
  Cockpit,
  Collection,
  Health,
  Identity,
  Job,
  JobList,
  Logs,
  Proposal,
  ProposalList,
  Risk,
  ScanCommandResult,
  ScanStatus,
  Settings,
  Ticker,
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

  clearOpenTrades(): Observable<unknown> {
    return this.http.post(`${this.base}/trades/clear-open`, {});
  }

  clearTradeHistory(): Observable<unknown> {
    return this.http.post(`${this.base}/trades/clear-history`, {});
  }

  setTradeNote(id: string, note: string): Observable<TradeNote> {
    return this.http.put<TradeNote>(
      `${this.base}/trades/${encodeURIComponent(id)}/note`, { note },
    );
  }

  /** The CSV export URL. Returned rather than fetched: the browser should
   *  download this through a normal navigation so it gets a Save dialog and
   *  the server's filename, which an XHR would throw away. */
  tradesExportUrl(query: TradeQuery = {}): string {
    const params = toParams(query).toString();
    return `${this.base}/trades/export.csv${params ? `?${params}` : ''}`;
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

  startTuneJob(args: Record<string, unknown>): Observable<Job> {
    return this.http.post<Job>(`${this.base}/jobs/tune`, args);
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

  tickers(): Observable<Collection<Ticker>> {
    return this.http.get<Collection<Ticker>>(`${this.base}/universe/tickers`);
  }

  addTicker(symbol: string): Observable<Ticker> {
    return this.http.post<Ticker>(`${this.base}/universe/tickers`, { symbol });
  }

  removeTicker(symbol: string): Observable<void> {
    return this.http.delete<void>(
      `${this.base}/universe/tickers/${encodeURIComponent(symbol)}`,
    );
  }

  suggestTickers(q: string): Observable<unknown> {
    return this.http.get(`${this.base}/universe/suggest`, { params: { q } });
  }

  /* -- risk ------------------------------------------------------------ */

  risk(): Observable<Risk> {
    return this.http.get<Risk>(`${this.base}/risk`);
  }

  setKillswitch(on: boolean, reason?: string): Observable<Risk> {
    return this.http.post<Risk>(`${this.base}/risk/killswitch`, { on, reason });
  }

  /* -- system ---------------------------------------------------------- */

  settings(): Observable<Settings> {
    return this.http.get<Settings>(`${this.base}/system/settings`);
  }

  previewSettings(values: Record<string, unknown>): Observable<unknown> {
    return this.http.post(`${this.base}/system/settings/preview`, values);
  }

  saveSettings(values: Record<string, unknown>): Observable<Settings> {
    return this.http.put<Settings>(`${this.base}/system/settings`, values);
  }

  /** A URL, not a request -- same reason as the CSV export. */
  settingsExportUrl(): string {
    return `${this.base}/system/settings/export`;
  }

  importSettings(body: FormData | Record<string, unknown>): Observable<Settings> {
    return this.http.post<Settings>(`${this.base}/system/settings/import`, body);
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

  clearLogs(source?: string): Observable<unknown> {
    return this.http.delete(`${this.base}/system/logs`, { params: toParams({ source }) });
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

  restartBot(): Observable<unknown> {
    return this.http.post(`${this.base}/system/bot/restart`, {});
  }

  /* -- market ---------------------------------------------------------- */

  ohlcv(ticker: string, params: Record<string, unknown> = {}): Observable<Candle[]> {
    return this.http.get<Candle[]>(
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
