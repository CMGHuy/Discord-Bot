import { HttpContextToken } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { NavigationEnd, NavigationStart, Router } from '@angular/router';

/** v171 D2. The admin server reads exactly this header with value `1` and
 *  then skips the shared cache's reuse window for that request's market
 *  data (still single-flighted, still at admin priority, tier 5). */
export const FRESH_HEADER = 'X-Swingbot-Fresh';

/** Per-request opt-in, for a caller that is a refresh but not a Retry. */
export const FRESH_REQUEST = new HttpContextToken<boolean>(() => false);

/** How long after the first NavigationEnd the page load's GETs stay fresh. */
export const BOOT_FRESH_WINDOW_MS = 10_000;

/**
 * Which requests are "fresh" (spec v171 D2, the partner's rule): the ones a
 * full page load makes (first load or browser reload) and the ones an
 * explicit refresh click makes. In-app navigation reuses the shared cache.
 *
 * The boot phase ends at the second NavigationStart (the first in-app route
 * change, or a background resolver refresh) or BOOT_FRESH_WINDOW_MS after the
 * first NavigationEnd, whichever comes first: a page left open then reuses
 * the cache for its event-driven refetches, like navigation does.
 */
@Injectable({ providedIn: 'root' })
export class FreshRequestService {
  private navigationStarts = 0;
  private bootEndsAt: number | null = null;
  private depth = 0;

  constructor() {
    inject(Router).events.subscribe((event) => {
      if (event instanceof NavigationStart) this.navigationStarts++;
      if (event instanceof NavigationEnd && this.bootEndsAt === null) {
        this.bootEndsAt = Date.now() + BOOT_FRESH_WINDOW_MS;
      }
    });
  }

  isBootPhase(): boolean {
    return this.navigationStarts < 2 && (this.bootEndsAt === null || Date.now() < this.bootEndsAt);
  }

  isMarking(): boolean {
    return this.depth > 0;
  }

  /** Requests whose interceptor chain runs inside `fn` carry the mark.
   *  HttpClient runs the chain at subscribe time, so `fn` must subscribe
   *  synchronously; every store `load()` in this app does. */
  markFresh<T>(fn: () => T): T {
    this.depth++;
    try {
      return fn();
    } finally {
      this.depth--;
    }
  }
}
