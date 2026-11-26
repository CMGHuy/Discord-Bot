import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { WritableSignal, provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { RegimeBanner, RegimeStore } from '../stores/regime.store';
import { RegimeBannerComponent } from './regime-banner';

const NUMBERS = 'SPY −5.7% vs SMA200 · −9.3% vs SMA50 · VIX 37.6';
const READING: RegimeBanner = {
  kind: 'reading', tone: 'correction', label: 'Correction · Stress', since: 6, numbers: NUMBERS,
  words: 'Dip in an uptrend, high volatility.', pullback: false,
  accessibleName: `Regime Correction, stress, 6 sessions; ${NUMBERS}`,
};
const empty = (el: HTMLElement) => el.innerHTML.replace(/<!--[\s\S]*?-->/g, '').trim();

describe('sb-regime-banner', () => {
  let banner: WritableSignal<RegimeBanner | null>;

  beforeEach(() => {
    banner = signal<RegimeBanner | null>(null);
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(),
                  { provide: RegimeStore, useValue: { banner, status: signal('ready'), refresh: () => undefined } }],
    });
  });

  function render(value: RegimeBanner | null): HTMLElement {
    banner.set(value);
    const fixture = TestBed.createComponent(RegimeBannerComponent);
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('renders nothing without a banner (NORMAL, off, loading, error)', () => {
    expect(empty(render(null))).toBe('');
  });

  it('shows the muted no-reading line on UNKNOWN, with no control', () => {
    const el = render({ ...READING, kind: 'none', tone: 'muted', label: 'No reading', since: null,
                        numbers: null, words: null, accessibleName: 'Regime: no reading' });
    expect(el.querySelector('[role="status"]')?.textContent?.trim()).toBe('Regime: no reading');
    expect(el.querySelector('button')).toBeNull();
  });

  it('shows the Trend: prefix, the label, the count and the numbers on a collapsed native button', () => {
    const button = render(READING).querySelector('button')!;
    expect(button.getAttribute('type')).toBe('button');
    expect(button.hasAttribute('sb-button')).toBe(true);
    expect([...button.classList]).toEqual(expect.arrayContaining(['regime-toggle', 'ghost']));
    expect(button.getAttribute('aria-expanded')).toBe('false');
    expect(button.getAttribute('aria-label')).toBe(READING.accessibleName);
    expect(button.querySelector('.lead')?.textContent?.trim()).toBe('Trend: Correction · Stress');
    expect(button.querySelector('.since')?.textContent?.trim()).toBe('since 6 sessions');
    expect(button.querySelector('.numbers')?.textContent?.trim()).toBe(NUMBERS);
    expect(button.querySelector('sb-chip')).toBeNull();
  });

  it('toggles aria-expanded and the plain-words panel (a native button: Enter and Space click it)', () => {
    const el = render(READING);
    const button = el.querySelector('button')!;
    const panel = el.querySelector(`#${button.getAttribute('aria-controls')}`) as HTMLElement;
    expect(panel.hidden).toBe(true);
    button.click();
    TestBed.tick();
    expect(button.getAttribute('aria-expanded')).toBe('true');
    expect(panel.hidden).toBe(false);
    expect(panel.textContent).toContain('Dip in an uptrend, high volatility.');
    expect(panel.textContent).toContain(NUMBERS);
    button.click();
    TestBed.tick();
    expect(button.getAttribute('aria-expanded')).toBe('false');
  });

  it('adds the Pullback watch chip on a pullback day and singularises one session', () => {
    const button = render({ ...READING, label: 'Correction', since: 1, pullback: true }).querySelector('button')!;
    expect(button.querySelector('sb-chip')?.textContent?.trim()).toBe('Pullback watch');
    expect(button.querySelector('.since')?.textContent?.trim()).toBe('since 1 session');
  });

  it('omits the count and the numbers when they are null', () => {
    const button = render({ ...READING, since: null, numbers: null }).querySelector('button')!;
    expect(button.querySelector('.since')).toBeNull();
    expect(button.querySelector('.numbers')).toBeNull();
  });

  it('keeps a 44px target at every width, hides the inline numbers on a phone, and uses no glyph', () => {
    const src = readFileSync(join(process.cwd(), 'src/app/shell/regime-banner.ts'), 'utf8');
    expect(src).toMatch(/\.regime-toggle \{[^}]*min-height: 44px;/);
    expect(src).toMatch(/@media \(max-width: 639px\) \{[^}]*\.numbers \{ display: none; \}/);
    expect(src).not.toMatch(/[⚠✕✖↓↑]/);
  });
});
