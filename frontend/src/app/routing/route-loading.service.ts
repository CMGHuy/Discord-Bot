import { Injectable, inject, signal } from '@angular/core';
import { NavigationCancel, NavigationEnd, NavigationError, ResolveEnd, ResolveStart, Router } from '@angular/router';
import { RESOLVER_ROUTE_DATA, ResolverRouteData, resolvedRoute } from './route-metadata';

export const ROUTE_LOADING_DELAY_MS = 1000;
export const LIVE_REFRESH_DEBOUNCE_MS = 300;

@Injectable({ providedIn: 'root' })
export class RouteLoadingService {
  private readonly _pending = signal(false);
  private readonly _visible = signal(false);
  private readonly _label = signal('Loading');
  private timer: ReturnType<typeof setTimeout> | null = null;
  readonly pending = this._pending.asReadonly();
  readonly visible = this._visible.asReadonly();
  readonly label = this._label.asReadonly();
  constructor() {
    inject(Router).events.subscribe((event) => {
      if (event instanceof ResolveStart) this.start(event.state.root);
      if (event instanceof ResolveEnd || event instanceof NavigationEnd || event instanceof NavigationCancel || event instanceof NavigationError) this.finish();
    });
  }
  private start(root: import('@angular/router').ActivatedRouteSnapshot): void {
    this.finish();
    const route = resolvedRoute(root);
    const meta = route?.data[RESOLVER_ROUTE_DATA] as ResolverRouteData | undefined;
    if (!meta) return;
    this._pending.set(true); this._label.set(`Loading ${meta.loadingLabel}`);
    this.timer = setTimeout(() => { this.timer = null; if (this._pending()) this._visible.set(true); }, ROUTE_LOADING_DELAY_MS);
  }
  private finish(): void { if (this.timer !== null) clearTimeout(this.timer); this.timer = null; this._pending.set(false); this._visible.set(false); }
}