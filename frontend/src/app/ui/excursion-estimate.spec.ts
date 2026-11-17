import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import {
  EXCURSION_EST_EXPLANATION,
  EXCURSION_EST_LABEL,
  ExcursionEstimate,
  isDailyEstimate,
} from './excursion-estimate';

describe('isDailyEstimate (v228, mirrors exit_quality.is_daily_estimate)', () => {
  it.each([
    ['daily', 0.5, true],
    ['daily', 1.99, true],
    ['daily', 0, true],
    ['daily', 2, false],
    ['daily', 3.2, false],
    // An unknown hold on daily bars is a short hold (V228-9's rule): every
    // daily figure is either trusted or marked, never neither.
    ['daily', null, true],
    ['daily', undefined, true],
    ['daily', Number.NaN, true],
    ['5min', 0.5, false],
    ['15min', null, false],
    ['hourly', 0.1, false],
    [null, 0.5, false],
    [undefined, undefined, false],
    ['', 0.5, false],
  ] as const)('source %s held %s days -> %s', (source, held, expected) => {
    expect(isDailyEstimate(source, held)).toBe(expected);
  });
});

describe('ExcursionEstimate', () => {
  beforeEach(() => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  const render = (): HTMLElement => {
    const fixture = TestBed.createComponent(ExcursionEstimate);
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  };

  it('shows the meaning as visible text, not behind a hover', () => {
    const el = render();
    expect(el.querySelector('.est')?.textContent?.trim()).toBe(EXCURSION_EST_LABEL);
    expect(EXCURSION_EST_LABEL).toBe('est. (daily bars)');
    expect(el.querySelector('[title]')).toBeNull();
  });

  it('puts the explanation in a tap- and keyboard-reachable hint with an aria-label', () => {
    const el = render();
    const trigger = el.querySelector<HTMLButtonElement>('sb-hint button.trigger');
    expect(trigger).not.toBeNull();
    expect(trigger!.tagName).toBe('BUTTON');            // focusable by Tab, opens on tap
    expect(trigger!.getAttribute('aria-label')).toBe('About this estimate');
    expect(el.querySelector('sb-hint [role="tooltip"]')?.textContent?.trim())
      .toBe(EXCURSION_EST_EXPLANATION);
    expect(EXCURSION_EST_EXPLANATION)
      .toBe('Held under 2 days, intraday bars unavailable, the range may be overstated.');
  });
});
