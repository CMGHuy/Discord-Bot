import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { SwUpdate, VersionEvent } from '@angular/service-worker';
import { Subject } from 'rxjs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { CHECK_INTERVAL_MS, PwaUpdateService, RELOAD_PAGE } from './pwa-update.service';

/* NG-PWA — automatic update rollout.
 *
 * Without this, a PWA installed on a phone can stay open indefinitely and
 * never notice a new deploy: the SW's own update check only fires on a full
 * navigation, which an installed app rarely does on its own. `SwUpdate` is
 * built to be faked directly (isEnabled + versionUpdates + the two methods),
 * so no real service worker is needed here.
 */

class FakeSwUpdate {
  isEnabled = true;
  readonly versionUpdates = new Subject<VersionEvent>();
  activateUpdate = vi.fn().mockResolvedValue(true);
  checkForUpdate = vi.fn().mockResolvedValue(false);
}

describe('PwaUpdateService', () => {
  let swUpdate: FakeSwUpdate;
  let reload: ReturnType<typeof vi.fn>;

  function setup(): PwaUpdateService {
    swUpdate = new FakeSwUpdate();
    reload = vi.fn();
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        { provide: SwUpdate, useValue: swUpdate },
        { provide: RELOAD_PAGE, useValue: reload },
      ],
    });
    return TestBed.inject(PwaUpdateService);
  }

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('does nothing when the service worker is disabled', () => {
    const service = setup();
    swUpdate.isEnabled = false;

    service.init();
    swUpdate.versionUpdates.next({ type: 'VERSION_READY' } as VersionEvent);

    expect(swUpdate.activateUpdate).not.toHaveBeenCalled();
    expect(reload).not.toHaveBeenCalled();
  });

  it('activates and reloads once a new version is ready', async () => {
    const service = setup();
    service.init();

    swUpdate.versionUpdates.next({ type: 'VERSION_READY' } as VersionEvent);
    // activateUpdate() resolves asynchronously; the reload only happens
    // after it actually resolves, not synchronously with the event.
    await Promise.resolve();
    await Promise.resolve();

    expect(swUpdate.activateUpdate).toHaveBeenCalledTimes(1);
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it('ignores version events that are not VERSION_READY', () => {
    const service = setup();
    service.init();

    swUpdate.versionUpdates.next({ type: 'VERSION_DETECTED' } as VersionEvent);
    swUpdate.versionUpdates.next({ type: 'NO_NEW_VERSION_DETECTED' } as VersionEvent);

    expect(swUpdate.activateUpdate).not.toHaveBeenCalled();
    expect(reload).not.toHaveBeenCalled();
  });

  it('checks for an update when the page becomes visible again', () => {
    const service = setup();
    service.init();

    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () => 'visible',
    });
    document.dispatchEvent(new Event('visibilitychange'));

    expect(swUpdate.checkForUpdate).toHaveBeenCalledTimes(1);
  });

  it('does not check for an update when the page becomes hidden', () => {
    const service = setup();
    service.init();

    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () => 'hidden',
    });
    document.dispatchEvent(new Event('visibilitychange'));

    expect(swUpdate.checkForUpdate).not.toHaveBeenCalled();
  });

  it('polls for an update on an interval while the app stays open', () => {
    vi.useFakeTimers();
    const service = setup();
    service.init();

    vi.advanceTimersByTime(CHECK_INTERVAL_MS);
    expect(swUpdate.checkForUpdate).toHaveBeenCalledTimes(1);

    vi.advanceTimersByTime(CHECK_INTERVAL_MS);
    expect(swUpdate.checkForUpdate).toHaveBeenCalledTimes(2);
  });

  it('stops polling and listening once destroyed', () => {
    vi.useFakeTimers();
    const service = setup();
    service.init();

    service.ngOnDestroy();
    vi.advanceTimersByTime(CHECK_INTERVAL_MS * 2);
    document.dispatchEvent(new Event('visibilitychange'));

    expect(swUpdate.checkForUpdate).not.toHaveBeenCalled();
  });
});
