import { Injectable, computed, effect, inject, signal, untracked } from '@angular/core';
import { takeUntilDestroyed, toSignal } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router } from '@angular/router';
import { filter, map } from 'rxjs';

import { PreferencesStore } from '../../stores/preferences.store';
import { ViewportService } from '../../ui/breakpoints';
import { destinationFor } from '../nav';
import { dockDefaultOpen, readDockOpen, writeDockOpen } from './live-state';

/**
 * Where the Live dock is and whether it is open -- v203 (spec v202 §4, D4).
 * Keyed by the destination (`/trades`), never a section or an old path, so
 * a redirect or a tab change cannot fork the choice. Stored only through
 * PreferencesStore (server-side, no browser storage). Before the read, or
 * after a failed one, the per-page default applies. Below 1024 px the dock
 * never docks; it opens as a sheet.
 */
@Injectable({ providedIn: 'root' })
export class DockState {
  private readonly router = inject(Router);
  private readonly preferences = inject(PreferencesStore);
  private readonly viewport = inject(ViewportService);
  private readonly url = toSignal(
    this.router.events.pipe(filter((event) => event instanceof NavigationEnd), map(() => this.router.url)),
    { initialValue: this.router.url },
  );
  private readonly sheet = signal(false);

  readonly destination = computed(() => destinationFor(this.url()));
  readonly docked = computed(() => !this.viewport.isNarrow());
  readonly open = computed(() => {
    const destination = this.destination();
    const fallback = dockDefaultOpen(destination);
    if (destination === null || !this.preferences.isLoaded()) return fallback;
    return readDockOpen(this.preferences.values(), destination, fallback);
  });
  readonly sheetOpen = this.sheet.asReadonly();

  constructor() {
    this.router.events
      .pipe(filter((event) => event instanceof NavigationEnd), takeUntilDestroyed())
      .subscribe(() => this.sheet.set(false));
    effect(() => {
      if (this.docked()) untracked(() => this.sheet.set(false));
    });
  }

  /** Flips the current destination's choice; off the nav model it writes nothing. */
  toggle(): void {
    const destination = this.destination();
    if (destination === null) return;
    const next = !this.open();
    this.preferences.update((prefs) => writeDockOpen(prefs, destination, next));
  }

  /** What an alarm or a strip tap asks for: the docked dock open, or the sheet. */
  reveal(): void {
    if (!this.docked()) {
      this.openSheet();
      return;
    }
    if (!this.open()) this.toggle();
  }

  openSheet(): void {
    this.sheet.set(true);
  }

  closeSheet(): void {
    this.sheet.set(false);
  }
}
