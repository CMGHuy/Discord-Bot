import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { MotionStarts } from './motion-starts';

/**
 * jsdom has no getAnimations() and fires no animationstart, so the no-replay
 * gate (spec v168 §4) observes this log instead: the route host, count-up,
 * draw-in and flash record every animation they START.
 */
describe('MotionStarts', () => {
  let starts: MotionStarts;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    starts = TestBed.inject(MotionStarts);
  });

  it('logs starts in order and counts them by kind', () => {
    starts.record('entrance', 'route');
    starts.record('count-first', 'stat:Win rate');
    starts.record('count-first', 'figure:Expectancy');
    starts.record('flash', 'flash');
    expect(starts.entries()).toEqual([
      { kind: 'entrance', key: 'route' },
      { kind: 'count-first', key: 'stat:Win rate' },
      { kind: 'count-first', key: 'figure:Expectancy' },
      { kind: 'flash', key: 'flash' },
    ]);
    expect(starts.count('count-first')).toBe(2);
    expect(starts.count('draw-in')).toBe(0);
  });

  it('hands out a copy, not its own log', () => {
    starts.record('draw-in', 'donut');
    const seen = starts.entries() as { kind: string; key: string }[];
    seen.length = 0;
    expect(starts.entries()).toHaveLength(1);
  });

  it('clears', () => {
    starts.record('entrance', 'route');
    starts.clear();
    expect(starts.entries()).toEqual([]);
    expect(starts.count('entrance')).toBe(0);
  });

  it('keeps only the latest 200, so a long-lived page cannot grow it', () => {
    for (let i = 0; i < 205; i++) starts.record('flash', `k${i}`);
    expect(starts.entries()).toHaveLength(200);
    expect(starts.entries()[0]).toEqual({ kind: 'flash', key: 'k5' });
  });
});
