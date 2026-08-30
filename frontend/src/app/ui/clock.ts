import { InjectionToken, Signal, signal } from '@angular/core';

/** How often the ambient clock advances. */
export const CLOCK_INTERVAL_MS = 30_000;

/**
 * Wall-clock time, as a signal, for values that must age on screen.
 *
 * The token is intentionally overridable in tests so suites can provide a
 * fixed signal rather than leave an interval running in Vitest.
 */
export const CLOCK = new InjectionToken<Signal<number>>('CLOCK', {
  providedIn: 'root',
  factory: () => {
    const now = signal(Date.now());
    setInterval(() => now.set(Date.now()), CLOCK_INTERVAL_MS);
    return now.asReadonly();
  },
});