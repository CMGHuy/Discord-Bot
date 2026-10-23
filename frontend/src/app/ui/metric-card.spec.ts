import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { MetricCard } from './metric-card';

describe('sb-metric-card tint (v181 §5)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  function render(inputs: Record<string, unknown>) {
    const f = TestBed.createComponent(MetricCard);
    f.componentRef.setInput('label', 'Figure');
    for (const [key, value] of Object.entries(inputs)) f.componentRef.setInput(key, value);
    f.detectChanges();
    const host = f.nativeElement as HTMLElement;
    return { host, value: host.querySelector('.value')! };
  }

  it('tints the card and colours the figure for a good or bad figure', () => {
    const good = render({ value: 1.2, tint: 'pos' });
    expect(good.host.classList.contains('tint-pos')).toBe(true);
    expect(good.value.classList.contains('pos')).toBe(true);
    const bad = render({ value: 1.2, tint: 'neg' });
    expect(bad.host.classList.contains('tint-neg')).toBe(true);
    expect(bad.value.classList.contains('neg')).toBe(true);
  });

  it('colours a warning figure without tinting the card', () => {
    const { host, value } = render({ value: 5, tint: 'warn' });
    expect(value.classList.contains('warn')).toBe(true);
    expect(host.classList.contains('tint-pos') || host.classList.contains('tint-neg')).toBe(false);
  });

  it('leaves a neutral card plain, whatever the sign', () => {
    const { host, value } = render({ value: -3, tint: 'neutral', tone: 'pnl' });
    expect(['pos', 'neg', 'warn'].some((c) => value.classList.contains(c))).toBe(false);
    expect(host.classList.contains('tint-neg')).toBe(false);
  });

  it('never colours or tints the dash of a missing figure', () => {
    const { host, value } = render({ value: null, tint: 'pos' });
    expect(value.classList.contains('absent')).toBe(true);
    expect(value.classList.contains('pos')).toBe(false);
    expect(host.classList.contains('tint-pos')).toBe(false);
  });

  it('keeps the v80 tone rule when no tint is given', () => {
    const { host, value } = render({ value: -2, tone: 'pnl' });
    expect(value.classList.contains('neg')).toBe(true);
    expect(host.classList.contains('tint-neg')).toBe(false);
  });
});
