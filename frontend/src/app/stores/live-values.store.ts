import { DestroyRef, Injectable, Signal, computed, effect, inject, signal, untracked } from '@angular/core';

import { ApiClient } from '../api/api-client';
import { EventStream } from '../api/event-stream';
import { MarketStatus, MarketUpdates, QuoteUpdate, RowQuoteFields } from '../api/models';

/** How often status is re-read when no event arrives: the only thing that
 *  notices a dead refresher, which raises no events. */
export const STATUS_POLL_MS = 60_000;

/** A locally-set refresh mark never outlives the server's mark timeout. */
export const LOCAL_REFRESH_TIMEOUT_MS = 120_000;

const localKey = (symbol: string) => 'quote:' + symbol;

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
 * v201: the one place live prices live. `/market/updates` is read on every
 * `market` event (and at start, on a stream going live, and on a 60 s poll),
 * so a price reaches every table that shows it without each page refetching.
 */
@Injectable({ providedIn: 'root' })
export class LiveValuesStore {
  private readonly api = inject(ApiClient);
  private readonly events = inject(EventStream);

  private cursor: string | null = null;
  private inFlight = false;
  private again = false;
  private readonly memo = new Map<string, Signal<QuoteUpdate | null>>();

  readonly status = signal<MarketStatus | null>(null);
  private readonly quotes = signal<Record<string, QuoteUpdate>>({});
  /** 'quote:SYM' -> request time in ms, for refreshes this tab asked for. */
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

  /** Rows with each symbol's live quote laid over them. Reads signals, so a
   *  computed calling it re-runs on updates. */
  patchRows<T extends RowQuoteFields>(rows: T[], symbolOf: (r: T) => string): T[] {
    return rows.map((row) => overlayQuote(row, this.quote(symbolOf(row))()));
  }

  requestRefresh(symbols: string[]): void {
    const at = Date.now();
    const keys = symbols.map((s) => localKey(s.toUpperCase()));
    this.local.update((m) => ({ ...m, ...Object.fromEntries(keys.map((k) => [k, at])) }));
    this.api.refreshMarket({ symbols }).subscribe({ error: () => this.clearLocal(keys) });
    setTimeout(() => this.clearLocal(keys, at), LOCAL_REFRESH_TIMEOUT_MS);
  }

  /* -- internals ------------------------------------------------------- */

  private resolve(sym: string): QuoteUpdate | null {
    const stored = this.quotes()[sym] ?? null;
    if (this.local()[localKey(sym)] === undefined) return stored;
    return { ...(stored ?? { symbol: sym, price: null, as_of: null, error: null }), refreshing: true };
  }

  private sync(): void {
    if (this.inFlight) {
      this.again = true;
      return;
    }
    this.inFlight = true;
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
    this.status.set(reply.status);
    this.cursor = reply.cursor;
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
    const changes = this.events.changes('market');
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
    const timer = setInterval(() => {
      if (typeof document === 'undefined' || !document.hidden) this.sync();
    }, STATUS_POLL_MS);
    destroyRef.onDestroy(() => clearInterval(timer));
  }
}
