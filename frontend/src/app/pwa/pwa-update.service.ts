import { Injectable, InjectionToken, OnDestroy, inject } from '@angular/core';
import { SwUpdate, VersionReadyEvent } from '@angular/service-worker';
import { filter } from 'rxjs/operators';

/**
 * How the reload actually happens, abstracted for a test to substitute a
 * spy. Real code never calls `window.location.reload()` directly, so
 * PwaUpdateService's tests never need a real browser navigation.
 */
export const RELOAD_PAGE = new InjectionToken<() => void>('RELOAD_PAGE', {
  providedIn: 'root',
  factory: () => () => window.location.reload(),
});

/**
 * How often to poll for a new version while the app stays open and
 * foregrounded. Visibility-change (below) and the SW's own registration
 * check already cover the two moments an update is most likely to land --
 * reopening an installed app, or loading it fresh -- so this is only the
 * safety net for a session left open (and foregrounded) longer than that.
 */
export const CHECK_INTERVAL_MS = 5 * 60_000;

/**
 * Makes a new deploy actually reach an open tab or an installed phone app,
 * instead of it sitting cached until someone thinks to reload.
 *
 * Without this, `@angular/service-worker`'s default behaviour is silent: it
 * downloads a new version in the background and does nothing with it until
 * the NEXT full navigation notices the swap -- which an installed PWA may
 * never do on its own, since the whole point of installing it is to never
 * leave the app. So this actively looks for an update (on visibility change
 * and on an interval) and, once one is ready, activates it and reloads
 * immediately -- "straightforward", not "eventually".
 */
@Injectable({ providedIn: 'root' })
export class PwaUpdateService implements OnDestroy {
  private readonly swUpdate = inject(SwUpdate);
  private readonly reload = inject(RELOAD_PAGE);

  private intervalId: ReturnType<typeof setInterval> | undefined;

  private readonly onVisibilityChange = (): void => {
    if (document.visibilityState === 'visible') void this.swUpdate.checkForUpdate();
  };

  /**
   * Called once from an app initializer (see app.config.ts). A no-op
   * outside a real service worker context -- dev mode, an unsupported
   * browser, or a test that hasn't opted in -- since `SwUpdate.isEnabled`
   * is false there and nothing below would ever fire anyway.
   */
  init(): void {
    if (!this.swUpdate.isEnabled) return;

    this.swUpdate.versionUpdates
      .pipe(filter((event): event is VersionReadyEvent => event.type === 'VERSION_READY'))
      .subscribe(() => {
        // Activate first, then reload: reloading before activation would
        // just reload into the still-active OLD version a second time.
        void this.swUpdate.activateUpdate().then(() => this.reload());
      });

    document.addEventListener('visibilitychange', this.onVisibilityChange);
    this.intervalId = setInterval(() => void this.swUpdate.checkForUpdate(), CHECK_INTERVAL_MS);
  }

  ngOnDestroy(): void {
    document.removeEventListener('visibilitychange', this.onVisibilityChange);
    if (this.intervalId !== undefined) clearInterval(this.intervalId);
  }
}
