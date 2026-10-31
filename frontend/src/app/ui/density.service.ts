import { DOCUMENT } from '@angular/common';
import { Injectable, InjectionToken, Signal, inject, signal } from '@angular/core';

/**
 * Row density (spec v195 §1.4): how tall a table row is and how much
 * padding a cell and a panel get, on a desktop with a fine pointer.
 *
 * Named dense/comfortable, never "compact": Compact already means
 * ViewportService.isNarrow() (ui-design.md), and data-table.types.ts's
 * `Density = 'compact' | 'full'` is the unrelated column-set choice.
 *
 * A per-DEVICE preference, so it lives in localStorage, not in the
 * server-side PreferencesStore: a phone and a desktop signed in to the same
 * account want different rows. Dense is the default and the fallback for
 * anything unreadable. Every storage call is guarded: private mode, a
 * blocked origin or a full quota never breaks the app; the choice then
 * lasts for the session.
 *
 * The service only writes <html data-density>. tokens.css owns what that
 * means, and only inside @media (min-width: 1024px) and (pointer: fine):
 * below 1024px or under touch the 44px rules win whatever is set here.
 */
export type RowDensity = 'dense' | 'comfortable';

/** The localStorage key. Per device; never sent to the server. */
export const DENSITY_PREF_KEY = 'ui.density';

/** The two calls the service needs from a key-value store. */
export interface DensityStorage {
  get(key: string): string | null;
  set(key: string, value: string): void;
}

/** localStorage, with both calls guarded (it can be absent or throw). */
function localStorageDensity(): DensityStorage {
  return {
    get(key: string): string | null {
      try {
        return globalThis.localStorage?.getItem(key) ?? null;
      } catch {
        return null;
      }
    },
    set(key: string, value: string): void {
      try {
        globalThis.localStorage?.setItem(key, value);
      } catch {
        /* Private mode or a full quota: the choice lasts this session. */
      }
    },
  };
}

/** The store `DensityService` reads and writes; specs override it. */
export const DENSITY_STORAGE = new InjectionToken<DensityStorage>('DENSITY_STORAGE', {
  providedIn: 'root',
  factory: localStorageDensity,
});

/** The stored density: 'comfortable' only for that exact string, else dense. */
export function readDensity(storage: DensityStorage): RowDensity {
  try {
    return storage.get(DENSITY_PREF_KEY) === 'comfortable' ? 'comfortable' : 'dense';
  } catch {
    return 'dense';
  }
}

@Injectable({ providedIn: 'root' })
export class DensityService {
  private readonly storage = inject(DENSITY_STORAGE);
  private readonly root = inject(DOCUMENT).documentElement;
  private readonly current = signal<RowDensity>(readDensity(this.storage));

  /** The active density; the profile menu and the command palette read it. */
  readonly density: Signal<RowDensity> = this.current.asReadonly();

  constructor() {
    this.apply();
  }

  /** Switch density for this device: signal, attribute and storage together. */
  set(density: RowDensity): void {
    this.current.set(density);
    try {
      this.storage.set(DENSITY_PREF_KEY, density);
    } catch {
      /* A custom store may throw; the attribute still switches below. */
    }
    this.apply();
  }

  private apply(): void {
    this.root.dataset['density'] = this.current();
  }
}
