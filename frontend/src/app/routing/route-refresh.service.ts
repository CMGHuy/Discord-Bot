import { Injectable, inject } from '@angular/core';
import { NavigationCancel, NavigationEnd, NavigationError, Router } from '@angular/router';
import { Subject, debounceTime, filter } from 'rxjs';

import { EventName, EventStream } from '../api/event-stream';
import { RouteLoadingService } from './route-loading.service';
import { RESOLVER_ROUTE_DATA, ResolverRouteData, resolvedRoute } from './route-metadata';

@Injectable({ providedIn: 'root' })
export class RouteRefreshService {
  private readonly router = inject(Router);
  private readonly loading = inject(RouteLoadingService);
  private readonly settle = new Subject<void>();
  private readonly events = new Set<EventName>();
  private mutationPending = false;

  constructor() {
    inject(EventStream).raised.subscribe((event) => {
      this.events.add(event);
      this.settle.next();
    });
    this.router.events.pipe(
      filter((event) => event instanceof NavigationEnd || event instanceof NavigationCancel || event instanceof NavigationError),
    ).subscribe(() => this.settle.next());
    this.settle.pipe(debounceTime(300)).subscribe(() => this.refresh());
  }

  requestMutationRefresh(): void {
    this.mutationPending = true;
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
    void this.router.navigateByUrl(this.router.url, { onSameUrlNavigation: 'reload', replaceUrl: true });
  }
}
