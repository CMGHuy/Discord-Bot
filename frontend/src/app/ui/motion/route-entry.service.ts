import { Injectable, Signal, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import {
  Event as RouterEvent,
  NavigationCancel,
  NavigationEnd,
  NavigationError,
  NavigationStart,
  Router,
  RoutesRecognized,
} from '@angular/router';

/** The path of a router URL: query string and fragment dropped. */
export function pathOf(url: string): string {
  const path = url.split(/[?#]/)[0];
  return path === '' ? '/' : path;
}

/** Same test as `RouteLoadingService`'s private one: the refresh passes
 *  `BACKGROUND_REFRESH_INFO` (`{ backgroundRefresh: true }`) as `info`. */
function isBackgroundRefresh(info: unknown): boolean {
  return typeof info === 'object' && info !== null
    && (info as { backgroundRefresh?: unknown }).backgroundRefresh === true;
}

/**
 * Once-per-route-activation bookkeeping for entrance motion (spec v168 §3, §4).
 *
 * `RouteRefreshService` re-runs the current route with a real `navigateByUrl`
 * on every relevant push, and `sb-async` destroys and re-creates its content on
 * every refetch. Either would replay an entrance if "first render" were the
 * trigger -- the permanent flicker the old "nothing on entrance" rule was
 * written against. So an entrance is keyed to an **activation id** that moves
 * only when the path changes, and every entrance consumer spends a
 * once-per-activation `claim(key)` before it animates. A re-created element
 * finds its claim already spent and renders its final state at once.
 *
 * `info` is read while the navigation is in flight: `currentNavigation()` is
 * null by `NavigationEnd`, where the id is committed.
 */
@Injectable({ providedIn: 'root' })
export class RouteEntryService {
  private readonly router = inject(Router);
  private readonly id = signal(0);
  private readonly claimed = new Set<string>();
  private committedPath: string | null = this.router.navigated ? pathOf(this.router.url) : null;
  private background = false;

  /** Moves by one per real path change; 0 until the first one. */
  readonly activation: Signal<number> = this.id.asReadonly();

  constructor() {
    this.router.events.pipe(takeUntilDestroyed()).subscribe((event) => this.onRouterEvent(event));
  }

  /** `true` the first time `key` asks within this activation, then `false`. */
  claim(key: string): boolean {
    if (this.claimed.has(key)) return false;
    this.claimed.add(key);
    return true;
  }

  private onRouterEvent(event: RouterEvent): void {
    if (event instanceof NavigationStart) this.background = false;
    if (event instanceof NavigationStart || event instanceof RoutesRecognized) {
      this.background ||= isBackgroundRefresh(this.router.currentNavigation()?.extras.info);
    } else if (event instanceof NavigationEnd) {
      this.commit(pathOf(event.urlAfterRedirects));
    } else if (event instanceof NavigationCancel || event instanceof NavigationError) {
      this.background = false;
    }
  }

  private commit(path: string): void {
    const background = this.background;
    const moved = path !== this.committedPath;
    this.background = false;
    this.committedPath = path;
    if (background || !moved) return;
    this.claimed.clear();
    this.id.update((n) => n + 1);
  }
}
