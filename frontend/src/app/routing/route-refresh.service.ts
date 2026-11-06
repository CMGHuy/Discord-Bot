import { DestroyRef, Injectable, inject } from '@angular/core';
import { NavigationCancel, NavigationEnd, NavigationError, Router } from '@angular/router';
import { Subject, debounceTime, filter } from 'rxjs';

import { EventName, EventStream } from '../api/event-stream';
import { BACKGROUND_REFRESH_INFO, RouteLoadingService } from './route-loading.service';
import { RESOLVER_ROUTE_DATA, ResolverRouteData, resolvedRoute } from './route-metadata';

/**
 * v206: the least time between two reloads a given event may cause.
 *
 * `scan` fires about once a second while a scan runs, and the System
 * workspace (`scan`/`providers` tabs) and ticker detail reload their whole
 * route on it -- a full resolve a second, per tab. The System page's own
 * `paused`/`pending` facts change only through `runtime_flags`, so 5 s is
 * enough. Every event not listed keeps the plain 300 ms debounce.
 */
export const EVENT_MIN_INTERVAL_MS: Partial<Record<EventName, number>> = { scan: 5000 };

@Injectable({ providedIn: 'root' })
export class RouteRefreshService {
  private readonly router = inject(Router);
  private readonly loading = inject(RouteLoadingService);
  private readonly settle = new Subject<void>();
  private readonly events = new Set<EventName>();
  private readonly lastAccepted = new Map<EventName, number>();
  private readonly held = new Map<EventName, ReturnType<typeof setTimeout>>();
  private mutationPending = false;

  constructor() {
    inject(EventStream).raised.subscribe((event) => this.accept(event));
    this.router.events.pipe(
      filter((event) => event instanceof NavigationEnd || event instanceof NavigationCancel || event instanceof NavigationError),
    ).subscribe(() => this.settle.next());
    this.settle.pipe(debounceTime(300)).subscribe(() => this.refresh());
    inject(DestroyRef).onDestroy(() => {
      for (const timer of this.held.values()) clearTimeout(timer);
      this.held.clear();
    });
  }

  requestMutationRefresh(): void {
    this.mutationPending = true;
    this.settle.next();
  }

  /** Leading edge at once; the rest of a burst inside the event's minimum
   *  interval becomes one trailing event at the end of it. */
  private accept(event: EventName): void {
    const interval = EVENT_MIN_INTERVAL_MS[event];
    if (interval === undefined) return this.queue(event);
    const wait = (this.lastAccepted.get(event) ?? Number.NEGATIVE_INFINITY) + interval - Date.now();
    if (wait <= 0) return this.release(event);
    if (this.held.has(event)) return;
    this.held.set(event, setTimeout(() => this.release(event), wait));
  }

  private release(event: EventName): void {
    this.held.delete(event);
    this.lastAccepted.set(event, Date.now());
    this.queue(event);
  }

  private queue(event: EventName): void {
    this.events.add(event);
    this.settle.next();
  }

  private refresh(): void {
    if (this.loading.pending()) return;

    const route = resolvedRoute(this.router.routerState.snapshot.root);
    const meta = route?.data[RESOLVER_ROUTE_DATA] as ResolverRouteData | undefined;
    const shouldRefresh = this.mutationPending || [...this.events].some((event) => meta?.refreshOn(event, route!) ?? false);
    this.events.clear();
    this.mutationPending = false;
    if (!shouldRefresh) return;
    void this.router.navigateByUrl(this.router.url, { onSameUrlNavigation: 'reload', replaceUrl: true, info: BACKGROUND_REFRESH_INFO });
  }
}
