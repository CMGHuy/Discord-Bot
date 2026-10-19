import { provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { PreferencesStore } from '../../stores/preferences.store';
import { installMatchMediaPolyfill } from '../../testing/match-media-polyfill';
import {
  MOTION_MODES,
  MOTION_PREF_KEY,
  MotionService,
  MotionState,
  parseMotion,
  provideMotion,
} from './motion.service';

type Prefs = Record<string, unknown>;

/** A stand-in for the signal store: the three members MotionService reads. */
function fakePreferences(loaded: boolean, values: Prefs = {}) {
  const isLoaded = signal(loaded);
  const current = signal<Prefs>(values);
  const update = vi.fn((mutate: (prefs: Prefs) => Prefs) => current.update(mutate));
  return { isLoaded, current, update, store: { isLoaded, values: current, update } };
}

function live(fake: ReturnType<typeof fakePreferences>): MotionService {
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideMotion('live'),
      { provide: PreferencesStore, useValue: fake.store },
    ],
  });
  return TestBed.inject(MotionService);
}

function fixed(mode: MotionState): MotionService {
  TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection(), provideMotion(mode)] });
  return TestBed.inject(MotionService);
}

describe('parseMotion', () => {
  it('accepts the three modes', () => {
    for (const mode of MOTION_MODES) expect(parseMotion(mode)).toBe(mode);
  });

  it('falls back to on for anything else (validated, not trusted)', () => {
    for (const junk of [undefined, null, '', 'pending', 'fast', 'ON', 42, {}]) {
      expect(parseMotion(junk), String(junk)).toBe('on');
    }
  });
});

describe('MotionService, live (spec v168 §1)', () => {
  afterEach(() => vi.restoreAllMocks());

  it('is pending until preferences load, so a cold load plays nothing', () => {
    const fake = fakePreferences(false);
    const motion = live(fake);
    expect(motion.mode()).toBe('pending');
    fake.isLoaded.set(true);
    expect(motion.mode()).toBe('on');
  });

  it('defaults to on when nothing is stored', () => {
    expect(live(fakePreferences(true)).mode()).toBe('on');
  });

  it('restores a persisted value', () => {
    expect(live(fakePreferences(true, { [MOTION_PREF_KEY]: 'reduced' })).mode()).toBe('reduced');
  });

  it('restores off', () => {
    expect(live(fakePreferences(true, { 'shell.motion': 'off' })).mode()).toBe('off');
  });

  it('falls back to on for an unknown stored value', () => {
    expect(live(fakePreferences(true, { 'shell.motion': 'sparkly' })).mode()).toBe('on');
  });

  it('persists a choice through PreferencesStore under shell.motion, keeping other keys', () => {
    const fake = fakePreferences(true, { 'shell.zoom': 110 });
    const motion = live(fake);
    motion.set('off');
    expect(fake.update).toHaveBeenCalledTimes(1);
    expect(fake.current()).toEqual({ 'shell.zoom': 110, 'shell.motion': 'off' });
    expect(motion.mode()).toBe('off');
  });

  it('never consults the OS reduced-motion setting (spec D2)', () => {
    installMatchMediaPolyfill();
    const spy = vi.spyOn(window, 'matchMedia');
    const fake = fakePreferences(false);
    const motion = live(fake);
    motion.mode();
    fake.isLoaded.set(true);
    motion.mode();
    motion.full();
    motion.active();
    motion.set('reduced');
    motion.mode();
    expect(spy).not.toHaveBeenCalled();
  });
});

describe('MotionService, fixed', () => {
  it('derives full and active from the mode', () => {
    const table: [MotionState, boolean, boolean][] = [
      ['on', true, true],
      ['reduced', false, true],
      ['off', false, false],
      ['pending', false, false],
    ];
    for (const [mode, full, active] of table) {
      TestBed.resetTestingModule();
      const motion = fixed(mode);
      expect([motion.mode(), motion.full(), motion.active()], mode).toEqual([mode, full, active]);
    }
  });

  it('needs no PreferencesStore (and so no HttpClient), and set() stays local', () => {
    const motion = fixed('on');
    motion.set('reduced');
    expect(motion.mode()).toBe('reduced');
  });

  it('is off for every spec that does not ask (the global test default)', () => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    expect(TestBed.inject(MotionService).mode()).toBe('off');
  });
});
