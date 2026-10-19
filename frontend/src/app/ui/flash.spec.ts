import { TestBed } from '@angular/core/testing';
import { Component, provideZonelessChangeDetection, signal } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { Flash } from './flash';
import { MotionStarts } from './motion/motion-starts';
import { provideMotion } from './motion/motion.service';

@Component({
  imports: [Flash],
  template: `<span [sbFlash]="value()">{{ value() }}</span>`,
})
class Host { value = signal(1); }

function setup() {
  const f = TestBed.createComponent(Host);
  f.detectChanges();
  return { f, span: (f.nativeElement as HTMLElement).querySelector('span')! };
}

describe('Flash', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection(), provideMotion('on')] });
  });

  it('does not flash on first render', () => {
    // Everything is "new" on arrival; flashing every cell would be a
    // full-screen strobe on load.
    expect(setup().span.classList.contains('flash-up')).toBe(false);
  });

  it('flashes up when the value rises', () => {
    const { f, span } = setup();
    f.componentInstance.value.set(2);
    f.detectChanges();
    expect(span.classList.contains('flash-up')).toBe(true);
  });

  it('flashes down when the value falls', () => {
    const { f, span } = setup();
    f.componentInstance.value.set(0);
    f.detectChanges();
    expect(span.classList.contains('flash-down')).toBe(true);
  });

  it('does not flash when a re-render reports the same value', () => {
    const { f, span } = setup();
    f.componentInstance.value.set(1);
    f.detectChanges();
    expect(span.className).toBe('');
  });
});

/* Spec v168 §3 #8: under Off --motion-scale is 0, so the flash would last 0s
 * and, with no animation running, animationend would never fire to remove the
 * class. The directive therefore adds nothing under Off. */
describe('Flash under Motion = Off', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection(), provideMotion('off')] });
  });

  it('adds no class when the value changes', () => {
    const { f, span } = setup();
    f.componentInstance.value.set(2);
    f.detectChanges();
    f.componentInstance.value.set(0);
    f.detectChanges();
    expect(span.className).toBe('');
    expect(TestBed.inject(MotionStarts).count('flash')).toBe(0);
  });
});

describe('Flash records its starts (v168 §4)', () => {
  it('records one flash per real change, none on first render or a repeat', () => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection(), provideMotion('on')] });
    const starts = TestBed.inject(MotionStarts);
    const { f } = setup();
    expect(starts.count('flash')).toBe(0);
    f.componentInstance.value.set(2);
    f.detectChanges();
    f.componentInstance.value.set(2);
    f.detectChanges();
    f.componentInstance.value.set(1);
    f.detectChanges();
    expect(starts.entries()).toEqual([
      { kind: 'flash', key: 'flash' },
      { kind: 'flash', key: 'flash' },
    ]);
  });

  it('still flashes under Reduced (the tint is colour, not movement)', () => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection(), provideMotion('reduced')] });
    const { f, span } = setup();
    f.componentInstance.value.set(2);
    f.detectChanges();
    expect(span.classList).toContain('flash-up');
  });
});
