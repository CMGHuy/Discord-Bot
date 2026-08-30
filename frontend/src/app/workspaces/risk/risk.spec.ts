import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { provideRouter } from '@angular/router';
import { describe, expect, it } from 'vitest';

import {
  authInterceptor,
  errorInterceptor,
  loadingInterceptor,
} from '../../api/interceptors';
import { Risk as RiskData } from '../../api/models';
import { Risk } from './risk';
import { RiskStore } from '../../stores/risk.store';

function payload(overrides: Partial<RiskData> = {}): RiskData {
  return {
    heat: { open_pct: 3, cap_pct: 20 },
    positions: [],
    sector_heat: [],
    clusters: [],
    throttle: { multiplier: 1, paused: false },
    killswitch: { on: false },
    scan_health: { latest_s: 1.2, slowdown: false },
    ...overrides,
  } as RiskData;
}

function seed(): { fixture: ComponentFixture<Risk>; backend: HttpTestingController } {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideRouter([]),
      provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
      provideHttpClientTesting(),
      RiskStore,
    ],
  });
  const fixture = TestBed.createComponent(Risk);
  TestBed.inject(RiskStore).load();
  const backend = TestBed.inject(HttpTestingController);
  return { fixture, backend };
}

describe('Risk states', () => {
  it('shows a skeleton while loading, before the first response', () => {
    const { fixture } = seed();
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('.skeleton')).toBeTruthy();
  });

  it('shows the error state on a first-load failure', async () => {
    const { fixture, backend } = seed();
    fixture.detectChanges();
    backend
      .expectOne('/api/v1/risk')
      .flush({ error: { code: 'unavailable', message: 'nope' } }, { status: 503, statusText: 'x' });
    await fixture.whenStable();
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('.failed')).toBeTruthy();
  });

  it('shows the measured-zero empty state, not a spinner, when there are no open positions', async () => {
    const { fixture, backend } = seed();
    fixture.detectChanges();
    backend.expectOne('/api/v1/risk').flush(payload({ positions: [] }));
    await fixture.whenStable();
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.textContent).toContain('No open risk');
    expect(el.querySelector('.skeleton')).toBeNull();
  });

  it('keeps the killswitch usable at zero open risk', async () => {
    const { fixture, backend } = seed();
    fixture.detectChanges();
    backend.expectOne('/api/v1/risk').flush(payload({ positions: [] }));
    await fixture.whenStable();
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    const button = [...el.querySelectorAll('button')].find((b) =>
      b.textContent?.includes('Engage killswitch'),
    );
    expect(button).toBeTruthy();
    expect(button?.disabled).toBe(false);
  });
});
