import { readFileSync } from 'node:fs';
import { join } from 'node:path';
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

describe('StatTile: one variant everywhere (v179 §3.3)', () => {
  const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/stat-tile.ts'), 'utf8');
  const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  /** The rule whose selector starts a line, so `.value` is not `.pos .value`. */
  const rule = (selector: string) =>
    SOURCE.match(new RegExp(`(?:^|\\n)\\s*${esc(selector)}\\s*\\{[^}]*\\}`))?.[0] ?? '';

  beforeEach(() => {
    preferenceValues = {};
    TestBed.configureTestingModule({ providers: [
      provideZonelessChangeDetection(),
      { provide: PreferencesStore, useValue: { values: () => preferenceValues } },
    ] });
  });

  it('fills its grid cell, so tiles in one row share a height', () => {
    for (const declaration of ['display: block', 'height: 100%', 'min-width: 0']) {
      expect(rule(':host')).toContain(declaration);
    }
    expect(rule('.tile')).toContain('height: 100%');
    expect(rule('.tile')).toContain('box-sizing: border-box');
    expect(rule('.tile')).toContain('min-width: 0');
  });

  it('stacks its parts left-aligned and has no inline or centred variant', () => {
    expect(rule('.tile')).toContain('flex-direction: column');
    expect(rule('.tile')).toContain('text-align: start');
    expect(SOURCE).not.toMatch(/justify-content:\s*center|flex-direction:\s*row/);
  });

  it('sets the value, the secondary and N= in the numeric face', () => {
    expect(rule('.value')).toContain('font-family: var(--font-num)');
    expect(SOURCE).toMatch(/\.sample, \.secondary \{ font-family: var\(--font-num\); \}/);
  });

  it('wraps a long label or caption instead of widening its track', () => {
    expect(rule('.label')).toContain('overflow-wrap: anywhere');
    expect(rule('.value')).toContain('overflow-wrap: anywhere');
  });

  it('renders label, value, secondary, N= and hint in that order, captions kept', () => {
    const el = render({ secondary: '+1,240.00 €', sample: 412, hint: 'Pre-tax, paper trades.' });
    expect([...el.children].map((child) => child.className.split(' ')[0]))
      .toEqual(['label', 'value', 'secondary', 'sample', 'hint']);
    expect(el.querySelector('.hint')!.textContent).toContain('Pre-tax, paper trades.');
  });
});
