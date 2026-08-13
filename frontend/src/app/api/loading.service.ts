import { Injectable, computed, signal } from '@angular/core';

/** How many requests are in flight, as a signal.
 *
 * A counter rather than a boolean because requests overlap constantly here:
 * an event arrives, three stores refetch, and a boolean set false by the
 * first response to land would clear the indicator while two are still
 * outstanding.
 *
 * The interceptor owns the increments (NG27). Nothing else should call
 * `started`/`finished` -- if a component finds itself wanting to, it is
 * doing HTTP outside `ApiClient`, which is the thing this layer exists to
 * prevent.
 */
@Injectable({ providedIn: 'root' })
export class LoadingService {
  private readonly count = signal(0);

  readonly inFlight = this.count.asReadonly();
  readonly isLoading = computed(() => this.count() > 0);

  started(): void {
    this.count.update((n) => n + 1);
  }

  finished(): void {
    // Clamped at zero: a double-finish would otherwise make the counter
    // negative and leave isLoading() permanently false, hiding every
    // subsequent request instead of failing visibly.
    this.count.update((n) => Math.max(0, n - 1));
  }
}
