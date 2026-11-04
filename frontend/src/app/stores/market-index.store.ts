import { computed, inject, signal } from '@angular/core';
import { signalStore, withComputed, withHooks, withMethods } from '@ngrx/signals';

import { TapeRow } from '../api/models';
import { TapeFeed } from './tape-feed';

/** Lane A's fixed symbols, in the exact order the tape shows them.
 *
 * Yahoo's own index formats (`swingbot/core/marketdata/ticker_utils.py`),
 * not the friendlier aliases ("SPX", "VIX", ...) that alias table resolves
 * FROM -- `/market/tape` prices the literal symbol it is given with no
 * alias lookup of its own (`_tape_symbols` just upper-cases each part). */
const INDEX_SYMBOLS = ['^GSPC', '^NDX', '^DJI', '^VIX'];

/**
 * Lane A of the shell tape — first-party replacement for the earlier
 * TradingView `ticker-tape` iframe.
 *
 * That widget was cross-origin: its scroll speed, its color theme and even
 * whether a given symbol (VIX included) painted at all were entirely up to
 * TradingView, not this app. This store prices the same four indices through
 * `/market/tape` so Lane A renders through the exact same markup and CSS as
 * Lane B (`tape.css`).
 *
 * The request is the `TapeFeed`'s (v201): this store registers
 * `INDEX_SYMBOLS` as owner `index` and reads its rows back in that fixed
 * display order (S&P, Nasdaq, Dow, VIX); a symbol the feed lacks is skipped.
 */
export const MarketIndexStore = signalStore(
  { providedIn: 'root' },
  withComputed((_store, feed = inject(TapeFeed)) => ({
    rows: computed(() => INDEX_SYMBOLS
      .map((symbol) => feed.rows()[symbol])
      .filter((row): row is TapeRow => !!row)),
    asOf: feed.asOf,
  })),
  withMethods((_store, feed = inject(TapeFeed)) => ({
    load: (): void => feed.refresh(),
  })),
  withHooks({
    onInit(_store, feed = inject(TapeFeed)) {
      feed.register('index', signal(INDEX_SYMBOLS).asReadonly());
    },
  }),
);
