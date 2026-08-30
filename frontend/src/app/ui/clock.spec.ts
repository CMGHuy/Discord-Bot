import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { describe, expect, it, vi } from 'vitest';

import { CLOCK, CLOCK_INTERVAL_MS } from './clock';

describe('CLOCK', () => {
  it('ticks on the documented interval', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-08-28T10:00:00Z'));
    TestBed.configureTestingModule({});
    const now = TestBed.inject(CLOCK);
    const first = now();

    vi.advanceTimersByTime(CLOCK_INTERVAL_MS);
    expect(now()).toBeGreaterThan(first);
    vi.useRealTimers();
  });

  it('is overridable, so no real timer runs in a suite under test', () => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [{ provide: CLOCK, useValue: signal(1_700_000_000_000) }],
    });
    expect(TestBed.inject(CLOCK)()).toBe(1_700_000_000_000);
  });

  it('is 30 seconds, not one', () => {
    expect(CLOCK_INTERVAL_MS).toBe(30_000);
  });
});