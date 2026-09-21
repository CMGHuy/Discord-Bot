import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { MIN_SAMPLE_N, StatTile } from './stat-tile';
import { PreferencesStore } from '../stores/preferences.store';

let preferenceValues: Record<string, unknown> = {};

function render(inputs: Record<string, unknown>): HTMLElement {
  const f = TestBed.createComponent(StatTile);
  f.componentRef.setInput('label', 'Win rate');
  f.componentRef.setInput('value', '68%');
  for (const [key, val] of Object.entries(inputs)) f.componentRef.setInput(key, val);
  f.detectChanges();
  return (f.nativeElement as HTMLElement).querySelector('.tile')!;
}

describe('StatTile (v85 D23)', () => {
  beforeEach(() => {
    preferenceValues = {};
    TestBed.configureTestingModule({ providers: [
      provideZonelessChangeDetection(),
      { provide: PreferencesStore, useValue: { values: () => preferenceValues } },
    ] });
  });

  it('renders the label and the value', () => {
    const el = render({});
    expect(el.querySelector('.label')!.textContent).toContain('Win rate');
    expect(el.querySelector('.value')!.textContent).toContain('68%');
  });

  it('renders the always-visible secondary amount and compact trend', () => {
    const el = render({ secondary: '+$1,240', trend: [1, 2, 3] });
    expect(el.querySelector('.secondary')!.textContent).toContain('+$1,240');
    expect(el.querySelector('sb-sparkline')).not.toBeNull();
  });

  it('renders a null value as no-value, never as zero', () => {
    const el = render({ value: null });
    expect(el.querySelector('.value')!.textContent!.trim()).toBe('—');
    expect(el.querySelector('.value')!.textContent).not.toContain('0');
  });

  it('renders the sample size adjacent to the value', () => {
    const el = render({ sample: 412 });
    expect(el.querySelector('.sample')!.textContent).toContain('N=412');
  });

  it('omits the sample line when no sample was supplied', () => {
    expect(render({}).querySelector('.sample')).toBeNull();
  });

  it('de-emphasises a figure below the minimum sample', () => {
    const el = render({ sample: 7 });
    expect(el.classList).toContain('thin');
  });

  it('says how many more trades a thin figure needs', () => {
    const el = render({ sample: 7 });
    expect(el.querySelector('.sample')!.getAttribute('title'))
      .toContain(`${MIN_SAMPLE_N - 7} more`);
  });

  it('does not de-emphasise a figure at the minimum', () => {
    expect(render({ sample: MIN_SAMPLE_N }).classList).not.toContain('thin');
  });

  it('marks a thin figure for assistive tech, not by colour alone', () => {
    const el = render({ sample: 7 });
    expect(el.querySelector('.sample')!.textContent).toContain('thin sample');
  });

  it('carries the tone as a class', () => {
    expect(render({ tone: 'neg' }).classList).toContain('neg');
  });

  it('uses the saved minimum sample when one is configured', () => {
    preferenceValues = { minSampleN: 100 };
    expect(render({ sample: 50 }).classList).toContain('thin');
    expect(render({ sample: 60 }).querySelector('.sample')!.getAttribute('title')).toContain('40 more');
  });
});
