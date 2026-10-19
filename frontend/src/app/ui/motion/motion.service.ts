import { Injectable, InjectionToken, Provider, Signal, computed, inject, signal } from '@angular/core';

import { PreferencesStore } from '../../stores/preferences.store';

/** The three choices the Motion control offers (spec v168 §1). */
export type MotionMode = 'on' | 'reduced' | 'off';
/** A mode, or `pending` until preferences have loaded. */
export type MotionState = MotionMode | 'pending';

export const MOTION_MODES: readonly MotionMode[] = ['on', 'reduced', 'off'];
/** Stored only through PreferencesStore, never localStorage (plan v21). */
export const MOTION_PREF_KEY = 'shell.motion';

/** A stored value, validated rather than trusted: anything unknown is On. */
export function parseMotion(stored: unknown): MotionMode {
  return MOTION_MODES.includes(stored as MotionMode) ? (stored as MotionMode) : 'on';
}

/**
 * Global the spec setup file sets to give every spec a default mode. It is a
 * global, not a TestBed provider, because under `ng test` src/test-setup.ts is
 * evaluated as its own module copy (so its MOTION_FIXED is not the specs'),
 * while `globalThis` is shared. Unset in the browser.
 */
export const MOTION_TEST_DEFAULT_KEY = '__sbMotionTestDefault';

function testDefault(): MotionState | null {
  const value = (globalThis as Record<string, unknown>)[MOTION_TEST_DEFAULT_KEY];
  return MOTION_MODES.includes(value as MotionMode) ? (value as MotionMode) : null;
}

/**
 * A fixed mode, for tests. `null` means "follow the user's preference"; the
 * root default is `null` in the browser and the test default in a spec.
 */
export const MOTION_FIXED = new InjectionToken<MotionState | null>('MOTION_FIXED', {
  providedIn: 'root',
  factory: testDefault,
});

/** Pin the mode (`'on'`, `'reduced'`, `'off'`, `'pending'`) or follow preferences (`'live'`). */
export function provideMotion(mode: MotionState | 'live'): Provider {
  return { provide: MOTION_FIXED, useValue: mode === 'live' ? null : mode };
}

/**
 * The one TS source of the motion mode (spec v168 §1). The shell writes it
 * to <html data-motion>, which is all the CSS reads; TS reads it here, never
 * from the attribute.
 *
 * **The OS reduced-motion setting is ignored by design (spec D2).** Windows
 * reports it whenever "Animation effects" is off, which is common on
 * laptops, and honouring it left the admin with no motion and no way back.
 * The Motion control (default On) is the switch, so this never asks the
 * browser for that media feature.
 *
 * `pending` until PreferencesStore has loaded (it also counts as loaded
 * when the GET fails), so a user who chose Off never sees a cold-load burst.
 */
@Injectable({ providedIn: 'root' })
export class MotionService {
  private readonly fixed = signal(inject(MOTION_FIXED));
  /** Injected only when following preferences: a fixed-mode spec needs no HttpClient. */
  private readonly preferences = this.fixed() === null ? inject(PreferencesStore) : null;

  readonly mode: Signal<MotionState> = computed(() => this.fixed() ?? this.stored());
  /** Everything runs: count-up, draw-in, lift, ping, drift. */
  readonly full: Signal<boolean> = computed(() => this.mode() === 'on');
  /** Entrances and dialog transitions run (as a fade under Reduced). */
  readonly active: Signal<boolean> = computed(() => this.mode() === 'on' || this.mode() === 'reduced');

  set(mode: MotionMode): void {
    if (this.preferences === null) {
      this.fixed.set(mode);
      return;
    }
    this.preferences.update((prefs) => ({ ...prefs, [MOTION_PREF_KEY]: mode }));
  }

  private stored(): MotionState {
    const preferences = this.preferences!;
    if (!preferences.isLoaded()) return 'pending';
    return parseMotion(preferences.values()[MOTION_PREF_KEY]);
  }
}
