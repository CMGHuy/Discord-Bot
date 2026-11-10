import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { TapeShock } from '../api/models';
import { ShockPill } from './shock-pill';
import { shockSummary } from './tape/tape';

const base: TapeShock = {
  label: 'SHOCK', since: '2026-11-05T14:45:00+00:00', as_of: '2026-11-05T15:00:00+00:00',
  breadth_pct: 42, sectors_down: 5, sectors_total: 8, spy_atr_move: -1.8, qqq_atr_move: -2.3,
  vix_level: 21.13, vix_chg_pct: 27.2, vix_missing: false,
};

describe('ShockPill (v210, phone header)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  function render(shock: TapeShock | null): HTMLElement {
    const fixture = TestBed.createComponent(ShockPill);
    fixture.componentRef.setInput('shock', shock);
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  const empty = (el: HTMLElement) => el.innerHTML.replace(/<!--[\s\S]*?-->/g, '').trim();

  it.each(['SHOCK', 'RECOVERY'] as const)('shows %s as a word of its own', (label) => {
    const pill = render({ ...base, label }).querySelector('.shock-pill')!;
    expect(pill.textContent!.trim()).toBe(label);
    expect(pill.getAttribute('data-label')).toBe(label);
  });

  it('renders nothing on NORMAL', () => {
    expect(empty(render({ ...base, label: 'NORMAL' }))).toBe('');
  });

  it('renders nothing without a shock object (detector off)', () => {
    expect(empty(render(null))).toBe('');
  });

  it('reads the full summary to a screen reader, VIX missing included', () => {
    const missing: TapeShock = { ...base, label: 'RECOVERY', vix_level: null, vix_chg_pct: null, vix_missing: true };
    const pill = render(missing).querySelector('.shock-pill')!;
    expect(pill.getAttribute('role')).toBe('status');
    expect(pill.getAttribute('aria-label')).toBe(shockSummary(missing));
    expect(pill.getAttribute('aria-label')).toContain('VIX missing');
    expect(pill.getAttribute('title')).toBe(shockSummary(missing));
    expect(pill.textContent!.trim()).toBe('RECOVERY');
  });

  it('is a status, not a tap target: no link, no button, no tabindex', () => {
    const el = render(base);
    const pill = el.querySelector('.shock-pill')!;
    expect(pill.tagName).toBe('SPAN');
    expect(el.querySelector('a, button, [tabindex]')).toBeNull();
  });

  it('hides its host from 640px and never grows the 48px phone bar', () => {
    const src = readFileSync(join(process.cwd(), 'src/app/shell/shock-pill.ts'), 'utf8');
    expect(src).toMatch(/@media \(min-width: 640px\) \{\s*:host \{ display: none; \}/);
    expect(src).toMatch(/\.shock-pill \{[^}]*height: 24px;/);
    expect(src).toMatch(/\.shock-pill \{[^}]*white-space: nowrap;/);
    expect(src).toMatch(/\.shock-pill \{[^}]*font-size: var\(--text-chip\);/);
  });
});
