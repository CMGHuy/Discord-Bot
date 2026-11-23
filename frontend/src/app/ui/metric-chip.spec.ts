import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { MetricChip } from './metric-chip';

/* v240 §1: the chip's figure carries a true minus on a loss, the same
 * fixed() rule as sb-metric-card. */
describe('sb-metric-chip', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  function render(inputs: Record<string, unknown>): HTMLElement {
    const f = TestBed.createComponent(MetricChip);
    f.componentRef.setInput('label', 'ExpR');
    for (const [key, value] of Object.entries(inputs)) f.componentRef.setInput(key, value);
    f.detectChanges();
    return f.nativeElement as HTMLElement;
  }

  const valueText = (host: HTMLElement) => host.querySelector('.value')!.textContent!.trim();

  it('prints a loss with U+2212, never a hyphen', () => {
    const text = valueText(render({ value: -0.42, decimals: 2, unit: 'R' }));
    expect(text).toBe('−0.42R');
    expect(text).not.toContain('-');
  });

  it('prints a gain unsigned and a rounded-away loss as an unsigned zero', () => {
    expect(valueText(render({ value: 0.42, decimals: 2, unit: 'R' }))).toBe('0.42R');
    expect(valueText(render({ value: -0.004, decimals: 2, unit: 'R' }))).toBe('0.00R');
  });

  it('shows the label', () => {
    expect(render({ value: 1 }).querySelector('.label')!.textContent!.trim()).toBe('ExpR');
  });
});
