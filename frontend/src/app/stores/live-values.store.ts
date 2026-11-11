import { DestroyRef, Injectable, Signal, computed, effect, inject, signal, untracked } from '@angular/core';

import { ApiClient } from '../api/api-client';
import { EventStream, MARKET_DATA_MIN_INTERVAL_MS } from '../api/event-stream';
import { MarketStatus, MarketUpdates, QuoteUpdate, RowQuoteFields, SnapshotUpdate } from '../api/models';

/** How often status is re-read when no read went out in that time: the only
 *  thing that notices a dead refresher, which raises no events. A tab that
 *  synced within the last STATUS_POLL_MS skips the tick (v218). */
export const STATUS_POLL_MS = 60_000;

/** A locally-set refresh mark never outlives the server's mark timeout. */
export const LOCAL_REFRESH_TIMEOUT_MS = 120_000;

const localKey = (symbol: string) => 'quote:' + symbol;
const snapshotKey = (key: string) => 'snapshot:' + key;

/** True when the update carries a price strictly newer than the row's own. */
function isNewer(row: RowQuoteFields, update: QuoteUpdate): boolean {
  if (update.price === null || update.as_of === null) return false;
  return !row.price_as_of || Date.parse(update.as_of) > Date.parse(row.price_as_of);
}

/** The fields an update would change on a row, empty when it changes none. */
function quotePatch(row: RowQuoteFields, update: QuoteUpdate): RowQuoteFields {
  const patch: RowQuoteFields = {};
  if (isNewer(row, update)) {
    if (row.current_price !== update.price) patch.current_price = update.price;
    if (row.price_as_of !== update.as_of) patch.price_as_of = update.as_of;
    if (row.price_age_s !== null && row.price_age_s !== undefined) patch.price_age_s = null;
  }
  if ((row.price_refreshing ?? false) !== update.refreshing) patch.price_refreshing = update.refreshing;
  if ((row.price_error ?? null) !== update.error) patch.price_error = update.error;
  return patch;
}

/**
 * Lay a live quote over a row. Pure: the row itself comes back when nothing
 * would change, so a computed that maps many rows keeps the unchanged ones
 * referentially equal. An older update never replaces a newer price; the
 * refreshing and error marks are always the update's.
 */
export function overlayQuote<T extends RowQuoteFields>(row: T, update: QuoteUpdate | null): T {
  if (update === null) return row;
  const patch = quotePatch(row, update);
  return Object.keys(patch).length === 0 ? row : { ...row, ...patch };
}

/**
 * v201: the one place live prices live. `/market/updates` is read at start,
 * on a stream going live, on `market` events through the shared 30 s
 * throttle (v218: one leading and one trailing read per burst), and on a 60 s
 * poll that fires only when no read went out in the last 60 s -- so a price
 * reaches every table that shows it without each page refetching.
 */
@Injectable({ providedIn: 'root' })
export class LiveValuesStore {
  private readonly api = inject(ApiClient);
  private readonly events = inject(EventStream);

  private cursor: string | null = null;
  private inFlight = false;
  private again = false;
  /** When this tab last sent `/market/updates` (ms since epoch); the poll defers to it. */
  private lastSyncAt = -Infinity;
  private readonly memo = new Map<string, Signal<QuoteUpdate | null>>();
  private readonly snapshotMemo = new Map<string, Signal<SnapshotUpdate | null>>();

  readonly status = signal<MarketStatus | null>(null);
  private readonly quotes = signal<Record<string, QuoteUpdate>>({});
  private readonly snapshots = signal<Record<string, SnapshotUpdate>>({});
  /** 'quote:SYM' or 'snapshot:key' -> request time in ms for this tab. */
  private readonly local = signal<Record<string, number>>({});

  readonly stalled = computed(() => this.status()?.heartbeat.stalled === true);

  constructor() {
    this.sync();
    this.watchMarketEvents();
    this.watchStreamState();
    this.startPoll(inject(DestroyRef));
  }

  /** The stored update for a symbol, refreshing while this tab awaits it. */
  quote(symbol: string): Signal<QuoteUpdate | null> {
    const sym = symbol.toUpperCase();
    let found = this.memo.get(sym);
    if (!found) {
      found = computed(() => this.resolve(sym));
      this.memo.set(sym, found);
    }
    return found;
  }

  /** The stored update for a snapshot, refreshing while this tab awaits it. */
  snapshot(key: string): Signal<SnapshotUpdate | null> {
    let found = this.snapshotMemo.get(key);
    if (!found) {
      found = computed(() => this.resolveSnapshot(key));
      this.snapshotMemo.set(key, found);
    }
    return found;
  }

  /** Rows with each symbol's live quote laid over them. Reads signals, so a
   *  computed calling it re-runs on updates. */
  patchRows<T extends RowQuoteFields>(rows: T[], symbolOf: (r: T) => string): T[] {
    return rows.map((row) => overlayQuote(row, this.quote(symbolOf(row))()));
  }

