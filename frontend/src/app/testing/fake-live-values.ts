import { Signal, WritableSignal, signal } from '@angular/core';
import { vi } from 'vitest';

import { MarketStatus, QuoteUpdate, RowQuoteFields } from '../api/models';
import { overlayQuote } from '../stores/live-values.store';

/**
 * A stand-in for `LiveValuesStore` in specs: no HTTP, no event stream.
 * `patchRows` delegates to the real `overlayQuote`, so a spec exercises the
 * production merge rule; `set` plays an arriving update.
 */
export class FakeLiveValues {
  readonly status = signal<MarketStatus | null>(null);
  readonly requestRefresh = vi.fn();
  private readonly quotes = new Map<string, WritableSignal<QuoteUpdate | null>>();

  private slot(symbol: string): WritableSignal<QuoteUpdate | null> {
    const key = symbol.toUpperCase();
    let found = this.quotes.get(key);
    if (!found) {
      found = signal<QuoteUpdate | null>(null);
      this.quotes.set(key, found);
    }
    return found;
  }

  quote(symbol: string): Signal<QuoteUpdate | null> {
    return this.slot(symbol).asReadonly();
  }

  set(symbol: string, update: Partial<QuoteUpdate>): void {
    this.slot(symbol).set({
      symbol, price: null, as_of: null, refreshing: false, error: null, ...update,
    } as QuoteUpdate);
  }

  patchRows<T extends RowQuoteFields>(rows: T[], symbolOf: (r: T) => string): T[] {
    return rows.map((row) => overlayQuote(row, this.quote(symbolOf(row))()));
  }
}
