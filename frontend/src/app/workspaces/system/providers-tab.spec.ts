import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { describe, expect, it } from 'vitest';

import {
  authInterceptor,
  errorInterceptor,
  loadingInterceptor,
} from '../../api/interceptors';
import { DataSourcesHealth, SystemHealth } from '../../api/models';
import { SystemStore } from '../../stores/system.store';
import { ProvidersTab, dataSourceName, fallbackText, scanSecondsText } from './providers-tab';

const HEALTH: SystemHealth = {
  providers: [],
  thresholds: { fallback_pct: 20, empty_pct: 5 },
  swallowed: [],
  bot_counts_since: null,
};

const ALPACA: DataSourcesHealth = {
  enabled: true, feed: 'iex', breaker_open: false, fallback_rate: 0.05, scans: 20,
};

interface Reading {
  scanHealth?: Record<string, unknown>;
  riskFails?: boolean;
}

async function render(reading: Reading = {}): Promise<HTMLElement> {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
      provideHttpClientTesting(),
      SystemStore,
    ],
  });
  const fixture = TestBed.createComponent(ProvidersTab);
  const backend = TestBed.inject(HttpTestingController);
  TestBed.inject(SystemStore).loadProviders();
  backend.expectOne('/api/v1/system/health').flush(HEALTH);
  const risk = backend.expectOne('/api/v1/risk');
  if (reading.riskFails) {
    risk.flush(
      { error: { code: 'unavailable', message: 'down' } },
      { status: 503, statusText: 'Service Unavailable' },
    );
  } else {
    risk.flush({
      scan_health: reading.scanHealth ?? {
        durations_s: [12, 14, 31], latest_s: 31, slowdown: false, data_sources: ALPACA,
      },
    });
  }
  fixture.detectChanges();
  await fixture.whenStable();
  fixture.detectChanges();
  return fixture.nativeElement as HTMLElement;
}

const headings = (el: HTMLElement) =>
  [...el.querySelectorAll('sb-panel h2')].map((h) => h.textContent!.trim());

describe('Providers tab helpers (moved from risk.ts, v195 §5.1)', () => {
  it('names the Alpaca feed, or yfinance alone when Alpaca is off', () => {
    expect(dataSourceName(ALPACA)).toBe('Alpaca · IEX');
    expect(dataSourceName({ ...ALPACA, enabled: false })).toBe('yfinance only');
  });

  it('gives the fallback rate over its sample, or says there was no traffic', () => {
    expect(fallbackText(ALPACA)).toBe('5.0% fallback (20 scans)');
    expect(fallbackText({ ...ALPACA, fallback_rate: null, scans: 3 }))
      .toBe('no Alpaca traffic yet (3 scans)');
  });

  it('prints the last duration in seconds, and an unknown one as a bare dash', () => {
    expect(scanSecondsText(31)).toBe('31.0s');
    expect(scanSecondsText(null)).toBe('—');
  });
});

describe('Providers tab (v195 §5.1)', () => {
  it('holds Data providers, Data source, Scan health and Swallowed errors, in that order', async () => {
    expect(headings(await render())).toEqual([
      'Data providers', 'Data source', 'Scan health', 'Swallowed errors',
    ]);
  });

  it('shows the last scan duration and the recent durations', async () => {
    const el = await render();
    expect(el.querySelector('.scan-latest')!.textContent!.trim()).toBe('31.0s');
    expect(el.querySelector('sb-sparkline')).toBeTruthy();
    expect(el.textContent).not.toContain('Scans are running slower');
  });

  it('warns in amber when scans run slower than usual', async () => {
    const el = await render({
      scanHealth: { durations_s: [12, 40], latest_s: 40, slowdown: true, data_sources: ALPACA },
    });
    const note = [...el.querySelectorAll('p.note')]
      .find((p) => p.textContent!.includes('Scans are running slower'))!;
    expect(note.classList).toContain('warn');
  });

  it('draws no sparkline before any scan was timed', async () => {
    const el = await render({ scanHealth: { durations_s: [], latest_s: null, slowdown: false } });
    expect(el.querySelector('sb-sparkline')).toBeNull();
    expect(el.querySelector('.scan-latest')!.textContent!.trim()).toBe('—');
  });

  /* v106 cases, moved from risk.spec.ts with the panel. */

  it('names the Alpaca feed and the fallback rate over its sample', async () => {
    const el = await render();
    expect(el.textContent).toContain('Alpaca · IEX');
    expect(el.textContent).toContain('5.0% fallback (20 scans)');
    expect(el.querySelector('.sources.warn')).toBeNull();
  });

  it('flags an open breaker as a warning', async () => {
    const el = await render({
      scanHealth: {
        durations_s: [], latest_s: 1.2, slowdown: false,
        data_sources: { ...ALPACA, breaker_open: true, fallback_rate: 0.4 },
      },
    });
    expect(el.querySelector('.sources.warn')).toBeTruthy();
    expect(el.textContent).toContain('Alpaca breaker open');
  });

  it('says yfinance only when Alpaca is off', async () => {
    const el = await render({
      scanHealth: {
        durations_s: [], latest_s: 1.2, slowdown: false,
        data_sources: { ...ALPACA, enabled: false, fallback_rate: null, scans: 0 },
      },
    });
    expect(el.textContent).toContain('yfinance only');
    expect(el.textContent).not.toContain('fallback (');
  });

  it('says there is no reading yet rather than naming no source', async () => {
    const el = await render({ scanHealth: { durations_s: [], latest_s: null, slowdown: false } });
    expect(el.textContent).toContain('No data-source reading yet.');
  });

  it('keeps the provider panels and says which read failed when /risk is down', async () => {
    const el = await render({ riskFails: true });
    expect(headings(el)).toContain('Data providers');
    const alert = el.querySelector('p.error[role="alert"]')!;
    expect(alert.textContent).toContain('Scan health and data source');
    expect(alert.textContent).toContain('The admin is not responding.');
  });
});
