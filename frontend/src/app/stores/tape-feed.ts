import { Injectable, Signal, computed, effect, inject, signal } from '@angular/core';

import { ApiClient } from '../api/api-client';
import { EventStream, MARKET_DATA_MIN_INTERVAL_MS } from '../api/event-stream';
import { TapeRow } from '../api/models';

function sameSymbols(a: readonly string[], b: readonly string[]): boolean {
  return a.length === b.length && a.every((symbol, i) => symbol === b[i]);
}

/** Union of every owner's symbols: upper-cased, de-duplicated, in
 *  registration order and then symbol order. */
function unionOf(owners: ReadonlyMap<string, Signal<string[]>>): string[] {
  const seen = new Set<string>();
  for (const symbols of owners.values()) {
    for (const symbol of symbols()) seen.add(symbol.toUpperCase());
  }
  return [...seen];
}

/**
 * v201: the one `/market/tape` request behind both shell lanes.
 *
 * `TapeStore` (lane B) and `MarketIndexStore` (lane A) each register their
 * symbols; the feed asks for the union once per poll. Refreshes coalesce in
 * one microtask, so every caller in the same tick shares a single request.
 * A failed refetch keeps the previous rows: blanking the strip would read as
 * "every position closed", the dangerous direction to be wrong in.
 */
@Injectable({ providedIn: 'root' })
export class TapeFeed {
  private readonly api = inject(ApiClient);
  private readonly owners = signal<ReadonlyMap<string, Signal<string[]>>>(new Map());
  private readonly merged = computed(() => unionOf(this.owners()), { equal: sameSymbols });
  private readonly _rows = signal<Record<string, TapeRow>>({});
  private readonly _asOf = signal<string | null>(null);
  private readonly _loading = signal(false);
  private latestRequest = 0;
  private queued = false;

  readonly rows = this._rows.asReadonly();
  readonly asOf = this._asOf.asReadonly();
  readonly loading = this._loading.asReadonly();

  constructor() {
    // v132: `scan` fires ~1/s during a scan and this refetch hits Yahoo.
    const scan = inject(EventStream).changes('scan', { minIntervalMs: MARKET_DATA_MIN_INTERVAL_MS });
    // v201: a landed price reaches the strip within 30 s, one merged request.
    const market = inject(EventStream).changes('market', { minIntervalMs: MARKET_DATA_MIN_INTERVAL_MS });
    effect(() => {
      scan();
      market();
      this.merged();
      this.refresh();
    });
  }

  register(owner: string, symbols: Signal<string[]>): void {
    this.owners.update((current) => new Map(current).set(owner, symbols));
  }

  refresh(): void {
    if (this.queued) return;
    this.queued = true;
    queueMicrotask(() => {
      this.queued = false;
      this.fetch();
    });
  }

  private fetch(): void {
    const symbols = this.merged();
    const request = ++this.latestRequest;
    if (!symbols.length) {
      this._rows.set({});
      this._loading.set(false);
      return;
    }
    this._loading.set(true);
    this.api.tape(symbols).subscribe({
      next: (response) => {
        if (request !== this.latestRequest) return;
        if (!response || !Array.isArray(response.rows)) return;
        this._rows.set(Object.fromEntries(response.rows.map((r) => [r.symbol.toUpperCase(), r])));
        this._asOf.set(response.as_of ?? null);
        this._loading.set(false);
      },
      // Silent and non-destructive: see the class comment.
      error: () => {
        if (request === this.latestRequest) this._loading.set(false);
      },
    });
  }
}