  requestRefresh(symbols: string[], snapshots: string[] = []): void {
    const at = Date.now();
    const keys = [...symbols.map((s) => localKey(s.toUpperCase())), ...snapshots.map(snapshotKey)];
    this.local.update((m) => ({ ...m, ...Object.fromEntries(keys.map((k) => [k, at])) }));
    const body = snapshots.length === 0 ? { symbols } : { symbols, snapshots };
    this.api.refreshMarket(body).subscribe({ error: () => this.clearLocal(keys, at) });
    setTimeout(() => this.clearLocal(keys, at), LOCAL_REFRESH_TIMEOUT_MS);
  }

  /* -- internals ------------------------------------------------------- */

  private resolve(sym: string): QuoteUpdate | null {
    const stored = this.quotes()[sym] ?? null;
    if (this.local()[localKey(sym)] === undefined) return stored;
    return { ...(stored ?? { symbol: sym, price: null, as_of: null, error: null }), refreshing: true };
  }

  private resolveSnapshot(key: string): SnapshotUpdate | null {
    const snapshots = this.snapshots();
    const stored = Object.hasOwn(snapshots, key) ? snapshots[key] : null;
    if (this.local()[snapshotKey(key)] === undefined) return stored;
    return { ...(stored ?? { key, computed_at: null, stale_inputs: false, error: null }), refreshing: true };
  }

  private sync(): void {
    if (this.inFlight) {
      this.again = true;
      return;
    }
    this.inFlight = true;
    this.lastSyncAt = Date.now();
    this.api.marketUpdates(this.cursor).subscribe({
      next: (reply) => this.merge(reply),
      error: () => this.finish(),
      complete: () => this.finish(),
    });
  }

  private finish(): void {
    this.inFlight = false;
    if (!this.again) return;
    this.again = false;
    this.sync();
  }

  private merge(reply: MarketUpdates): void {
    if (reply.quotes.length > 0) {
      this.quotes.update((m) => {
        const next = { ...m };
        for (const item of reply.quotes) next[item.symbol.toUpperCase()] = item;
        return next;
      });
      this.clearLocal(reply.quotes.filter((u) => !u.refreshing || u.error).map((u) => localKey(u.symbol.toUpperCase())));
    }
    this.mergeSnapshots(reply.snapshots ?? []);
    this.status.set(reply.status);
    this.cursor = reply.cursor;
  }

  private mergeSnapshots(updates: SnapshotUpdate[]): void {
    if (updates.length === 0) return;
    const latest = Object.fromEntries(updates.map((update) => [update.key, update]));
    this.snapshots.update((stored) => ({ ...stored, ...latest }));
    this.clearSnapshotMarks(Object.values(latest));
  }

  private clearSnapshotMarks(updates: SnapshotUpdate[]): void {
    const local = this.local();
    const done = updates.filter((update) => {
      const requestedAt = local[snapshotKey(update.key)];
      if (requestedAt === undefined) return false;
      if (update.error !== null) return true;
      return !update.refreshing && update.computed_at !== null && Date.parse(update.computed_at) >= requestedAt;
    });
    this.clearLocal(done.map((update) => snapshotKey(update.key)));
  }

  /** Drop local marks; with `at`, only those still carrying that request time. */
  private clearLocal(keys: string[], at?: number): void {
    const current = this.local();
    const drop = keys.filter((k) => k in current && (at === undefined || current[k] === at));
    if (drop.length === 0) return;
    const next = { ...current };
    for (const k of drop) delete next[k];
    this.local.set(next);
  }

  private watchMarketEvents(): void {
    // v218: the refresher raises `market` after every cycle, and an
    // unthrottled read per event was the idle tab's biggest single source
    // (12 of 33 requests in 120 s, v206 "Plan 2 after"). The shared throttle
    // keeps the first event's read immediate and folds the rest of a burst
    // into one trailing read, so the burst's last price still lands.
    const changes = this.events.changes('market', { minIntervalMs: MARKET_DATA_MIN_INTERVAL_MS });
    let seen = untracked(changes);
    effect(() => {
      const n = changes();
      if (n === seen) return;
      seen = n;
      this.sync();
    });
  }

  private watchStreamState(): void {
    let previous = untracked(this.events.state);
    effect(() => {
      const state = this.events.state();
      const wentLive = state === 'live' && previous !== 'live';
      previous = state;
      if (wentLive) this.sync();
    });
  }

  private startPoll(destroyRef: DestroyRef): void {
    const timer = setInterval(() => this.pollIfQuiet(), STATUS_POLL_MS);
    destroyRef.onDestroy(() => clearInterval(timer));
  }

  /** The poll covers silence only: a hidden tab, or a tab that read within
   *  the last STATUS_POLL_MS, has nothing to catch up on. */
  private pollIfQuiet(): void {
    if (typeof document !== 'undefined' && document.hidden) return;
    if (Date.now() - this.lastSyncAt >= STATUS_POLL_MS) this.sync();
  }
}
