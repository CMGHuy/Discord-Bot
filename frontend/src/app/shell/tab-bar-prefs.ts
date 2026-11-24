import { Injectable, InjectionToken, Signal, computed, inject, signal } from '@angular/core';

import { SessionStore } from '../stores/session.store';
import { DEFAULT_PHONE_TAB_PATHS, NAV_ENTRIES, NavEntry, navEntriesFor, phoneTabsFor } from './nav';

/**
 * The pages the phone's bottom tab bar holds -- spec v240 §6 (D9).
 *
 * A per-BROWSER preference in localStorage['ui.tabbar'], not PreferencesStore:
 * the partner chose per browser (a phone and a desktop want different bars),
 * as for ui.theme (theme.service.ts's header records why that exception to
 * the plan v21 rule holds). Its own TAB_BAR_STORAGE token, mirroring
 * THEME_STORAGE, so a spec swaps in an in-memory map.
 *
 * The stored value is a JSON array of nav paths, validated on every read
 * against the pages the login may open (navEntriesFor(isAdmin)): unknown,
 * duplicate and admin-only-for-a-viewer paths drop, the Dashboard is forced
 * first, the list is cut to MAX_TAB_PAGES; nothing valid, or not JSON, gives
 * the default. A stored '/trades/calendar' (pre-v247) is '/calendar'.
 *
 * TabBarPrefs (below) re-validates on every read and never rewrites storage
 * by reading; only an edit saves.
 */
export const TAB_BAR_PREF_KEY = 'ui.tabbar';

/** Pages on the bar, the Dashboard included; More is always added after them. */
export const MAX_TAB_PAGES = 4;

/** The pinned first tab; the editor offers it no buttons. */
const HOME_PATH = '/dashboard';

/** Paths a stored list may still hold from before a move (v247: Calendar left Trades). */
const RENAMED_TAB_PATHS: Readonly<Record<string, string>> = { '/trades/calendar': '/calendar' };

/** The two calls the service needs; a spec swaps it for an in-memory map. */
export interface TabBarStorage {
  get(key: string): string | null;
  set(key: string, value: string): void;
}

function localStorageTabBar(): TabBarStorage {
  return {
    get(key: string): string | null {
      try { return globalThis.localStorage?.getItem(key) ?? null; } catch { return null; }
    },
    set(key: string, value: string): void {
      try { globalThis.localStorage?.setItem(key, value); } catch { /* Private mode or a full quota: the choice lasts this session. */ }
    },
  };
}

export const TAB_BAR_STORAGE = new InjectionToken<TabBarStorage>('TAB_BAR_STORAGE', {
  providedIn: 'root',
  factory: localStorageTabBar,
});

function defaultPaths(known: ReadonlySet<string>): string[] {
  return DEFAULT_PHONE_TAB_PATHS.filter((path) => known.has(path));
}

/** The valid bar for a raw stored value and the pages the login may open. Pure. */
export function sanitizeTabPaths(raw: unknown, visible: readonly NavEntry[]): string[] {
  const known = new Set(visible.map((entry) => entry.path));
  if (!Array.isArray(raw)) return defaultPaths(known);
  const kept = new Set(
    raw
      .filter((item): item is string => typeof item === 'string')
      .map((path) => RENAMED_TAB_PATHS[path] ?? path)
      .filter((path) => known.has(path)),
  );
  if (kept.size === 0) return defaultPaths(known);
  kept.delete(HOME_PATH);
  const home = known.has(HOME_PATH) ? [HOME_PATH] : [];
  return [...home, ...kept].slice(0, MAX_TAB_PAGES);
}

/** The stored value parsed, or null when it is missing, not JSON or unreadable. */
function parseStored(storage: TabBarStorage): unknown {
  try {
    const text = storage.get(TAB_BAR_PREF_KEY);
    return text === null ? null : JSON.parse(text);
  } catch {
    return null;
  }
}

export function readTabPaths(storage: TabBarStorage, visible: readonly NavEntry[]): string[] {
  return sanitizeTabPaths(parseStored(storage), visible);
}

const samePaths = (a: readonly string[], b: readonly string[]) =>
  a.length === b.length && a.every((path, index) => path === b[index]);

/**
 * The phone tab bar's pages as signals (spec v240 §6). PhoneTabBar,
 * MoreSheet and phoneTabPathFor read `tabs()`; the tab-bar editor reads
 * `tabs()`/`underMore()` and calls the edit methods. Every edit goes
 * through set(), which validates like a read and saves the result.
 */
@Injectable({ providedIn: 'root' })
export class TabBarPrefs {
  private readonly storage = inject(TAB_BAR_STORAGE);
  private readonly session = inject(SessionStore);

  /** Validated against the whole model, not the login: the session loads after
   *  the shell boots, and an admin's System tab must survive that moment. */
  private readonly stored = signal<readonly string[]>(readTabPaths(this.storage, NAV_ENTRIES));
  private readonly visible = computed(() => navEntriesFor(this.session.isAdmin()));

  /** The bar's pages in order, valid for this login. */
  readonly paths: Signal<readonly string[]> = computed(
    () => sanitizeTabPaths(this.stored(), this.visible()),
    { equal: samePaths },
  );
  /** The bar's entries, with the phone labels (the Dashboard reads Home). */
  readonly tabs: Signal<readonly NavEntry[]> = computed(() => phoneTabsFor(this.paths(), this.visible()));
  /** Every other page the login may open, in rail order, with rail labels. */
  readonly underMore: Signal<readonly NavEntry[]> = computed(() => {
    const onBar = new Set(this.paths());
    return this.visible().filter((entry) => !onBar.has(entry.path));
  });
  readonly canAdd: Signal<boolean> = computed(() => this.paths().length < MAX_TAB_PAGES);
  readonly isDefault: Signal<boolean> = computed(() =>
    samePaths(this.paths(), sanitizeTabPaths(DEFAULT_PHONE_TAB_PATHS, this.visible())));

  /** Validates `paths` like a read, then saves them. A throwing store keeps the change for this session. */
  set(paths: readonly string[]): void {
    const next = sanitizeTabPaths([...paths], this.visible());
    this.stored.set(next);
    try { this.storage.set(TAB_BAR_PREF_KEY, JSON.stringify(next)); } catch { /* A custom store may throw; the bar still changes. */ }
  }

  add(path: string): void {
    if (!this.canAdd() || !this.underMore().some((entry) => entry.path === path)) return;
    this.set([...this.paths(), path]);
  }

  remove(path: string): void {
    if (path === HOME_PATH || !this.paths().includes(path)) return;
    this.set(this.paths().filter((kept) => kept !== path));
  }

  moveUp(path: string): void {
    this.swap(this.paths().indexOf(path), -1);
  }

  moveDown(path: string): void {
    this.swap(this.paths().indexOf(path), 1);
  }

  /** Back to the default; returns the list it replaced, for an Undo. */
  reset(): readonly string[] {
    const before = this.paths();
    this.set(DEFAULT_PHONE_TAB_PATHS);
    return before;
  }

  /** Swaps index with index + step; the pinned Dashboard (0) never moves. */
  private swap(index: number, step: -1 | 1): void {
    const paths = [...this.paths()];
    const target = index + step;
    if (index < 1 || target < 1 || target >= paths.length) return;
    [paths[index], paths[target]] = [paths[target], paths[index]];
    this.set(paths);
  }
}
