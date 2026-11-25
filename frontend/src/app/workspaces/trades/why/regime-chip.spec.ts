import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { RegimeChip, regimeChip } from './regime-chip';

describe('regimeChip', () => {
  it.each([
    ['would_veto', { label: 'would skip', tone: 'bad', prefix: '×' }],
    ['caution', { label: 'caution', tone: 'warn', prefix: '!' }],
    ['pullback_watch', { label: 'pullback watch', tone: 'info', prefix: '↺' }],
    ['aligned', { label: 'aligned', tone: 'neutral', prefix: '' }],
  ])('maps %s to its words, colour and text prefix', (action, chip) => {
    expect(regimeChip({ bear_regime: 'CORRECTION', regime_action: action })).toEqual(chip);
  });

  it.each([
    ['no context', null],
    ['undefined context', undefined],
    ['a legacy plan without the keys', { rs_pctile: 62 }],
    ['a state without an action', { bear_regime: 'BEAR' }],
    ['action none', { bear_regime: 'NORMAL', regime_action: 'none' }],
    ['an unknown action', { regime_action: 'would_short' }],
    ['a non-string action', { regime_action: 42 }],
  ])('shows no chip for %s', (_name, ctx) => {
    expect(regimeChip(ctx as Record<string, unknown> | null | undefined)).toBeNull();
  });

  it("reads the stamped action, never the plan's state or today's", () => {
    expect(regimeChip({ bear_regime: 'NORMAL', regime_action: 'would_veto' })?.label).toBe('would skip');
  });
});

describe('sb-regime-chip', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  function render(context: Record<string, unknown> | null): HTMLElement {
    const fixture = TestBed.createComponent(RegimeChip);
    fixture.componentRef.setInput('context', context);
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('renders the prefix, the words and the tone, lower case', () => {
    const el = render({ bear_regime: 'BEAR', regime_action: 'would_veto' });
    const chip = el.querySelector('sb-chip .chip') as HTMLElement;
    expect(chip.textContent?.trim()).toBe('× would skip');
    expect(chip.classList).toContain('bad');
    expect(chip.classList).not.toContain('caps');
  });

  it('renders an aligned chip without a prefix', () => {
    expect(render({ regime_action: 'aligned' }).querySelector('sb-chip')?.textContent?.trim()).toBe('aligned');
  });

  it('names itself for hover and for assistive tech', () => {
    const el = render({ regime_action: 'caution' });
    expect(el.querySelector('.regime-chip')?.getAttribute('title'))
      .toBe('Regime when issued: caution (shadow, no effect on this plan)');
    expect(el.querySelector('.sr')?.textContent?.trim()).toBe('Regime when issued:');
  });

  it('renders nothing for a legacy plan', () => {
    expect(render({ rs_pctile: 62 }).querySelector('.regime-chip')).toBeNull();
  });

  it('takes its own line on a phone and is never truncated', () => {
    const src = readFileSync(join(process.cwd(), 'src/app/workspaces/trades/why/regime-chip.ts'), 'utf8');
    expect(src).toMatch(/@media \(max-width: 639px\) \{\s*:host \{ flex-basis: 100%; \}/);
    // A max-width declaration (ends in `;`), not the 639px media query above.
    expect(src).not.toMatch(/text-overflow|max-width: \d+\w*;/);
  });
});
