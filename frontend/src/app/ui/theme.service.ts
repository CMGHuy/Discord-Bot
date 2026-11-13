import { DOCUMENT } from '@angular/common';
import { Injectable, InjectionToken, Signal, inject, signal } from '@angular/core';

/**
 * The two looks of the admin UI: Black (Graphite) and Dark blue (Navy), spec
 * v225. tokens.css owns what `data-theme="navy"` means; this file only decides
 * which one is on.
 *
 * It is a per-BROWSER preference kept in localStorage, not `PreferencesStore`:
 * the partner chose per browser, and index.html's pre-paint script must read it
 * before the bundle parses (`PreferencesStore` loads over HTTP after the shell
 * boots). The plan v21 rule "shell preferences go through PreferencesStore" is
 * about account-level settings and does not cover this one.
 *
 * Anything unreadable is Graphite, and a junk stored value is not rewritten
 * until the user chooses.
 */
export type Theme = 'graphite' | 'navy';

export const THEME_PREF_KEY = 'ui.theme';

/** The two calls the service needs; a spec swaps it for an in-memory map. */
export interface ThemeStorage {
  get(key: string): string | null;
  set(key: string, value: string): void;
}

function localStorageTheme(): ThemeStorage {
  return {
    get(key: string): string | null {
      try { return globalThis.localStorage?.getItem(key) ?? null; } catch { return null; }
    },
    set(key: string, value: string): void {
      try { globalThis.localStorage?.setItem(key, value); } catch { /* Private mode or a full quota: the choice lasts this session. */ }
    },
  };
}

export const THEME_STORAGE = new InjectionToken<ThemeStorage>('THEME_STORAGE', { providedIn: 'root', factory: localStorageTheme });

/** Navy only for the exact stored string `navy`; everything else is Graphite. */
export function readTheme(storage: ThemeStorage): Theme {
  try { return storage.get(THEME_PREF_KEY) === 'navy' ? 'navy' : 'graphite'; } catch { return 'graphite'; }
}

@Injectable({ providedIn: 'root' })
export class ThemeService {
  private readonly storage = inject(THEME_STORAGE);
  private readonly root = inject(DOCUMENT).documentElement;
  private readonly current = signal<Theme>(readTheme(this.storage));
  readonly theme: Signal<Theme> = this.current.asReadonly();

  constructor() { this.apply(); }

  set(theme: Theme): void {
    this.current.set(theme);
    try { this.storage.set(THEME_PREF_KEY, theme); } catch { /* A custom store may throw; the attribute still switches below. */ }
    this.apply();
  }

  toggle(): void {
    this.set(this.current() === 'navy' ? 'graphite' : 'navy');
  }

  private apply(): void {
    this.root.dataset['theme'] = this.current();
    // The browser chrome follows --bg. Read back, never a literal: the colour
    // gate (primitives.spec.ts) allows no hex in a .ts file.
    const bg = getComputedStyle(this.root).getPropertyValue('--bg').trim();
    const meta = this.root.ownerDocument.querySelector<HTMLMetaElement>('meta[name="theme-color"]');
    if (meta && bg) meta.content = bg;
  }
}
