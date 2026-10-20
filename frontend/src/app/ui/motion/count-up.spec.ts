import { Component, provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { PreferencesStore } from '../../stores/preferences.store';
import { Figure } from '../figure';
import { MetricCard } from '../metric-card';
import { MetricChip } from '../metric-chip';
import { StatTile } from '../stat-tile';
import { COUNT_MS, CountUp, easeOutCubic } from './count-up';
import { MotionStarts } from './motion-starts';
import { MotionState, provideMotion } from './motion.service';

let frames: FrameRequestCallback[] = [];
let handles = new Map<number, FrameRequestCallback>();

/** Runs every queued frame at time `at` (ms); frames they queue wait for the next call. */
function frame(at: number): void {
  const due = frames;
  frames = [];
  for (const callback of due) callback(at);
}

function configure(mode: MotionState): void {
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideRouter([]),
      provideMotion(mode),
      { provide: PreferencesStore, useValue: { values: () => ({}) } },
    ],
  });
}

@Component({
  imports: [CountUp],
  template: `<span class="value" [sbCountUp]="value()" [countFormat]="format" countKey="figure:Expectancy"
    [countAbsent]="absent()"></span>`,
})
class Host {
  readonly value = signal<number | null>(100);
  readonly absent = signal('—');
  readonly format = (value: number) => value.toFixed(1);
}

function mount() {
  const fixture = TestBed.createComponent(Host);
  fixture.detectChanges();
  const span = (fixture.nativeElement as HTMLElement).querySelector('.value') as HTMLElement;
  return { fixture, span, text: () => span.textContent };
}

