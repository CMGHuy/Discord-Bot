import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { Magnitude } from './magnitude';

function render(value: number | null, max = 4) {
  const f = TestBed.createComponent(Magnitude);
  f.componentRef.setInput('value', value);
  f.componentRef.setInput('max', max);
  f.detectChanges();
  return f.nativeElement as HTMLElement;
}

describe('Magnitude', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('scales the bar against max', () => {
    expect(render(2, 4).querySelector('.bar')!.getAttribute('style')).toContain('50%');
  });

  it('grows leftward for a negative so the zero line reads as a centre', () => {
    expect(render(-2, 4).querySelector('.bar')!.classList.contains('neg')).toBe(true);
  });

  it('clamps beyond max rather than overflowing the cell', () => {
    expect(render(99, 4).querySelector('.bar')!.getAttribute('style')).toContain('100%');
  });

  it('renders nothing for an absent value', () => {
    expect(render(null).querySelector('.bar')).toBeNull();
  });

  it('is decorative, so it is hidden from assistive tech', () => {
    // The adjacent cell already carries the number; announcing the bar too
    // would read every figure twice.
    expect(render(2).getAttribute('aria-hidden')).toBe('true');
  });
});
