import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { SystemHealth } from '../../api/models';
import {
  ProviderHealthPanel,
  breaches,
  providerLines,
  rateText,
} from './provider-health-panel';

const ROW = {
  at: '2026-10-09T14:05:00+00:00',
  tickers: 150,
  provider_fallback_rate: 0.04,
  stale_symbols: 1,
  empty_symbols: 2,
  empty_rate: 2 / 150,
};

const HEALTH: SystemHealth = {
  providers: [
    { ...ROW, at: '2026-10-09T14:10:00+00:00', provider_fallback_rate: 0.25,
      empty_symbols: 12, empty_rate: 0.08, old_print_rate: 0.42 },
    { ...ROW, old_print_rate: null },
    { at: '2026-10-09T14:00:00+00:00', tickers: 150, provider_fallback_rate: null,
      stale_symbols: null, empty_symbols: null, empty_rate: null },
  ],
  thresholds: { fallback_pct: 20, empty_pct: 5 },
  notifications: null,
  swallowed: [],
  bot_counts_since: null,
};

function render(health: SystemHealth | null, stale = false): HTMLElement {
  const fixture = TestBed.createComponent(ProviderHealthPanel);
  fixture.componentRef.setInput('health', health);
  fixture.componentRef.setInput('stale', stale);
  fixture.detectChanges();
  return fixture.nativeElement as HTMLElement;
}

describe('provider health formatting', () => {
  it('renders the old-print rate, and a dash when it is null or missing (v223)', () => {
    const lines = providerLines(HEALTH);

    expect(lines[0].oldPrint).toBe('42.0%');
    expect(lines[1].oldPrint).toBe('—');
    expect(lines[2].oldPrint).toBe('—');
  });

  it('renders a fraction as an unsigned one-decimal percentage', () => {
    expect(rateText(0.04)).toBe('4.0%');
    expect(rateText(0)).toBe('0.0%');
  });

  it('renders an unknown rate as an em dash, never as 0%', () => {
    expect(rateText(null)).toBe('—');
    expect(rateText(undefined)).toBe('—');
  });

  it('breaches strictly above the threshold, as the bot alerts', () => {
    expect(breaches(0.21, 20)).toBe(true);
    expect(breaches(0.2, 20)).toBe(false);
    expect(breaches(null, 20)).toBe(false);
  });

  it('keeps the server order and carries pre-v148 rows as dashes', () => {
    const lines = providerLines(HEALTH);

    expect(lines).toHaveLength(3);
    expect(lines[0]).toMatchObject({ fallback: '25.0%', fallbackBreach: true, emptyBreach: true });
    expect(lines[1]).toMatchObject({ fallbackBreach: false, empty: '2 (1.3%)', stale: '1' });
    expect(lines[2]).toMatchObject({
      fallback: '—', empty: '—', stale: '—', fallbackBreach: false, emptyBreach: false,
    });
  });

  it('has no lines before the first answer', () => {
    expect(providerLines(null)).toEqual([]);
  });
});

describe('ProviderHealthPanel', () => {
  it('shows an Old prints column with its own hint and no breach mark (v223)', () => {
    const el = render(HEALTH);
    const headers = [...el.querySelectorAll('thead th')].map((th) => th.textContent ?? '');
    const oldHeader = el.querySelectorAll('thead th')[4];

    expect(headers).toHaveLength(6);
    expect(headers[4]).toContain('Old prints');
    expect(oldHeader.querySelector('[role="tooltip"]')!.textContent!.trim())
      .toBe('Old IEX prints re-asked from yfinance, share of live-price asks');
    const firstRow = el.querySelectorAll('tbody tr')[0].querySelectorAll('td');
    expect(firstRow).toHaveLength(6);
    expect(firstRow[4].textContent!.trim()).toBe('42.0%');
    expect(firstRow[4].classList.contains('breach')).toBe(false);
    expect(el.querySelectorAll('tbody tr')[2].querySelectorAll('td')[4].textContent!.trim()).toBe('—');
  });

  it('says the old-print rate is shown, not alerted on', () => {
    expect(render(HEALTH).querySelector('.explain')!.textContent)
      .toContain('share of live-price asks; it is shown here, not alerted on');
  });

  beforeEach(() => TestBed.configureTestingModule({
    providers: [provideZonelessChangeDetection()],
  }));

  it('renders one row per scan', () => {
    expect(render(HEALTH).querySelectorAll('tbody tr')).toHaveLength(3);
  });

  it('marks a breach with text as well as colour', () => {
    const cells = render(HEALTH).querySelectorAll('td.breach');

    expect(cells).toHaveLength(2);
    cells.forEach((cell) => expect(cell.textContent).toContain('over limit'));
  });

  it('names the alert thresholds it marks against', () => {
    const text = render(HEALTH).textContent ?? '';

    expect(text).toContain('above 20%');
    expect(text).toContain('above 5%');
  });

  it('says so when no scan is recorded', () => {
    const el = render({ ...HEALTH, providers: [] });

    expect(el.querySelector('table')).toBeNull();
    expect(el.textContent).toContain('No scan recorded yet');
  });
});

describe('ProviderHealthPanel unavailable state', () => {
  beforeEach(() => TestBed.configureTestingModule({
    providers: [provideZonelessChangeDetection()],
  }));

  it.each([[null, false], [HEALTH, true]] as const)(
    'says unavailable, not empty, when health is missing or stale', (health, stale) => {
      const el = render(health, stale);
      expect(el.textContent).toContain('Provider health unavailable');
      expect(el.textContent).not.toContain('No scan recorded yet');
    },
  );
});
