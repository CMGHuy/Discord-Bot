import { Preferences } from '../api/models';

/**
 * Which watchlist tickers ride the shell's live tape — spec v77.
 *
 * A flat dotted key alongside `shell.sidebar` and the SR12 table keys, so
 * adding this preference is adding a key rather than migrating everything
 * already saved.
 *
 * **The read is tolerant**, for the same reason `table-prefs.ts` is: this value
 * is written by one version of the app and read by the next, and is
 * hand-editable on the server. A stored value is a hint. The worst case is an
 * empty tape, which is exactly what someone who has never flagged anything
 * sees — never a broken shell.
 */
export const TAPE_SYMBOLS_KEY = 'tape.symbols';

/** Uppercase, trimmed, deduped, order preserved. */
function normalise(symbols: readonly unknown[]): string[] {
  const out: string[] = [];
  for (const raw of symbols) {
    if (typeof raw !== 'string') continue;
    const symbol = raw.trim().toUpperCase();
    if (symbol && !out.includes(symbol)) out.push(symbol);
  }
  return out;
}

export function readTapeSymbols(prefs: Preferences): string[] {
  const stored = prefs?.[TAPE_SYMBOLS_KEY];
  return Array.isArray(stored) ? normalise(stored) : [];
}

export function writeTapeSymbols(prefs: Preferences, symbols: string[]): Preferences {
  return { ...prefs, [TAPE_SYMBOLS_KEY]: normalise(symbols) };
}

export function toggleTapeSymbol(prefs: Preferences, symbol: string): Preferences {
  const current = readTapeSymbols(prefs);
  const wanted = symbol.trim().toUpperCase();
  return writeTapeSymbols(
    prefs,
    current.includes(wanted) ? current.filter((s) => s !== wanted) : [...current, wanted],
  );
}