beforeEach(() => {
  frames = [];
  handles = new Map();
  // Zoneless Angular races its own change-detection flush against
  // requestAnimationFrame and cancels the loser, so a bare queue would hold
  // (and cancel) Angular's callbacks too. Only the directive's step frames
  // are queued; cancel removes exactly its own handle.
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
    if (callback.name !== 'step') return 0;
    frames.push(callback);
    handles.set(frames.length, callback);
    return frames.length;
  });
  vi.stubGlobal('cancelAnimationFrame', (handle: number) => {
    const callback = handles.get(handle);
    frames = frames.filter((queued) => queued !== callback);
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('easeOutCubic', () => {
  it('runs 0 to 1 and is past three quarters at the midpoint', () => {
    expect(easeOutCubic(0)).toBe(0);
    expect(easeOutCubic(0.5)).toBe(0.875);
    expect(easeOutCubic(1)).toBe(1);
  });
});

describe('CountUp (spec v168 §3 #3)', () => {
  it('under On counts 0 to the value through intermediate values and settles on the formatted value', () => {
    configure('on');
    const { text } = mount();
    expect(text()).toBe('0.0');
    frame(0);
    frame(COUNT_MS / 2);
    expect(text()).toBe('87.5');
    frame(COUNT_MS);
    expect(text()).toBe('100.0');
    expect(frames).toHaveLength(0);
    expect(TestBed.inject(MotionStarts).entries()).toEqual([{ kind: 'count-first', key: 'figure:Expectancy' }]);
  });

  it('under On eases a later change from A to B', () => {
    configure('on');
    const { fixture, text } = mount();
    frame(0);
    frame(COUNT_MS);
    fixture.componentInstance.value.set(200);
    fixture.detectChanges();
    expect(text()).toBe('100.0');
    frame(1000);
    frame(1000 + COUNT_MS / 2);
    expect(text()).toBe('187.5');
    frame(1000 + COUNT_MS);
    expect(text()).toBe('200.0');
    expect(TestBed.inject(MotionStarts).count('count-change')).toBe(1);
  });

  it('shows the absent text at once for null, with no count', () => {
    configure('on');
    TestBed.overrideTemplate(Host, `<span class="value" [sbCountUp]="null" [countFormat]="format"
      countKey="figure:Expectancy"></span>`);
    const { text } = mount();
    expect(text()).toBe('—');
    expect(frames).toHaveLength(0);
    expect(TestBed.inject(MotionStarts).entries()).toEqual([]);
  });

  it('uses countAbsent for null when one is given', () => {
    configure('on');
    const { fixture, text } = mount();
    fixture.componentInstance.absent.set('n/a');
    fixture.componentInstance.value.set(null);
    fixture.detectChanges();
    expect(text()).toBe('n/a');
  });

  for (const mode of ['off', 'reduced', 'pending'] as const) {
    it(`under ${mode} renders the final value synchronously, first value and changes alike`, () => {
      configure(mode);
      const { fixture, text } = mount();
      expect(text()).toBe('100.0');
      fixture.componentInstance.value.set(42);
      fixture.detectChanges();
      expect(text()).toBe('42.0');
      expect(frames).toHaveLength(0);
      expect(TestBed.inject(MotionStarts).entries()).toEqual([]);
    });
  }

  it('does not replay: a re-created element with a spent claim renders its final value', () => {
    configure('on');
    const first = mount();
    first.fixture.destroy();
    const second = mount();
    expect(second.text()).toBe('100.0');
    expect(TestBed.inject(MotionStarts).count('count-first')).toBe(1);
  });

  it('cancels its frame on destroy', () => {
    configure('on');
    const { fixture } = mount();
    expect(frames).toHaveLength(1);
    fixture.destroy();
    expect(frames).toHaveLength(0);
  });

  it('writes the final value when requestAnimationFrame does not exist', () => {
    vi.stubGlobal('requestAnimationFrame', undefined);
    configure('on');
    const { text } = mount();
    expect(text()).toBe('100.0');
  });
});

describe('CountUp wired into the KPI primitives (spec amendment 1)', () => {
  function finish(): void {
    frame(0);
    frame(COUNT_MS);
  }

  it('sb-figure counts its value and settles on the unit-formatted text', () => {
    configure('on');
    const f = TestBed.createComponent(Figure);
    f.componentRef.setInput('label', 'Expectancy');
    f.componentRef.setInput('value', 1234.5);
    f.componentRef.setInput('unit', '%');
    f.componentRef.setInput('decimals', 1);
    f.detectChanges();
    const value = (f.nativeElement as HTMLElement).querySelector('.value')!;
    expect(value.textContent).toBe('0.0%');
    finish();
    expect(value.textContent).toBe('1,234.5%');
    expect(TestBed.inject(MotionStarts).entries()).toEqual([{ kind: 'count-first', key: 'figure:Expectancy' }]);
  });

  it('sb-stat-tile counts the number inside its pre-formatted text', () => {
    configure('on');
    const f = TestBed.createComponent(StatTile);
    f.componentRef.setInput('label', 'Total P&L');
    f.componentRef.setInput('value', '+$1,240');
    f.detectChanges();
    const value = (f.nativeElement as HTMLElement).querySelector('.value')!;
    expect(value.textContent).toBe('+$0');
    finish();
    expect(value.textContent).toBe('+$1,240');
    expect(TestBed.inject(MotionStarts).entries()).toEqual([{ kind: 'count-first', key: 'stat:Total P&L' }]);
  });

  it('sb-stat-tile shows text with no number as it is', () => {
    configure('on');
    const f = TestBed.createComponent(StatTile);
    f.componentRef.setInput('label', 'Status');
    f.componentRef.setInput('value', 'n/a');
    f.detectChanges();
    expect((f.nativeElement as HTMLElement).querySelector('.value')!.textContent).toBe('n/a');
    expect(frames).toHaveLength(0);
  });

  it('sb-metric-card counts with toFixed and its unit', () => {
    configure('on');
    const f = TestBed.createComponent(MetricCard);
    f.componentRef.setInput('label', 'Balance');
    f.componentRef.setInput('value', 50);
    f.componentRef.setInput('unit', ' €');
    f.detectChanges();
    const value = (f.nativeElement as HTMLElement).querySelector('.value')!;
    finish();
    expect(value.textContent).toBe('50.00 €');
    expect(TestBed.inject(MotionStarts).entries()).toEqual([{ kind: 'count-first', key: 'metric:Balance' }]);
  });

  it('sb-metric-chip counts with toFixed and its unit', () => {
    configure('on');
    const f = TestBed.createComponent(MetricChip);
    f.componentRef.setInput('label', 'Win rate');
    f.componentRef.setInput('value', 61);
    f.componentRef.setInput('unit', '%');
    f.componentRef.setInput('decimals', 0);
    f.detectChanges();
    const value = (f.nativeElement as HTMLElement).querySelector('.value')!;
    finish();
    expect(value.textContent).toBe('61%');
    expect(TestBed.inject(MotionStarts).entries()).toEqual([{ kind: 'count-first', key: 'chip:Win rate' }]);
  });

  it('sb-figure shows its final value at once under the Off test default', () => {
    configure('off');
    const f = TestBed.createComponent(Figure);
    f.componentRef.setInput('label', 'Expectancy');
    f.componentRef.setInput('value', 54.23);
    f.componentRef.setInput('unit', '%');
    f.componentRef.setInput('decimals', 1);
    f.detectChanges();
    expect((f.nativeElement as HTMLElement).querySelector('.value')!.textContent).toBe('54.2%');
  });
});
